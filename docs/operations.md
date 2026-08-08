# 運用確認

## 公開 URL

`samconfig.toml` と `template.yaml` では `serverless.portfolio.cobaemon.com` が `DomainName` として扱われています。

公開入口は CloudFront です。Route53 の A レコード（`template.yaml` の `ApiGatewayRecordSet`）は CloudFront の別名を指し、prod は `d3mh423zcvv61u.cloudfront.net.`、staging は `d2t5vawf3svyin.cloudfront.net.` です（出典: `aws route53 list-resource-record-sets --hosted-zone-id Z00462201BTRUWFZ0YO7V` の実測結果を記録した [`development-records/unused-resource-removal-django-retirement.md`](development-records/unused-resource-removal-django-retirement.md) 第 8.4 節）。API Gateway のカスタムドメインは退役済みで存在しません（出典: 同記録 第 8.3 節、`aws apigateway get-domain-names` = 0 件）。

## 非破壊の疎通確認

HTTPS の GET 確認:

```powershell
curl.exe -iL --max-time 30 https://serverless.portfolio.cobaemon.com/
```

アプリケーションパスの確認:

```powershell
curl.exe -i --max-time 20 https://serverless.portfolio.cobaemon.com/portfolio/top/
```

DNS の確認:

```powershell
Resolve-DnsName serverless.portfolio.cobaemon.com
```

静的ファイルの確認:

```powershell
curl.exe -I --max-time 20 https://d3mh423zcvv61u.cloudfront.net/css/styles.min.e55cb46da026.css
```

ハッシュ付きファイル名は `django.contrib.staticfiles.storage.ManifestStaticFilesStorage` により内容が変わるたびに変化します（出典: `config/settings/prod.py` の `STORAGES["staticfiles"]`）。上記コマンドの `styles.min.e55cb46da026.css` が現在も存在するかは本ドキュメント更新時点では未確認です。現行のファイル名はマニフェスト `staticfiles/staticfiles.json` で確認してください（出典: `scripts/check_static_manifest.py` の `manifest_path`）。

言語別ページの確認（`Accept-Language` 交渉の結果として `/<lang>/portfolio/top/index.html` が配信されます。出典: `template.yaml` の `DisplayRouterFunction`）:

```powershell
curl.exe -i --max-time 20 -H "Accept-Language: en" https://serverless.portfolio.cobaemon.com/portfolio/top/
```

## 許可メソッド

表示経路（CloudFront の Default Behavior、オリジンは S3）は `GET`、`HEAD`、`OPTIONS` を許可します（出典: `template.yaml` の `DefaultCacheBehavior.AllowedMethods`）。

問い合わせ経路（`PathPattern: /portfolio/contact`）は CloudFront 側で 7 メソッド（`GET`/`HEAD`/`OPTIONS`/`PUT`/`POST`/`PATCH`/`DELETE`）を許可しますが、オリジン側の `ContactApi` に定義されているのは `POST /portfolio/contact` と `OPTIONS /portfolio/contact` のみです（出典: `template.yaml` の `CacheBehaviors` と `ContactFunction.Events`（`ContactPost` / `ContactOptions`））。

## 問い合わせ経路の疎通確認

`POST /portfolio/contact` の疎通確認は Amazon SES による実際のメール送信を伴います（出典: [`development-records/unused-resource-removal-django-retirement.md`](development-records/unused-resource-removal-django-retirement.md) 第 8.5 節末尾）。実施可否を判断したうえで行ってください。

`Origin` ヘッダを伴わない POST は HTTP 403（`{"error": "origin_rejected"}`）、4 項目（`full_name` / `email` / `phone_number` / `message`）以外のフィールド名を用いた POST は HTTP 400（`{"error": "validation_error", ...}`）となります。これは設計上の挙動です（出典: `contact_function/handler.py` の Origin 検証、`contact_function/domain/validators.py` の `_ALLOWED_FIELDS`、同記録 第 8.5 節）。

## CloudWatch Logs

`ContactFunction` は `AWSLambdaBasicExecutionRole` ポリシーを持ちます。CloudWatch Logs の参照には AWS CLI 認証情報が必要です。

```powershell
aws logs describe-log-groups --profile aws_portfolio_profile
aws logs tail /aws/lambda/<ContactFunctionName> --profile aws_portfolio_profile
```

Lambda 関数名は `template.yaml` では明示していないため、CloudFormation が生成した物理名を参照します。実測値は prod が `cobaemon-serverless-portfolio-stac-ContactFunction-x7VR1cRQFuz5`、staging が `cobaemon-serverless-portfolio-stag-ContactFunction-YpXVheb5VsqJ` です（出典: `aws lambda list-functions` の実測結果を記録した [`development-records/unused-resource-removal-django-retirement.md`](development-records/unused-resource-removal-django-retirement.md) 第 8.3 節）。

```powershell
aws cloudformation describe-stack-resource `
  --stack-name cobaemon-serverless-portfolio-stack `
  --logical-resource-id ContactFunction `
  --query StackResourceDetail.PhysicalResourceId `
  --region ap-northeast-1 `
  --profile aws_portfolio_profile
```

## AWS CLI プロファイル

`samconfig.toml` は `profile = "aws_portfolio_profile"` を指定しています。

## 関連ファイル

- [`samconfig.toml`](../samconfig.toml)
- [`template.yaml`](../template.yaml)
- [`pipeline.yaml`](../pipeline.yaml)
- [`contact_function/handler.py`](../contact_function/handler.py)
- [`scripts/measurement/non_regression_check.py`](../scripts/measurement/non_regression_check.py)
