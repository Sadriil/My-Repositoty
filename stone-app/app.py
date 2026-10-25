import json, sqlite3, secrets, hashlib, hmac, time, math, os
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT=Path(__file__).parent
DATA=Path(os.environ.get('STONE_DATA_DIR',ROOT/'runtime')); DATA.mkdir(exist_ok=True)
CAT=json.loads((ROOT/'data/catalog.json').read_text())
app=FastAPI(title='Stone Production')
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
def db():
 c=sqlite3.connect(DATA/'stone.sqlite');c.row_factory=sqlite3.Row;return c
with db() as c:
 c.executescript('CREATE TABLE IF NOT EXISTS users (login TEXT PRIMARY KEY, salt TEXT, hash TEXT, role TEXT); CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, login TEXT, expires REAL); CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, body TEXT); CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, created REAL, body TEXT, result TEXT, status TEXT);')
 c.execute('INSERT OR IGNORE INTO settings VALUES (1,?)',(json.dumps(dict(exchange=85,markup=1,sink_promo=True,overrides={})),))
def settings():
 with db() as c:return json.loads(c.execute('SELECT body FROM settings WHERE id=1').fetchone()[0])
def user(req):
 with db() as c:
  row=c.execute('SELECT u.login,u.role FROM sessions s JOIN users u ON u.login=s.login WHERE s.token=? AND s.expires>?',(req.cookies.get('stone_session',''),time.time())).fetchone()
 return dict(row) if row else None
def staff(req,admin=False):
 u=user(req)
 if not u or (admin and u['role']!='admin'):raise HTTPException(403,'Нет доступа')
 return u
def check_origin(req):
 origin=req.headers.get('origin')
 if origin and origin!=str(req.base_url).rstrip('/'):raise HTTPException(403,'Недопустимый источник запроса')
@app.middleware('http')
async def security(req,call_next):
 if req.method in ('POST','PUT','DELETE'):
  try:check_origin(req)
  except HTTPException as e:return JSONResponse({'detail':e.detail},status_code=e.status_code)
 r=await call_next(req)
 r.headers['X-Content-Type-Options']='nosniff';r.headers['Cache-Control']='no-store';r.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'self'"
 return r
class Part(BaseModel):
 model_config={"allow_inf_nan":False}
 length:float=Field(gt=0,le=15000)
 width:float=Field(gt=0,le=4000)
class Quote(BaseModel):
 model_config={"allow_inf_nan":False}
 material:str
 parts:list[Part]=Field(min_length=1,max_length=10)
 walls:list[Part]=Field(default_factory=list,max_length=5)
 edge:str='2'; edge_height:int=40;edge_length:float=Field(default=0,ge=0,le=1000)
 border:str='2';border_height:int=40;border_length:float=Field(default=0,ge=0,le=1000)
 sink:str='2';sink_count:int=Field(default=0,ge=0,le=100)
 radius:int=Field(default=0,ge=0,le=100)
 inset:int=Field(default=0,ge=0,le=100)
 plywood:float=Field(default=0,ge=0,le=1000)
 grooves:int=Field(default=0,ge=0,le=100)
 km:float=Field(default=0,ge=0,le=10000)
 reinforcement:float=Field(default=0,ge=0,le=1000)
 drain:int=Field(default=0,ge=0,le=100)
 installation:bool=True
class Order(BaseModel):
 quote:Quote
 name:str=Field(min_length=2,max_length=120)
 phone:str=Field(min_length=6,max_length=50)
 address:str=Field(default='',max_length=500)
 comment:str=Field(default='',max_length=2000)
def item(kind,id):
 for i in CAT[kind]:
  if i['id']==id:return i
 raise HTTPException(422,'Позиция отсутствует в справочнике')
def height(kind,h):
 for i in CAT[kind]:
  if i['height']==h:return i['usd']
 raise HTTPException(422,'Недопустимая высота')
def calculate(q,internal=False,discount=0):
 cfg=settings();m=item('materials',q.material);rate=max(85,cfg['exchange'])*1.15;markup=cfg['markup']
 usd=cfg['overrides'].get(m['id'],m['usd']);price=usd*rate*markup
 area=sum(p.length*(p.width+40 if p.width<560 else p.width)/1e6 for p in q.parts)
 billed=max(1,area);wall=sum(p.length*p.width/1e6 for p in q.walls)
 edge=item('edges',q.edge);border=item('borders',q.border);item('sinks',q.sink)
 sinkprice=(m['sink_usd'] if cfg['sink_promo'] and billed>=1.8 and isinstance(m['sink_usd'],(int,float)) else 285)
 lines=[]
 def add(name,qty,unit,unit_price):
  if qty:lines.append(dict(name=name,quantity=round(qty,6),unit=unit,price=round(unit_price,2),amount=round(qty*unit_price,2)))
 add('Столешница',billed,'м²',price);add('Стеновая панель',wall,'м²',price)
 add('Кромка: '+edge['name'],q.edge_length,'пог. м',(edge['usd']+height('edge_heights',q.edge_height))*rate*markup)
 add('Бортик: '+border['name'],q.border_length,'пог. м',(border['usd']+height('border_heights',q.border_height))*rate*markup)
 add('Мойка: '+item('sinks',q.sink)['name'],q.sink_count,'шт.',sinkprice*rate*markup)
 for name,qty,unit,pr in [('Радиусные элементы сверх двух',max(0,q.radius-2),'шт.',30*markup),('Вклейка мойки / утапливание поверхности',q.inset,'шт.',50),('Подложка из фанеры',q.plywood,'пог. м',50*markup),('Проточки',q.grooves,'шт.',7*markup),('Выезд за МКАД сверх 20 км',max(0,q.km-20),'км',1.5*markup),('Усиление силовой конструкцией',q.reinforcement,'пог. м',50),('Слив и перелив',q.drain,'шт.',30),('Замер, доставка и монтаж',int(q.installation),'компл.',150*markup)]:add(name,qty,unit,pr*rate)
 subtotal=round(sum(x['amount'] for x in lines),2);total=round(subtotal*(1-discount/100),2)
 r=dict(material=m['name'],area=round(area,6),billed_area=round(billed,6),wall_area=round(wall,6),lines=lines,subtotal=subtotal,discount=discount,total=total,notice='Предварительная стоимость. Окончательная стоимость подтверждается менеджером после уточнения размеров и деталей заказа.')
 if internal:
  sheets=math.ceil((billed+wall)/.55)/4+q.sink_count*.25;glue=math.ceil(sheets*2)
  raw=sheets*m['sheet_usd']*cfg['exchange']*m['factor']+glue*1700
  edge_labor=edge.get('labor',0)
  labor=(area+wall)*4000+q.edge_length*edge_labor+q.border_length*border.get('labor',0)+q.sink_count*7000+max(0,q.radius-2)*1000+q.inset*1500+q.grooves*100
  transport=(12500+max(0,q.km-20)*100) if q.installation else 0
  cost=round(raw+labor+(area+wall)*2000+transport,2)
  r['internal']=dict(rate=round(rate,4),sheets=sheets,glue=glue,materials=round(raw,2),manufacturing=round(labor,2),cost=cost,profit=round(total-cost,2),note='Расчётная себестоимость по Excel. Расход листов необходимо проверить; ручные затраты на специальные услуги не включены.')
 return r
