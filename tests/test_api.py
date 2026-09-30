import os,secrets,json,time
import pytest
from fastapi.testclient import TestClient
from backend.api import app
from backend import store
@pytest.fixture(autouse=True)
def isolated_store(tmp_path,monkeypatch):
 monkeypatch.setattr(store,'DB',tmp_path/'jobs.sqlite3');store.init()
def client():
 c=TestClient(app);c.headers['x-service-token']=os.environ['SERVICE_TOKEN'];c.get('/api/session');return c
def test_service_auth():assert TestClient(app).get('/api/health').status_code==401
def test_isolation_cancel_idempotency_export():
 a,b=client(),client();key=secrets.token_hex(12)
 payload={'case_id':'already-fast','request_key':key}
 first=a.post('/api/jobs',json=payload);assert first.status_code==202
 id=first.json()['id'];assert a.post('/api/jobs',json=payload).json()['id']==id
 assert b.get('/api/jobs/'+id).status_code==404
 assert b.post('/api/jobs/'+id+'/cancel',json={}).status_code==404
 assert b.get('/api/jobs/'+id+'/report').status_code==404
 assert a.get('/api/jobs/'+id+'/report').status_code==409
 assert a.post('/api/jobs/'+id+'/cancel',json={}).json()['state']=='cancelled'
 store.finish(id,'completed',{'test':'export'})
 assert a.get('/api/jobs/'+id+'/report').json()=={'test':'export'}
def test_anonymous_custom_sql_forbidden():
 assert client().post('/api/jobs',json={'query':'SELECT id FROM orders','request_key':secrets.token_hex(12)}).status_code==401
def test_unsafe_input_rejected_before_budget():
 assert client().post('/api/jobs',json={'case_id':'unsafe','request_key':secrets.token_hex(12)}).status_code==422
def test_live_auth_invalid_connection_redaction():
 c=client();assert c.post('/api/connections',json={'label':'bad','url':'postgresql://a:private-value@localhost:1/no'}).status_code==401
 assert c.post('/api/login',json={'password':os.environ['ADMIN_PASSWORD']}).status_code==200
 r=c.post('/api/connections',json={'label':'bad','url':'postgresql://a:private-value@localhost:1/no'})
 assert r.status_code==422 and 'private-value' not in r.text
def test_csrf():
 c=client();c.headers['origin']='https://evil.example';c.headers['x-app-origin']='https://queryotter.example'
 assert c.post('/api/logout',json={}).status_code==403
