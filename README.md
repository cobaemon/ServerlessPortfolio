# ServerlessPortfolio

Djangoベースのサーバーレスポートフォリオアプリケーションのデプロイ手順書です。

## 前提条件

- AWS CLI がインストールされていること
- AWS SAM CLI がインストールされていること
- AWS プロファイル `aws_portfolio_profile` が設定されていること
- Python 3.12 がインストールされていること

## デプロイ手順

### 1. 依存関係のデプロイ

まず、S3バケットやCloudFrontのOrigin Access Controlなどの依存リソースをデプロイします：

```bash
sam deploy --template-file dependencies.yaml \
  --stack-name cobaemon-portfolio-dependencies-prod \
  --parameter-overrides Env=prod \
  --capabilities CAPABILITY_IAM \
  --profile aws_portfolio_profile
```

### 2. CI/CDパイプラインのデプロイ

次に、CodePipelineを使用したCI/CDパイプラインをデプロイします：

```bash
sam deploy --template-file pipeline.yaml \
  --stack-name CobaemonServerlessPortfolio-Pipeline \
  --parameter-overrides Env=prod,S3Bucket=cobaemon-serverless-portfolio-prod-artifacts,StackName=cobaemon-portfolio-stack \
  --capabilities CAPABILITY_NAMED_IAM \
  --profile aws_portfolio_profile
```

### 3. ガイド付きデプロイ（初回または設定変更時）

初回デプロイ時や設定を変更する場合は、ガイド付きデプロイを使用できます：

```bash
sam deploy --template-file pipeline.yaml \
  --profile aws_portfolio_profile \
  --guided
```

## デプロイ構成

### 依存関係（dependencies.yaml）
- S3バケット（静的ファイル用）
- CloudFront Origin Access Control
- S3バケットポリシー

### CI/CDパイプライン（pipeline.yaml）
- CodePipeline（ソース、ビルド、デプロイステージ）
- CodeBuildプロジェクト
- IAMロールとポリシー

### ビルド設定（buildspec.yml）
- Python 3.12環境
- Django翻訳ファイルの生成・コンパイル
- 静的ファイルの収集とS3同期
- SAMビルドとパッケージング

## 環境変数とシークレット

アプリケーションは以下のAWS Secrets ManagerとParameter Storeを使用します：

### Secrets Manager
- `DJANGO_SECRET_KEY`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GITHUB_CLIENT_ID`
- `GITHUB_CLIENT_SECRET`

### Parameter Store
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `DEFAULT_FROM_EMAIL`
- `DEFAULT_TO_EMAIL`
- `EMAIL_HOST`
- `EMAIL_PORT`

## 注意事項

- デプロイ前に必要なシークレットとパラメータがAWS Secrets ManagerとParameter Storeに設定されていることを確認してください
- 初回デプロイ時は、依存関係を先にデプロイしてからパイプラインをデプロイしてください
- 本番環境では `Env=prod` パラメータを使用してください
