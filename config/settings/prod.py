# config/settings/prod.py
import os

from django.core.exceptions import ImproperlyConfigured

from .base import *

DEBUG = False

def get_env_variable(var_name):
    """
    Returns the value of the environment variable var_name.
    Raises ImproperlyConfigured if the variable is not set.
    """
    try:
        return os.environ[var_name]
    except KeyError:
        raise ImproperlyConfigured(f"Set the {var_name} environment variable")

# 本番環境では、デフォルト値を設定せず必須項目とする
SECRET_KEY = get_env_variable("DJANGO_SECRET_KEY")

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

EMAIL_HOST_USER = get_env_variable("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = get_env_variable("EMAIL_HOST_PASSWORD")
GOOGLE_CLIENT_ID = get_env_variable("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = get_env_variable("GOOGLE_CLIENT_SECRET")
GITHUB_CLIENT_ID = get_env_variable("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = get_env_variable("GITHUB_CLIENT_SECRET")

csrf_trusted_origins = os.environ.get("CSRF_TRUSTED_ORIGINS")
if not csrf_trusted_origins:
    raise ImproperlyConfigured("Set the CSRF_TRUSTED_ORIGINS environment variable")
CSRF_TRUSTED_ORIGINS = csrf_trusted_origins.split(",")

DEFAULT_FROM_EMAIL = get_env_variable("DEFAULT_FROM_EMAIL")
DEFAULT_TO_EMAIL = get_env_variable("DEFAULT_TO_EMAIL")
EMAIL_HOST = get_env_variable("EMAIL_HOST")
EMAIL_PORT = get_env_variable("EMAIL_PORT")

# セキュリティ強化のための設定
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
