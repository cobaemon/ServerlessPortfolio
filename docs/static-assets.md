# 静的ファイル配信

## ソース配置

アプリケーション側の静的ファイルは `portfolio/static` 配下にあります。`staticfiles` は `collectstatic` の出力先です。

`config/settings/base.py` の `STATIC_ROOT` は `BASE_DIR / "staticfiles"` です。

リポジトリ直下の `static` ディレクトリは使用しません。`portfolio/static` は Django app static として検出されます。

## 本番配信

`template.yaml` は `CloudFrontDistribution` を定義し、S3 静的ファイルバケットをオリジンにします。

CloudFront の `DefaultCacheBehavior` は次の設定を持ちます。

- `ViewerProtocolPolicy: redirect-to-https`
- `AllowedMethods`: `GET`, `HEAD`, `OPTIONS`
- `CachedMethods`: `GET`, `HEAD`, `OPTIONS`
- `Compress: true`
- `CachePolicyId: 658327ea-f89d-4fab-a63d-7e88639e58f6`

## Manifest Storage

`CLOUDFRONT_DOMAIN_NAME` が設定された本番/ステージングでは、`prod.py` の staticfiles backend に Django 標準の `django.contrib.staticfiles.storage.ManifestStaticFilesStorage`（ローカル manifest ストレージ）を使用します。`collectstatic` はハッシュ名付きの静的ファイルをローカルの `STATIC_ROOT`（`staticfiles/`）へ収集し、`staticfiles.json`（manifest）を生成します。URL は `STATIC_URL`（`https://<CLOUDFRONT_DOMAIN_NAME>/`）＋ハッシュ名で生成されます。

S3 へのアップロードは `buildspec.yml` の `aws s3 sync staticfiles/ s3://...-static/ --delete` が担います（S3 直アップロード型ストレージは使用しません。直アップロード型は `sync --delete` と衝突し、ローカル `staticfiles/` に存在しないアップロード済みアセットを削除して 403 を招くため）。

## ビルド時処理

`buildspec.yml` は次の静的ファイル処理を行います。

- `scripts/generate_static_assets.py` が Google Fonts の commit 固定 URL から `Montserrat.ttf` と `Lato.ttf` を `portfolio/static/assets/fonts` に取得。
- `scripts/generate_static_assets.py` が `portfolio/static/css/styles.css` を `csscompressor` で圧縮し、`styles.min.css` を生成。
- `python manage.py collectstatic --noinput` を実行。
- `python manage.py render_static` を実行。
- `staticfiles/` を `s3://cobaemon-serverless-portfolio-${ENV}-static/` に `--delete` 付きで同期。
- 同期成功後、CloudFront のキャッシュを破棄して新しくする（`aws cloudfront create-invalidation --paths "/*"`）。S3 更新だけではエッジが TTL 満了まで旧内容を返すため、更新内容を即時反映する。ディストリビューション ID は既存アプリスタックの `CloudFrontDistribution` リソースから解決し、初回デプロイ等で未検出の場合はスキップする（新規配信のため不要）。

`Montserrat.ttf` と `Lato.ttf` のライセンス確認結果は [`external-assets.md`](external-assets.md) に記載しています。

## 静的ファイル参照検査

`scripts/check_static_manifest.py` は `staticfiles/staticfiles.json` の `paths` を読み、`templates` 配下の `{% static '...' %}` 参照が manifest に存在するかを検査します。

## 関連ファイル

- [`portfolio/static`](../portfolio/static)
- [`staticfiles`](../staticfiles)
- [`config/settings/prod.py`](../config/settings/prod.py)
- [`portfolio/management/commands/render_static.py`](../portfolio/management/commands/render_static.py)
- [`scripts/check_static_manifest.py`](../scripts/check_static_manifest.py)
- [`buildspec.yml`](../buildspec.yml)
- [`template.yaml`](../template.yaml)
