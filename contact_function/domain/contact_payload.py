"""Contact_Payload 値オブジェクトを定義するモジュール.

問い合わせ送信で受け付ける個人データを表す不変の値オブジェクトを提供する。
GDPR のデータ最小化（出典: requirements.md R5-1, R9-5）に従い、氏名・メール
アドレス・電話番号・メッセージの 4 項目のみを保持し、これら以外のフィールドを
保持・処理しない（出典: design.md「Data Models > DM1」）。

本モジュールはドメイン最内層に属し、Django・adapters 層・handler 層・認証情報の
いずれにも依存しない（出典: design.md C3、requirements.md R4-6, R13-2）。
なお入力値の検証規則（形式・最大文字数等）は `validators.py`（別タスク）が担う。
本モジュールは値の保持と不変性・項目限定の保証のみを責務とする（SRP）。
"""

from dataclasses import dataclass


# frozen=True で生成後の再代入を禁止し不変性を保証する。
# slots=True で __slots__ を定義し、4 項目以外の属性追加を型レベルで禁止する
# （4 項目限定の保証、出典: design.md DM1「4 項目以外は処理対象にしない」）。
@dataclass(frozen=True, slots=True)
class ContactPayload:
    """問い合わせ内容を表す不変の値オブジェクト.

    保持する項目は次の 4 項目のみであり、これ以外のフィールドは保持しない
    （GDPR データ最小化、出典: requirements.md R5-1, R9-5、design.md DM1）。

    Attributes:
        full_name: 氏名（出典: DM1、既存 ContactForm.full_name と整合）。
        email: メールアドレス（出典: DM1）。
        phone_number: 電話番号（出典: DM1、既存 ContactForm.phone_number と整合）。
        message: 問い合わせ本文（出典: DM1）。
    """

    # 氏名（必須・非空。文字数上限等の検証は validators.py が担う）。
    full_name: str
    # メールアドレス（必須・電子メール形式。検証は validators.py が担う）。
    email: str
    # 電話番号（必須・数字のみ。検証は validators.py が担う）。
    phone_number: str
    # 問い合わせ本文（必須・非空。検証は validators.py が担う）。
    message: str
