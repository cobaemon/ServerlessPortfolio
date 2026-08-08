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

`ContactFunction` は `Handler: contact_function.handler.lambda_handler`、`Runtime: python3.12`、`CodeUri: ./` で定義されています。`Globals.Function` により Timeout 30 秒、MemorySize 1024 MB、`x86_64` Architecture が適用されます（出典: `template.yaml` の `Globals` と `ContactFunction`）。

`ReservedConcurrentExecutions` は設定していません。対象アカウントの Lambda 同時実行上限が 10 であり、予約すると未予約同時実行が 10 を下回るため設定できないことが理由です（出典: `template.yaml` の `ContactFunction` 内コメント、`aws lambda get-account-settings`）。

Django 実行用 Lambda（`DjangoFunction`）と API Gateway REST API（`DjangoApi`）、API Gateway カスタムドメイン、REGIONAL の ACM 証明書は退役済みで、`template.yaml` に宣言はありません（出典: [`development-records/unused-resource-removal-django-retirement.md`](development-records/unused-resource-removal-django-retirement.md) 第 1.1・8.2・8.3 節）。

API Gateway（`ContactApi`）の StageName は `Env` パラメータと同じ値です。

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

主な処理は次の通りです（出典: `buildspec.yml`）。

- Control Platform の検証（`--validate-hooks`、`--validate-githooks`、`--self-test`）。
- バージョン固定済み `requirements.txt` のインストール。
- `aws-sam-cli==1.160.1`、`csscompressor==0.9.5`、`pyyaml==6.0.3` のインストール。
- `python manage.py check --fail-level WARNING` による Django settings check。
- `python -m scripts.measurement.non_regression_check` による非退行検証（HTTPS 強制・S3 OAC 経由のみ・7 言語表示配信・Contact_Payload 4 項目限定・CSP 付与を IaC と Django 設定から検証。不適合があれば非ゼロ終了）。
- Route53 ホストゾーンと既存 A レコードの検出。
- Django 翻訳ファイルの生成とコンパイル。
- Google Fonts から `Montserrat.ttf` と `Lato.ttf` を取得して `portfolio/static/assets/fonts` に配置。
- `portfolio/static/css/styles.css` から `styles.min.css` を生成。
- `python manage.py collectstatic --noinput`。
- `python manage.py render_static` による 7 言語分の表示ページ事前レンダリング（いずれかの言語で失敗すると `CommandError` で中断し、S3 同期を行いません）。
- 全言語の生成に成功した場合のみ `staticfiles/` を `s3://cobaemon-serverless-portfolio-${ENV}-static/` へ `--delete` 付きで同期し、続けて対象 CloudFront ディストリビューションへ `create-invalidation --paths "/*"` を実行。
- `sam build --use-container`。
- `sam package --output-template-file packaged.yaml --s3-bucket $S3Bucket`。
- `parameters.json` と `bucketpolicy-parameters.json` の生成。`parameters.json` には `render_static` が生成した統一 CSP（`staticfiles/prerender_manifest.json` の `content_security_policy`）を `ContentSecurityPolicy` として注入し、`CloudFrontCertificateArn` が非空のときは us-east-1 の `acm:DescribeCertificate` から取得した検証 CNAME を `AcmValidationRecordName` / `AcmValidationRecordValue` として注入します（検証レコードが 1 件でない場合はフォールバックせず中断）。

`buildspec-deps.yml` は CloudFront OAC と静的ファイルバケットの存在を検出し、`deps-parameters.json` を生成します。

## Staging デプロイ

staging のデプロイ、確認、ロールバック、影響範囲は [`staging-deployment-runbook.md`](staging-deployment-runbook.md) に記載しています。

## デプロイ後のAWS確認

STG と PROD のデプロイ作業は、AWS 側の反映確認を責任範囲に含めます。完了報告には、CodePipeline の source revision と status、CloudFormation の stack status、Lambda（`ContactFunction`）の関数構成（`aws lambda get-function-configuration`）を証跡として含めます。

`ContactFunction` には `AutoPublishAlias` を設定していないため、エイリアス（`live`）とバージョン発行は存在しません。したがってエイリアス/バージョン/SnapStart readiness は証跡の対象外です（出典: `template.yaml` の `ContactFunction`。`AutoPublishAlias` と `SnapStart` の記述なし。SnapStart 不在は `tests/iac/test_template_policies.py` の `SnapStartAbsenceTests` で検証）。

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

現行 Lambda log group は `template.yaml` の `ContactFunctionLogGroup`（`AWS::Logs::LogGroup`、`LogGroupName: /aws/lambda/${ContactFunction}`）で管理し、`RetentionInDays: 365` を設定します。退役した `DjangoFunctionLogGroup` はスタック更新時に削除されました（出典: [`development-records/unused-resource-removal-django-retirement.md`](development-records/unused-resource-removal-django-retirement.md) 第 8.2 節）。

既存 log group は CloudFormation import で stack 管理へ取り込みます。`DeletionPolicy` と `UpdateReplacePolicy` は `Delete` とし、template 管理から外れた log group は保持しません。

現行 Lambda、現行 CodeBuild、現行 Synthetics に対応しない log group は管理外 log group として削除対象です。

## IAM 権限最適化

IAM 権限縮小は、初回 staging デプロイを完了してから staging で段階的に検証します。

具体的な手順は [`ai-progress/iam-permission-optimization.md`](ai-progress/iam-permission-optimization.md) に記載しています。

## 手動補助スクリプト

`deploy-deps.ps1` は既存の CloudFront OAC と S3 バケットを検出し、`dependencies.yaml` を `sam deploy` するための PowerShell スクリプトです。既定の `Env` は `prod`、既定の `StackName` は `cobaemon-portfolio-dependencies-prod`、既定の `Profile` は `aws_portfolio_profile` です。

## 関連ファイル

- [`samconfig.toml`](../samconfig.toml)
- [`template.yaml`](../template.yaml)
- [`pipeline.yaml`](../pipeline.yaml)
- [`buildspec.yml`](../buildspec.yml)
- [`buildspec-deps.yml`](../buildspec-deps.yml)
- [`deploy-deps.ps1`](../deploy-deps.ps1)
