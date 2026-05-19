# Staging デプロイ Runbook

## 目的

このRunbookは、`staging` 環境の初回デプロイ、確認、不測の事態のロールバック、影響範囲を定義します。

## 対象

対象環境は `Env=staging` です。

| 項目 | 値 |
| --- | --- |
| staging ドメイン | `staging.serverless.portfolio.cobaemon.com` |
| pipeline stack | `cobaemon-serverless-portfolio-staging-pipeline` |
| application stack | `cobaemon-serverless-portfolio-staging-stack` |
| dependencies stack | `cobaemon-portfolio-dependencies-staging` |
| bucket policy stack | `cobaemon-serverless-portfolio-bucketpolicy-staging` |
| artifact bucket | `cobaemon-serverless-portfolio-staging-artifacts` |
| static bucket | `cobaemon-serverless-portfolio-staging-static` |
| pipeline name | `cobaemon-serverless-portfolio-staging-pipeline` |
| source branch | `dev` |
| AWS region | `ap-northeast-1` |
| AWS profile | `aws_portfolio_profile` |

## 参照

- [`staging-values-policy.md`](staging-values-policy.md)
- [`samconfig.toml`](../samconfig.toml)
- [`pipeline.yaml`](../pipeline.yaml)
- [`buildspec.yml`](../buildspec.yml)
- [`buildspec-deps.yml`](../buildspec-deps.yml)
- [`dependencies.yaml`](../dependencies.yaml)
- [`template.yaml`](../template.yaml)
- [`bucketpolicy.yaml`](../bucketpolicy.yaml)
- [`config/settings/staging.py`](../config/settings/staging.py)

## 事前確認

AWSアカウントを確認する。

```powershell
aws sts get-caller-identity --profile aws_portfolio_profile
```

staging 用 Secret が存在し、削除予定でないことを確認する。

```powershell
aws secretsmanager describe-secret `
  --secret-id staging/portfolio/secret `
  --region ap-northeast-1 `
  --profile aws_portfolio_profile
```

staging 用 Parameter Store が9件存在することを確認する。

```powershell
aws ssm describe-parameters `
  --parameter-filters Key=Name,Option=BeginsWith,Values=/staging/portfolio/parameter/ `
  --region ap-northeast-1 `
  --profile aws_portfolio_profile `
  --query "length(Parameters[])"
```

staging 用 artifact bucket が存在することを確認する。

```powershell
aws s3api head-bucket `
  --bucket cobaemon-serverless-portfolio-staging-artifacts `
  --profile aws_portfolio_profile
```

Route53 hosted zone が存在することを確認する。

```powershell
aws route53 list-hosted-zones-by-name `
  --dns-name cobaemon.com `
  --profile aws_portfolio_profile
```

テンプレート構文を確認する。

```powershell
$env:AWS_CLI_FILE_ENCODING='UTF-8'
aws cloudformation validate-template --template-body file://pipeline.yaml --region ap-northeast-1 --profile aws_portfolio_profile
aws cloudformation validate-template --template-body file://dependencies.yaml --region ap-northeast-1 --profile aws_portfolio_profile
aws cloudformation validate-template --template-body file://template.yaml --region ap-northeast-1 --profile aws_portfolio_profile
aws cloudformation validate-template --template-body file://bucketpolicy.yaml --region ap-northeast-1 --profile aws_portfolio_profile
```

Git worktree に意図しない差分がないことを確認する。

```powershell
git status --short --branch
git diff --check
```

## 初回デプロイ手順

staging pipeline stack を作成または更新する。

```powershell
sam deploy --template-file pipeline.yaml --config-env staging
```

pipeline の作成状態を確認する。

```powershell
aws cloudformation describe-stacks `
  --stack-name cobaemon-serverless-portfolio-staging-pipeline `
  --region ap-northeast-1 `
  --profile aws_portfolio_profile `
  --query "Stacks[0].StackStatus"
```

pipeline 実行状態を確認する。

```powershell
aws codepipeline get-pipeline-state `
  --name cobaemon-serverless-portfolio-staging-pipeline `
  --region ap-northeast-1 `
  --profile aws_portfolio_profile
```

pipeline が実行する順序は次の通りです。

1. `Source`
2. `UpdatePipeline`
3. `BuildDependencies`
4. `DeployDependencies`
5. `Build`
6. `Deploy`

## デプロイ後確認

staging 関連スタックの状態を確認する。

```powershell
aws cloudformation describe-stacks `
  --region ap-northeast-1 `
  --profile aws_portfolio_profile `
  --query "Stacks[?contains(StackName, 'staging')].{StackName:StackName,Status:StackStatus}"
```

staging pipeline の最終状態を確認する。

```powershell
aws codepipeline get-pipeline-state `
  --name cobaemon-serverless-portfolio-staging-pipeline `
  --region ap-northeast-1 `
  --profile aws_portfolio_profile
```

API Gateway custom domain を確認する。

```powershell
aws apigateway get-domain-name `
  --domain-name staging.serverless.portfolio.cobaemon.com `
  --region ap-northeast-1 `
  --profile aws_portfolio_profile
