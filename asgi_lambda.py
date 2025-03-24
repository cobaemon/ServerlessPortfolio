from mangum import Mangum

from config.asgi import application  # 通常の asgi.py から ASGI アプリケーションをインポート

handler = Mangum(application, lifespan="off")
