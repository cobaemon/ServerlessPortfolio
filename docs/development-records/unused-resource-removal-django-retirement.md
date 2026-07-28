# 不要リソースの削除記録（Django 表示経路の退役: テンプレート変更とスタック更新手順）

本記録は spec `cost-performance-optimization` のタスク 11「不要リソースの削除」の成果物である。
対象は `template.yaml` からの退役リソース宣言の除去、その局所検証、および人手承認を前提とするスタック更新手順の定義である。
削除対象および扱いの決定は、タスク 10 の記録 `docs/development-records/unused-resource-scan-django-retirement.md`（以下「スキャン記録」）に従う。

- 実施日時: 2026-07-28（作業ツリー上の変更。コミットは未実施）
- 基準 revision: `8580e717557c242b9f9b68767a2f5a121d61a772`（出典: `git rev-parse HEAD`）
- 変更ファイル: `template.yaml`, `buildspec.yml`, `pipeline.yaml`, `tests/iac/test_template_policies.py`（出典: `git status --porcelain` の ` M` 4 件）
- 本記録時点で AWS への変更操作（スタック更新・リソース削除）は実施していない（第 6 節 A 参照）

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

## 6. 未確認事項（`undetermined`。完了扱いにしない）

A. スタック更新（staging・prod。各環境で単一の更新。出典: ユーザー指示 2026-07-28）の実施と完了状態: 実施結果は第 8 節に記録する。
B. 削除後の対象リソース不在の実測: 実施結果は第 8 節に記録する。
C. 公開エンドポイント（`/portfolio/top/` 表示、`/portfolio/contact` POST）の削除後疎通: 実施結果は第 8 節に記録する。
D. 既存検証 CNAME との競合の有無: 既存レコードは CloudFormation が `ServerlessCertificate` の DNS 検証として作成したものであり、同名同値のレコードを新規リソースとして宣言した際の CloudFormation の挙動は公式リファレンスに記載がなく実測もない（出典: スキャン記録「追加調査 4」）。単一のスタック更新の結果（第 4 節確認項目 2・4）で判定する。競合が発生した場合はフォールバックせずスタックイベントを根拠に報告して停止する。
E. 段階分割コミットの作成: ユーザー指示（2026-07-28、スキャン記録「扱いの決定」追加の決定）により単一のスタック更新で実施するため、コミット分割は行わない（不要）。
F. `DjangoFunctionLogGroup` のログ保全（エクスポート）の要否: スキャン記録「未確認事項 2」のまま未確認。
G. `Outputs.ApiUrl` のリポジトリ外利用者の有無: スキャン記録「未確認事項 4」のまま未確認。
H. `samconfig.toml` 9 行目の `parameter_overrides` に残る `AllowedOrigin` / `AllowedHosts` / `DomainName`: これらは `pipeline.yaml` の `Parameters`（4-38 行）に存在せず、revision `8580e71` 時点でも当該テンプレートに対応しない指定であった（出典: `git show HEAD:pipeline.yaml` に該当パラメータの記載なし）。本タスクの変更で `template.yaml` 側の同名パラメータも除去されたため、リポジトリ内に対応する宣言は存在しない。除去の可否は未決定。
I. `asgi_lambda.py` および Django 表示経路向けコードの位置付け: `DjangoFunction` 退役によりデプロイ対象から外れたが、その扱い（保持・除去）は本タスクの範囲外であり未決定。

## 7. 本タスクの範囲外

- `dependencies.yaml` / `bucketpolicy.yaml` の変更（非破壊、未変更）
- ドキュメント（`docs/architecture.md`、`README.md` 等）の整合更新（タスク 12 の範囲）

## 8. スタック更新の実施記録（staging → prod）

本節は 2026-07-28 のユーザー指示（タスク 11 の実行命令。これが破壊的操作に対する人手承認）に基づく実施記録である。
実行の進行に応じて追記する。
