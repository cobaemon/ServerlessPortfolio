# ドキュメント索引

このディレクトリは ServerlessPortfolio の詳細ドキュメントを管理します。

## 文書一覧

- [アーキテクチャ](architecture.md): Django、Lambda、API Gateway、Route53、ACM、S3、CloudFront の構成。
- [アプリケーション構成](application.md): Django アプリ、URL、ビュー、フォーム、言語設定。
- [設定とシークレット](configuration.md): Django 設定、環境変数、Secrets Manager、Parameter Store。
- [開発環境](development.md): ローカル実行、依存関係、テスト、静的ファイル生成。
- [デプロイと CI/CD](deployment.md): SAM、CodePipeline、CodeBuild、CloudFormation の流れ。
- [静的ファイル配信](static-assets.md): collectstatic、S3 同期、CloudFront、Manifest Storage。
- [運用確認](operations.md): 非破壊の疎通確認、ログ確認、既存の AWS CLI 設定。
- [既知の状態](current-state.md): 現在の実装状態と未実装の要件文書。

## 関連ファイル

- [`README.md`](../README.md)
- [`template.yaml`](../template.yaml)
- [`dependencies.yaml`](../dependencies.yaml)
- [`pipeline.yaml`](../pipeline.yaml)
- [`buildspec.yml`](../buildspec.yml)
- [`buildspec-deps.yml`](../buildspec-deps.yml)
- [`config/settings/base.py`](../config/settings/base.py)
- [`config/settings/dev.py`](../config/settings/dev.py)
- [`config/settings/prod.py`](../config/settings/prod.py)
