"""旧資産除去（legacy-asset-cleanup）判定層のテストパッケージ.

本パッケージは `scripts/cleanup/` 配下の判定層モジュールに対する
例ベース単体テストおよびプロパティベーステスト（PBT）を収める名前空間である
（出典: `.kiro/specs/legacy-asset-cleanup/design.md`「Testing Strategy > 二層
構成」、同 tasks.md 1.3〜1.5、3.2、3.4、3.6、3.7、4.2、4.3、4.5）。

判定層は Django・boto3・ファイル I/O に依存しないため、本パッケージのテストは
Django セットアップなしで判定ロジックを検証できる（出典: design.md
「Architecture > 依存方向」）。

既存 `tests/measurement/` および `tests/iac/` と一貫して標準ライブラリ
`unittest` を用い、PBT には `hypothesis==6.158.0`（MPL-2.0、出典:
`requirements-dev.txt:18`。本ファイル作成時に
`Select-String -Path requirements-dev.txt -Pattern '^hypothesis=='` で再確認した
実体値。tasks.md の記載 `requirements-dev.txt:19` との差異は行番号のみ）を用いる。
"""
