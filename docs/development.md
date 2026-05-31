# 開発環境

## Python 依存関係

`requirements.txt` には direct dependency と transitive dependency のバージョンを記載しています。Windows ローカルだけで必要な依存は `sys_platform == 'win32'`、Linux/Docker だけで必要な依存は `sys_platform != 'win32'` の marker を付けています。

外部資産と dependency のライセンスは [`external-assets.md`](external-assets.md) に記載しています。

## ローカル設定

ローカル開発用設定は `config/settings/dev.py` です。

プロジェクトルートの `.env` が存在する場合、`dev.py` は `python-dotenv` で読み込みます。

Docker を使用する場合は [`local-docker.md`](local-docker.md) の手順を使用します。

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

`portfolio/tests.py` には問い合わせフォーム、CSRF、URL routing、production static storage settings の回帰テストがあります。

```powershell
$env:DJANGO_SETTINGS_MODULE="config.settings.dev"
python manage.py check --fail-level WARNING
python manage.py test
```

Docker で同じ検査を実行する場合は次を使用します。

```powershell
docker compose run --rm verify
```

## AGENTS Hook

Git hooks は `.githooks` を使用します。有効化コマンドは次の通りです。

```powershell
git config core.hooksPath .githooks
```

Hook 本体は `scripts/project_control_guard.py` です。CodexHook と GitHook は同じ共通ポリシーを使用します。`pre-commit` は制御系ファイル、CodexHook 設定、GitHook 設定、staged diff、インシデント記録を検査します。`commit-msg` は commit message のタイトルと本文を検査します。

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

Docker で静的ファイル収集を確認する場合は、作業ツリーへの出力を避けるため dry-run を使用します。

```powershell
docker compose run --rm web python manage.py collectstatic --noinput --dry-run
```

## 関連ファイル

- [`requirements.txt`](../requirements.txt)
- [`Dockerfile`](../Dockerfile)
- [`compose.yaml`](../compose.yaml)
- [`manage.py`](../manage.py)
- [`AGENTS.md`](../AGENTS.md)
- [`scripts/project_control_guard.py`](../scripts/project_control_guard.py)
- [`scripts/branch-finalize-next.ps1`](../scripts/branch-finalize-next.ps1)
- [`config/settings/dev.py`](../config/settings/dev.py)
- [`portfolio/tests.py`](../portfolio/tests.py)
- [`portfolio/management/commands/render_static.py`](../portfolio/management/commands/render_static.py)
