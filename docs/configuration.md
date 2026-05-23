# 設定とシークレット

## Django 設定ファイル

`config/settings/base.py` は共通設定です。`config/settings/dev.py`、`config/settings/staging.py`、`config/settings/prod.py` は `base.py` または `prod.py` を import して環境別設定を上書きします。

## 共通設定

`base.py` では次を定義しています。

- `INSTALLED_APPS`
- `MIDDLEWARE`
- `TEMPLATES`
- SQLite データベース
- `LANGUAGE_CODE = 'ja'`
- `TIME_ZONE = 'Asia/Tokyo'`
- `LANGUAGES`
- `STATIC_URL`
- `STATIC_ROOT`
- `STORAGES`
- `CONTENT_SECURITY_POLICY`
- `LOGGING`

`STATICFILES_DIRS` は `BASE_DIR / "static"` を参照します。

## ローカル開発設定

`config/settings/dev.py` は `.env` が存在する場合に読み込みます。

`dev.py` の既定値は次の通りです。

- `DEBUG = False`
- `SECRET_KEY`: `DJANGO_SECRET_KEY` 環境変数、未設定時は `dev-default-secret-key`
- `ALLOWED_HOSTS`: `ALLOWED_HOSTS` 環境変数、未設定時は `localhost,127.0.0.1`
- `127.0.0.1` と `127.0.0.1:3000` を `ALLOWED_HOSTS` に追加
- `EMAIL_BACKEND`: `EMAIL_HOST` があれば SMTP、なければ console backend

`EMAIL_USE_TLS` と `EMAIL_USE_SSL` が同時に `True` の場合は `ImproperlyConfigured` を送出します。

## 本番設定

`config/settings/prod.py` は `DEBUG = False` です。

本番設定では次の環境変数が未設定の場合に `ImproperlyConfigured` を送出します。

- `DJANGO_SECRET_KEY`
- `ALLOWED_HOSTS`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GITHUB_CLIENT_ID`
- `GITHUB_CLIENT_SECRET`
- `CSRF_TRUSTED_ORIGINS`
- `DEFAULT_FROM_EMAIL`
- `DEFAULT_TO_EMAIL`
- `EMAIL_HOST`
- `EMAIL_PORT`

本番設定では次のセキュリティ関連値が設定されています。

- `SECURE_SSL_REDIRECT = True`
- `SESSION_COOKIE_SECURE = True`
- `CSRF_COOKIE_SECURE = True`

`EMAIL_USE_TLS` と `EMAIL_USE_SSL` が同時に `True` の場合は `ImproperlyConfigured` を送出します。

## Staging 設定

`config/settings/staging.py` は `config/settings/prod.py` を import し、`ENV = "staging"` を設定します。

## AWS から注入される値

`template.yaml` は Lambda 環境変数として Secrets Manager と Parameter Store の動的参照を使用します。

### Secrets Manager

`template.yaml` は `${Env}/portfolio/secret` から次の値を参照します。

- `DJANGO_SECRET_KEY`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GITHUB_CLIENT_ID`
- `GITHUB_CLIENT_SECRET`

### Parameter Store

`template.yaml` は次の Parameter Store パスを参照します。

- `/${Env}/portfolio/parameter/allowed_hosts`
- `/${Env}/portfolio/parameter/default_from_email`
- `/${Env}/portfolio/parameter/default_to_mail`
- `/${Env}/portfolio/parameter/email_host`
- `/${Env}/portfolio/parameter/email_port`
- `/${Env}/portfolio/parameter/email_use_tls`
- `/${Env}/portfolio/parameter/email_use_ssl`
- `/${Env}/portfolio/parameter/log_level`

`AllowedOrigin` と `AllowedHosts` パラメータは `AWS::SSM::Parameter::Value<String>` 型です。

## 静的ファイル設定

`prod.py` では `CLOUDFRONT_DOMAIN_NAME` が設定されている場合、`STATIC_URL` を `https://{CLOUDFRONT_DOMAIN_NAME}/` に変更します。その場合、staticfiles backend は `config.storage_backends.LocalManifestS3Storage` です。

S3 オブジェクトの ACL は `AWS_DEFAULT_ACL = None` です。静的ファイルへの読み取り権限は、公開 ACL ではなく CloudFront OAC と S3 bucket policy で制御します。

`CLOUDFRONT_DOMAIN_NAME` がない場合、`STATIC_URL` は `/static/` です。

## 関連ファイル

- [`config/settings/base.py`](../config/settings/base.py)
- [`config/settings/dev.py`](../config/settings/dev.py)
- [`config/settings/staging.py`](../config/settings/staging.py)
- [`config/settings/prod.py`](../config/settings/prod.py)
- [`template.yaml`](../template.yaml)
- [`samconfig.toml`](../samconfig.toml)
