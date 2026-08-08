# config/settings/prod.py
import os

from django.core.exceptions import ImproperlyConfigured

from .base import *

# WhiteNoise is unnecessary when serving static files via CloudFront
MIDDLEWARE = [mw for mw in MIDDLEWARE if mw != 'whitenoise.middleware.WhiteNoiseMiddleware']

# WhiteNoise's runserver helper is also unnecessary in production
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != 'whitenoise.runserver_nostatic']


DEBUG = False


# 本番環境では、環境変数が設定されていない場合はエラーにする
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured("Set the DJANGO_SECRET_KEY environment variable")

# ALLOWED_HOSTS はカンマ区切りの文字列として環境変数に設定されている前提
allowed_hosts = os.environ.get("ALLOWED_HOSTS")
if not allowed_hosts:
    raise ImproperlyConfigured("Set the ALLOWED_HOSTS environment variable")
ALLOWED_HOSTS = allowed_hosts.split(",")

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# SMTP 経路は本番設定から全面的に除去した。対象は SMTP 認証情報（ユーザー名・パスワード）
# に加え、SMTP 接続設定値（ホスト・ポート・TLS 有効化・SSL 有効化）である。
# 問い合わせメール送信は Amazon SES 直連携（Contact_Function）が担うため、
# SMTP 認証情報および接続設定値を Secrets Manager・Parameter Store・ビルド環境・
# Django 設定のいずれからも保持しない。Django 側の送信バックエンドは後述の
# EMAIL_BACKEND で console バックエンドを明示設定する
# （出典: requirements.md R4-1/R4-2/R4-17、design.md C8、tasks.md 12.1）。

# OAuth設定 - 必須項目
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
if not GOOGLE_CLIENT_ID:
    raise ImproperlyConfigured("Set the GOOGLE_CLIENT_ID environment variable")

GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
if not GOOGLE_CLIENT_SECRET:
    raise ImproperlyConfigured("Set the GOOGLE_CLIENT_SECRET environment variable")

GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID")
if not GITHUB_CLIENT_ID:
    raise ImproperlyConfigured("Set the GITHUB_CLIENT_ID environment variable")

GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET")
if not GITHUB_CLIENT_SECRET:
    raise ImproperlyConfigured("Set the GITHUB_CLIENT_SECRET environment variable")

csrf_trusted_origins = os.environ.get("CSRF_TRUSTED_ORIGINS")
if not csrf_trusted_origins:
    raise ImproperlyConfigured("Set the CSRF_TRUSTED_ORIGINS environment variable")
CSRF_TRUSTED_ORIGINS = csrf_trusted_origins.split(",")

# メール設定 - 必須項目
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL")
if not DEFAULT_FROM_EMAIL:
    raise ImproperlyConfigured("Set the DEFAULT_FROM_EMAIL environment variable")

DEFAULT_TO_EMAIL = os.environ.get("DEFAULT_TO_EMAIL")
if not DEFAULT_TO_EMAIL:
    raise ImproperlyConfigured("Set the DEFAULT_TO_EMAIL environment variable")

# メール送信バックエンド - 明示設定（必須）
# 本番・staging の Django プロセスは SMTP 送信経路を持たない。Django の既定値は
# SMTP バックエンド（localhost:25）であり、未指定のままでは暗黙の既定へ依存する
# フォールバック状態となるため、console バックエンドを単一値として明示設定する。
# config/settings/staging.py の `from .prod import *` により staging も同値を継承する
# （出典: requirements.md R4-17/R4-11、design.md C8「確定事項（Approver 判断済み）」）。
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# セキュリティ強化のための設定
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# AWS S3とCloudFrontの設定 - オプション項目
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")

# ENV設定 - デフォルト値あり
ENV = os.environ.get('ENV', 'prod')

AWS_STORAGE_BUCKET_NAME = f"cobaemon-serverless-portfolio-{ENV}-static"
AWS_S3_REGION_NAME = 'ap-northeast-1'

# CloudFrontの設定
AWS_S3_CUSTOM_DOMAIN = os.environ.get('CLOUDFRONT_DOMAIN_NAME')
AWS_S3_OBJECT_PARAMETERS = {
    'CacheControl': 'max-age=86400',
}

# 静的ファイルの設定
if AWS_S3_CUSTOM_DOMAIN:
    STATIC_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/'
    # 静的アセットは「ビルド時に collectstatic でローカル STATIC_ROOT へハッシュ名付きで収集し、
    # buildspec の `aws s3 sync staticfiles/ s3://...-static/ --delete` で S3 へ配置する」モデル
    # （静的ファースト配信）。したがって staticfiles ストレージはローカルの
    # ManifestStaticFilesStorage を用い、URL のみ STATIC_URL（CloudFront ドメイン）＋ハッシュ名で
    # 生成する。S3 直アップロード型ストレージ（S3ManifestStaticStorage 系）は collectstatic が
    # アセットを S3 へ直接アップロードするため、後続の `s3 sync --delete` が「ローカル staticfiles/ に
    # 存在しない」当該アセットを削除して 403 を招く。この衝突を避けるため直アップロード型は用いない
    # （出典: buildspec.yml の collectstatic→s3 sync、requirements.md R3-2/R3-3、design.md C1/C9、本不具合修正）。
    STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'
    STORAGES = {
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage",
        },
        "default": {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        },
    }
    # Include the CloudFront domain in CSP directives so static assets load
    _STATIC_DOMAIN = f"https://{AWS_S3_CUSTOM_DOMAIN}"
    # Append the CloudFront domain to CSP directives defined in base settings
    _csp = CONTENT_SECURITY_POLICY.setdefault("DIRECTIVES", {})
    _csp.setdefault("default-src", []).append(_STATIC_DOMAIN)
    _csp.setdefault("script-src", []).append(_STATIC_DOMAIN)
    _csp.setdefault("script-src-elem", []).append(_STATIC_DOMAIN)
    _csp.setdefault("style-src", []).append(_STATIC_DOMAIN)
    _csp.setdefault("style-src-elem", []).append(_STATIC_DOMAIN)
    _csp.setdefault("font-src", []).append(_STATIC_DOMAIN)
    _csp.setdefault("img-src", []).append(_STATIC_DOMAIN)
else:
    # CloudFrontが設定されていない場合のフォールバック
    STATIC_URL = '/static/'

# S3 object access is granted by CloudFront OAC and bucket policy, not public ACLs.
AWS_DEFAULT_ACL = None
AWS_S3_FILE_OVERWRITE = False

# # django-storagesを有効化
# DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
