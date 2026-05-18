# 既知の状態

## 実装済みの主要ファイル

- Django プロジェクト: `config`
- Django アプリ: `portfolio`
- Lambda エントリーポイント: `asgi_lambda.py`
- SAM アプリケーション定義: `template.yaml`
- 依存リソース定義: `dependencies.yaml`
- パイプライン定義: `pipeline.yaml`
- CodeBuild 定義: `buildspec.yml`、`buildspec-deps.yml`
- 静的ファイルバケットポリシー定義: `bucketpolicy.yaml`

## staging 関連

`.kiro/specs/staging-environment/requirements.md` には staging 環境追加の要件文書があります。

現在の実装ファイルでは、SAM テンプレートの `Env` `AllowedValues` は `dev` と `prod` です。`config/settings/staging.py` は存在しません。

## テスト

`portfolio/tests.py` は存在しますが、テストケースは定義されていません。

## 独自モデル

`portfolio/models.py` に独自モデルは定義されていません。

## AWS 認証設定

`samconfig.toml` は `aws_portfolio_profile` を指定しています。このリポジトリ内には AWS CLI 認証情報は含まれていません。

## Git 状態

ドキュメント作成前の作業ツリーでは `.gitignore` に未コミット変更がありました。このドキュメント整備では `.gitignore` を変更対象にしていません。

## 関連ファイル

- [`.kiro/specs/staging-environment/requirements.md`](../.kiro/specs/staging-environment/requirements.md)
- [`template.yaml`](../template.yaml)
- [`dependencies.yaml`](../dependencies.yaml)
- [`pipeline.yaml`](../pipeline.yaml)
- [`bucketpolicy.yaml`](../bucketpolicy.yaml)
- [`portfolio/tests.py`](../portfolio/tests.py)
- [`portfolio/models.py`](../portfolio/models.py)
