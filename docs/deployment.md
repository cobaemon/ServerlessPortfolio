# デプロイと CI/CD

## SAM 設定

`samconfig.toml` の default deploy parameters は次の値を含みます。

- `stack_name = "cobaemon-serverless-portfolio-stack"`
- `region = "ap-northeast-1"`
- `capabilities = "CAPABILITY_NAMED_IAM"`
- `profile = "aws_portfolio_profile"`
- `DomainName="serverless.portfolio.cobaemon.com"`
- `Env="prod"`
- `BranchName="main"`
- `TemplatePath="packaged.yaml"`

## アプリケーションテンプレート

`template.yaml` は `Env` パラメータとして `dev` と `prod` を許容します。既定値は `prod` です。

`DjangoFunction` は Python 3.12 Runtime、`x86_64` Architecture、Timeout 30 秒、MemorySize 512 MB で定義されています。

API Gateway の StageName は `prod` 環境では `prod`、それ以外では `dev` です。

## パイプライン

`pipeline.yaml` は次の CodePipeline ステージを定義します。

- `Source`
- `UpdatePipeline`
- `BuildDependencies`
- `DeployDependencies`
- `Build`
- `Deploy`

`Source` は CodeStarSourceConnection を使い、`FullRepositoryId` と `BranchName` パラメータを参照します。既定値は `cobaemon/ServerlessPortfolio` と `main` です。

`Deploy` ステージは `CloudFormationDeploy` と `BucketPolicyDeploy` を実行します。

## CodeBuild

`buildspec.yml` は Python 3.12 を使用します。

主な処理は次の通りです。

- `requirements.txt` のインストール。
- `aws-sam-cli` と `csscompressor` のインストール。
- Route53 ホストゾーンと既存 A レコードの検出。
- Django 翻訳ファイルの生成とコンパイル。
- Google Fonts から `Montserrat.ttf` と `Lato.ttf` を取得して `portfolio/static/assets/fonts` に配置。
- `portfolio/static/css/styles.css` から `styles.min.css` を生成。
- `python manage.py collectstatic --noinput`。
- `python manage.py render_static`。
- `staticfiles/` を `s3://cobaemon-serverless-portfolio-${ENV}-static/` へ同期。
- `sam build --use-container`。
- `sam package --output-template-file packaged.yaml --s3-bucket $S3Bucket`。
- `parameters.json` と `bucketpolicy-parameters.json` の生成。

`buildspec-deps.yml` は CloudFront OAC と静的ファイルバケットの存在を検出し、`deps-parameters.json` を生成します。

## 手動補助スクリプト

`deploy-deps.ps1` は既存の CloudFront OAC と S3 バケットを検出し、`dependencies.yaml` を `sam deploy` するための PowerShell スクリプトです。既定の `Env` は `prod`、既定の `StackName` は `cobaemon-portfolio-dependencies-prod`、既定の `Profile` は `aws_portfolio_profile` です。

## 関連ファイル

- [`samconfig.toml`](../samconfig.toml)
- [`template.yaml`](../template.yaml)
- [`pipeline.yaml`](../pipeline.yaml)
- [`buildspec.yml`](../buildspec.yml)
- [`buildspec-deps.yml`](../buildspec-deps.yml)
- [`deploy-deps.ps1`](../deploy-deps.ps1)
