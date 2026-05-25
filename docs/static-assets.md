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

`config/storage_backends.py` は `LocalManifestS3Storage` を定義しています。

`LocalManifestS3Storage` は `S3ManifestStaticStorage` を継承し、manifest storage としてローカルの `staticfiles` ディレクトリを参照します。`load_manifest()` は manifest のパス区切りを `/` に正規化します。

## ビルド時処理

`buildspec.yml` は次の静的ファイル処理を行います。

- Google Fonts の `Montserrat.ttf` と `Lato.ttf` を `portfolio/static/assets/fonts` に取得。
- `portfolio/static/css/styles.css` を `csscompressor` で圧縮し、`styles.min.css` を生成。
- `python manage.py collectstatic --noinput` を実行。
- `python manage.py render_static` を実行。
- `staticfiles/` を `s3://cobaemon-serverless-portfolio-${ENV}-static/` に `--delete` 付きで同期。

`Montserrat.ttf` と `Lato.ttf` のライセンス確認結果は [`external-assets.md`](external-assets.md) に記載しています。

## 静的ファイル参照検査

`scripts/check_static_manifest.py` は `staticfiles/staticfiles.json` の `paths` を読み、`templates` 配下の `{% static '...' %}` 参照が manifest に存在するかを検査します。

## 関連ファイル

- [`portfolio/static`](../portfolio/static)
- [`staticfiles`](../staticfiles)
- [`config/storage_backends.py`](../config/storage_backends.py)
- [`portfolio/management/commands/render_static.py`](../portfolio/management/commands/render_static.py)
- [`scripts/check_static_manifest.py`](../scripts/check_static_manifest.py)
- [`buildspec.yml`](../buildspec.yml)
- [`template.yaml`](../template.yaml)
