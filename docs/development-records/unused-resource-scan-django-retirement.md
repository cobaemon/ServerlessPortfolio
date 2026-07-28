# 不要リソースのスキャン記録（Django 表示経路の退役対象棚卸し）

本記録は spec `cost-performance-optimization` のタスク 10「不要リソースのスキャン（削除対象の確定）」の成果物である。
目的は、静的ファースト配信への切替後に残存している Django 表示経路のリソースを棚卸しし、削除対象を事実に基づいて確定することである。
本作業は読み取り専用の照会のみで構成され、AWS リソースの変更・削除および `template.yaml` の変更は行っていない。

- 実施日時: 2026-07-27T17:33+09:00（出典: `Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"`）
- source revision: `8580e717557c242b9f9b68767a2f5a121d61a772`（出典: `git rev-parse HEAD`。作業ツリーに未コミット変更なし。出典: `git status --porcelain` の出力が空）
- 対象アカウント: `864454139429`（出典: `aws sts get-caller-identity --profile aws_portfolio_profile`）
- 使用プロファイル/リージョン: `aws_portfolio_profile` / `ap-northeast-1`（CloudFront・us-east-1 ACM は `us-east-1`）
- AWS CLI: `aws-cli/2.34.22`（出典: `aws --version`）

## 確認対象

1. 退役候補 `DjangoFunction`（prod / staging）の呼び出し実績
2. CloudFront から `DjangoApi` が参照されていないこと（prod / staging）
3. CloudFormation スタック管理下の Django 関連リソース一覧（関数／エイリアス／バージョン／IAM ロール／ロググループ／Lambda Permission／API Gateway RestApi・Stage・Deployment）
4. API Gateway カスタムドメイン（`serverless.portfolio.cobaemon.com` / `staging.serverless.portfolio.cobaemon.com`）のベースパスマッピングの残存状況と扱い
5. 削除に伴う周辺参照（Route53 レコード、ACM 証明書、`template.yaml` の参照、Outputs、テスト）

## 確認結果

### 1. `DjangoFunction` の呼び出し実績（CloudWatch `AWS/Lambda` Invocations）

実行コマンド（`--period 86400 --statistics Sum`、期間 `2026-03-29T00:00:00Z` 〜 `2026-07-27T08:40:00Z`）:

```powershell
aws cloudwatch get-metric-statistics --namespace AWS/Lambda --metric-name Invocations `
  --dimensions Name=FunctionName,Value=<関数名> `
  --start-time 2026-03-29T00:00:00Z --end-time 2026-07-27T08:40:00Z `
  --period 86400 --statistics Sum --profile aws_portfolio_profile --region ap-northeast-1
