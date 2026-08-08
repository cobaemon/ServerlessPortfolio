# 既知の状態

## 実装済みの主要ファイル

- Django プロジェクト: `config`（ビルド時の静的化と設定検証に使用）
- Django アプリ: `portfolio`
- 問い合わせ用 Lambda: `contact_function/`（エントリーポイントは `contact_function/handler.py` の `lambda_handler`。出典: `template.yaml` の `ContactFunction.Handler`）
- 表示ページ静的化コマンド: `portfolio/management/commands/render_static.py`（7 言語分の事前レンダリングと統一 CSP 生成）
- SAM アプリケーション定義: `template.yaml`
- 依存リソース定義: `dependencies.yaml`
- パイプライン定義: `pipeline.yaml`
- CodeBuild 定義: `buildspec.yml`、`buildspec-deps.yml`
- 静的ファイルバケットポリシー定義: `bucketpolicy.yaml`

## Django 表示経路の退役（反映済み）

表示ページは S3 + CloudFront の静的配信で、動的経路は `POST /portfolio/contact`（`ContactApi` → `ContactFunction`）のみです。Django 実行用 Lambda（`DjangoFunction`）、API Gateway REST API（`DjangoApi`）、API Gateway カスタムドメイン、REGIONAL の ACM 証明書は `template.yaml` から除去され、staging・prod の両スタックで削除が完了しています（出典: [`development-records/unused-resource-removal-django-retirement.md`](development-records/unused-resource-removal-django-retirement.md) 第 8.2・8.3 節。`aws cloudformation describe-stack-resources` / `aws lambda list-functions` / `aws apigateway get-rest-apis` / `aws apigateway get-domain-names` の実測）。

Mangum ベースの Lambda エントリーポイント `asgi_lambda.py` と SAM ビルド生成物 `.aws-sam/build.toml` は git 追跡下から除去済みです（出典: `git ls-files -- asgi_lambda.py .aws-sam/` の一致 0 件。`.aws-sam/` は `.gitignore:173` により以後も追跡対象外）。実行時の Lambda 関数は `ContactFunction` のみで、ハンドラは `contact_function.handler.lambda_handler` です（出典: `template.yaml:171`、`template.yaml:174`）。

## CodePipeline trigger

`pipeline.yaml` は CodePipeline V2 trigger を定義しています。

`docs/**`、`AGENTS.md`、`scripts/branch-finalize-next.ps1`、`README.md`、`LICENSE` だけを含む push は pipeline を起動しません。

除外対象外の path を含む push は pipeline 起動対象です。未知の root file は pipeline 起動側に倒します。

## staging 関連

staging 環境は `Env=staging` として実装されています。

staging 用の値方針は [`staging-values-policy.md`](staging-values-policy.md) に記載しています。

staging のデプロイ、確認、ロールバック、影響範囲は [`staging-deployment-runbook.md`](staging-deployment-runbook.md) に記載しています。

## テスト

`portfolio/tests/test_regression.py` には問い合わせフォーム、CSRF、URL routing、production static storage settings の回帰テストが定義されています（`portfolio/tests.py` は `portfolio/tests/` パッケージへ移行済み。出典: `portfolio/tests/` の構成）。

これに加えて次のテストがあります（出典: 各ディレクトリ）。

- `tests/iac/`: `template.yaml` / `buildspec.yml` のポリシー・スナップショットテスト（SnapStart 不在、SES 最小権限、OAC 限定、CSP と HTTPS 強制、スロットリング、退役リソースの不在、未解決参照の不在など）。
- `tests/measurement/`: コスト帰属・実測・非退行検証スクリプトのテスト。
- `tests/self_test.py` と `python -m scripts.control_platform.cli --self-test`: Control Platform の self-test。
- `contact_function/tests/`: Contact_Function のドメイン/アダプタ単体テストとプロパティテスト。
- `portfolio/tests/test_render_static.py`、`test_property_csp_hash.py`、`test_property_csp_allowlist.py`: 静的化と CSP 生成のテスト。

## ローカル Docker 環境

`Dockerfile` と `compose.yaml` は、`config.settings.dev` を使用するローカル検証環境を定義しています。手順は [`local-docker.md`](local-docker.md) に記載しています。

## 独自モデル

`portfolio/models.py` に独自モデルは定義されていません。

## AWS 認証設定

`samconfig.toml` は `aws_portfolio_profile` を指定しています。このリポジトリ内には AWS CLI 認証情報は含まれていません。

## 関連ファイル

- [`.kiro/specs/staging-environment/requirements.md`](../.kiro/specs/staging-environment/requirements.md)
- [`Dockerfile`](../Dockerfile)
- [`compose.yaml`](../compose.yaml)
- [`template.yaml`](../template.yaml)
- [`dependencies.yaml`](../dependencies.yaml)
- [`pipeline.yaml`](../pipeline.yaml)
- [`bucketpolicy.yaml`](../bucketpolicy.yaml)
- [`contact_function/handler.py`](../contact_function/handler.py)
- [`portfolio/tests/test_regression.py`](../portfolio/tests/test_regression.py)
- [`portfolio/models.py`](../portfolio/models.py)
