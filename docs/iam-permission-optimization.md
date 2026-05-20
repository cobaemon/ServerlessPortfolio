# IAM 権限最適化手順

この手順は、既存の本番環境へ直接反映せず、staging で権限縮小を検証してから prod へ反映するための手順です。

## 前提

初回 staging デプロイが未完了の場合は、現在のテンプレートで staging pipeline、dependencies、application、bucket policy の各スタックを一度作成し、staging URL の疎通確認を完了してから IAM 権限縮小を開始します。

初回から最小権限化すると、失敗原因が staging 構成不備か IAM 権限不足かを切り分けにくくなります。IAM 権限縮小は staging 用 IAM Role の実体が作成された後に開始します。

対象の staging IAM Role は次の通りです。

| 用途 | Role |
| --- | --- |
| CodePipeline | `staging-portfolio-pipeline-role` |
| CodeBuild | `staging-portfolio-build-role` |
| CloudFormation | `staging-portfolio-cfn-role` |

## Phase 1: 低リスク修正

`template.yaml` から Lambda の `SecretsManagerReadWrite` を削除します。

対象:

- [`template.yaml`](../template.yaml)

`pipeline.yaml` の `CodeBuildServiceRole` から `AdministratorAccess` を削除します。

対象:

- [`pipeline.yaml`](../pipeline.yaml)

`CodeBuildServiceRole` に必要な inline policy を追加します。

| 対象 | 権限範囲 |
| --- | --- |
| Secrets Manager | `${Env}/portfolio/secret-*` |
| Systems Manager Parameter Store | `${Env}/portfolio/parameter/*` |
| static bucket | `cobaemon-serverless-portfolio-${Env}-static` |
| artifact bucket | `S3Bucket` |
| Route53 | read |
| CloudFormation | `DescribeStackResource` |
| CloudFront OAC | list / create |
| CloudWatch Logs | write |

ローカル検証を実行します。

```powershell
$env:AWS_CLI_FILE_ENCODING='UTF-8'
aws cloudformation validate-template --template-body file://pipeline.yaml --region ap-northeast-1 --profile aws_portfolio_profile
aws cloudformation validate-template --template-body file://template.yaml --region ap-northeast-1 --profile aws_portfolio_profile
git diff --check
```

## Phase 2: staging で検証

staging pipeline stack は手動デプロイしません。

Phase 1 の変更を commit し、`dev` へ統合した後、`dev` を push して staging pipeline の自動実行で検証します。

push 前に、`dev` が Phase 1 の変更を含むことを確認します。

```powershell
git rev-parse dev
git log --oneline dev -5
```

`dev` を push します。

```powershell
git push origin dev
```

staging pipeline が push された `dev` revision を取得していることを確認します。

```powershell
aws codepipeline list-pipeline-executions `
  --pipeline-name cobaemon-serverless-portfolio-staging-pipeline `
  --max-results 1 `
  --region ap-northeast-1 `
  --profile aws_portfolio_profile `
  --query "pipelineExecutionSummaries[0].{id:pipelineExecutionId,status:status,revision:sourceRevisions[0].revisionId}"
```

staging pipeline 実行状態を確認します。

```powershell
aws codepipeline get-pipeline-state `
  --name cobaemon-serverless-portfolio-staging-pipeline `
  --region ap-northeast-1 `
  --profile aws_portfolio_profile
```

CodeBuild が権限不足で失敗した場合は、CodeBuild ログで不足 Action を確認します。

```powershell
aws logs describe-log-streams `
  --log-group-name /aws/codebuild/cobaemon-serverless-portfolio-staging-pipeline-Build `
  --order-by LastEventTime `
  --descending `
  --region ap-northeast-1 `
  --profile aws_portfolio_profile