@app.get('/')
async def home():return FileResponse(ROOT/'static/index.html')
@app.get('/api/catalog')
async def catalog():return {k:([{x:i[x] for x in ['id','name']} for i in v] if k in ['materials','edges','borders','sinks'] else [i['height'] for i in v]) for k,v in CAT.items() if k!='images'} | {'images':CAT['images']}
@app.post('/api/quote')
async def quote(q:Quote):return calculate(q)
@app.post('/api/orders')
async def order(o:Order):
 r=calculate(o.quote);id=secrets.token_hex(5).upper()
 with db() as c:c.execute('INSERT INTO orders VALUES (?,?,?,?,?)',(id,time.time(),o.model_dump_json(),json.dumps(r,ensure_ascii=False),'Новая'))
 return dict(id=id,result=r)
ATTEMPTS={}
@app.post('/api/login')
async def login(req:Request):
 key=req.client.host;now=time.time();ATTEMPTS[key]=[t for t in ATTEMPTS.get(key,[]) if now-t<900]
 if len(ATTEMPTS[key])>=10:raise HTTPException(429,'Слишком много попыток. Повторите через 15 минут.')
 ATTEMPTS[key].append(now);body=await req.json()
 with db() as c:
  u=c.execute('SELECT * FROM users WHERE login=?',(str(body.get('login',''))[:120],)).fetchone()
  salt=u['salt'] if u else '0000000000000000'
  hashed=hashlib.scrypt(str(body.get('password',''))[:1000].encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
  if not u or not hmac.compare_digest(hashed,u['hash']):raise HTTPException(401,'Неверный логин или пароль')
  token=secrets.token_urlsafe(32);c.execute('INSERT INTO sessions VALUES (?,?,?)',(token,u['login'],now+28800))
 r=JSONResponse(dict(login=u['login'],role=u['role']));r.set_cookie('stone_session',token,httponly=True,samesite='strict',secure=req.url.scheme=='https',max_age=28800);return r
@app.get('/api/me')
async def me(req:Request):return user(req)
@app.post('/api/logout')
async def logout(req:Request):
 with db() as c:c.execute('DELETE FROM sessions WHERE token=?',(req.cookies.get('stone_session',''),))
 r=JSONResponse({'ok':True});r.delete_cookie('stone_session');return r
@app.get('/api/staff/orders')
async def orders(req:Request):
 staff(req)
 with db() as c:rows=c.execute('SELECT * FROM orders ORDER BY created DESC LIMIT 300').fetchall()
 return [dict(id=r['id'],created=r['created'],body=json.loads(r['body']),result=json.loads(r['result']),status=r['status']) for r in rows]
@app.put('/api/staff/orders/{id}')
async def status(id:str,req:Request):
 staff(req);body=await req.json();s=body.get('status')
 if s not in ['Новая','В работе','Согласована','Завершена']:raise HTTPException(422,'Неверный статус')
 with db() as c:
  if not c.execute('UPDATE orders SET status=? WHERE id=?',(s,id)).rowcount:raise HTTPException(404,'Заявка не найдена')
 return {'ok':True}
@app.post('/api/staff/quote')
async def staffquote(q:Quote,req:Request,discount:float=0):
 staff(req)
 if not 0<=discount<=100:raise HTTPException(422,'Скидка от 0 до 100%')
 return calculate(q,True,discount)
@app.get('/api/admin/settings')
async def getsettings(req:Request):staff(req,True);return settings()
class Settings(BaseModel):
 model_config={"allow_inf_nan":False}
 exchange:float=Field(ge=1,le=10000)
 markup:float=Field(ge=.1,le=10)
 sink_promo:bool
 overrides:dict[str,float]=Field(default_factory=dict)
@app.put('/api/admin/settings')
async def savesettings(s:Settings,req:Request):
 staff(req,True)
 for k,v in s.overrides.items():
  item('materials',k)
  if not math.isfinite(v) or not 0<v<100000:raise HTTPException(422,'Некорректная цена')
 with db() as c:c.execute('UPDATE settings SET body=? WHERE id=1',(s.model_dump_json(),))
 return {'ok':True}
