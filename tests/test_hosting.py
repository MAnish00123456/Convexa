"""Exercise Vercel handler + official libSQL engine locally (no cloud credentials).

The connection target alone is redirected to a disposable libSQL file; SQL,
transactions, FTS, blobs and request lifecycle use the deployed code path.
"""
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import test_http
from core import hosting, store, cloud_db, assistant, knowledge
from api import index
from cryptography.fernet import Fernet


class HostedTests(test_http.HTTPTests):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='convexa-hosted-tests-')
        cls.env = patch.dict(os.environ, {
            'CONVEXA_DATABASE_URL': 'libsql://test.invalid',
            'CONVEXA_DATABASE_AUTH_TOKEN': 'test-token-not-real',
            'CONVEXA_SECRET_KEY': Fernet.generate_key().decode(),
        })
        cls.env.start()
        cls.datapatch = patch.object(store, 'DATA_DIR', Path(cls.temp.name) / 'scratch')
        cls.datapatch.start()
        real = cloud_db.Connection
        cls.connection_patch = patch.object(cloud_db, 'Connection', lambda *args: real(str(Path(cls.temp.name) / 'persistent.db')))
        cls.connection_patch.start()
        # VERCEL=1 requires Secure cookies. Use remote storage mode over local HTTP;
        # separately test the secure-cookie path below.
        index._ready = False
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), index.handler)
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        import app
        cls.limit_patch = patch.object(app, 'MAX_UPLOAD', 4_000_000)
        cls.limit_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.limit_patch.stop()
        cls.connection_patch.stop()
        cls.datapatch.stop()
        cls.env.stop()
        cls.temp.cleanup()
        index._ready = False

    def test_blob_survives_scratch_cleanup_and_cold_start(self):
        item = self.add(title='persistent upload', kind='file')
        path = '/api/items/' + item['id'] + '/file'
        payload = b'Normalization prevents update anomalies.'
        code, result = self.client.call(path+'?filename=notes.txt', 'PUT', raw=payload)
        self.assertEqual(code, 201, result)
        self.assertTrue(result['item']['has_file'])
        import shutil
        shutil.rmtree(store.DATA_DIR)
        index._ready = False
        self.assertEqual(self.client.call(path), (200, payload))
        self.assertTrue(self.query('anomalies'))
        other = test_http.BrowserClient(self.base)
        other.register()
        self.assertEqual(other.call(path)[0], 404)
        self.assertEqual(self.client.call('/api/items/'+item['id'], 'DELETE')[0], 200)
        with store.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM file_parts WHERE item_id=?', (item['id'],)).fetchone()[0], 0)

    def test_file_replacement_and_ranges(self):
        item = self.add(title='range test', kind='file')
        path = '/api/items/'+item['id']+'/file'
        for data in (b'old', b'new contents'):
            self.assertEqual(self.client.call(path+'?filename=data.txt', 'PUT', raw=data)[0], 201)
        import urllib.request
        req = urllib.request.Request(self.base+path, headers={'Range':'bytes=1-3'})
        with self.client.opener.open(req) as r:
            self.assertEqual(r.status, 206)
            self.assertEqual(r.read(), b'ew ')
        self.assertEqual(self.client.call(path)[1], b'new contents')

    def test_import_finishes_before_response_and_failure_is_retryable(self):
        with patch.object(knowledge, 'fetch_youtube_captions', return_value=('[0:00] Foreign keys reference primary keys.', '')):
            item = self.add(title='Video',kind='youtube',url='https://www.youtube.com/watch?v=HXV3zeQKqGY')
        stored = self.client.call('/api/items/'+item['id'])[1]['item']
        self.assertEqual(stored['status'], 'searchable')
        self.assertIn('Foreign keys', stored['transcript'])
        with patch.object(knowledge, 'fetch_youtube_captions', side_effect=TimeoutError()):
            item = self.add(title='Video unavailable',kind='youtube',url='https://www.youtube.com/watch?v=HXV3zeQKqGY')
        stored = self.client.call('/api/items/'+item['id'])[1]['item']
        self.assertEqual(stored['status'], 'metadata_only')
        self.assertTrue(stored['meta']['processing_error'])

    def test_voice_retry_uses_persistent_audio_and_user_settings(self):
        self.client.call('/api/ai/settings','POST',{'keys':{'groq':'fake-key'},'providers':{'voice':'groq'}})
        item = self.add(title='Audio',kind='voice')
        with patch.object(assistant,'transcribe_audio', return_value=('', 'Fixture unavailable')):
            code, res = self.client.call('/api/items/'+item['id']+'/file?filename=voice.wav','PUT',raw=b'RIFFfixture')
        self.assertEqual(code,201,res)
        def transcribe(path):
            self.assertEqual(path.read_bytes(),b'RIFFfixture')
            self.assertEqual(assistant.get_setting('GROQ_API_KEY'),'fake-key')
            return 'Recorded facts about relational databases.', ''
        with patch.object(assistant,'transcribe_audio',side_effect=transcribe):
            code,res = self.client.call('/api/items/'+item['id']+'/refresh','POST',{})
        self.assertEqual(code,200,res)
        self.assertIn('Recorded facts',self.client.call('/api/items/'+item['id'])[1]['item']['transcript'])

    def test_cloud_size_limits_and_full_detail(self):
        item = self.add(title='Large source', body='x' * 180000)
        listing = self.client.call('/api/items?q=Large')[1]['results']
        listed = next(h['item'] for h in listing if h['item']['id'] == item['id'])
        self.assertLessEqual(len(listed['body']), 1000)
        full = self.client.call('/api/items/'+item['id'])[1]['item']
        self.assertEqual(len(full['body']),180000)
        path='/api/items/'+item['id']+'/file?filename=boundary.txt'
        self.assertEqual(self.client.call(path,'PUT',raw=b'a'*4_000_000)[0],201)
        import urllib.request, urllib.error
        request=urllib.request.Request(self.base+path,data=b'',method='PUT',headers={
            'Content-Length':'4000001','X-CSRF-Token':self.client.csrf,
            'Content-Type':'application/octet-stream'})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.client.opener.open(request)
        self.assertEqual(caught.exception.code,400)

    def test_upload_database_failure_keeps_previous_file(self):
        item=self.add(title='Atomic file')
        path='/api/items/'+item['id']+'/file'
        self.assertEqual(self.client.call(path+'?filename=before.txt','PUT',raw=b'previous')[0],201)
        with patch.object(store,'save_file',side_effect=RuntimeError('simulated write failure')):
            self.assertEqual(self.client.call(path+'?filename=after.txt','PUT',raw=b'replacement')[0],500)
        self.assertEqual(self.client.call(path)[1],b'previous')

    def test_key_encryption_survives_cold_start(self):
        key='fake-private-key-for-test'
        code,res=self.client.call('/api/ai/settings','POST',{'keys':{'gemini':key}})
        self.assertEqual(code,200,res)
        index._ready=False
        code,res=self.client.call('/api/ai/settings')
        self.assertTrue(res['settings']['keys']['gemini'])
        self.assertNotIn(key,str(res))
        self.assertNotIn(key.encode(),(Path(self.temp.name)/'persistent.db').read_bytes())

    def test_semantic_index_resumes_in_batches(self):
        for i in range(12): self.add(title=f'Batch {i}',body='Foreign keys maintain referential integrity.')
        self.client.call('/api/ai/settings','POST',{'keys':{'gemini':'fake'},'providers':{'embeddings':'gemini'}})
        with patch.object(assistant,'embed',side_effect=lambda texts: [[0.5,0.5] for _ in texts]):
            total=0
            for _ in range(20):
                code,res=self.client.call('/api/semantic/reindex','POST',{})
                self.assertEqual(code,200,res)
                self.assertLessEqual(res['indexed_chunks'],10)
                total+=res['indexed_chunks']
                if not res['remaining']: break
            else: self.fail('Index did not finish')
            self.assertGreater(total,10)
            self.assertEqual(self.client.call('/api/semantic/reindex','POST',{})[1]['indexed_chunks'],0)

    def test_invitation_and_login_throttle(self):
        other=test_http.BrowserClient(self.base)
        body={'email':'limited@example.org','password':'password123'}
        with patch.dict(os.environ,{'CONVEXA_INVITE_CODE':'private-demo'}):
            self.assertEqual(other.call('/api/register','POST',body)[0],403)
            self.assertEqual(other.call('/api/register','POST',dict(body,invite_code='private-demo'))[0],200)
        for _ in range(20): other.call('/api/login','POST',dict(body,password='wrongpassword'))
        self.assertEqual(other.call('/api/login','POST',body)[0],429)


class ConfigurationTests(unittest.TestCase):
    def test_vercel_refuses_local_storage(self):
        with patch.dict(os.environ,{'VERCEL':'1','CONVEXA_DATABASE_URL':''}):
            with self.assertRaisesRegex(RuntimeError,'persistent'): hosting.validate()

    def test_remote_requires_stable_key(self):
        with patch.dict(os.environ,{'CONVEXA_DATABASE_URL':'libsql://test.invalid','CONVEXA_DATABASE_AUTH_TOKEN':'fake','CONVEXA_SECRET_KEY':''}):
            with self.assertRaisesRegex(RuntimeError,'SECRET_KEY'): hosting.validate()

    def test_secure_cookie_on_vercel(self):
        obj=object.__new__(index.handler); obj.headers={}
        with patch.dict(os.environ,{'VERCEL':'1'}):
            self.assertIn('; Secure',obj._cookie('token',100))
