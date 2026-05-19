# 開発環境

## Python 依存関係

`requirements.txt` には次のパッケージ名が記載されています。

- `django`
- `django-environ`
- `django-storages`
- `boto3`
- `gunicorn`
- `pillow`
- `pillow-avif-plugin`
- `django-csp`
- `psycopg2-binary`
- `cryptography`
- `django-allauth`
- `django-otp`
- `qrcode`
- `requests`
- `pyjwt`
- `awsgi; sys_platform != 'win32'`
- `whitenoise`
- `mangum`
- `python-dotenv`

バージョン固定は `requirements.txt` には記載されていません。

## ローカル設定

ローカル開発用設定は `config/settings/dev.py` です。

`.env` が存在する場合、`dev.py` は `python-dotenv` で読み込みます。

## ローカル実行

Django 管理コマンドの入口は `manage.py` です。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DJANGO_SETTINGS_MODULE="config.settings.dev"
python manage.py migrate
python manage.py runserver
```

## テスト

`portfolio/tests.py` は存在しますが、テストケースは定義されていません。

```powershell
$env:DJANGO_SETTINGS_MODULE="config.settings.dev"
python manage.py test
```

## AGENTS Hook

Git hooks は `.githooks` を使用します。有効化コマンドは次の通りです。

```powershell
git config core.hooksPath .githooks
```

Hook 本体は `scripts/agents-compliance-check.ps1` です。`pre-commit` は `AGENTS.md` の必須原則マーカーと成果物ドキュメントのエビデンスラベルを検査します。`commit-msg` は commit message のタイトルと本文を検査します。

## 静的ファイル

静的ファイル収集は Django の `collectstatic` を使用します。

```powershell
$env:DJANGO_SETTINGS_MODULE="config.settings.dev"
python manage.py collectstatic
```

`portfolio/management/commands/render_static.py` は `templates/portfolio_base.html` を `STATIC_ROOT/index.html` にレンダリングする管理コマンドです。

```powershell
$env:DJANGO_SETTINGS_MODULE="config.settings.dev"
python manage.py render_static
```

## 関連ファイル

- [`requirements.txt`](../requirements.txt)
- [`manage.py`](../manage.py)
- [`AGENTS.md`](../AGENTS.md)
- [`scripts/agents-compliance-check.ps1`](../scripts/agents-compliance-check.ps1)
- [`config/settings/dev.py`](../config/settings/dev.py)
- [`portfolio/tests.py`](../portfolio/tests.py)
- [`portfolio/management/commands/render_static.py`](../portfolio/management/commands/render_static.py)
