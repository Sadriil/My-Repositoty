import argparse,getpass,hashlib,secrets
from app import db
p=argparse.ArgumentParser(description='Управление доступом Stone Production');p.add_argument('login');p.add_argument('--role',choices=['admin','employee'],default='employee');a=p.parse_args()
pw=getpass.getpass('Пароль (от 12 символов): ')
if len(pw)<12:raise SystemExit('Пароль слишком короткий')
if pw!=getpass.getpass('Повторите пароль: '):raise SystemExit('Пароли не совпадают')
salt=secrets.token_bytes(16);hashed=hashlib.scrypt(pw.encode(),salt=salt,n=16384,r=8,p=1).hex()
with db() as c:
 c.execute('INSERT OR REPLACE INTO users VALUES (?,?,?,?)',(a.login,salt.hex(),hashed,a.role));c.execute('DELETE FROM sessions WHERE login=?',(a.login,))
print('Доступ сохранён:',a.login,a.role)
