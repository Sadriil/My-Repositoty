#!/bin/bash
set -e
cd -- "$(dirname -- "$0")/.."
echo 'Stone Production — локальная версия для macOS'
PYTHON_BIN=''
for candidate in python3.14 python3.13 python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys, tkinter; assert sys.version_info >= (3,12)' >/dev/null 2>&1; then
        PYTHON_BIN="$candidate"
        break
    fi
done
if [ -z "$PYTHON_BIN" ]; then
    echo 'Нужен Python 3.12 или новее с Tkinter. Установите Python с python.org, затем повторите запуск.'
    open 'https://www.python.org/downloads/macos/'
    read -r -p 'Нажмите Enter, чтобы закрыть окно…' unused_reply
    exit 1
fi
APP_ENV="$HOME/Library/Application Support/Stone Production/python-env"
if [ ! -x "$APP_ENV/bin/python" ]; then
    mkdir -p "$(dirname -- "$APP_ENV")"
    "$PYTHON_BIN" -m venv "$APP_ENV"
fi
if ! "$APP_ENV/bin/python" -c 'import fastapi,uvicorn; assert fastapi.__version__=="0.141.1" and uvicorn.__version__=="0.52.1"' >/dev/null 2>&1; then
    echo 'Первая установка: скачиваем необходимые компоненты…'
    "$APP_ENV/bin/python" -m pip install -r requirements.txt || {
        echo 'Установка не завершена. Проверьте интернет и повторите запуск.'
        read -r -p 'Нажмите Enter…' unused_reply
        exit 1
    }
fi
exec "$APP_ENV/bin/python" desktop.py
