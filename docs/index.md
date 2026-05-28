# ドキュメント索引

このディレクトリは ServerlessPortfolio の詳細ドキュメントを管理します。

## 配置ルール

`docs/` 直下には、プロジェクト仕様、設計、設定、運用、デプロイ、開発環境など、継続的に参照するプロジェクトドキュメントを配置します。

AI 作業進捗、作業途中の AI 用 TODO、AI が使用する確認記録は `docs/ai-progress/` に配置します。

作業中に発生した指示違反、手順逸脱、影響発生、復旧対応の記録は `docs/incidents/` に配置します。

開発過程で発生または使用する調査、方針、対応案、検討記録は `docs/development-records/` に配置します。

`docs/` 直下へ新しい文書を追加する場合は、恒久的なプロジェクトドキュメントであることを確認し、この索引へ追加します。

## 文書一覧

- [アーキテクチャ](architecture.md): Django、Lambda、API Gateway、Route53、ACM、S3、CloudFront の構成。
- [アプリケーション構成](application.md): Django アプリ、URL、ビュー、フォーム、言語設定。
- [設定とシークレット](configuration.md): Django 設定、環境変数、Secrets Manager、Parameter Store。
- [開発環境](development.md): ローカル実行、依存関係、テスト、AGENTS Hook、静的ファイル生成。
- [Docker ローカル環境](local-docker.md): Docker Compose によるローカル検証、起動、動作確認。
- [デプロイと CI/CD](deployment.md): SAM、CodePipeline、CodeBuild、CloudFormation の流れ。
- [AI 作業進捗](ai-progress/README.md): AI 作業進捗、作業途中の TODO、AI が使用する確認記録。
- [開発記録](development-records/README.md): 開発過程で発生・使用する調査、方針、対応案の記録。
- [Staging デプロイ Runbook](staging-deployment-runbook.md): staging デプロイ、確認、ロールバック、影響範囲。
- [IAM 権限最適化手順](iam-permission-optimization.md): staging で IAM 権限縮小を検証してから prod へ反映する手順。
- [インシデント記録](incidents/README.md): 作業中に発生した指示違反、手順逸脱、影響発生、復旧対応の記録。
- [静的ファイル配信](static-assets.md): collectstatic、S3 同期、CloudFront、Manifest Storage。
- [外部資産とライセンス](external-assets.md): Docker image、Python dependencies、build tools、Google Fonts の取得元とライセンス。
- [運用確認](operations.md): 非破壊の疎通確認、ログ確認、既存の AWS CLI 設定。
- [Staging 実値方針](staging-values-policy.md): staging 用ドメイン、Secrets Manager、Parameter Store の投入方針。
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
