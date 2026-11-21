import unittest
from unittest.mock import patch
import urllib.error
from core import assistant

class ReviewRegressions(unittest.TestCase):
    def test_openai_chat_response_contract(self):
        with patch.object(assistant, '_http', return_value={'choices':[{'message':{'content':'Verified [1]'}}]}) as http:
            self.assertEqual(assistant._chat('Use sources','Question','[1] Evidence','openai'),'Verified [1]')
            self.assertTrue(http.call_args.args[0].endswith('/chat/completions'))
            self.assertEqual(http.call_args.args[1]['model'],'gpt-4o-mini')

    def test_quota_error_is_actionable_and_sanitized(self):
        error=urllib.error.HTTPError('https://example.invalid/private',429,'secret provider payload',{},None)
        with patch('urllib.request.urlopen',side_effect=error):
            with self.assertRaisesRegex(RuntimeError,'Quota exhausted or rate limited') as caught:
                assistant._http('https://example.invalid')
            self.assertNotIn('secret',str(caught.exception))

    def test_diagnostics_preserve_safe_failure_reason(self):
        with patch.object(assistant,'chat_provider',return_value='groq'), patch.object(assistant,'embedding_provider',return_value=None), patch.object(assistant,'voice_provider',return_value=None), patch.object(assistant,'_chat',side_effect=RuntimeError('Invalid API key (HTTP 401)')):
            result=assistant.connection_test()
            self.assertFalse(result['chat']['ok'])
            self.assertEqual(result['chat']['status'],'Invalid API key (HTTP 401)')
            self.assertIn('real audio',result['voice']['status'])

    def test_title_match_sends_actual_sample_content_to_model(self):
        import json, subprocess
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        script="const vm=require('vm'),fs=require('fs');const c=vm.createContext({});vm.runInContext(fs.readFileSync('web/samples.js','utf8')+';globalThis.samples=knowledgeSamples;',c);console.log(JSON.stringify(c.samples));"
        samples=json.loads(subprocess.check_output(['node','-e',script],cwd=root))
        for kind, question, evidence in [
            ('chat','Why do we normalize a database? Answer in one sentence.','avoid insertion, update and deletion anomalies'),
            ('note','What is a DBMS?','helps store, retrieve and manage structured data'),
            ('file','Explain atomicity','all operations in a transaction succeed together'),
        ]:
            with self.subTest(kind=kind):
                sample=samples[kind]
                item={'id':'fixture','kind':kind,'title':sample['title'],'body':sample['body'],'transcript':'','extracted_text':sample.get('fileText','')}
                hits=[{'item':item,'match':{'section':'title','excerpt':item['title']}}]
                with patch.object(assistant,'chat_provider',return_value='gemini'),patch.object(assistant,'_chat',return_value='Test response [1]') as chat:
                    result=assistant.answer(question,hits)
                self.assertIn(evidence,chat.call_args.args[2])
                self.assertEqual(result['mode'],'gemini AI (source-grounded)')
                self.assertLessEqual(len(result['sources'][0]['excerpt']),950)

    def test_title_without_content_does_not_become_invented_evidence(self):
        hit={'item':{'id':'x','kind':'note','title':'Normalization'},'match':{'section':'title','excerpt':'Normalization'}}
        with patch.object(assistant,'chat_provider',return_value=None):
            result=assistant.answer('Why normalize?', [hit])
        self.assertIn('no source content',result['sources'][0]['excerpt'])
