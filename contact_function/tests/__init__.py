"""Contact_Function のテストパッケージ.

本パッケージはドメイン純粋ロジックおよびアダプタ/ハンドラのテストを保持する。
テストは Django をロードせずに実行できる（出典: requirements.md R4-1, R4-2、
design.md「Testing Strategy」）。プロパティテスト（PBT）は Hypothesis
（MPL-2.0、出典: requirements-dev.txt）を用い、design.md「Correctness
Properties」の各プロパティを 1 テスト・最小 100 反復で検証する。

実行コマンド（プロジェクトルートから、Django 非ロード）:
    python -m unittest discover -s contact_function/tests -p "test_*.py"
または個別モジュール:
    python -m unittest contact_function.tests.test_property_valid_payload
"""
