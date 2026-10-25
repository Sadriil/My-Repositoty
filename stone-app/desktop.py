"""Локальный запуск Stone Production; используется также сборкой macOS .app."""
import os
import sys
import socket
import threading
import webbrowser
import hashlib
import secrets
import sqlite3
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog, filedialog


def data_directory():
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'Stone Production'
    return Path.home() / '.stone-production'


def main():
    root = tk.Tk()
    root.title('Stone Production')
    root.geometry('480x280')
    root.resizable(False, False)
    root.configure(bg='#f4f3ed')
    root.withdraw()
    data = data_directory()
    data.mkdir(parents=True, exist_ok=True)
    try:
        data.chmod(0o700)
    except OSError:
        pass
    os.environ['STONE_DATA_DIR'] = str(data)
    import uvicorn
    from app import app, db

    with db() as conn:
        needs_admin = conn.execute("SELECT 1 FROM users WHERE role='admin'").fetchone() is None
    if needs_admin:
        messagebox.showinfo('Первый запуск', 'Создайте пароль администратора.\nЛогин: admin\nПароль хранится только на вашем компьютере.', parent=root)
        while True:
            password = simpledialog.askstring('Первый запуск', 'Пароль администратора (от 12 символов):', show='•', parent=root)
            if password is None:
                root.destroy()
                return
            if len(password) < 12:
                messagebox.showerror('Пароль', 'Нужно не менее 12 символов.', parent=root)
                continue
            confirm = simpledialog.askstring('Подтверждение', 'Повторите пароль:', show='•', parent=root)
            if confirm is None:
                root.destroy()
                return
            if password != confirm:
                messagebox.showerror('Пароль', 'Пароли не совпадают.', parent=root)
                continue
            salt = secrets.token_bytes(16)
            hashed = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1).hex()
            with db() as conn:
                conn.execute('INSERT OR REPLACE INTO users VALUES (?,?,?,?)', ('admin', salt.hex(), hashed, 'admin'))
            password = confirm = None
            break

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    config = uvicorn.Config(app, host='127.0.0.1', port=port, log_config=None, access_log=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{port}'
    tk.Label(root, text='STONE PRODUCTION', font=('Helvetica', 19, 'bold'), bg='#f4f3ed', fg='#304f42').pack(pady=(24, 6))
    status = tk.Label(root, text='Запускаем локальное приложение…', bg='#f4f3ed', fg='#59685c')
    status.pack(pady=5)
    tk.Label(root, text='Данные хранятся на этом компьютере.\nЭто окно должно оставаться открытым во время работы.', bg='#f4f3ed', fg='#59685c', justify='center').pack(pady=8)
    open_button = tk.Button(root, text='Открыть калькулятор', command=lambda: webbrowser.open(url), state='disabled', width=28)
    open_button.pack(pady=4)

    def backup():
        path = filedialog.asksaveasfilename(parent=root, title='Сохранить резервную копию', initialfile='Stone-Production-backup.sqlite', defaultextension='.sqlite')
        if not path:
            return
        if Path(path).resolve() == (data/'stone.sqlite').resolve():
            messagebox.showerror('Резервная копия', 'Выберите другой файл, не текущую базу.', parent=root)
            return
        try:
            with sqlite3.connect(data/'stone.sqlite') as src, sqlite3.connect(path) as dst:
                src.backup(dst)
            messagebox.showinfo('Резервная копия', 'Копия базы сохранена. Она содержит заявки и учётные записи. Храните её в безопасном месте.', parent=root)
        except Exception as exc:
            messagebox.showerror('Резервная копия', str(exc), parent=root)

    tk.Button(root, text='Резервная копия базы', command=backup, width=28).pack(pady=4)

    def close():
        server.should_exit = True
        thread.join(timeout=3)
        sock.close()
        root.destroy()

    tk.Button(root, text='Завершить работу', command=close, width=28).pack(pady=4)
    root.protocol('WM_DELETE_WINDOW', close)
    root.deiconify()
    tries = 0

    def ready():
        nonlocal tries
        if server.started:
            status.config(text='Приложение работает локально')
            open_button.config(state='normal')
            webbrowser.open(url)
        elif not thread.is_alive() or tries > 100:
            messagebox.showerror('Ошибка запуска', 'Не удалось запустить локальный сервер.', parent=root)
            close()
        else:
            tries += 1
            root.after(100, ready)

    root.after(100, ready)
    root.mainloop()


def smoke_test(report):
    import tempfile
    import time
    import json
    import urllib.request
    import urllib.error
    os.environ['STONE_DATA_DIR'] = tempfile.mkdtemp(prefix='stone-app-smoke-')
    import uvicorn
    from app import app, ROOT
    assert (ROOT/'static/index.html').is_file()
    assert (ROOT/'data/catalog.json').is_file()
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    url = f'http://127.0.0.1:{sock.getsockname()[1]}'
    server = uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    try:
        for _ in range(200):
            if server.started:
                break
            if not thread.is_alive():
                raise RuntimeError('Server stopped')
            time.sleep(.05)
        assert server.started, 'Server did not start'
        def read(path):
            with urllib.request.urlopen(url+path, timeout=10) as r:
                return r.read()
        assert b'STONE' in read('/')
        assert b'function' in read('/static/app.js')
        catalog = json.loads(read('/api/catalog'))
        assert len(catalog['materials']) == 668
        req = urllib.request.Request(url+'/api/quote', data=json.dumps({'material':catalog['materials'][0]['id'], 'parts':[{'length':1000,'width':600}], 'installation':False}).encode(), headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req, timeout=10) as r:
            quote = json.load(r)
        assert quote['total'] == 28347.5
        assert 'internal' not in quote
        try:
            read('/api/admin/settings')
        except urllib.error.HTTPError as e:
            assert e.code == 403
        else:
            raise AssertionError('Admin route is exposed')
        Path(report).write_text(json.dumps({'ok':True,'materials':668,'quote':quote['total']}))
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()


if __name__ == '__main__':
    if '--smoke-test' in sys.argv:
        smoke_test(sys.argv[sys.argv.index('--report')+1])
    else:
        main()
