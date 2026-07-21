"""Contact_Function パッケージ.

問い合わせ送信の動的処理を担う Django 非依存の軽量サーバーレス実行単位.
本パッケージはクリーンアーキテクチャに従い、内側（ドメイン層）から外側
（アダプタ層・ハンドラ層）へと構成する。依存方向は常に外側から内側へ向け、
ドメイン層は Django・adapters・handler に依存しない
（出典: design.md「Components and Interfaces > C3」、requirements.md R4-6）。
"""
