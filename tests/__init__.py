"""リポジトリ横断テストパッケージ.

本パッケージは、特定の Django アプリや `contact_function` パッケージに属さない
横断的テスト（IaC のスナップショット/ポリシーテスト等）を収容する。

`python -m unittest tests.iac.test_template_policies` の形式でテストを探索・実行
できるようにするためのパッケージマーカーであり、実行時ロジックは持たない
（出典: tasks.md 5.5、既存 `contact_function/tests/__init__.py` と同一方針）。

注記: 既存の `tests/self_test.py` は `python tests/self_test.py` としてスクリプト
直接実行される（`tests/self_test.py` 冒頭の sys.path 操作参照）。本 `__init__.py` の
追加はスクリプト直接実行に影響しない（パス実行時 Python は当該ファイルを
`__main__` として実行するため）。
"""
