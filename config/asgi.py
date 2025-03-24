"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

# 環境変数で使用する設定ファイルを指定
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.prod')

# ASGI アプリケーションの取得
application = get_asgi_application()
