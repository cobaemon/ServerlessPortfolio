# ServerlessPortfolio

Django 6.0 系のポートフォリオサイトを AWS Lambda と API Gateway で実行し、静的ファイルを S3 と CloudFront で配信するプロジェクトです。

## 構成

- アプリケーション: Django プロジェクト `config` と Django アプリ `portfolio`
- Lambda エントリーポイント: `asgi_lambda.py`
- 本番 Django 設定: `config/settings/prod.py`
- ローカル開発 Django 設定: `config/settings/dev.py`
- AWS SAM アプリケーション定義: `template.yaml`
- 依存リソース定義: `dependencies.yaml`
- S3 バケットポリシー定義: `bucketpolicy.yaml`
- CI/CD パイプライン定義: `pipeline.yaml`
- CodeBuild 定義: `buildspec.yml`、`buildspec-deps.yml`
- SAM デプロイ設定: `samconfig.toml`

## アプリケーション機能

- `/` から `/portfolio/top/` への恒久リダイレクト
- `/portfolio/top/` のポートフォリオページ表示
- `/portfolio/contact` の問い合わせ POST 処理
- Django i18n による日本語、英語、フランス語、スペイン語、ロシア語、簡体中国語、アラビア語の言語定義
- Django CSP による Content Security Policy 設定
- メール送信設定に基づく問い合わせ内容の送信

## AWS 構成

`template.yaml` は、Lambda、API Gateway、API Gateway カスタムドメイン、ACM 証明書、Route53 A レコード、静的ファイル用 CloudFront ディストリビューションを定義しています。

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
- [IAM 権限最適化手順](docs/iam-permission-optimization.md)
- [静的ファイル配信](docs/static-assets.md)
- [外部資産とライセンス](docs/external-assets.md)
- [運用確認](docs/operations.md)
- [既知の状態](docs/current-state.md)

## ライセンス

このリポジトリには `LICENSE` として GNU General Public License v3.0 が配置されています。
