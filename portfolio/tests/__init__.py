"""portfolio アプリのテストパッケージ.

従来は単一モジュール `portfolio/tests.py` にテストを配置していたが、CSP ハッシュ
生成（tasks.md 4.1）のプロパティテスト（tasks.md 4.2）を追加するにあたり、steering
`django-tests.md`「テストが増えた場合は `tests/` ディレクトリに分割可（`__init__.py`
を含めること）」に従いパッケージへ分割した（出典: .kiro/steering/django-tests.md）。

本パッケージの構成:
    - test_regression.py: 既存の Django リグレッションテスト（ルーティング・CSRF・
      本番設定・API Gateway ルートリダイレクト。`django.test.SimpleTestCase` 継承）。
      `python manage.py test portfolio` で従来どおり探索・実行される。
    - test_property_csp_hash.py: Property 5（CSP ハッシュ生成は nonce を含まず
      インラインの SHA-256 を含む）のプロパティテスト。検証対象 `_csp_hash.py` は
      Django 非依存のため Django をロードせず `python -m unittest` でも実行できる。
"""
