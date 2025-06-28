# ServerlessPortfolio

Djangoベースのサーバーレスポートフォリオアプリケーションです。AWS Lambda、API Gateway、CloudFront、S3を使用した完全なサーバーレスアーキテクチャで構築されています。

## 概要

このプロジェクトは、個人のポートフォリオサイトをサーバーレス環境で運用するためのDjangoアプリケーションです。以下の特徴があります：

- **サーバーレスアーキテクチャ**: AWS Lambda + API Gateway
- **静的ファイル配信**: CloudFront + S3
- **CI/CDパイプライン**: AWS CodePipeline + CodeBuild
- **多言語対応**: Django国際化機能
- **セキュリティ**: AWS Secrets Manager + Parameter Store
- **カスタムドメイン**: Route53 + ACM証明書

## 機能

- レスポンシブなポートフォリオサイト
- お問い合わせフォーム（メール送信機能）
- 多言語対応（日本語、英語、フランス語、スペイン語、ロシア語、中国語、アラビア語）
- 静的ファイルの最適化配信
- セキュアな環境変数管理

## アーキテクチャ

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   CloudFront    │    │   API Gateway   │    │   AWS Lambda    │
│   (CDN)         │    │   (REST API)    │    │   (Django App)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   S3 Bucket     │    │   Route53       │    │   Secrets       │
│   (Static Files)│    │   (DNS)         │    │   Manager       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 前提条件

- AWS CLI がインストールされていること
- AWS SAM CLI がインストールされていること
- AWS プロファイル `aws_portfolio_profile` が設定されていること
- Python 3.12 がインストールされていること
- Route53でホストゾーンが設定されていること

## セットアップ

### 1. ローカル開発環境のセットアップ

```bash
# リポジトリのクローン
git clone https://github.com/cobaemon/ServerlessPortfolio.git
cd ServerlessPortfolio

# 仮想環境の作成とアクティベート
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 依存関係のインストール
pip install -r requirements.txt

# 環境変数の設定
cp env.json.example env.json
# env.jsonを編集して必要な環境変数を設定

# データベースのマイグレーション
python manage.py migrate

# 開発サーバーの起動
python manage.py runserver
```

### 2. AWS設定

#### AWS CLIプロファイルの設定

```bash
aws configure --profile aws_portfolio_profile
```

#### 必要なAWSリソースの事前設定

以下のリソースをAWSコンソールまたはCLIで事前に設定してください：

**Secrets Manager** (`prod/portfolio/secret`):
- `DJANGO_SECRET_KEY`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GITHUB_CLIENT_ID`
- `GITHUB_CLIENT_SECRET`

**Parameter Store**:
- `/prod/portfolio/parameter/allowed_hosts`
- `/prod/portfolio/parameter/csrf_trusted_origins`
- `/prod/portfolio/parameter/default_from_email`
- `/prod/portfolio/parameter/default_to_mail`
- `/prod/portfolio/parameter/email_host`
- `/prod/portfolio/parameter/email_port`

ホストゾーンIDはデプロイ時にRoute53から自動検出されるため、Parameter Storeでの管理は不要になりました。

## デプロイ手順

### 方法1: CI/CDパイプラインを使用した自動デプロイ（推奨）

#### 1. パイプラインのデプロイ

パイプラインには `dependencies.yaml` を利用した依存リソースのデプロイ処理が含まれているため、まずパイプラインだけをデプロイします。以降はコードをプッシュするだけで自動的に依存リソースとアプリケーションが更新されます。

```bash
sam deploy --template-file pipeline.yaml --stack-name CobaemonServerlessPortfolio-Pipeline --parameter-overrides "Env=prod" "S3Bucket=cobaemon-serverless-portfolio-prod-artifacts" "StackName=cobaemon-serverless-portfolio-stack" --capabilities CAPABILITY_NAMED_IAM --profile aws_portfolio_profile
```

**注意**: パイプラインがデプロイされると、`pipeline.yaml` からパイプライン自身を更新するステージが実行され、その後 `template.yaml` を用いたアプリケーションのデプロイまで自動で行われます。以降はコードをプッシュするだけで自動的にパイプラインが更新され、最新のアプリケーションがデプロイされます。

### 方法2: 手動デプロイ

#### 1. 依存関係のデプロイ

```bash
sam deploy --template-file dependencies.yaml --stack-name cobaemon-portfolio-dependencies-prod --parameter-overrides Env=prod --capabilities CAPABILITY_IAM --profile aws_portfolio_profile
```

#### 2. メインアプリケーションの手動デプロイ

```bash
HOSTED_ZONE_ID=$(aws route53 list-hosted-zones-by-name \
  --dns-name cobaemon.com \
  --query 'HostedZones[0].Id' --output text | awk -F/ '{print $3}')
