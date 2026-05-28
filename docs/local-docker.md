# Docker ローカル環境

## 目的

Docker ローカル環境は、ホスト OS の Python や virtualenv に依存せず、Django の設定検査、テスト、静的ファイル参照検査、ブラウザでのローカル動作確認を同じ手順で再実行するために使用します。

この環境は `config.settings.dev` を使用します。staging または prod の Secrets Manager、Parameter Store、S3、CloudFront には接続しません。

## 外部資産

`Dockerfile` は digest 固定した `python:3.12-slim-bookworm` を base image として使用します。

- Docker Docs は Docker Official Images を Docker Hub の curated repositories と説明しています。
- `docker-library/python` は Docker Official Image packaging for Python のリポジトリで、GitHub 上の license 表示は MIT license です。
- Python パッケージは `requirements.txt` と build tool の `csscompressor==0.9.5` を使用します。`csscompressor` のライセンス確認結果は [`external-assets.md`](external-assets.md) に記録しています。

## ビルド

```powershell
docker compose build
```

## 検証

設定検査、Django test、静的資産生成、`collectstatic`、`render_static`、静的ファイル manifest 参照検査をまとめて実行します。

```powershell
docker compose run --rm verify
```

この検証は `python manage.py check --fail-level WARNING` を含むため、Django warning が残っている場合は失敗します。

`verify` は `scripts/generate_static_assets.py` を実行します。このスクリプトは Google Fonts の commit 固定 URL から `Montserrat.ttf` と `Lato.ttf` を取得し、`portfolio/static/css/styles.css` から `portfolio/static/css/styles.min.css` を生成します。

## ローカル起動

```powershell
docker compose up web
```

起動後、別の PowerShell から次を確認します。

```powershell
curl.exe -iL http://localhost:8000/
curl.exe -i http://localhost:8000/portfolio/top/
```

`/` は `/portfolio/top/` へ redirect し、`/portfolio/top/` は `200 OK` を返します。

## 管理コマンド

任意の Django 管理コマンドは `web` service で実行します。

```powershell
docker compose run --rm web python manage.py check --fail-level WARNING
docker compose run --rm web python manage.py test
docker compose run --rm web python scripts/generate_static_assets.py
docker compose run --rm web python manage.py collectstatic --noinput
docker compose run --rm web python manage.py render_static
```

`collectstatic` を dry-run なしで実行すると、bind mount された作業ツリーの `staticfiles/` に出力します。`staticfiles/` は生成物であり Git 管理対象ではありません。

## 停止

```powershell
docker compose down
```

## 関連ファイル

- [`Dockerfile`](../Dockerfile)
- [`compose.yaml`](../compose.yaml)
- [`.dockerignore`](../.dockerignore)
- [`requirements.txt`](../requirements.txt)
- [`config/settings/dev.py`](../config/settings/dev.py)
