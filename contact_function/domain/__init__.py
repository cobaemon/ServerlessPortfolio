"""Contact_Function ドメイン層パッケージ.

問い合わせ送信の純粋なビジネスロジック（値オブジェクト・検証・ユースケース・
ポート抽象）を収める最内層。本層は Django・adapters 層・handler 層に依存せず、
抽象（ポート）にのみ依存する（依存性逆転、出典: design.md C3、requirements.md
R4-6, R13-2）。認証情報にも依存しない（Cognito-ready、出典: requirements.md R13-2）。
"""