if [ -z "$HOSTED_ZONE_ID" ] || [ "$HOSTED_ZONE_ID" = "None" ]; then
  echo "Hosted zone not found for cobaemon.com" >&2
  exit 1
fi
sam deploy --template-file template.yaml \
  --stack-name cobaemon-serverless-portfolio-stack \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides Env=prod HostedZoneId=$HOSTED_ZONE_ID \
  --profile aws_portfolio_profile
```

### 設定ファイルを使用したデプロイ

`samconfig.toml`が設定されている場合は、以下のコマンドでデプロイできます：

```bash
sam deploy --guided
```

#### (任意) PowerShell スクリプトによる依存関係デプロイ

依存リソースは通常 CodePipeline から自動的にデプロイされるため、追加の作業は不要
です。何らかの理由でパイプラインを使わずにデプロイしたい場合は、`deploy-deps.ps1`
を実行すると既存のCloudFront Origin Access Control と S3 バケットを検出して
`sam deploy` を実行できます。

```powershell
./deploy-deps.ps1 -Env prod -StackName cobaemon-portfolio-dependencies-prod -Profile aws_portfolio_profile
```

### PowerShellでの実行について

上記のコマンドは1行で記述していますが、PowerShellで複数行に分けて実行したい場合は、バッククォート（`）を使用してください：

```powershell
sam deploy --template-file dependencies.yaml `
  --stack-name cobaemon-portfolio-dependencies-prod `
  --parameter-overrides Env=prod `
  --capabilities CAPABILITY_IAM `
  --profile aws_portfolio_profile
```

## デプロイ構成

### 依存関係（dependencies.yaml）
- S3バケット（静的ファイル用）
- CloudFront Origin Access Control（既存リソースの再利用可能）
- S3バケットポリシー
- **CodePipeline が既存のCloudFront Origin Access Control と S3 バケットを自動検出し、存在する場合は再利用**

### メインアプリケーション（template.yaml）
- AWS Lambda関数（Djangoアプリケーション）
- API Gateway（REST API）
- CloudFrontディストリビューション
- Route53レコード
- ACM証明書
- カスタムドメイン設定

### CI/CDパイプライン（pipeline.yaml）
- CodePipeline（ソース、ビルド、デプロイステージ）
- CodeBuildプロジェクト
- IAMロールとポリシー
- **パイプラインのデプロイステージで`template.yaml`を自動的にビルド・デプロイ**

### ビルド設定（buildspec.yml）
- Python 3.12環境
- Django翻訳ファイルの生成・コンパイル
- 静的ファイルの収集とS3同期
- SAMビルドとパッケージング
- `template.yaml`から`packaged.yaml`を生成

## 環境変数とシークレット

アプリケーションは以下のAWS Secrets ManagerとParameter Storeを使用します：

### Secrets Manager
- `DJANGO_SECRET_KEY`: Djangoの秘密鍵
- `EMAIL_HOST_USER`: メール送信用ユーザー名
- `EMAIL_HOST_PASSWORD`: メール送信用パスワード
- `GOOGLE_CLIENT_ID`: Google OAuthクライアントID
- `GOOGLE_CLIENT_SECRET`: Google OAuthクライアントシークレット
- `GITHUB_CLIENT_ID`: GitHub OAuthクライアントID
- `GITHUB_CLIENT_SECRET`: GitHub OAuthクライアントシークレット

### Parameter Store
- `ALLOWED_HOSTS`: 許可されたホスト名
- `CSRF_TRUSTED_ORIGINS`: CSRF保護の信頼できるオリジン
- `DEFAULT_FROM_EMAIL`: デフォルト送信者メールアドレス
- `DEFAULT_TO_EMAIL`: デフォルト宛先メールアドレス
- `EMAIL_HOST`: メールサーバーホスト
- `EMAIL_PORT`: メールサーバーポート

## 開発

### ローカル開発

```bash
# 開発サーバーの起動
python manage.py runserver

# 静的ファイルの収集
python manage.py collectstatic

# 翻訳ファイルの生成
python manage.py makemessages -l ja
python manage.py makemessages -l en
# 他の言語も同様

# 翻訳ファイルのコンパイル
python manage.py compilemessages
```

