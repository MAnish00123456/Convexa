"""Run against an actual deployment using a dedicated test account.
Usage: python scripts/smoke_deployment.py https://your-project.vercel.app [--ai]
Only its own temporary notes, map links and attachments are deleted.
"""
import argparse
import getpass
import http.cookiejar
import json
import os
import urllib.request
import urllib.error
import uuid

parser=argparse.ArgumentParser()
parser.add_argument('url')
parser.add_argument('--ai',action='store_true',help='Also spend a small amount of provider quota on connection tests')
args=parser.parse_args()
base=args.url.rstrip('/')
if not base.startswith('https://'):
    parser.error('Use the HTTPS deployment URL.')
jar=http.cookiejar.CookieJar()
client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
csrf=''

def call(path,method='GET',body=None,raw=None):
    headers={'X-CSRF-Token':csrf}
    data=raw
    if body is not None:
        data=json.dumps(body).encode();headers['Content-Type']='application/json'
    elif raw is not None: headers['Content-Type']='application/octet-stream'
    req=urllib.request.Request(base+path,data=data,headers=headers,method=method)
    with client.open(req,timeout=180) as r:
        blob=r.read()
        return json.loads(blob) if r.headers.get_content_type()=='application/json' else blob

created=[]
try:
    health=call('/api/health')
    assert health['status']=='ok' and health['storage']=='cloud', 'Deployment is not using persistent cloud storage'
    assert b'Convexa' in call('/app') or b'convexa' in call('/app')
    email=os.environ.get('CONVEXA_TEST_EMAIL') or input('Dedicated test-account email: ')
    password=os.environ.get('CONVEXA_TEST_PASSWORD') or getpass.getpass('Password: ')
    login=call('/api/login','POST',{'email':email,'password':password});csrf=login['csrf']
    marker='smoke'+uuid.uuid4().hex
    for title in [marker,marker+' attachment']:
        item=call('/api/items','POST',{'kind':'note','title':title,'body':'Foreign keys maintain referential integrity.'})['item']
        created.append(item['id'])
    uploaded=b'Persistent deployment attachment for Convexa smoke test.'
    path='/api/items/'+created[1]+'/file'
    call(path+'?filename=smoke.txt','PUT',raw=uploaded)
    assert call(path)==uploaded,'Attachment round trip failed'
    assert call('/api/items?q='+marker)['count']>=2,'Search failed'
    call('/api/mindmap/edge','POST',{'source':created[0],'target':created[1]})
    assert any(x['source_id'] in created for x in call('/api/mindmap')['edges'])
    call('/api/ai/settings')
    # Log out/in to verify database-backed session and persisted knowledge.
    call('/api/logout','POST',{})
    login=call('/api/login','POST',{'email':email,'password':password});csrf=login['csrf']
    assert call(path)==uploaded
    if args.ai:
        report=call('/api/ai/test','POST',{})
        print('Provider diagnostic (no keys):',json.dumps(report))
    print('PASS: live routes, login, durable file round trip, search, map links, settings and re-login.')
    print('For cold-start persistence: save a permanent test note, redeploy, then reopen and download it.')
except Exception as error:
    print('FAIL:',type(error).__name__,'- check deployment logs, protection settings and test-account credentials.')
    raise SystemExit(1)
finally:
    for item_id in created:
        try: call('/api/items/'+item_id,'DELETE')
        except Exception: print('Cleanup needed for smoke-test item:',item_id)
    if csrf:
        try: call('/api/logout','POST',{})
        except Exception: pass