```

Route53 A レコードを確認する。

```powershell
aws route53 list-resource-record-sets `
  --hosted-zone-id Z00462201BTRUWFZ0YO7V `
  --query "ResourceRecordSets[?Name=='staging.serverless.portfolio.cobaemon.com.']" `
  --profile aws_portfolio_profile
```

ACM 証明書を確認する。

```powershell
aws acm list-certificates `
  --region ap-northeast-1 `
  --profile aws_portfolio_profile `
  --query "CertificateSummaryList[?DomainName=='staging.serverless.portfolio.cobaemon.com']"
```

HTTP疎通を確認する。

```powershell
curl.exe -iL --max-time 30 https://staging.serverless.portfolio.cobaemon.com/
curl.exe -i --max-time 20 https://staging.serverless.portfolio.cobaemon.com/portfolio/top/
```

## ロールバック方針

prod 環境の stack、pipeline、Route53 レコード、Secret、Parameter Store は変更しない。

staging pipeline が失敗した場合は、まず失敗箇所を確認する。

```powershell
aws codepipeline get-pipeline-state `
  --name cobaemon-serverless-portfolio-staging-pipeline `
  --region ap-northeast-1 `
  --profile aws_portfolio_profile
```

CloudFormation stack event を確認する。

```powershell
aws cloudformation describe-stack-events `
  --stack-name cobaemon-serverless-portfolio-staging-stack `
  --region ap-northeast-1 `
  --profile aws_portfolio_profile
```

CodeBuild ロググループを確認する。

```powershell
aws logs describe-log-streams `
  --log-group-name /aws/codebuild/cobaemon-serverless-portfolio-staging-pipeline-Build `
  --order-by LastEventTime `
  --descending `
  --region ap-northeast-1 `
  --profile aws_portfolio_profile
```

直前の正常な `dev` コミットへ戻す場合は、`dev` に修正コミットまたは revert コミットを作成して pipeline を再実行する。履歴を書き換える `reset --hard`、force push、`--no-verify` は使用しない。

staging 環境を撤去する場合は、明示承認後に staging stack だけを逆順で削除する。

```powershell
aws cloudformation delete-stack --stack-name cobaemon-serverless-portfolio-bucketpolicy-staging --region ap-northeast-1 --profile aws_portfolio_profile
aws cloudformation delete-stack --stack-name cobaemon-serverless-portfolio-staging-stack --region ap-northeast-1 --profile aws_portfolio_profile
aws cloudformation delete-stack --stack-name cobaemon-portfolio-dependencies-staging --region ap-northeast-1 --profile aws_portfolio_profile
aws cloudformation delete-stack --stack-name cobaemon-serverless-portfolio-staging-pipeline --region ap-northeast-1 --profile aws_portfolio_profile
```

artifact bucket、Secret、Parameter Store は手動管理項目のため、stack削除では削除されない。

## 影響範囲

staging デプロイで作成または更新される対象は `staging` 名を含むAWSリソースです。

| 種別 | 対象 |
| --- | --- |
| CodePipeline | `cobaemon-serverless-portfolio-staging-pipeline` |
| CodeBuild | `cobaemon-serverless-portfolio-staging-pipeline-Build`, `cobaemon-serverless-portfolio-staging-pipeline-Deps` |
| CloudFormation | `cobaemon-serverless-portfolio-staging-pipeline`, `cobaemon-portfolio-dependencies-staging`, `cobaemon-serverless-portfolio-staging-stack`, `cobaemon-serverless-portfolio-bucketpolicy-staging` |
| IAM Role | `staging-portfolio-pipeline-role`, `staging-portfolio-build-role`, `staging-portfolio-cfn-role` |
| S3 | `cobaemon-serverless-portfolio-staging-artifacts`, `cobaemon-serverless-portfolio-staging-static` |
| CloudFront | `cobaemon-serverless-portfolio-staging-static` を origin とする distribution |
| API Gateway | `staging.serverless.portfolio.cobaemon.com` の custom domain と `staging` stage |
| ACM | `staging.serverless.portfolio.cobaemon.com` の証明書 |
| Route53 | `staging.serverless.portfolio.cobaemon.com` の A レコード、ACM DNS validation レコード |
| Secrets Manager | `staging/portfolio/secret` の参照 |
| Parameter Store | `/staging/portfolio/parameter/*` の参照 |

prod 用の `serverless.portfolio.cobaemon.com`、`prod/portfolio/secret`、`/prod/portfolio/parameter/*`、`cobaemon-serverless-portfolio-pipeline` は staging 設定では参照しない。

## 停止条件

次の場合はデプロイを続行しない。

- `aws sts get-caller-identity` のアカウントが想定と異なる。
- `staging/portfolio/secret` が存在しない、または削除予定である。
- `/staging/portfolio/parameter/` 配下が9件ではない。
- `cobaemon-serverless-portfolio-staging-artifacts` が存在しない。
- CloudFormation template validation が失敗する。
- Git worktree に意図しない差分がある。
- pipeline stack が `ROLLBACK_COMPLETE` または `UPDATE_ROLLBACK_FAILED` になる。