### テスト

```bash
# テストの実行
python manage.py test
```

### 静的ファイルの管理

```bash
# 静的ファイルの収集
python manage.py collectstatic

# S3への同期（本番環境）
aws s3 sync staticfiles/ s3://cobaemon-serverless-portfolio-prod-static/ --delete
```

## トラブルシューティング

### よくある問題

1. **デプロイエラー**
   - AWS認証情報が正しく設定されているか確認
   - 必要なIAM権限があるか確認
   - 依存関係が先にデプロイされているか確認
  - 既存のCloudFront Origin Access Control や静的ファイルバケットが残っている場合、
    CodePipeline が自動で検出して再利用します。パイプラインを使わない場合は、
    `deploy-deps.ps1` を実行して同じ動作を行えます。

2. **静的ファイルが表示されない**
   - CloudFrontディストリビューションの設定を確認
   - S3バケットのポリシーを確認
   - Origin Access Controlの設定を確認

3. **メール送信エラー**
   - Secrets Managerの設定を確認
   - メールサーバーの設定を確認
   - ネットワーク設定を確認

4. **ドメインが解決できない**
   - `serverless.portfolio.cobaemon.com` が NXDOMAIN となる場合、Route53 に正しい A レコードが作成されているか確認
   - ホストゾーン自体が存在しない場合は、`cobaemon.com` 用のホストゾーンを作成し、スタックを再デプロイ
   - 再デプロイ後に A レコードが消える場合は、CodeBuild の環境変数 `EXISTING_ARECORD` を `false` に固定する
   - DNS 反映まで最大 48 時間かかることがあるため、変更後しばらく待ってから再度アクセスする

### ログの確認

```bash
# CloudWatchログの確認
aws logs describe-log-groups --profile aws_portfolio_profile
aws logs tail /aws/lambda/CobaemonServerlessPortfolioFunction --profile aws_portfolio_profile
```

## パフォーマンス最適化

- CloudFrontによる静的ファイルのキャッシュ
- Lambda関数のメモリとタイムアウト設定の最適化
- 画像の最適化（Pillow AVIFプラグイン使用）
- データベース接続の最適化

## セキュリティ

- AWS Secrets Managerによる機密情報の管理
- Parameter Storeによる設定値の管理
- CORS設定によるクロスオリジン制御
- CSRF保護の実装
- Content Security Policy (CSP) の実装

## 監視とログ

- CloudWatch Logsによるログ管理
- CloudWatch Metricsによるメトリクス監視
- API Gatewayのアクセスログ
- CloudFrontのアクセスログ

## 注意事項

- デプロイ前に必要なシークレットとパラメータがAWS Secrets ManagerとParameter Storeに設定されていることを確認してください
- **CI/CDパイプラインを使用する場合**: パイプラインを一度デプロイすれば、依存リソースとメインアプリケーションの両方が自動的に展開・更新されます
- **手動デプロイの場合**: 依存関係→メインアプリケーションの順序でデプロイしてください
- **既存リソースの自動検出**: CodePipeline がCloudFront Origin Access ControlとS3バケットを検出し、既存のものがあれば再利用します。見つからない場合はビルドステップが自動的にOACを作成し、そのIDをCloudFormationに渡します。パイプラインを使わない場合は `deploy-deps.ps1` を実行してください
- CloudFront への操作はグローバルリージョン(us-east-1)で実行する必要があるため、
  ビルドプロジェクトでは `AWS_DEFAULT_REGION=us-east-1` を設定しています
- 本番環境では `Env=prod` パラメータを使用してください
- カスタムドメインを使用する場合は、Route53でホストゾーンが設定されていることを確認してください

## ライセンス

このプロジェクトは [GNU General Public License v3.0](LICENSE) の下で公開されています。

## 貢献

プルリクエストやイシューの報告を歓迎します。貢献する前に、以下の手順に従ってください：

1. このリポジトリをフォーク
2. 機能ブランチを作成 (`git checkout -b feature/amazing-feature`)
3. 変更をコミット (`git commit -m 'Add some amazing feature'`)
4. ブランチにプッシュ (`git push origin feature/amazing-feature`)
5. プルリクエストを作成

## 作者

- **cobaemon** - *初期開発* - [GitHub](https://github.com/cobaemon)

## 謝辞

- Django コミュニティ
- AWS SAM チーム
- オープンソースコミュニティ