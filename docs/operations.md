# 運用確認

## 公開 URL

`samconfig.toml` と `template.yaml` では `serverless.portfolio.cobaemon.com` が `DomainName` として扱われています。

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

## HEAD リクエスト

`template.yaml` の Lambda API Events は `/` と `/{proxy+}` に対して `GET`、`POST`、`OPTIONS` を定義しています。`HEAD` は Lambda API Events には定義されていません。

## CloudWatch Logs

Lambda は `AWSLambdaBasicExecutionRole` ポリシーを持ちます。CloudWatch Logs の参照には AWS CLI 認証情報が必要です。

```powershell
aws logs describe-log-groups --profile aws_portfolio_profile
aws logs tail /aws/lambda/<LambdaLogGroupName> --profile aws_portfolio_profile
```

Lambda 関数名は `template.yaml` では明示されていません。`FunctionName` はコメントアウトされています。

## AWS CLI プロファイル

`samconfig.toml` は `profile = "aws_portfolio_profile"` を指定しています。

## 関連ファイル

- [`samconfig.toml`](../samconfig.toml)
- [`template.yaml`](../template.yaml)
- [`pipeline.yaml`](../pipeline.yaml)
