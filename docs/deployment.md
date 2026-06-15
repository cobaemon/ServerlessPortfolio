# デプロイと CI/CD

## SAM 設定

`samconfig.toml` の default deploy parameters は次の値を含みます。

- `stack_name = "cobaemon-serverless-portfolio-stack"`
- `region = "ap-northeast-1"`
- `capabilities = "CAPABILITY_NAMED_IAM"`
- `profile = "aws_portfolio_profile"`
- `DomainName="serverless.portfolio.cobaemon.com"`
- `Env="prod"`
- `BranchName="main"`
- `TemplatePath="packaged.yaml"`

## アプリケーションテンプレート

`template.yaml` は `Env` パラメータとして `staging` と `prod` を許容します。既定値は `prod` です。

`DjangoFunction` は Python 3.12 Runtime、`x86_64` Architecture、Timeout 30 秒、MemorySize 512 MB で定義されています。

API Gateway の StageName は `Env` パラメータと同じ値です。

## パイプライン

`pipeline.yaml` は次の CodePipeline ステージを定義します。

- `Source`
- `UpdatePipeline`
- `BuildDependencies`
- `DeployDependencies`
- `Build`
- `Deploy`

`Source` は CodeStarSourceConnection を使い、`FullRepositoryId` と `BranchName` パラメータを参照します。既定値は `cobaemon/ServerlessPortfolio` と `main` です。

CodePipeline は V2 pipeline として定義し、Git push trigger に file path filter を設定します。

`FilePaths.Excludes` は、デプロイ、ビルド、runtime に影響しないことを確認した path だけを除外します。除外対象は次の通りです。

- `docs/**`
- `AGENTS.md`
- `scripts/branch-finalize-next.ps1`
- `README.md`
- `LICENSE`

上記の path だけを含む push は pipeline を起動しません。除外対象外の path が 1 つでも含まれる push は pipeline 起動対象です。未知の root file は除外対象に含めず、pipeline 起動側に倒します。

`Deploy` ステージは `CloudFormationDeploy` と `BucketPolicyDeploy` を実行します。

## CodeBuild

`buildspec.yml` は Python 3.12 を使用します。

主な処理は次の通りです。

- バージョン固定済み `requirements.txt` のインストール。
- `aws-sam-cli==1.160.1` と `csscompressor==0.9.5` のインストール。
- `python manage.py check --fail-level WARNING` による Django settings check。
- Route53 ホストゾーンと既存 A レコードの検出。
- Django 翻訳ファイルの生成とコンパイル。
- Google Fonts から `Montserrat.ttf` と `Lato.ttf` を取得して `portfolio/static/assets/fonts` に配置。
- `portfolio/static/css/styles.css` から `styles.min.css` を生成。
- `python manage.py collectstatic --noinput`。
- `python manage.py render_static`。
- `staticfiles/` を `s3://cobaemon-serverless-portfolio-${ENV}-static/` へ同期。
- `sam build --use-container`。
- `sam package --output-template-file packaged.yaml --s3-bucket $S3Bucket`。
- `parameters.json` と `bucketpolicy-parameters.json` の生成。

`buildspec-deps.yml` は CloudFront OAC と静的ファイルバケットの存在を検出し、`deps-parameters.json` を生成します。

## Staging デプロイ

staging のデプロイ、確認、ロールバック、影響範囲は [`staging-deployment-runbook.md`](staging-deployment-runbook.md) に記載しています。

## デプロイ後のAWS確認

STG と PROD のデプロイ作業は、AWS 側の反映確認を責任範囲に含めます。完了報告には、CodePipeline の source revision と status、CloudFormation の stack status、Lambda の alias/version/readiness を証跡として含めます。

公開エンドポイントがある場合は、HTTP または browser の疎通結果も確認し、未確認項目が残る場合は完了ではなく未確認として報告します。

## S3 artifact bucket の保持

CodePipeline artifact bucket は `pipeline.yaml` の `S3Bucket` parameter と `ArtifactStore.Location` で既存 bucket を参照します。bucket 本体はこの template では作成しないため、CloudFormation import は行いません。

対象 bucket は次の2件です。

- `cobaemon-serverless-portfolio-prod-artifacts`
- `cobaemon-serverless-portfolio-staging-artifacts`

保持ルールの正本は [`aws/s3-lifecycle/artifacts-365-days.json`](../aws/s3-lifecycle/artifacts-365-days.json) とします。365日経過した artifact object を削除対象にし、開始後7日を超えた未完了 multipart upload を中止します。

AWSへ適用する場合は、このJSONをそのまま `put-bucket-lifecycle-configuration` に渡します。適用後は `get-bucket-lifecycle-configuration` の結果が正本JSONと一致することを証跡として残します。

## CloudWatch Logs の保持

現行 CodeBuild log group は `pipeline.yaml` の `AWS::Logs::LogGroup` で管理し、`RetentionInDays: 365` を設定します。

現行 Lambda log group は `template.yaml` の `AWS::Logs::LogGroup` で管理し、`RetentionInDays: 365` を設定します。

既存 log group は CloudFormation import で stack 管理へ取り込みます。`DeletionPolicy` と `UpdateReplacePolicy` は `Delete` とし、template 管理から外れた log group は保持しません。

現行 Lambda、現行 CodeBuild、現行 Synthetics に対応しない log group は管理外 log group として削除対象です。

## IAM 権限最適化

IAM 権限縮小は、初回 staging デプロイを完了してから staging で段階的に検証します。

具体的な手順は [`iam-permission-optimization.md`](iam-permission-optimization.md) に記載しています。

## 手動補助スクリプト

`deploy-deps.ps1` は既存の CloudFront OAC と S3 バケットを検出し、`dependencies.yaml` を `sam deploy` するための PowerShell スクリプトです。既定の `Env` は `prod`、既定の `StackName` は `cobaemon-portfolio-dependencies-prod`、既定の `Profile` は `aws_portfolio_profile` です。

## 関連ファイル

- [`samconfig.toml`](../samconfig.toml)
- [`template.yaml`](../template.yaml)
- [`pipeline.yaml`](../pipeline.yaml)
- [`buildspec.yml`](../buildspec.yml)
- [`buildspec-deps.yml`](../buildspec-deps.yml)
- [`deploy-deps.ps1`](../deploy-deps.ps1)
