# ServerlessPortfolio

Django 6.0.3（出典: `requirements.txt`）で構築したポートフォリオサイトを、表示ページは S3 と CloudFront から静的配信し、問い合わせ送信のみ Django 非依存の Lambda（`ContactFunction`）と API Gateway（`ContactApi`）で処理するプロジェクトです（出典: `template.yaml` の `CloudFrontDistribution` / `ContactApi` / `ContactFunction`）。

## 構成

- アプリケーション: Django プロジェクト `config` と Django アプリ `portfolio`（ビルド時の静的化と設定検証に使用。実行時に Django を動かす Lambda はありません）
- Lambda エントリーポイント: `contact_function/handler.py` の `lambda_handler`（出典: `template.yaml` の `ContactFunction.Handler: contact_function.handler.lambda_handler`）
- 表示ページ静的化コマンド: `portfolio/management/commands/render_static.py`（7 言語分の事前レンダリング）
- 本番 Django 設定: `config/settings/prod.py`
- ローカル開発 Django 設定: `config/settings/dev.py`
- AWS SAM アプリケーション定義: `template.yaml`
- 依存リソース定義: `dependencies.yaml`
- S3 バケットポリシー定義: `bucketpolicy.yaml`
- CI/CD パイプライン定義: `pipeline.yaml`
- CodeBuild 定義: `buildspec.yml`、`buildspec-deps.yml`
- SAM デプロイ設定: `samconfig.toml`

## アプリケーション機能

- `/` および `/portfolio/top/` を、CloudFront Function（`DisplayRouterFunction`）が `Accept-Language` 交渉の結果に従って `/<lang>/portfolio/top/index.html` へ内部書き換え（出典: `template.yaml` の `DisplayRouterFunction.FunctionCode`）
- `/portfolio/top/` のポートフォリオページ表示（S3 上の事前レンダリング済み HTML を CloudFront が配信）
- `/portfolio/contact` の問い合わせ POST 処理（`ContactApi` 経由で `ContactFunction` が処理）
- Django i18n による日本語、英語、フランス語、スペイン語、ロシア語、簡体中国語、アラビア語の言語定義（出典: `config/settings/base.py` の `LANGUAGES`）
- ハッシュベース Content-Security-Policy の配信（ビルドが `render_static` で生成し、CloudFront の `DisplayResponseHeadersPolicy` が付与。nonce は使用しません）
- Amazon SES（SESv2 `SendEmail`）による問い合わせ内容の送信（出典: `contact_function/adapters/ses_email_sender.py`）

## AWS 構成

`template.yaml` は、問い合わせ用 Lambda（`ContactFunction`）、問い合わせ用 API Gateway REST API（`ContactApi`）、そのロググループ、CloudFront ディストリビューション（S3 オリジンと `ContactApi` オリジン）、表示用レスポンスヘッダポリシー、表示ルーティング用 CloudFront Function、Route53 A レコード（Alias 先は CloudFront）、ACM 検証 CNAME レコードを定義しています。

Django 実行用 Lambda（`DjangoFunction`）、その API Gateway REST API（`DjangoApi`）、API Gateway カスタムドメイン、REGIONAL の ACM 証明書は退役済みで、`template.yaml` から除去されています（出典: [`docs/development-records/unused-resource-removal-django-retirement.md`](docs/development-records/unused-resource-removal-django-retirement.md)）。

`dependencies.yaml` は、静的ファイル用 S3 バケット、CloudFront Origin Access Control、S3 バケットポリシーを定義しています。

`pipeline.yaml` は、CodeConnections からソースを取得し、依存リソース、アプリケーション、バケットポリシーを CodePipeline と CodeBuild でデプロイする構成を定義しています。

## ドキュメント

詳細は `docs` 配下に分割しています。

- [ドキュメント索引](docs/index.md)
- [アーキテクチャ](docs/architecture.md)
- [アプリケーション構成](docs/application.md)
- [設定とシークレット](docs/configuration.md)
- [開発環境](docs/development.md)
- [Docker ローカル環境](docs/local-docker.md)
- [デプロイと CI/CD](docs/deployment.md)
- [IAM 権限最適化手順](docs/ai-progress/iam-permission-optimization.md)
- [静的ファイル配信](docs/static-assets.md)
- [外部資産とライセンス](docs/external-assets.md)
- [運用確認](docs/operations.md)
- [既知の状態](docs/current-state.md)

## ライセンス

このリポジトリには `LICENSE` として GNU General Public License v3.0 が配置されています。
