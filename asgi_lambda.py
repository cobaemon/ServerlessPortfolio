"""
AWS Lambda用のASGIハンドラー
DjangoアプリケーションをAWS Lambda環境で実行するためのエントリーポイント
"""

from mangum import Mangum

from config.asgi import application  # Django ASGIアプリケーションをインポート

# Mangumを使用してDjangoアプリケーションをLambdaハンドラーとして設定
# lifespan="off"でライフサイクルイベントを無効化（Lambda環境では不要）
handler = Mangum(application, lifespan="off")
