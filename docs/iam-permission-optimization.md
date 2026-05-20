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

## ブランチと反映制御

権限最適化の実装作業は `vA.B.C` 形式の作業ブランチで行います。

`dev` または `main` で直接 commit、merge、修正、push してはいけません。

`dev` への統合は、ユーザーが明示的に `branch-finalize-next` の実行を指示した場合のみ、[`AGENTS.md`](../AGENTS.md) の `branch-finalize-next` 手順で行います。

`branch-finalize-next` は push しません。staging 検証のために `dev` を push する場合は、`branch-finalize-next` 完了後に次を確認してから、ユーザーの明示許可を得て `git push origin dev` を実行します。

```powershell
git status --short --branch
git rev-parse dev
git rev-parse origin/dev
git log --oneline origin/dev..dev
```

`main` への統合と push は prod 反映です。staging の全フェーズ完了後、別途ユーザーの明示許可と `main` 反映対象差分の確認がある場合のみ実行します。

`sam deploy --template-file pipeline.yaml --config-env staging` は、初回 staging pipeline stack が存在しない場合の初回構築に限ります。既に staging pipeline が存在する場合、権限最適化の検証は `dev` push による staging pipeline 自動実行で行います。

`sam deploy --template-file pipeline.yaml --config-env default` による prod 反映は行いません。

## 作業責任範囲と完了条件

各 Phase の作業は、ローカル commit だけでは完了扱いにしません。

staging pipeline 検証を含む Phase では、次を責任範囲に含めます。

- `vA.B.C` 作業ブランチで変更する。
- ローカル検証を実行する。
- 作業ブランチで commit する。
- ユーザーが明示的に `branch-finalize-next` の実行を指示した場合、`branch-finalize-next` を実行する。
- `branch-finalize-next` 完了後、push 対象差分、対象ブランチ、`origin/dev..dev` の内容を確認する。
- ユーザーが明示的に `dev` push を許可した場合、`git push origin dev` を実行する。
- staging pipeline が push した `dev` commit を source revision として取得していることを確認する。
- staging pipeline の対象ステージが成功したこと、または権限不足の失敗内容を確認する。

完了報告では、commit SHA、`branch-finalize-next` 実行有無、push した commit、pipeline execution id、pipeline source revision、pipeline status を報告します。

`branch-finalize-next`、`dev` push、pipeline 検証が必要な Phase で未実施項目がある場合は、完了ではなく未完了として報告します。

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

Phase 1 の変更は、`vA.B.C` 作業ブランチで commit します。

staging pipeline stack は手動デプロイしません。

ユーザーが明示的に `branch-finalize-next` の実行を指示した場合のみ、作業ブランチを `dev` へ統合します。

`branch-finalize-next` 完了後、staging 検証のために `dev` を push します。

```powershell
git push origin dev
```

staging pipeline が push した `dev` revision を取得していることを確認します。

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

不足 Action だけを追加する場合は、`dev` で直接修正してはいけません。

次の `vA.B.C` 作業ブランチで修正し、再度 `branch-finalize-next` と `git push origin dev` によって staging pipeline を再実行します。

`AdministratorAccess` は戻しません。

Phase 2 の完了条件は、`git push origin dev` によって起動した staging pipeline の source revision が push した `dev` commit と一致し、対象 pipeline 実行状態を確認済みであることです。

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

変更は `vA.B.C` 作業ブランチで commit し、ユーザーが明示的に `branch-finalize-next` の実行を指示した場合のみ `dev` へ統合します。

staging pipeline の再実行は、`dev` push による自動実行で行います。

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

Phase 3 の完了条件は、`branch-finalize-next` による `dev` 統合、明示許可後の `git push origin dev`、push した `dev` commit と staging pipeline source revision の一致、`DeployDependencies`、`Deploy`、`BucketPolicyDeploy` の成功確認です。

ローカル commit のみで Phase 3 を完了扱いにしてはいけません。

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

変更は `vA.B.C` 作業ブランチで commit し、ユーザーが明示的に `branch-finalize-next` の実行を指示した場合のみ `dev` へ統合します。

staging pipeline の再実行は、`dev` push による自動実行で行います。

```powershell
git push origin dev
aws codepipeline get-pipeline-state `
  --name cobaemon-serverless-portfolio-staging-pipeline `
  --region ap-northeast-1 `
  --profile aws_portfolio_profile
```

全ステージ成功を確認します。

Phase 4 の完了条件は、`branch-finalize-next` による `dev` 統合、明示許可後の `git push origin dev`、push した `dev` commit と staging pipeline source revision の一致、全ステージ成功の確認です。

## Phase 5: prod 反映

staging で成功した最小権限を prod に反映します。

`Env=prod` で同じ `pipeline.yaml` を使用するため、prod では `prod-portfolio-*` Role が同じ権限設計になります。

prod 反映は手動デプロイしません。

prod 反映前に、`main` へ統合する差分が IAM Role 権限変更の範囲に限定されていることを確認します。

```powershell
git diff --name-only origin/main..dev
git log --oneline origin/main..dev
```

意図しない変更がないことを確認してから、別途ユーザーの明示許可を得て `main` へ統合し、`main` push による prod pipeline 自動実行で反映します。

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
- 現在ブランチが `dev` または `main` の場合。
- `branch-finalize-next` を使わずに `dev` へ統合しようとしている場合。
- `dev` または `main` に直接 commit しようとしている場合。
- `dev` push 前に `origin/dev..dev` の差分を確認していない場合。
- prod 反映前に `origin/main..dev` の差分を確認していない場合。
- push によって起動した pipeline の source revision が push した commit と一致しない場合。

## 参照

- [`template.yaml`](../template.yaml)
- [`pipeline.yaml`](../pipeline.yaml)
- [`samconfig.toml`](../samconfig.toml)
- [`staging-deployment-runbook.md`](staging-deployment-runbook.md)
