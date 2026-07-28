# 不要リソースの削除記録（Django 表示経路の退役: テンプレート変更とスタック更新手順）

本記録は spec `cost-performance-optimization` のタスク 11「不要リソースの削除」の成果物である。
対象は `template.yaml` からの退役リソース宣言の除去、その局所検証、および人手承認を前提とするスタック更新手順の定義である。
削除対象および扱いの決定は、タスク 10 の記録 `docs/development-records/unused-resource-scan-django-retirement.md`（以下「スキャン記録」）に従う。

- 実施日時: 2026-07-28（テンプレート変更、コミット `d7cd60f`、staging・prod のスタック更新）
- 基準 revision: `8580e717557c242b9f9b68767a2f5a121d61a772`（変更前。出典: `git rev-parse HEAD`）
- 反映 revision: `d7cd60fb24200bc7b50953532a00830da4ce44ed`（`dev` および `main`。出典: `git log --oneline -1`）
- 変更ファイル: `template.yaml`, `buildspec.yml`, `pipeline.yaml`, `tests/iac/test_template_policies.py`（出典: `git status --porcelain` の ` M` 4 件）
- AWS への変更操作（スタック更新によるリソース削除）は 2026-07-28 のユーザー指示（タスク 11 の実行命令）を人手承認として実施した。結果は第 8 節に記録する

## 1. `template.yaml` の変更内容（除去・改修・追加）

除去前の行番号は `git show HEAD:template.yaml`（revision `8580e71`）で確認した値、現位置は作業ツリーの値（出典: `Select-String -Path template.yaml`）である。
なおスキャン記録「確認結果 5」が記す行番号（例: `DjangoFunction` = 121-190 行）は、同一 revision の committed ファイル上の位置（`DjangoFunction` = 88 行）と一致しない。本記録では `git show` で再確認した値を用いる。

### 1.1 除去した宣言（スキャン記録「削除対象の確定」「扱いの決定」に対応）

| 除去した論理 ID / 要素 | 除去前の位置（`8580e71`） | 根拠 |
| --- | --- | --- |
| `DjangoFunction`（表示経路イベント `PostEndpoint` / `ProxyGet` / `ProxyPost` / `ProxyOptions` を含む） | 88 行〜 | スキャン記録「削除対象の確定」 |
| `DjangoFunctionLogGroup` | 159 行〜 | 同上 |
| `DjangoApi` | 167 行〜 | 同上 |
| `ServerlessCertificate`（REGIONAL 証明書） | 285 行〜 | スキャン記録「扱いの決定」2 |
| `ApiGatewayCustomDomain` | 294 行〜 | 同上 |
| `ApiGatewayBasePathMapping` | 303 行〜 | 同上 |
| `Outputs.ApiUrl`（`Value: !Ref DjangoApi`） | 655 行〜 | スキャン記録「削除対象の確定」 |
| `Parameters.AllowedOrigin` / `Parameters.AllowedHosts` | 20 行 / 24 行 | 参照元が `DjangoFunction` の環境変数と `DjangoApi.Cors` のみであり、除去後は未参照となるため（出典: `git show HEAD:template.yaml`） |
| `Conditions.IsProd` / `Mappings.EnvMapping` | 75 行 / 80-87 行 | `EnvMapping` の参照元は `DjangoFunction.Environment.DJANGO_SETTINGS_MODULE` のみ、`IsProd` の参照元はコメントアウト済み `WAFWebACLAssociation` のみであったため |

### 1.2 改修した宣言

| 論理 ID | 現位置 | 内容 |
| --- | --- | --- |
| `ApiGatewayRecordSet` | 291 行〜（除去前 317 行〜） | `AliasTarget` の `!If HasCloudFrontCertificate` 分岐（偽側が `ApiGatewayCustomDomain` を参照）を除去し CloudFront 固定へ改修。作成条件を `CreateCloudFrontARecord`（`CreateARecord` かつ `HasCloudFrontCertificate`）へ変更。論理 ID は維持し、同名 A レコードの削除・再作成による切断を避ける（スキャン記録「扱いの決定」3） |
| コメントアウト済み `WAFWebACLAssociation` | 425 行〜 | 参照先を `DjangoApiStage` / `DjangoApi` から `ContactApiStage` / `ContactApi` へ改め、除去済みリソースへの記述参照を残さない |
| `ContactFunctionLogGroup` 前後のコメント | 253 行〜 | `DjangoFunction` を現存前提とする記述を「退役済み」の事実に合わせて修正 |

