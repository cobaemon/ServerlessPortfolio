"""計測・検証スクリプトのテストパッケージ.

本パッケージは `scripts/measurement/` 配下の計測・検証スクリプト
（cost-performance-optimization spec の tasks.md 8. 系）に対する
例ベース単体テスト・スモークテストを収める名前空間である（出典:
design.md「Testing Strategy > 単体/例ベーステスト・統合/スモーク」、
同「PBT 適用可否評価」＝実測系は PBT 不適合・例ベース/スモークで担保）。

既存 IaC テスト（`tests/iac/`）と一貫して標準ライブラリ `unittest` を用いる。
"""
