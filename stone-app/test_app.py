import os,tempfile,unittest,hashlib,secrets
os.environ['STONE_DATA_DIR']=tempfile.mkdtemp(prefix='stone-tests-')
import asyncio,httpx
class TestClient:
 def __init__(self,app):self.app=app;self.cookies=httpx.Cookies()
 def request(self,method,url,**kwargs):
  async def run():
   async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://testserver',cookies=self.cookies) as c:
    r=await c.request(method,url,**kwargs);self.cookies.update(c.cookies);return r
  return asyncio.run(run())
 def get(self,url,**kwargs):return self.request('GET',url,**kwargs)
 def post(self,url,**kwargs):return self.request('POST',url,**kwargs)
from app import app,db,settings,CAT
class Tests(unittest.TestCase):
 def setUp(self):
  self.c=TestClient(app);self.q={'material':CAT['materials'][0]['id'],'parts':[{'length':1000,'width':600}],'installation':False}
 def test_minimum_area(self):
  r=self.c.post('/api/quote',json=self.q).json();self.assertEqual(r['billed_area'],1);self.assertEqual(r['total'],28347.5)
 def test_width_allowance_and_boundary(self):
  self.q['parts']=[{'length':2000,'width':559}];self.assertEqual(self.c.post('/api/quote',json=self.q).json()['area'],1.198)
  self.q['parts'][0]['width']=560;self.assertEqual(self.c.post('/api/quote',json=self.q).json()['area'],1.12)
 def test_reinforcement(self):
  base=self.c.post('/api/quote',json=self.q).json()['total'];self.q['reinforcement']=2
  self.assertAlmostEqual(self.c.post('/api/quote',json=self.q).json()['total']-base,9775)
 def test_free_limits(self):
  base=self.c.post('/api/quote',json=self.q).json()['total'];self.q.update(radius=2,km=20)
  self.assertEqual(self.c.post('/api/quote',json=self.q).json()['total'],base)
 def test_access(self):
  for route in ['/api/staff/orders','/api/admin/settings']:self.assertEqual(self.c.get(route).status_code,403)
  r=self.c.get('/api/catalog').json();self.assertNotIn('usd',r['materials'][0]);self.assertNotIn('internal',self.c.post('/api/quote',json=self.q).json())
 def test_bad_inputs(self):
  self.q['parts'][0]['width']=-1;self.assertEqual(self.c.post('/api/quote',json=self.q).status_code,422)
 def test_order_saved(self):
  r=self.c.post('/api/orders',json={'quote':self.q,'name':'Тест','phone':'+79991234567'});self.assertEqual(r.status_code,200)
  with db() as c:self.assertIsNotNone(c.execute('SELECT id FROM orders WHERE id=?',(r.json()['id'],)).fetchone())
 def test_login_and_roles(self):
  salt=secrets.token_bytes(16);password='test-password-12345';h=hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1).hex()
  with db() as c:c.execute('INSERT OR REPLACE INTO users VALUES (?,?,?,?)',('tester',salt.hex(),h,'employee'))
  self.assertEqual(self.c.post('/api/login',json={'login':'tester','password':password}).status_code,200)
  self.assertEqual(self.c.get('/api/staff/orders').status_code,200);self.assertEqual(self.c.get('/api/admin/settings').status_code,403)
  self.assertIn('internal',self.c.post('/api/staff/quote',json=self.q).json())
  self.c.post('/api/logout',json={});self.assertEqual(self.c.get('/api/staff/orders').status_code,403)
 def test_course_floor(self):
  cfg=settings()
  try:
   with db() as c:c.execute('UPDATE settings SET body=json_set(body,\'$.exchange\',70) WHERE id=1')
   self.assertEqual(self.c.post('/api/quote',json=self.q).json()['total'],28347.5)
  finally:
   import json
   with db() as c:c.execute('UPDATE settings SET body=?',(json.dumps(cfg),))
 def test_origin(self):
  self.assertEqual(self.c.post('/api/orders',json={},headers={'origin':'https://evil.example'}).status_code,403)
if __name__=='__main__':unittest.main()