### 1.3 追加した宣言（スキャン記録「扱いの決定」1 に対応）

| 論理 ID / 要素 | 現位置 | 内容 |
| --- | --- | --- |
| `Parameters.AcmValidationRecordName` / `AcmValidationRecordValue` | 111-118 行 | us-east-1（CloudFront 用）ACM 証明書の DNS 検証 CNAME の名前・値。既定は空文字（未指定時はレコードを宣言しない）。値はハードコードせずビルドが供給する |
| `Conditions.HasAcmValidationRecord` | 140-143 行 | 上記 2 パラメータが双方非空のときのみ真 |
| `Conditions.CreateCloudFrontARecord` | 134-137 行 | `CreateARecord` かつ `HasCloudFrontCertificate` |
| `AcmValidationRecordSet`（`AWS::Route53::RecordSet`, CNAME, TTL 300） | 272-282 行 | 旧 `ServerlessCertificate` の DNS 検証として CloudFormation が作成していた検証 CNAME を、本スタックの独立リソースとして引き継ぐ。ACM は DNS 検証証明書の自動更新に当該 CNAME の存置を要件とする（出典: スキャン記録「追加調査 3」、AWS 公式 [Renewal for domains validated by DNS](https://docs.aws.amazon.com/acm/latest/userguide/dns-renewal-validation.html)。内容はライセンス配慮のため要約している） |

### 1.4 非破壊（削除していないリソース）

`ContactApi` / `ContactFunction` / `ContactFunctionLogGroup` / `CloudFrontDistribution` / `DisplayResponseHeadersPolicy` / `DisplayRouterFunction` / `ApiGatewayRecordSet`（論理 ID 維持）および S3・OAC 関連（`dependencies.yaml` 管理、未変更）は存置している。
出典: `template.yaml` 144-696 行の `Resources` セクション、`tests/iac/test_template_policies.py::RetiredDisplayPathAbsenceTests::test_preserved_resources_present` の合格。

## 2. `buildspec.yml` / `pipeline.yaml` の付随変更

| ファイル | 位置 | 内容 |
| --- | --- | --- |
| `buildspec.yml` | 316-363 行 | `parameters.json` 生成段で、`CloudFrontCertificateArn`（Parameter Store 由来）が非空のとき us-east-1 の `acm:DescribeCertificate` から `DomainValidationOptions[].ResourceRecord` を取得し `AcmValidationRecordName` / `AcmValidationRecordValue` を注入する。検証レコードが 1 件でない場合はフォールバックせず `SystemExit` で中断する。除去済みパラメータ `AllowedOrigin` / `AllowedHosts` の注入を停止 |
| `pipeline.yaml` | 462-470 行 | CodeBuild サービスロールに `acm:DescribeCertificate`（`arn:aws:acm:us-east-1:${AWS::AccountId}:certificate/*` に限定、参照専用）を追加。上記取得に必要 |
| `pipeline.yaml` | 574-577 行 | CloudFormation サービスロールに `lambda:DeleteAlias` を追加。退役対象 `DjangoFunctionAliaslive` の削除に必要 |

スタック更新時の削除に必要な他の権限は既に付与済みである（出典: `pipeline.yaml` `CloudFormationServiceRole`）:
`iam:DeleteRole` 533 行（`Sid: ManagePortfolioIamRoles` 529 行〜）、`lambda:DeleteFunction` 573 行 / `lambda:RemovePermission` 588 行（`Sid: ManagePortfolioLambda` 567 行〜）、`apigateway:DELETE` 599 行（`Sid: ManagePortfolioApiGateway` 596 行〜）、`acm:DeleteCertificate` 616 行（`Sid: ManagePortfolioCertificate` 612 行〜）、`route53:ChangeResourceRecordSets` 639 行（`Sid: ManagePortfolioHostedZoneRecords` 636 行〜）、`logs:DeleteLogGroup` 767 行（`Sid: ManagePortfolioLogs` 763 行〜。対象に `/aws/lambda/*portfolio*` を含む）。

## 3. テスト・ローカル検証の結果（実行済み）

| 検証 | コマンド | 結果 |
| --- | --- | --- |
| SAM テンプレート妥当性・lint | `sam validate --template-file template.yaml --region ap-northeast-1 --profile aws_portfolio_profile --lint` | `template.yaml is a valid SAM Template` |
| IaC ポリシー/スナップショットテスト | `python -m unittest tests.iac.test_template_policies -v` | `Ran 24 tests` / `OK` |
| 全テスト（tests 配下） | `python -m unittest discover -s tests -t .` | `Ran 76 tests` / `OK`（追加テスト 5 件を含む） |
| Control Platform self-test（CLI） | `python -m scripts.control_platform.cli --self-test` | 全ケース `"ok": true`（`"ok": false` の出力なし） |
| Control Platform self-test（tests） | `python tests/self_test.py` | 全 10 ケース `PASS` |

### 3.1 追加したテスト（`tests/iac/test_template_policies.py`）

`RetiredDisplayPathAbsenceTests`（901 行〜）を追加し、以下 5 件を検証する。

1. `test_retired_display_path_resources_absent`: `DjangoFunction` / `DjangoFunctionLogGroup` / `DjangoApi` / `ApiGatewayCustomDomain` / `ApiGatewayBasePathMapping` / `ServerlessCertificate` がテンプレートに存在しない。
2. `test_api_url_output_absent`: `Outputs.ApiUrl` が存在しない。
3. `test_preserved_resources_present`: `ContactApi` / `ContactFunction` / `CloudFrontDistribution` / `DisplayResponseHeadersPolicy` が存置されている（非破壊）。
4. `test_no_unresolved_references`: `Ref` / `Fn::GetAtt` / `Fn::Sub` の参照名がすべて Parameters・Resources・擬似パラメータに解決する（未解決参照の不在）。
5. `test_condition_references_resolve`: `Fn::If` / `Fn::Condition` / リソースの `Condition` がすべて `Conditions` に解決する。

既存 `SnapStartAbsenceTests` から `_DJANGO_FUNCTION_ID` 前提のアサーションを除去した（`DjangoFunction` 退役に伴う修正。スキャン記録「未確認事項 5」の解消）。

### 3.2 リポジトリ内の残存参照（機能依存ではないラベル・出典表記）

`scripts/measurement/cost_attribution.py`（費目ラベル `Lambda(DjangoFunction/Contact_Function)` 等、151・161・171 行付近）と `scripts/measurement/cold_start_protocol.py`（Baseline の出典表記、389 行）に名称参照が残る。
これらは過去の Baseline 実測の出典・費目ラベルであり、テンプレートへの参照ではない（出典: `grep`）。ドキュメント側の整合はタスク 12 の対象である。

## 4. スタック更新手順（人手承認を前提とする運用手順）

スキャン記録「扱いの決定」および同節「追加の決定」（決定主体: ユーザー。決定日時: 2026-07-28）に従い、**検証 CNAME の宣言（1.3）と退役リソースの除去（1.1）・改修（1.2）を同一のスタック更新（単一の更新）に含めて同時に実施**し、実施順は **staging → prod** とする。
CLI による個別削除は行わない（スタックのドリフトを生み、次回デプロイで再作成されるため。出典: スキャン記録「削除対象の確定」）。

デプロイ経路は CodePipeline（ソースブランチ: `dev` = staging / `main` = prod。出典: `pipeline.yaml` `Parameters.BranchName` 24-27 行、`samconfig.toml`）であり、スタック更新は CloudFormation デプロイアクションが実行する。したがって staging への反映は `dev` ブランチへのコミット・プッシュにより行う。

含める変更（単一の更新）: 本記録 1.1 の除去、1.2 の改修、1.3 の追加、`buildspec.yml` のパラメータ注入（2 節）、`pipeline.yaml` の `acm:DescribeCertificate` および `lambda:DeleteAlias` 追加（2 節）。

確認項目（各環境で実施）:

1. パイプライン実行の結果（`aws codepipeline get-pipeline-state --name <pipeline>`）。
2. スタック更新が `UPDATE_COMPLETE` で終了すること（`aws cloudformation describe-stacks --stack-name <stack> --query "Stacks[0].StackStatus"`）。
3. 退役リソースの不在: `aws cloudformation describe-stack-resources`（`DjangoFunction` / `DjangoFunctionAliaslive` / `DjangoFunctionVersion*` / `DjangoFunctionRole` / `DjangoFunctionLogGroup` / `DjangoFunction*PermissionStage` / `DjangoApi` / `DjangoApiStage` / `DjangoApiDeployment*` / `ApiGatewayCustomDomain` / `ApiGatewayBasePathMapping` / `ServerlessCertificate` が現れないこと）、`aws lambda list-functions`、`aws apigateway get-rest-apis`、`aws apigateway get-domain-names`、`aws acm list-certificates --region ap-northeast-1`。
4. `AcmValidationRecordSet` がスタックリソースに存在し、検証 CNAME が Route53 に存置されていること（`aws cloudformation describe-stack-resources`、`aws route53 list-resource-record-sets --hosted-zone-id Z00462201BTRUWFZ0YO7V`）。
5. us-east-1 証明書が `ISSUED` かつ `RenewalEligibility: ELIGIBLE` であること（`aws acm describe-certificate --region us-east-1`）。
6. 公開エンドポイントの疎通: `https://serverless.portfolio.cobaemon.com/portfolio/top/` の表示（GET）と `https://serverless.portfolio.cobaemon.com/portfolio/contact` への POST 応答（staging は `staging.serverless.portfolio.cobaemon.com`）。
7. `scripts/measurement/non_regression_check.py` による非退行検証（HTTPS 強制・OAC 経由のみ・7 言語表示ページ配信・CSP 付与）。

本更新の実施は破壊的操作であり人手承認を前提とする。リソース削除を伴い、`DjangoFunctionLogGroup` は `DeletionPolicy: Delete` のためログが失われる（prod 375,901 バイト / staging 120,543 バイト。出典: スキャン記録「確認結果 3」）。
スタック更新が失敗した場合はフォールバック（別手段への切替・回避実装・再試行）を行わず、ロールバック状況とスタックイベント（`aws cloudformation describe-stack-events`）を根拠に報告して停止する。

## 5. 検証済み事項

1. `template.yaml` から退役対象の宣言が除去されている（テスト 1・2、`sam validate --lint` 合格）。
2. 未解決参照が残っていない（テスト 4・5、`sam validate --lint` 合格）。
3. 非破壊対象が存置されている（テスト 3）。
4. 既存の IaC ポリシー（SnapStart 不在・SES 最小権限・OAC 限定・CSP/HTTPS 強制・スロットリング・WAF 不在）が退役後も満たされている（`tests.iac.test_template_policies` 24 件合格）。
5. `buildspec.yml` の検証段構成が保たれている（`tests.iac.test_buildspec` を含む全 76 件合格）。
6. スタック更新に必要な削除系 IAM 権限が CloudFormation サービスロールに揃っている（第 2 節の該当行）。
7. staging・prod 両環境でスタック更新が `UPDATE_COMPLETE` で完了し、ロールバック・失敗イベントがない（第 8.2 節）。
8. 退役対象リソースが両環境の AWS 実体から不在である（Lambda・API Gateway REST API・カスタムドメイン・REGIONAL 証明書・スタックリソース一覧。第 8.3 節）。
9. ACM の DNS 検証 CNAME が両環境で存置され、us-east-1 証明書が `ISSUED` / `RenewalEligibility=ELIGIBLE` である（第 8.4 節）。
10. 公開エンドポイントが両環境で疎通している（`/portfolio/top/` GET = 200、`/portfolio/contact` POST = 200）。非退行検証は両環境 11 チェックすべて `COMPLIANT`（第 8.5 節）。

## 6. 未確認事項（`undetermined`。完了扱いにしない）

A〜E は実施・実測により解消した（第 5 節 7〜10、第 8 節）。以下は解消済み項目の到達点と、残る `undetermined` を区別して記す。

解消済み:

- A. スタック更新（staging・prod。各環境で単一の更新。出典: ユーザー指示 2026-07-28）: 両環境 `UPDATE_COMPLETE`（第 8.2 節）。
- B. 削除後の対象リソース不在: 実測済み（第 8.3 節）。
- C. 公開エンドポイントの削除後疎通: GET 200 / POST 200、非退行 11 チェック `COMPLIANT`（第 8.5 節）。
- D. 既存検証 CNAME との競合: 両環境で `AcmValidationRecordSet` が `CREATE_COMPLETE` となり、検証 CNAME は TTL 300 のまま存置された（第 8.2・8.4 節）。競合は発生していない。
- E. 段階分割コミットの作成: 単一のスタック更新で実施したため不要（コミット `d7cd60f` 1 件）。

残る `undetermined`:

F. `DjangoFunctionLogGroup` のログ保全（エクスポート）の要否: 未確認のまま更新を実施したため、ログ（prod 375,901 バイト / staging 120,543 バイト）は削除された（第 8.2 節）。保全の要否は依然として未確認であり、削除は取り消せない。
G. `Outputs.ApiUrl` のリポジトリ外利用者の有無: スキャン記録「未確認事項 4」のまま未確認。
H. `samconfig.toml` 9 行目の `parameter_overrides` に残る `AllowedOrigin` / `AllowedHosts` / `DomainName`: これらは `pipeline.yaml` の `Parameters`（4-38 行）に存在せず、revision `8580e71` 時点でも当該テンプレートに対応しない指定であった（出典: `git show HEAD:pipeline.yaml` に該当パラメータの記載なし）。本タスクの変更で `template.yaml` 側の同名パラメータも除去されたため、リポジトリ内に対応する宣言は存在しない。除去の可否は未決定。
I. `asgi_lambda.py` および Django 表示経路向けコードの位置付け: `DjangoFunction` 退役によりデプロイ対象から外れたが、その扱い（保持・除去）は本タスクの範囲外であり未決定。

## 7. 本タスクの範囲外

- `dependencies.yaml` / `bucketpolicy.yaml` の変更（非破壊、未変更）
- ドキュメント（`docs/architecture.md`、`README.md` 等）の整合更新（タスク 12 の範囲）

## 8. スタック更新の実施記録（staging → prod）

本節は 2026-07-28 のユーザー指示（タスク 11 の実行命令。これが破壊的操作に対する人手承認）に基づく実施記録である。
各環境で単一のスタック更新（検証 CNAME 宣言と退役リソース除去を同時適用）を実施した。

### 8.1 コミットと反映

| 項目 | 値 | 出典（実行コマンド） |
| --- | --- | --- |
| コミット | `d7cd60fb24200bc7b50953532a00830da4ce44ed`（`refactor(iac): retire Django display path and declare ACM validation CNAME`） | `git commit -F <msg>`（git フックは有効。`commit-msg` は ALLOW） |
| 対象ファイル | `template.yaml` / `buildspec.yml` / `pipeline.yaml` / `tests/iac/test_template_policies.py` / 本記録 / スキャン記録（6 files changed, 824 insertions, 198 deletions） | `git commit` 出力 |
| staging 反映 | `git switch dev` → `git push origin dev`（`8580e71..d7cd60f`） | `git push origin dev` |
| prod 反映 | `git switch main` → `git merge --ff-only dev` → `git push origin main`（`8580e71..d7cd60f`） | `git merge` / `git push origin main` |

反映直前のローカル検証（すべて合格）: `sam validate --template-file template.yaml --region ap-northeast-1 --profile aws_portfolio_profile --lint` = `valid SAM Template`、`python -m unittest discover -s tests -t .` = `Ran 76 tests / OK`、`python -m scripts.control_platform.cli --self-test` = `"ok": false` の出力なし、`python tests/self_test.py` = 全 10 ケース `PASS`。

### 8.2 パイプラインとスタック更新の結果

| 環境 | パイプライン実行 ID / revision | 全ステージ結果 | スタック | 状態 / 最終更新 |
| --- | --- | --- | --- | --- |
| staging | `fc88c514-0048-47bc-a8ab-760320613d2f` / `d7cd60f` | Source・UpdatePipeline・BuildDependencies・DeployDependencies・Build・Deploy すべて `Succeeded` | `cobaemon-serverless-portfolio-staging-stack` | `UPDATE_COMPLETE` / 2026-07-28T06:32:18Z |
| prod | `ae543e31-3fa0-4564-9d60-de254991d718` / `d7cd60f` | 同上すべて `Succeeded` | `cobaemon-serverless-portfolio-stack` | `UPDATE_COMPLETE` / 2026-07-28T06:58:53Z |

出典: `aws codepipeline list-pipeline-executions`、`aws codepipeline get-pipeline-state --name cobaemon-serverless-portfolio-staging-pipeline|cobaemon-serverless-portfolio-pipeline`、`aws cloudformation describe-stacks --query "Stacks[0].{status:StackStatus,updated:LastUpdatedTime}"`（いずれも `--region ap-northeast-1 --profile aws_portfolio_profile`）。

スタックイベント（`aws cloudformation describe-stack-events`）では両環境で `AcmValidationRecordSet` の `CREATE_COMPLETE` が退役リソースの削除より先に記録され、`*_FAILED` および `ROLLBACK` 系のイベントは存在しない。

削除完了（`DELETE_COMPLETE`）が記録された論理 ID（両環境で同一。staging 06:33:02-06:34:10Z / prod 06:59:36-07:00:43Z）:
`DjangoFunction`、`DjangoFunctionAliaslive`、`DjangoFunctionRole`、`DjangoFunctionLogGroup`、`DjangoFunctionPostEndpointPermissionStage`、`DjangoFunctionProxyGetPermissionStage`、`DjangoFunctionProxyPostPermissionStage`、`DjangoFunctionProxyOptionsPermissionStage`、`DjangoApi`、`DjangoApiStage`、`DjangoApiDeploymentd8051f505f`、`ApiGatewayCustomDomain`、`ApiGatewayBasePathMapping`、`ServerlessCertificate`。

`DjangoFunctionLogGroup` は `DeletionPolicy: Delete` により削除され、当該ロググループのログ（prod 375,901 バイト / staging 120,543 バイト。出典: スキャン記録「確認結果 3」）は失われた。エクスポートは実施していない。

### 8.3 削除後のリソース棚卸し（実測）

| 確認 | コマンド | 結果 |
| --- | --- | --- |
| スタックリソース一覧 | `aws cloudformation describe-stack-resources --stack-name <各スタック>` | 両環境とも 13 件で、`AcmValidationRecordSet` / `ApiGatewayRecordSet` / `CloudFrontDistribution` / `ContactApi` / `ContactApiDeployment322166271b` / `ContactApiStage` / `ContactFunction` / `ContactFunctionContactOptionsPermissionStage` / `ContactFunctionContactPostPermissionStage` / `ContactFunctionLogGroup` / `ContactFunctionRole` / `DisplayResponseHeadersPolicy` / `DisplayRouterFunction` のみ。退役対象の論理 ID は存在しない |
| Lambda 関数 | `aws lambda list-functions` | 残存は `cobaemon-serverless-portfolio-stac-ContactFunction-x7VR1cRQFuz5`（prod）と `cobaemon-serverless-portfolio-stag-ContactFunction-YpXVheb5VsqJ`（staging）の 2 件のみ。`DjangoFunction` を含む関数は 0 件 |
| API Gateway REST API | `aws apigateway get-rest-apis` | 残存は `4ia2s2c7j3`（prod ContactApi）と `pdf7bj82d5`（staging ContactApi）。`5ao0xzfhph`（prod DjangoApi）・`0vmnuyh30j`（staging DjangoApi）は不在 |
| API Gateway カスタムドメイン | `aws apigateway get-domain-names` | 0 件（`serverless.portfolio.cobaemon.com` / `staging.serverless.portfolio.cobaemon.com` とも不在） |
| ACM（ap-northeast-1） | `aws acm list-certificates --region ap-northeast-1` | 旧 `ServerlessCertificate` の物理 ID（prod `576646b5-be52-4217-b38f-d5b61d2a9032` / staging `1b49250a-87a1-454d-a851-798f7a89c1b1`。出典: スキャン記録「確認結果 4」）はいずれも不在。残る 3 件（`3c4b6f02-4db9-49a8-9b03-147ca7baf5fc` / `a51e2a53-eb2a-487f-9a45-944b35980326` / `d21e5ed8-f919-4ec7-a1a7-af8d793d6db5`）は本スタック群の管理外である（スタックリソース一覧に対応する論理 ID なし） |

### 8.4 検証 CNAME と us-east-1 証明書

`aws route53 list-resource-record-sets --hosted-zone-id Z00462201BTRUWFZ0YO7V` の結果、以下が TTL 300 の CNAME として存置されている。

- prod: `_9afd031f8f75b92e5ef70ce914afd8fd.serverless.portfolio.cobaemon.com.` → `_615610039787f7d01a294226ab3ab053.xlfgrmvvlj.acm-validations.aws.`
- staging: `_d70937ca68d49a47995c0f8a29bb8e9c.staging.serverless.portfolio.cobaemon.com.` → `_6fbea12a2bd06cf8cb2d00d54eb7989a.jkddzztszm.acm-validations.aws.`

A レコードは CloudFront を指したまま維持されている（prod → `d3mh423zcvv61u.cloudfront.net.` / staging → `d2t5vawf3svyin.cloudfront.net.`）。

`aws acm describe-certificate --region us-east-1` の結果、`serverless.portfolio.cobaemon.com`（`E3QK078NBPDKHO` で使用中）と `staging.serverless.portfolio.cobaemon.com`（`E18LO9XBUTT6Y9` で使用中）はともに `Status=ISSUED`、`RenewalEligibility=ELIGIBLE`、`NotAfter=2027-02-06T08:59:59+09:00`。

### 8.5 公開エンドポイントの疎通と非退行検証

| 環境 | 検証 | 結果 |
| --- | --- | --- |
| staging | `GET https://staging.serverless.portfolio.cobaemon.com/portfolio/top/` | HTTP 200、本文 38,015 バイト、`Content-Security-Policy` 付与（nonce なし） |
| staging | `POST https://staging.serverless.portfolio.cobaemon.com/portfolio/contact`（`Origin` 付き、4 項目 JSON） | HTTP 200、`Access-Control-Allow-Origin: https://staging.serverless.portfolio.cobaemon.com`、本文 `{"message": "問い合わせを受け付けました。"}` |
| staging | `python -m scripts.measurement.non_regression_check --base-url https://staging.serverless.portfolio.cobaemon.com` | 11 チェックすべて `COMPLIANT`、終了コード 0 |
| prod | `GET https://serverless.portfolio.cobaemon.com/portfolio/top/` | HTTP 200、本文 38,015 バイト |
| prod | `POST https://serverless.portfolio.cobaemon.com/portfolio/contact`（`Origin` 付き、4 項目 JSON） | HTTP 200、`Access-Control-Allow-Origin: https://serverless.portfolio.cobaemon.com`、本文 `{"message": "問い合わせを受け付けました。"}` |
| prod | `python -m scripts.measurement.non_regression_check --base-url https://serverless.portfolio.cobaemon.com` | 11 チェックすべて `COMPLIANT`、終了コード 0 |

POST 検証で観測した事実として、`Origin` ヘッダなしの要求は HTTP 403（`{"error": "origin_rejected"}`）、フィールド名が `name` / `phone` の要求は HTTP 400（`{"error": "validation_error", "fields": ["full_name", "phone_number"]}`）となった。いずれも `contact_function/handler.py` の Origin 検証（287-288 行）と `contact_function/domain/validators.py` の `_ALLOWED_FIELDS`（26 行）に一致する設計上の挙動であり、本変更による退行ではない。

なお POST 検証は Amazon SES による実際のメール送信を伴う（staging・prod 各 1 通）。