```

| 対象 | 結果 |
| --- | --- |
| prod `cobaemon-serverless-portfolio-stack-DjangoFunction-2a6VdxuyoNIc`（FunctionName 次元） | Datapoints 空（データポイント 0 件） |
| prod 同関数 `Resource=...:live` 次元（2026-07-24〜） | Datapoints 空 |
| staging `cobaemon-serverless-portfolio-stagi-DjangoFunction-pl6hrBiymccs`（FunctionName 次元） | Datapoints 空 |
| staging 同関数 `Resource=...:live` 次元（2026-07-24〜） | Datapoints 空 |

対照確認（照会方法が有効であることの確認。同一コマンド形・同一期間）:

| 対象 | 結果 |
| --- | --- |
| prod `cobaemon-serverless-portfolio-stac-ContactFunction-x7VR1cRQFuz5` | `2026-07-23` Sum=1.0、`2026-07-26` Sum=3.0 |

事実: 上記期間において `DjangoFunction`（prod / staging）の Invocations データポイントは 0 件であり、同一形式の照会が ContactFunction では値を返した。
なお CloudWatch はデータのない期間についてデータポイントを返さないため、「データポイント 0 件」は当該期間に当該メトリクスのデータが記録されていないことを示す。

`DjangoFunction` のバージョン・エイリアス（出典: `aws lambda list-versions-by-function` / `aws lambda list-aliases`）:

| 対象 | バージョン | `SnapStart.ApplyOn` | エイリアス |
| --- | --- | --- | --- |
| prod | `$LATEST`, `4` | すべて `None` | `live` → `4` |
| staging | `$LATEST`, `11`〜`19` | すべて `None` | `live` → `19` |

事実: 現存する全バージョンで SnapStart は `None`（有効版は 0 件）。

### 2. API Gateway `DjangoApi` の参照状況とリクエスト実績

CloudFront ディストリビューション設定（出典: `aws cloudfront get-distribution-config --id <id>`）:

| ディストリビューション | Alias | オリジン | 既定ビヘイビア | 追加ビヘイビア |
| --- | --- | --- | --- | --- |
| prod `E3QK078NBPDKHO`（`d3mh423zcvv61u.cloudfront.net`） | `serverless.portfolio.cobaemon.com` | `S3-cobaemon-serverless-portfolio-prod-static`、`ContactApi-prod`（`4ia2s2c7j3.execute-api...`, パス `/prod`） | S3 オリジン、`redirect-to-https` | `/portfolio/contact` → `ContactApi-prod`、`redirect-to-https` |
| staging `E18LO9XBUTT6Y9`（`d2t5vawf3svyin.cloudfront.net`） | `staging.serverless.portfolio.cobaemon.com` | `S3-cobaemon-serverless-portfolio-staging-static`、`ContactApi-staging`（`pdf7bj82d5.execute-api...`, パス `/staging`） | S3 オリジン、`redirect-to-https` | `/portfolio/contact` → `ContactApi-staging`、`redirect-to-https` |

事実: どちらのディストリビューションにも `DjangoApi`（prod `5ao0xzfhph` / staging `0vmnuyh30j`）を指すオリジンおよびビヘイビアは存在しない。

API Gateway リクエスト実績（出典: `aws cloudwatch get-metric-statistics --namespace AWS/ApiGateway --metric-name Count --dimensions Name=ApiName,Value=CobaemonServerlessPortfolioApi Name=Stage,Value=<prod|staging>`、期間 `2026-03-29`〜`2026-07-27`、`--period 86400 --statistics Sum`）:

| 対象 | 結果 |
| --- | --- |
| `CobaemonServerlessPortfolioApi` / `prod` | Datapoints 空 |
| `CobaemonServerlessPortfolioApi` / `staging` | Datapoints 空 |
| 対照 `CobaemonServerlessPortfolioContactApi` / `prod` | `2026-07-23` Sum=1.0、`2026-07-26` Sum=3.0 |

メトリクス自体は存在する（出典: `aws cloudwatch list-metrics --namespace AWS/ApiGateway --dimensions Name=ApiName,Value=CobaemonServerlessPortfolioApi` に `Count`/`Latency`/`4XXError`/`5XXError`/`IntegrationLatency` の prod・staging 次元が存在）ため、上記は「当該期間にリクエストが記録されていない」ことを示す。

REST API 一覧（出典: `aws apigateway get-rest-apis`）:

| ID | 名称 | 作成日 |
| --- | --- | --- |
| `5ao0xzfhph` | CobaemonServerlessPortfolioApi（prod, DjangoApi） | 2025-06-27 |
| `0vmnuyh30j` | CobaemonServerlessPortfolioApi（staging, DjangoApi） | 2026-05-19 |
| `4ia2s2c7j3` | CobaemonServerlessPortfolioContactApi（prod） | 2026-07-23 |
| `pdf7bj82d5` | CobaemonServerlessPortfolioContactApi（staging） | 2026-07-23 |

`DjangoApi` のステージ（出典: `aws apigateway get-stages --rest-api-id <id>`）:

| API | ステージ | デプロイ ID | WAF | アクセスログ |
| --- | --- | --- | --- | --- |
| `5ao0xzfhph` | `Stage`, `prod` | ともに `oakxol` | なし | なし |
| `0vmnuyh30j` | `Stage`, `staging` | ともに `9d4mvh` | なし | なし |

事実: SAM 既定の `Stage` ステージが両 API に存在する（`template.yaml` に明示宣言はなく、CloudFormation スタックリソース一覧にも `DjangoApiStage`（= `prod`/`staging`）のみが現れる）。
使用量プラン・API キーによる参照は存在しない（出典: `aws apigateway get-usage-plans` → `items` 空）。

### 3. CloudFormation スタック管理下の削除対象リソース一覧

出典: `aws cloudformation describe-stack-resources --stack-name <stack>`（`ap-northeast-1`）。

#### prod スタック `cobaemon-serverless-portfolio-stack`（`UPDATE_COMPLETE`, 2026-07-23T10:55:53Z 更新）

| 論理 ID | 種別 | 物理 ID | 状態 |
| --- | --- | --- | --- |
| `DjangoFunction` | `AWS::Lambda::Function` | `cobaemon-serverless-portfolio-stack-DjangoFunction-2a6VdxuyoNIc` | UPDATE_COMPLETE |
| `DjangoFunctionAliaslive` | `AWS::Lambda::Alias` | `...:DjangoFunction-2a6VdxuyoNIc:live` | UPDATE_COMPLETE |
| `DjangoFunctionVersion96c2a5d8e9` | `AWS::Lambda::Version` | `...:DjangoFunction-2a6VdxuyoNIc:4` | CREATE_COMPLETE |
| `DjangoFunctionRole` | `AWS::IAM::Role` | `cobaemon-serverless-portfolio-st-DjangoFunctionRole-uRryT9Da8SGA` | CREATE_COMPLETE |
| `DjangoFunctionLogGroup` | `AWS::Logs::LogGroup` | `/aws/lambda/cobaemon-serverless-portfolio-stack-DjangoFunction-2a6VdxuyoNIc` | CREATE_COMPLETE |
| `DjangoFunctionPostEndpointPermissionStage` | `AWS::Lambda::Permission` | `...-19P5zxdxZn6G` | UPDATE_COMPLETE |
| `DjangoFunctionProxyGetPermissionStage` | `AWS::Lambda::Permission` | `...-X10Ez2OrtR6B` | UPDATE_COMPLETE |
| `DjangoFunctionProxyPostPermissionStage` | `AWS::Lambda::Permission` | `...-LocgL4aDjyUE` | UPDATE_COMPLETE |
| `DjangoFunctionProxyOptionsPermissionStage` | `AWS::Lambda::Permission` | `...-ymvWDQobIvRY` | UPDATE_COMPLETE |
| `DjangoApi` | `AWS::ApiGateway::RestApi` | `5ao0xzfhph` | UPDATE_COMPLETE |
| `DjangoApiStage` | `AWS::ApiGateway::Stage` | `prod` | UPDATE_COMPLETE |
| `DjangoApiDeploymentd8051f505f` | `AWS::ApiGateway::Deployment` | `oakxol` | CREATE_COMPLETE |

#### staging スタック `cobaemon-serverless-portfolio-staging-stack`（`UPDATE_COMPLETE`, 2026-07-23T09:02:00Z 更新）

| 論理 ID | 種別 | 物理 ID | 状態 |
| --- | --- | --- | --- |
| `DjangoFunction` | `AWS::Lambda::Function` | `cobaemon-serverless-portfolio-stagi-DjangoFunction-pl6hrBiymccs` | UPDATE_COMPLETE |
| `DjangoFunctionAliaslive` | `AWS::Lambda::Alias` | `...:DjangoFunction-pl6hrBiymccs:live` | UPDATE_COMPLETE |
| `DjangoFunctionVersion50c57128bb` | `AWS::Lambda::Version` | `...:DjangoFunction-pl6hrBiymccs:19` | CREATE_COMPLETE |
| `DjangoFunctionRole` | `AWS::IAM::Role` | `cobaemon-serverless-portfolio-st-DjangoFunctionRole-Oq2yls7ME1Kn` | CREATE_COMPLETE |
| `DjangoFunctionLogGroup` | `AWS::Logs::LogGroup` | `/aws/lambda/cobaemon-serverless-portfolio-stagi-DjangoFunction-pl6hrBiymccs` | CREATE_COMPLETE |
| `DjangoFunctionPostEndpointPermissionStage` | `AWS::Lambda::Permission` | `...-RQzFyiYfY2Rm` | UPDATE_COMPLETE |
| `DjangoFunctionProxyGetPermissionStage` | `AWS::Lambda::Permission` | `...-J3pFSB6alhUy` | UPDATE_COMPLETE |
| `DjangoFunctionProxyPostPermissionStage` | `AWS::Lambda::Permission` | `...-GiHiI8y9npTO` | UPDATE_COMPLETE |
| `DjangoFunctionProxyOptionsPermissionStage` | `AWS::Lambda::Permission` | `...-BqLcc7VxkXp8` | UPDATE_COMPLETE |
| `DjangoApi` | `AWS::ApiGateway::RestApi` | `0vmnuyh30j` | UPDATE_COMPLETE |
| `DjangoApiStage` | `AWS::ApiGateway::Stage` | `staging` | UPDATE_COMPLETE |
| `DjangoApiDeploymentd8051f505f` | `AWS::ApiGateway::Deployment` | `9d4mvh` | CREATE_COMPLETE |

保持（削除対象外）のリソース（同一スタック内。出典: 上記 `describe-stack-resources`）: `ContactFunction`、`ContactFunctionRole`、`ContactFunctionLogGroup`、`ContactFunction*PermissionStage`、`ContactApi`、`ContactApiStage`、`ContactApiDeployment322166271b`、`CloudFrontDistribution`、`DisplayResponseHeadersPolicy`、`DisplayRouterFunction`、`ApiGatewayRecordSet`。

Lambda リソースポリシー（出典: `aws lambda get-policy --function-name <関数>:live`）: 4 件の `lambda:InvokeFunction` 許可がいずれも `DjangoApi` の execute-api ARN（prod は `...:5ao0xzfhph/*/{OPTIONS|GET|POST}/*` と `.../POST/`、staging は `...:0vmnuyh30j/...`）を `AWS:SourceArn` 条件に持つ。`DjangoApi` 以外の呼び出し元許可は存在しない。

IAM ロール（出典: `aws iam list-attached-role-policies` / `aws iam list-role-policies`）: prod `...-uRryT9Da8SGA`、staging `...-Oq2yls7ME1Kn` はいずれもアタッチ済みマネージドポリシーが `arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole` のみ、インラインポリシーは 0 件。

ロググループ（出典: `aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/cobaemon-serverless-portfolio"`）:

| ロググループ | 保持日数 | 保存バイト |
| --- | --- | --- |
| `/aws/lambda/cobaemon-serverless-portfolio-stack-DjangoFunction-2a6VdxuyoNIc` | 365 | 375,901 |
| `/aws/lambda/cobaemon-serverless-portfolio-stagi-DjangoFunction-pl6hrBiymccs` | 365 | 120,543 |
| `/aws/lambda/cobaemon-serverless-portfolio-stac-ContactFunction-x7VR1cRQFuz5` | 365 | 1,747 |
| `/aws/lambda/cobaemon-serverless-portfolio-stag-ContactFunction-YpXVheb5VsqJ` | 365 | 4,561 |

`DjangoFunctionLogGroup` は `template.yaml` で `DeletionPolicy: Delete` / `UpdateReplacePolicy: Delete` を持つ（出典: `template.yaml` 192-199 行）。スタック更新による削除でログは失われる。

アカウント内の Lambda 関数は上記 4 関数のみで、スタック外の孤立した Django 関連関数は存在しない（出典: `aws lambda list-functions`）。

### 4. API Gateway カスタムドメインとベースパスマッピング

出典: `aws apigateway get-base-path-mappings --domain-name <domain>` / `aws apigateway get-domain-name --domain-name <domain>`。

| ドメイン | basePath | restApiId | stage | エンドポイント種別 | regionalDomainName | 証明書 |
| --- | --- | --- | --- | --- | --- | --- |
| `serverless.portfolio.cobaemon.com` | `(none)` | `5ao0xzfhph`（DjangoApi） | `prod` | REGIONAL | `d-gp8fh90ydk.execute-api.ap-northeast-1.amazonaws.com` | `arn:aws:acm:ap-northeast-1:864454139429:certificate/576646b5-be52-4217-b38f-d5b61d2a9032` |
| `staging.serverless.portfolio.cobaemon.com` | `(none)` | `0vmnuyh30j`（DjangoApi） | `staging` | REGIONAL | `d-bzya9utumk.execute-api.ap-northeast-1.amazonaws.com` | `arn:aws:acm:ap-northeast-1:864454139429:certificate/1b49250a-87a1-454d-a851-798f7a89c1b1` |

事実: ベースパスマッピングは両環境で `DjangoApi` に残存している。証明書 ARN は両スタックの `ServerlessCertificate`（REGIONAL）の物理 ID と一致する。

Route53（出典: `aws route53 list-resource-record-sets --hosted-zone-id Z00462201BTRUWFZ0YO7V`）:

| レコード | 種別 | Alias 先 |
| --- | --- | --- |
| `serverless.portfolio.cobaemon.com.` | A | `d3mh423zcvv61u.cloudfront.net.`（= prod CloudFront `E3QK078NBPDKHO`。出典: `aws cloudfront list-distributions`） |
| `staging.serverless.portfolio.cobaemon.com.` | A | `d2t5vawf3svyin.cloudfront.net.`（= staging CloudFront `E18LO9XBUTT6Y9`） |
| `_9afd031f8f75b92e5ef70ce914afd8fd.serverless.portfolio.cobaemon.com.` | CNAME | `_615610039787f7d01a294226ab3ab053.xlfgrmvvlj.acm-validations.aws.`（TTL 300） |
| `_d70937ca68d49a47995c0f8a29bb8e9c.staging.serverless.portfolio.cobaemon.com.` | CNAME | `_6fbea12a2bd06cf8cb2d00d54eb7989a.jkddzztszm.acm-validations.aws.`（TTL 300） |

事実: 公開ホスト名の A レコードは CloudFront を指しており、API Gateway カスタムドメインの `regionalDomainName` を指していない。
`template.yaml` の `ApiGatewayRecordSet` は `HasCloudFrontCertificate` 条件で切り替わる構成で（出典: `template.yaml` 386-409 行）、両スタックの `CloudFrontCertificateArn` パラメータが設定済みのため CloudFront 側の分岐が選択されている（出典: `aws cloudformation describe-stacks --query "Stacks[0].Parameters"`。prod = `arn:aws:acm:us-east-1:...:certificate/541abab2-fd33-49c8-a27f-23a95c4b8380`、staging = `.../9ac1240d-8015-451c-8e91-4a072a41ea92`）。

ACM 証明書の使用状況（出典: `aws acm describe-certificate`）:

| 証明書 | リージョン | 状態 | InUseBy | 検証 CNAME |
| --- | --- | --- | --- | --- |
| `576646b5-...`（prod, `ServerlessCertificate`） | ap-northeast-1 | ISSUED | `arn:aws:elasticloadbalancing:ap-northeast-1:969236854626:loadbalancer/app/prod-nrt-1-cdtls-1-2-{206,231,7}/...`（3 件） | `_9afd031f8f75b92e5ef70ce914afd8fd...` = `_615610039787f7d01a294226ab3ab053...` |
| `541abab2-...`（prod, CloudFront 用） | us-east-1 | ISSUED | `arn:aws:cloudfront::864454139429:distribution/E3QK078NBPDKHO` | 同上（prod 証明書と同一の名前・値） |
| `1b49250a-...`（staging, `ServerlessCertificate`） | ap-northeast-1 | ISSUED | `arn:aws:elasticloadbalancing:ap-northeast-1:969236854626:loadbalancer/app/prod-nrt-1-cdtls-1-2-{183,277,295}/...`（3 件） | `_d70937ca68d49a47995c0f8a29bb8e9c...` = `_6fbea12a2bd06cf8cb2d00d54eb7989a...` |
| `9ac1240d-...`（staging, CloudFront 用） | us-east-1 | ISSUED | `arn:aws:cloudfront::864454139429:distribution/E18LO9XBUTT6Y9` | 同上（staging 証明書と同一の名前・値） |

事実: REGIONAL 証明書と us-east-1 証明書は、同一ドメインに対して同一の検証 CNAME 名・値を共有している。
us-east-1 の 2 証明書はいずれのスタックのリソース一覧にも現れず（出典: 両スタックの `describe-stack-resources`）、`CloudFrontCertificateArn` パラメータとして外部から与えられている。

### 5. `template.yaml` および周辺の参照箇所（削除時に影響する宣言）

出典: `template.yaml`（行番号は本記録作成時点の revision `8580e71`）。

| 参照箇所 | 内容 |
| --- | --- |
| 121-190 行 | `DjangoFunction` 宣言（`Handler: asgi_lambda.handler`, `AutoPublishAlias: live`, 環境変数に `CloudFrontDistribution.DomainName` 参照、`Events`: `PostEndpoint`/`ProxyGet`/`ProxyPost`/`ProxyOptions`） |
| 192-199 行 | `DjangoFunctionLogGroup`（`LogGroupName: !Sub "/aws/lambda/${DjangoFunction}"`） |
| 200-238 行 | `DjangoApi`（`GET /` の mock 301、Cors 設定） |
| 376-384 行 | `ApiGatewayBasePathMapping`（`DependsOn: DjangoApiStage`、`RestApiId: !Ref DjangoApi`） |
| 386-409 行 | `ApiGatewayRecordSet`（`!If HasCloudFrontCertificate` の偽側分岐が `ApiGatewayCustomDomain` の `RegionalDomainName` / `RegionalHostedZoneId` を参照） |
| 803-805 行 | `Outputs.ApiUrl`（`Value: !Ref DjangoApi`。`Export` なし） |
| 532-539 行 | コメントアウト済み `WAFWebACLAssociation` 内に `DjangoApiStage` / `DjangoApi` 参照 |

リポジトリ内の他参照（出典: `grep`）:

- `tests/iac/test_template_policies.py` 341-377 行: `_DJANGO_FUNCTION_ID = "DjangoFunction"` を定義し、`DjangoFunction` と `ContactFunction` の 2 関数の存在を前提とするアサーションがある（削除時に修正が必要）。
- `docs/architecture.md` 39-44 行、`docs/deployment.md` 19-23 行、`docs/staging-deployment-runbook.md` 158-167 行: 削除対象に関する記述が残る（タスク 12 の対象）。
- `scripts/measurement/cost_attribution.py`（費目ラベル `Lambda(DjangoFunction/Contact_Function)` 等）、`scripts/measurement/cold_start_protocol.py`（出典文字列）に名称参照がある（機能依存ではなくラベル・出典表記）。
- `Outputs.ApiUrl` に `Export` はなく、`pipeline.yaml` / `buildspec.yml` からの参照は `grep` で検出されなかった。

### 削除対象の確定（本記録時点）

以下を「削除対象」として確定する。根拠は上記 1〜3（呼び出し実績 0、CloudFront からの参照なし、スタック管理下であること）。

- prod / staging 各スタックの `DjangoFunction`、`DjangoFunctionAliaslive`、`DjangoFunctionVersion*`、`DjangoFunctionRole`、`DjangoFunctionLogGroup`、`DjangoFunction*PermissionStage`（各 4 件）
- prod / staging 各スタックの `DjangoApi`、`DjangoApiStage`、`DjangoApiDeployment*`（および SAM 既定の `Stage` ステージ）
- `template.yaml` の対応宣言（`DjangoFunction` / `DjangoFunctionLogGroup` / `DjangoApi` / 表示経路イベント 4 件 / `Outputs.ApiUrl`）

削除手段は `template.yaml` から宣言を除去してスタックを更新することとする（CLI 個別削除はスタックのドリフトを生み、次回デプロイで再作成されるため採らない。出典: 上記 3 のスタックリソース一覧と `template.yaml` の宣言）。

以下は「削除対象外（保持）」とする。根拠は現行の公開経路で使用中であること（上記 2・4）。

- `CloudFrontDistribution`、`DisplayResponseHeadersPolicy`、`DisplayRouterFunction`、`ContactApi`／`ContactApiStage`／`ContactApiDeployment*`、`ContactFunction`／`ContactFunctionRole`／`ContactFunctionLogGroup`／`ContactFunction*PermissionStage`、`ApiGatewayRecordSet`、us-east-1 の CloudFront 用 ACM 証明書、S3／OAC（`dependencies.yaml` 管理）

## 未確認事項（`undetermined`。削除可と決めつけない）

1. `ApiGatewayCustomDomain` / `ApiGatewayBasePathMapping` / `ServerlessCertificate`（REGIONAL）の扱い: 追加調査の後にユーザー判断で決定済み（本記録末尾「扱いの決定」節を参照）。以下は判断の前提として記録した事実とリスクである。
   - 確定事実: ベースパスマッピングは `DjangoApi` に残存（上記 4）。公開ホスト名の A レコードは CloudFront を指す（上記 4）。したがって現行の DNS 経路上、カスタムドメイン経由で `DjangoApi` に到達する経路は確認されていない。
   - 未確認リスク: REGIONAL 証明書（`ServerlessCertificate`）と us-east-1 の CloudFront 用証明書は同一の検証 CNAME 名・値を共有している（上記 4）。`ServerlessCertificate` を CloudFormation から削除した場合に、`DomainValidationOptions.HostedZoneId` 指定により CloudFormation が作成した検証 CNAME レコードが削除され、us-east-1 証明書の将来の自動更新（DNS 検証）に影響するか否かは本スキャンでは確認していない（`undetermined`）。
   - 未確認: `ApiGatewayCustomDomain` を削除した場合の `ApiGatewayRecordSet` の `!If` 偽側分岐（`ApiGatewayCustomDomain` 参照）の扱い。テンプレートから当該リソースを除去する場合は同レコードの分岐も併せて改修が必要であり、その改修方針は未決定（`undetermined`）。
   - よって本タスクでは「削除対象」「保持」のいずれにも確定せず、扱いはユーザー判断事項として保留する。
2. `DjangoFunctionLogGroup` のログ消失可否: prod 375,901 バイト / staging 120,543 バイトのログが `DeletionPolicy: Delete` によりスタック更新で失われる。保全（エクスポート）の要否は未確認（`undetermined`）。
3. `2026-03-29` より前の `DjangoFunction` / `DjangoApi` の呼び出し実績: 本スキャンの照会期間外であり未確認（`undetermined`）。削除判断は「現在の公開経路に含まれないこと」（上記 2・4）と「照会期間内の実績 0」に基づく。
4. `Outputs.ApiUrl` の外部利用者: `Export` は無く、リポジトリ内参照も検出されなかったが、リポジトリ外（手作業・外部ツール）からの参照有無は未確認（`undetermined`）。
5. `tests/iac/test_template_policies.py` の `DjangoFunction` 前提アサーションの修正方針: 未決定（タスク 11 で扱う）。
6. スタック更新（破壊的操作）の実施可否・実施タイミング: 本タスクでは実施していない。人手承認を前提とする運用手順として未実施（`undetermined`）。

## 本タスクで実施していないこと

- AWS リソースの作成・変更・削除（実行した AWS CLI は `sts get-caller-identity` / `describe-*` / `get-*` / `list-*` の読み取り専用のみ）
- `template.yaml` その他 IaC の変更
- CloudFormation スタックの更新

## 追加調査: ACM 検証 CNAME レコードの所有関係と us-east-1 証明書更新への影響

ユーザー判断により、未確認事項 1 の判断前に追加調査を実施した（実施日時: 2026-07-27、読み取り専用照会および公式ドキュメント参照のみ）。

### 調査結果

1. 検証 CNAME レコードは CloudFormation が作成している（staging について確認済み）
   - 出典: `aws cloudtrail lookup-events --lookup-attributes AttributeKey=EventName,AttributeValue=ChangeResourceRecordSets --start-time 2026-04-28T00:00:00Z --end-time 2026-07-27T09:00:00Z --region us-east-1`
   - 該当イベント: `2026-05-19T23:32:23+09:00`、`userIdentity.invokedBy = cloudformation.amazonaws.com`、`action = UPSERT`、対象 `_d70937ca68d49a47995c0f8a29bb8e9c.staging.serverless.portfolio.cobaemon.com.`（CNAME）。
   - 同 CloudTrail 照会範囲の他イベント: `2026-05-19T23:34:29` に staging の A レコード CREATE（CloudFormation）、`2026-07-23T15:18:48`（staging）／`2026-07-23T19:59:18`（prod）に A レコードの DELETE + CREATE（CloudFormation。CloudFront への切替に対応）。
   - prod の検証 CNAME（`_9afd031f...`）の作成イベントは、prod 証明書の作成時期（`ServerlessCertificate` = REGIONAL 証明書、API `5ao0xzfhph` 作成日 2025-06-27）が CloudTrail の参照可能期間外であるため確認できない（`undetermined`）。
   - `2026-07-23` に us-east-1 証明書用の検証 CNAME を新規作成したイベントは存在しない。両環境で REGIONAL 証明書と us-east-1 証明書の検証 CNAME 名・値が同一であること（本記録「確認結果 4」）と整合する。

2. us-east-1（CloudFront 用）証明書の状態（出典: `aws acm describe-certificate --region us-east-1`）

| 証明書 | Type | Status | 検証方式 | 検証状態 | NotAfter | RenewalEligibility |
| --- | --- | --- | --- | --- | --- | --- |
| `541abab2-...`（prod） | AMAZON_ISSUED | ISSUED | DNS | SUCCESS | 2027-02-06T08:59:59+09:00 | ELIGIBLE |
| `9ac1240d-...`（staging） | AMAZON_ISSUED | ISSUED | DNS | SUCCESS | 2027-02-06T08:59:59+09:00 | ELIGIBLE |

3. ACM の自動更新要件（公式ドキュメント）
   - [DNS validation](https://docs.aws.amazon.com/acm/latest/userguide/dns-validation.html): CNAME レコードの追加は一度だけでよく、証明書が使用中かつ当該 CNAME レコードが存置されている限り ACM が自動更新する旨が記載されている。
   - [Renewal for domains validated by DNS](https://docs.aws.amazon.com/acm/latest/userguide/dns-renewal-validation.html): 更新の要件として、ACM が指定する DNS CNAME レコードがパブリック DNS から参照可能であることが挙げられている。
   - [Troubleshoot managed certificate renewal](https://docs.aws.amazon.com/acm/latest/userguide/troubleshooting-renewal.html): DNS 検証証明書の更新失敗は、DNS 設定上の CNAME レコードの欠落または不正が主要因である旨が記載されている。
   - 上記はいずれも AWS 公式ドキュメント（一次情報。第三原則8に適合）。内容はライセンス配慮のため逐語引用せず要約している。

4. CloudFormation による検証レコードの削除挙動: 公式リファレンス未記載（`undetermined`）
   - 参照: [AWS::CertificateManager::Certificate](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-certificatemanager-certificate.html)。同ページには、Route 53 ホストゾーン・同一アカウント・DNS 検証の 3 条件が満たされる場合にドメイン検証が自動処理される旨の記載はあるが、証明書リソース削除時に検証 CNAME レコードを削除するか否かの記載は存在しない。
   - CloudTrail の参照可能期間内に、証明書削除に伴う検証 CNAME の DELETE イベントは観測されていない（本アカウントで当該操作が行われていないため）。したがって削除挙動は実測未確認（`undetermined`）。

### 追加調査から確定した事実と残るリスク

- 確定: staging の検証 CNAME は CloudFormation（`ServerlessCertificate` の DNS 検証）によって作成された。
- 確定: us-east-1 の CloudFront 用証明書 2 件は DNS 検証・更新対象（ELIGIBLE、期限 2027-02-06）であり、REGIONAL 証明書と同一の検証 CNAME に依存している。
- 確定: ACM 公式ドキュメントは、DNS 検証証明書の自動更新に当該 CNAME レコードの存置を要件としている。
- 未確認（`undetermined`）: `ServerlessCertificate`（REGIONAL）をスタックから削除した際に、CloudFormation が当該検証 CNAME レコードを削除するか否か。公式リファレンスに記載がなく、実測も存在しない。
- 未確認（`undetermined`）: prod の検証 CNAME レコードの作成主体（CloudTrail 参照可能期間外）。

以上より、`ServerlessCertificate`（REGIONAL）の削除は、us-east-1 証明書の将来の自動更新を損なう可能性が排除できていない。リスクを排除するには、削除前に検証 CNAME レコードを `AWS::Route53::RecordSet` として明示宣言するなどの手当てが必要であり、その方針は未決定（`undetermined`）である。本スキャンでは当該 3 リソース（`ApiGatewayCustomDomain` / `ApiGatewayBasePathMapping` / `ServerlessCertificate`）の扱いを確定しない。

## 扱いの決定（`ApiGatewayCustomDomain` / `ApiGatewayBasePathMapping` / `ServerlessCertificate`）

決定主体: ユーザー。決定日時: 2026-07-27。決定内容は「検証 CNAME を明示宣言してから削除する」。

追加の決定（決定主体: ユーザー。決定日時: 2026-07-28。出典: 同日のユーザー指示）: 検証 CNAME の宣言と、証明書・カスタムドメインの削除は**同一のスタック更新（単一の更新）で同時に実施する**。実施順は staging → prod とする。

決定の内容（タスク 11 で反映する事項）:

1. 検証 CNAME レコードを `template.yaml` に `AWS::Route53::RecordSet` として明示宣言し、スタック更新で当該レコードをスタック管理下に取り込む。
   - prod: `_9afd031f8f75b92e5ef70ce914afd8fd.serverless.portfolio.cobaemon.com.` CNAME → `_615610039787f7d01a294226ab3ab053.xlfgrmvvlj.acm-validations.aws.`
   - staging: `_d70937ca68d49a47995c0f8a29bb8e9c.staging.serverless.portfolio.cobaemon.com.` CNAME → `_6fbea12a2bd06cf8cb2d00d54eb7989a.jkddzztszm.acm-validations.aws.`
   - 出典（現行値）: `aws route53 list-resource-record-sets --hosted-zone-id Z00462201BTRUWFZ0YO7V`、`aws acm describe-certificate`（本記録「確認結果 4」）。
2. `ApiGatewayBasePathMapping`、`ApiGatewayCustomDomain`、`ServerlessCertificate`（REGIONAL）を `template.yaml` から除去する。除去は 1 の宣言追加と同一のスタック更新に含める（上記「追加の決定」2026-07-28）。
3. `ApiGatewayRecordSet`（`template.yaml` 386-409 行）の `!If HasCloudFrontCertificate` 偽側分岐が `ApiGatewayCustomDomain` を参照しているため、当該レコードを CloudFront 固定へ改修する（`ApiGatewayCustomDomain` への未解決参照を残さない）。
4. 実施順は staging → prod とし、各環境でスタック更新の完了状態、公開エンドポイントの疎通、検証 CNAME レコードの存置を確認する。

決定の根拠:

- 現行の公開経路はカスタムドメイン（API Gateway）を経由していない（Route53 A レコードは CloudFront を指す。本記録「確認結果 4」）ため、削除は公開挙動に影響しない。
- 未使用リソースを残さないという整合性要求（`.kiro/steering/principles.md` 第三原則 2/4）を満たす。
- 唯一のリスクであった「REGIONAL 証明書削除時に共有の検証 CNAME が失われ、us-east-1 証明書の自動更新（期限 2027-02-06）が損なわれる可能性」は、検証 CNAME を独立した Route53 リソース（`AcmValidationRecordSet`）としてスタック管理下に宣言することで前提から排除する（ACM は当該 CNAME の存置を自動更新の要件とする。出典: 本記録「追加調査 3」）。

本決定に伴い残る未確認事項と対処方針:

- 検証 CNAME を `AWS::Route53::RecordSet` として宣言する際、既存レコード（現在は CloudFormation が `ServerlessCertificate` の DNS 検証として作成したもの）と同名同値のリソースを新規宣言することによる競合の有無は未確認（`undetermined`）。CloudFormation の当該挙動は公式リファレンスに記載がなく、実測もない（出典: 本記録「追加調査 4」）。
- 対処方針（ユーザー指示 2026-07-28 に基づく）: 単一のスタック更新で実施する。競合が発生した場合はフォールバック（別手段への切替・再試行・回避実装）を行わず、スタックイベント（`aws cloudformation describe-stack-events`）を根拠に報告して停止する。
- なお 2026-07-27 時点の本記録には「2 段階に分けて実施する」旨の記述があったが、これはユーザー決定ではなくエージェントの推論であった（決定主体の記載を欠いていた）。2026-07-28 のユーザー指示（同時実施）に従い本節を是正した。
