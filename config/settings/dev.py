import os
from pathlib import Path

import dotenv

from .base import *

# プロジェクトルートのパス（base.py 内で既に定義されている場合は省略可）
BASE_DIR = Path(__file__).resolve().parent.parent

# .env ファイルが存在すれば読み込む
dotenv_file = BASE_DIR / '.env'
if dotenv_file.exists():
    dotenv.load_dotenv(dotenv_path=dotenv_file)

DEBUG = False

# SECRET_KEY は .env にあればそちらを、なければ環境変数、さらになければデフォルト値
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-default-secret-key")

# ALLOWED_HOSTS は、.envや環境変数に値があればそれを使用、なければデフォルトで localhost,127.0.0.1
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(',')

print(f'\n\n{ALLOWED_HOSTS}\n\n')
if "127.0.0.1" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("127.0.0.1")
# SAM Local でのリクエストヘッダーに "127.0.0.1:3000" が含まれるため、それも追加
if "127.0.0.1:3000" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("127.0.0.1:3000")

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}