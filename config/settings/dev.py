import os

import dotenv

from .base import *

# .env ファイルが存在すれば読み込む
dotenv_file = BASE_DIR / '.env'
if dotenv_file.exists():
    dotenv.load_dotenv(dotenv_path=dotenv_file)

DEBUG = False

# SECRET_KEY は .env にあればそちらを、なければ環境変数、さらになければデフォルト値
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-default-secret-key")

# ALLOWED_HOSTS は、.envや環境変数に値があればそれを使用、なければデフォルトで localhost,127.0.0.1
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(',')
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

# メール設定
# SMTP 接続設定値（ホスト・ポート・TLS 有効化・SSL 有効化）と
# SMTP 認証情報（ユーザー名・パスワード）の読み込み、および
# SMTP / console のバックエンド分岐は除去した。ローカル開発では送信を行わず、
# console バックエンドを単一値として明示設定する
# （出典: requirements.md R4-1/R4-3、design.md C8 区分 B-3、tasks.md 12.2）。
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "webmaster@localhost")
DEFAULT_TO_EMAIL = os.environ.get("DEFAULT_TO_EMAIL", "")
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

