"""Contact_Function アダプタ層パッケージ.

クリーンアーキテクチャの外側（インフラ／フレームワーク連携）を収める層。
本層はドメイン層（`contact_function.domain`）が定義する抽象ポートを実装し、
AWS SDK（boto3）等の外部依存を内側へ持ち込まない方向で結合する
（依存性逆転、出典: design.md「Components and Interfaces > C3」依存規則、
requirements.md R4-6）。

依存方向は常に外側から内側（adapters → domain）へ向け、domain は本層に
依存しない（出典: design.md C3、requirements.md R4-6）。本層も Django には
依存しない（Contact_Function は Django 非依存、出典: requirements.md R4-1, R4-2）。
"""
