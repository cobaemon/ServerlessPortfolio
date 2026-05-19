# Staging 実値方針

## 方針

staging 環境は `Env=staging` として構築する。AWS 上の検証環境名は `staging` に統一し、ローカル開発用の `config/settings/dev.py` とは分離する。

## ドメイン

staging 用カスタムドメインは次の値とする。

```text
staging.serverless.portfolio.cobaemon.com
```

`DomainName` パラメータにはこの値を指定する。API Gateway カスタムドメイン、ACM 証明書、Route53 A レコードはこのドメインを対象に作成する。

## Secrets Manager

staging 用 Secrets Manager 名は次の値とする。

```text
staging/portfolio/secret
```

この Secret は JSON 形式で次のキーを持つ。

```json
{
  "DJANGO_SECRET_KEY": "<staging 用に新規生成した Django secret key>",
  "EMAIL_HOST_USER": "<staging 用 SMTP ユーザー>",
  "EMAIL_HOST_PASSWORD": "<staging 用 SMTP パスワード>",
  "GOOGLE_CLIENT_ID": "<staging 用 Google OAuth client id>",
  "GOOGLE_CLIENT_SECRET": "<staging 用 Google OAuth client secret>",
  "GITHUB_CLIENT_ID": "<staging 用 GitHub OAuth client id>",
  "GITHUB_CLIENT_SECRET": "<staging 用 GitHub OAuth client secret>"
}
```

`DJANGO_SECRET_KEY` は本番値を流用しない。OAuth クライアントを staging で使用しない場合でも、現在の本番設定と同じ必須環境変数として扱うため、staging 用の値を投入する。

## Parameter Store

staging 用 Parameter Store は次のパス配下に配置する。

```text
/staging/portfolio/parameter/
```

| パラメータ | 値 |
| --- | --- |
| `/staging/portfolio/parameter/allowed_hosts` | `staging.serverless.portfolio.cobaemon.com` |
| `/staging/portfolio/parameter/csrf_trusted_origins` | `https://staging.serverless.portfolio.cobaemon.com` |
| `/staging/portfolio/parameter/default_from_email` | staging 用送信元メールアドレス |
| `/staging/portfolio/parameter/default_to_mail` | staging 用問い合わせ通知先メールアドレス |
| `/staging/portfolio/parameter/email_host` | staging 用 SMTP ホスト |
| `/staging/portfolio/parameter/email_port` | staging 用 SMTP ポート |
| `/staging/portfolio/parameter/email_use_tls` | `True` または `False` |
| `/staging/portfolio/parameter/email_use_ssl` | `True` または `False` |
| `/staging/portfolio/parameter/log_level` | `INFO` |

`email_use_tls` と `email_use_ssl` は同時に `True` にしない。

## SAM / CI/CD に渡す staging 値

staging 用の SAM パラメータは次の値を基準にする。

| パラメータ | 値 |
| --- | --- |
| `Env` | `staging` |
| `DomainName` | `staging.serverless.portfolio.cobaemon.com` |
| `AllowedOrigin` | `/staging/portfolio/parameter/csrf_trusted_origins` |
| `AllowedHosts` | `/staging/portfolio/parameter/allowed_hosts` |
| `S3Bucket` | `cobaemon-serverless-portfolio-staging-artifacts` |
| `CodePipelineName` | `cobaemon-serverless-portfolio-staging-pipeline` |
| `StackName` | `cobaemon-serverless-portfolio-staging-stack` |
| `TemplatePath` | `packaged.yaml` |

staging 用依存リソースのスタック名は次の値とする。

```text
cobaemon-portfolio-dependencies-staging
```

staging 用バケットポリシースタック名は次の値とする。

```text
cobaemon-serverless-portfolio-bucketpolicy-staging
```

## AWS リソース命名

| リソース | 値 |
| --- | --- |
| 静的ファイル S3 バケット | `cobaemon-serverless-portfolio-staging-static` |
| CloudFront OAC 名 | `OAC-for-cobaemon-serverless-portfolio-staging-static` |
| Pipeline IAM Role | `staging-portfolio-pipeline-role` |
| CodeBuild IAM Role | `staging-portfolio-build-role` |
| CloudFormation IAM Role | `staging-portfolio-cfn-role` |
| CloudFront ResponseHeadersPolicy | `StaticFilesCORS-staging` |

## 手動作成が必要なもの

- `staging/portfolio/secret`
- `/staging/portfolio/parameter/*`
- `cobaemon-serverless-portfolio-staging-artifacts`
- `staging.serverless.portfolio.cobaemon.com` を作成できる Route53 ホストゾーン
- staging 用 OAuth クライアントを使う場合の OAuth 側リダイレクト URI 登録

## テンプレート修正で対応するもの

- `Env` の `AllowedValues` を `staging` / `prod` に変更する。
- `config/settings/staging.py` を追加する。
- Secrets Manager 参照を `${Env}/portfolio/secret` に変更する。
- Parameter Store 参照を `/${Env}/portfolio/parameter/*` に変更する。
- buildspec の `prod` 固定値を `ENV` に基づく値へ変更する。
- pipeline の IAM policy と S3 ARN を `Env` に基づく値へ変更する。
- `samconfig.toml` に staging 用 deploy セクションを追加する。