```

不足 Action だけを追加し、再度 commit、`dev` への統合、`git push origin dev` によって staging pipeline を再実行します。

`AdministratorAccess` は戻しません。

## Phase 3: CloudFormation Role 縮小

`staging-portfolio-cfn-role` から `AdministratorAccess` を外します。

CloudFormation がこのプロジェクトで作成または更新するサービスに限定します。

- IAM
- Lambda
- API Gateway
- ACM
- Route53
- CloudFront
- S3
- CodePipeline
- CodeBuild
- Logs
- CloudFormation
- Secrets Manager
- Systems Manager Parameter Store

変更を commit し、`dev` へ統合した後、`dev` を push して staging pipeline の自動実行で検証します。

```powershell
git push origin dev
aws codepipeline list-pipeline-executions `
  --pipeline-name cobaemon-serverless-portfolio-staging-pipeline `
  --max-results 1 `
  --region ap-northeast-1 `
  --profile aws_portfolio_profile `
  --query "pipelineExecutionSummaries[0].{id:pipelineExecutionId,status:status,revision:sourceRevisions[0].revisionId}"
```

次の処理が成功するまで不足 Action だけを追加します。

- `DeployDependencies`
- `Deploy`
- `BucketPolicyDeploy`

## Phase 4: CodePipeline Role 縮小

`staging-portfolio-pipeline-role` から `AdministratorAccess` を外します。

必要権限に限定します。

| 対象 | 権限範囲 |
| --- | --- |
| CodeConnections | connection 使用 |
| CodeBuild | start / batch get |
| CloudFormation | stack / change set 操作 |
| artifact bucket | read / write |
| IAM | `iam:PassRole` を `staging-portfolio-cfn-role` のみに限定 |

変更を commit し、`dev` へ統合した後、`dev` を push して staging pipeline の自動実行で検証します。

```powershell
git push origin dev
aws codepipeline get-pipeline-state `
  --name cobaemon-serverless-portfolio-staging-pipeline `
  --region ap-northeast-1 `
  --profile aws_portfolio_profile
```

全ステージ成功を確認します。

## Phase 5: prod 反映

staging で成功した最小権限を prod に反映します。

`Env=prod` で同じ `pipeline.yaml` を使用するため、prod では `prod-portfolio-*` Role が同じ権限設計になります。

prod 反映は手動デプロイしません。

prod 反映前に、`main` へ統合する差分が IAM Role 権限変更の範囲に限定されていることを確認します。

```powershell
git diff --name-only origin/main..dev
git log --oneline origin/main..dev
```

意図しない変更がないことを確認してから、`main` へ統合し、`main` を push して prod pipeline の自動実行で反映します。

```powershell
git push origin main
aws codepipeline list-pipeline-executions `
  --pipeline-name cobaemon-serverless-portfolio-pipeline `
  --max-results 1 `
  --region ap-northeast-1 `
  --profile aws_portfolio_profile `
  --query "pipelineExecutionSummaries[0].{id:pipelineExecutionId,status:status,revision:sourceRevisions[0].revisionId}"
```

prod pipeline の全ステージ成功を確認します。

## Phase 6: ユーザーと未使用 Policy 整理

`cobaemon_portfolio` の active access key 2 件の用途を確認します。

```powershell
aws iam list-access-keys --user-name cobaemon_portfolio --profile aws_portfolio_profile
```

使っていない key は無効化します。削除は無効化後に影響確認してから行います。

AttachmentCount 0 の Policy は用途確認後に削除します。

- `cobaemon_portfolio_update_route53_record`
- `CodeBuildBasePolicy-codebuild-cobaemon-serverless-portfolio-project-role-ap-northeast-1`

## 停止条件

次のいずれかに該当する場合は作業を停止します。

- staging pipeline が権限不足以外で失敗した場合。
- CloudFormation が本番 stack 名を更新対象に含む場合。
- 変更セットに prod ドメイン、prod secret、prod SSM、prod pipeline 以外の意図しない変更がある場合。
- 不足権限の原因がログで確認できない場合。

## 参照

- [`template.yaml`](../template.yaml)
- [`pipeline.yaml`](../pipeline.yaml)
- [`samconfig.toml`](../samconfig.toml)
- [`staging-deployment-runbook.md`](staging-deployment-runbook.md)
