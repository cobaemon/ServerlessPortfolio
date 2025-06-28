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

# メール設定 - 必須項目
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER")
if not EMAIL_HOST_USER:
    raise ImproperlyConfigured("Set the EMAIL_HOST_USER environment variable")

EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD")
if not EMAIL_HOST_PASSWORD:
    raise ImproperlyConfigured("Set the EMAIL_HOST_PASSWORD environment variable")

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

EMAIL_HOST = os.environ.get("EMAIL_HOST")
if not EMAIL_HOST:
    raise ImproperlyConfigured("Set the EMAIL_HOST environment variable")

EMAIL_PORT = os.environ.get("EMAIL_PORT")
if not EMAIL_PORT:
    raise ImproperlyConfigured("Set the EMAIL_PORT environment variable")

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
    STATICFILES_STORAGE = 'config.storage_backends.LocalManifestS3Storage'
    STORAGES = {
        "staticfiles": {
            "BACKEND": "config.storage_backends.LocalManifestS3Storage",
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

# S3の設定
AWS_DEFAULT_ACL = 'public-read'
AWS_S3_FILE_OVERWRITE = False

# # django-storagesを有効化
# DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
