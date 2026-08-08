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

`portfolio/tests/test_regression.py` には問い合わせフォーム、CSRF、URL routing、production static storage settings の回帰テストがあります（`portfolio/tests.py` は `portfolio/tests/` パッケージへ移行済み。出典: `portfolio/tests/__init__.py` のパッケージドキュメント）。同パッケージには `test_render_static.py`（`render_static` の生成失敗時のビルド中断とハニーポット非収集の単体テスト）、`test_property_csp_hash.py`、`test_property_csp_allowlist.py`（CSP のプロパティテスト）もあります（出典: `portfolio/tests/` の構成）。

```powershell
$env:DJANGO_SETTINGS_MODULE="config.settings.dev"
python manage.py check --fail-level WARNING
python manage.py test
```

Docker で同じ検査を実行する場合は次を使用します。

```powershell
docker compose run --rm verify
```

## 静的ファイル

静的ファイル収集は Django の `collectstatic` を使用します。

```powershell
$env:DJANGO_SETTINGS_MODULE="config.settings.dev"
python manage.py collectstatic
```

`portfolio/management/commands/render_static.py` は表示ページ（`/portfolio/top/`）を `settings.LANGUAGES` の 7 言語（`ja, en, fr, es, ru, zh-hans, ar`）分フルページ静的化する管理コマンドです。各言語を `translation.override` で有効化して `index.html`（`portfolio_base.html` を継承）をレンダリングし、`STATIC_ROOT/<lang>/portfolio/top/index.html` を生成します。ルートの `STATIC_ROOT/index.html` は既定言語 `settings.LANGUAGE_CODE`（`ja`）のフルページの複製で、あわせて統一 CSP と生成物一覧を `STATIC_ROOT/prerender_manifest.json` へ書き出します（出典: `portfolio/management/commands/render_static.py` の `_LANG_PAGE_RELATIVE_FORMAT` / `_ROOT_PAGE_RELATIVE` / `_MANIFEST_RELATIVE` と `Command.handle`、`config/settings/base.py` の `LANGUAGES` / `LANGUAGE_CODE`）。いずれかの言語でレンダリングに失敗した場合は `CommandError` で中断し、ファイルを一切書き出しません（出典: 同ファイルの `_render_language_page` / `_write_outputs`）。

```powershell
$env:DJANGO_SETTINGS_MODULE="config.settings.dev"
python manage.py render_static
```

本コマンドは `settings.AWS_S3_CUSTOM_DOMAIN` を必須とし、未設定時はフォールバックせず `CommandError` で中断します。当該設定を定義しているのは `config/settings/prod.py`（環境変数 `CLOUDFRONT_DOMAIN_NAME` から取得）のみで、`config/settings/dev.py` には定義がありません（出典: `portfolio/management/commands/render_static.py` の `_resolve_cloudfront_domain`、`config/settings/prod.py` の `AWS_S3_CUSTOM_DOMAIN`）。

CI では `collectstatic` の後に本コマンドを実行し、成功した場合にのみ `aws s3 sync staticfiles/ s3://${BUCKET_NAME}/ --delete` を行います。生成された `prerender_manifest.json` の `content_security_policy` は `parameters.json` の `ContentSecurityPolicy` へ注入されます（出典: `buildspec.yml` の pre_build 段の `python manage.py render_static` と post_build 段の `parameters.json` 生成処理）。

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
- [`scripts/branch-finalize-next.ps1`](../scripts/branch-finalize-next.ps1)
- [`config/settings/dev.py`](../config/settings/dev.py)
- [`portfolio/tests/test_regression.py`](../portfolio/tests/test_regression.py)
- [`portfolio/management/commands/render_static.py`](../portfolio/management/commands/render_static.py)
