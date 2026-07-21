"""問い合わせ送信ユースケースと ContactResult を定義するモジュール.

検証済みの問い合わせ入力を Email_Sender ポートへ引き渡す送信ユースケースと、
その処理結果を型安全に表す `ContactResult`（出典: design.md「Data Models >
DM2」）を提供する。本モジュールはドメイン最内層に属し、Django・adapters 層・
handler 層のいずれにも依存しない。依存は抽象ポート `ports.EmailSender`
（DM3）にのみ向ける（依存性逆転、出典: design.md C3、requirements.md R4-6）。

処理方針（出典: design.md C3, DM2, Error Handling、requirements.md R4-4,
R6-4, R6-5, R6-6, R12-5）:
    - 入力検証（`validators.validate_contact_input`）が成功した場合にのみ
      Contact_Payload を構築し Email_Sender へ引き渡す（R4-4）。
    - 検証失敗時は送信せず `ValidationError`（不備対象項目付）を返す（R5 系）。
    - Email_Sender の送信が例外を送出した場合、当該例外を握りつぶさず
      `exc_info` 付きで明示ログ記録した上で `SendFailed` を返し、呼び出し元へ
      失敗を伝播する。成功として扱わない（フォールバック禁止、R6-4, R6-5,
      R12-5）。
    - 送信成功時は `Success` を返す（R6-6）。

GDPR データ最小化（出典: requirements.md R5-1, R9-5、design.md DM1）に従い、
Contact_Payload には 4 項目（full_name, email, phone_number, message）のみを
明示的に引き渡し、それ以外のフィールドを送信内容として流入させない。

`OriginRejected` / `HoneypotRejected` の判定は handler 層（別タスク 2.x）の
責務であり本ユースケースでは生成しないが、`ContactResult` 型は DM2 に従い
これらの結果も表現できるよう定義する（出典: design.md DM2, C7）。
"""

import logging
from dataclasses import dataclass, field

from contact_function.domain.contact_payload import ContactPayload
from contact_function.domain.ports import EmailSender
from contact_function.domain.validators import validate_contact_input

# ログ出力は標準ライブラリ logging を使用し、モジュール単位のロガーを取得する
# （出典: design.md Error Handling、.kiro/steering/coding-conventions.md
# 「logger = logging.getLogger(__name__)」パターン）。
logger = logging.getLogger(__name__)


# frozen=True で生成後の再代入を禁止し不変性を保証する。slots=True で
# __slots__ を定義し余剰属性の追加を型レベルで禁止する（既存の値オブジェクト
# 実装と一貫させる、出典: contact_payload.py / validators.py の実装様式）。
@dataclass(frozen=True, slots=True)
class ContactResult:
    """問い合わせ送信処理の結果を表す基底型（sealed hierarchy の根）.

    実際の結果は本クラスを継承する各サブクラス（`Success` /
    `ValidationError` / `OriginRejected` / `HoneypotRejected` /
    `SendFailed`）のいずれかのインスタンスとして表現される
    （出典: design.md「Data Models > DM2」）。HTTP ステータスへのマッピングは
    handler 層が行い、本型は結果の意味のみを保持する（出典: design.md C3,
    DM2）。付随情報を持たない結果は本基底型のサブクラスとして空定義する。
    """


@dataclass(frozen=True, slots=True)
class Success(ContactResult):
    """検証成功かつ SES 送信成功を表す結果（HTTP 200 系へマッピング）.

    出典: design.md DM2、requirements.md R6-6。付随情報を持たない終端結果。
    """


@dataclass(frozen=True, slots=True)
class ValidationError(ContactResult):
    """入力検証失敗を表す結果（HTTP 400 系へマッピング）.

    不備の対象項目名を保持し、handler 層がエラー内容へ反映する
    （出典: design.md DM2、requirements.md R5-2〜R5-6, R5-1）。

    Attributes:
        fields: 不備の対象となったフィールド名の不変な列。
    """

    # 不備対象フィールド名の不変な列（既定は空タプル。不変性のため tuple 型）。
    fields: tuple[str, ...] = field(default=())


@dataclass(frozen=True, slots=True)
class OriginRejected(ContactResult):
    """Origin 不正・欠落・空による拒否を表す結果（HTTP 4xx へマッピング）.

    本結果は handler 層（別タスク 2.x）の Origin 検証で生成される
    （出典: design.md DM2, C7、requirements.md R8-2, R8-3）。本ユースケースは
    生成しないが、DM2 に従い型として表現できるよう定義する。
    """


@dataclass(frozen=True, slots=True)
class HoneypotRejected(ContactResult):
    """ハニーポット発火による拒否を表す結果（HTTP 4xx へマッピング）.

    隠しフィールドに値が存在する（ボット自動投稿）場合に handler 層
    （別タスク 2.x）で生成される（出典: design.md DM2, C7、requirements.md
    R8-6, R9-5）。本ユースケースは生成しないが、DM2 に従い型として表現できる
    よう定義する。
    """


@dataclass(frozen=True, slots=True)
class SendFailed(ContactResult):
    """SES 送信失敗を表す結果（HTTP 500 系へマッピング）.

    例外を握りつぶさず、呼び出し元が明示的にログ記録・通知できるよう失敗の
    文脈（エラーメッセージ）を保持する（フォールバック禁止、出典: design.md
    DM2, Error Handling、requirements.md R6-4, R6-5, R12-5）。

    Attributes:
        error: 送信失敗時の例外に由来するエラーメッセージ（文脈情報）。
    """

    # 送信失敗時の例外由来メッセージ（呼び出し元での通知・記録用）。
    error: str


def send_contact(
    fields: dict[str, str],
    from_addr: str,
    to_addr: str,
    email_sender: EmailSender,
) -> ContactResult:
    """問い合わせ入力を検証し、成功時のみ Email_Sender へ引き渡すユースケース.

    依存性逆転（DIP）に従い、具体的な送信実装ではなく抽象ポート
    `EmailSender` にのみ依存する（出典: design.md C3, DM3、requirements.md
    R4-6）。検証は `validators.validate_contact_input` に委譲し、成功時のみ
    Contact_Payload を構築して送信する（R4-4）。

    処理の流れ（出典: design.md C3, DM2, Error Handling）:
        1. 入力を検証する。不備があれば送信せず `ValidationError` を返す。
        2. 検証成功時、4 項目のみで Contact_Payload を構築する（GDPR データ
           最小化、R5-1, R9-5）。
        3. Email_Sender へ引き渡す。例外送出時は握りつぶさず `exc_info` 付きで
           ログ記録し `SendFailed` を返す（R6-4, R6-5, R12-5）。
        4. 送信成功時は `Success` を返す（R6-6）。

    Args:
        fields: 問い合わせ入力のフィールド名から値へのマッピング。handler 層が
            リクエストから変換し、ハニーポット等の非内容フィールドを除去した
            上で渡す（出典: design.md C3, C7）。
        from_addr: SES 送信元アドレス（設定値由来、ハードコードしない。
            出典: design.md DM4、requirements.md R6-7）。
        to_addr: SES 宛先アドレス（設定値由来）。
        email_sender: 送信を担う抽象ポート実装（handler 層が注入する具体
            実装、出典: design.md C3, DM3）。

    Returns:
        ContactResult: 処理結果。検証失敗時は `ValidationError`、送信失敗時は
            `SendFailed`、送信成功時は `Success`。
    """
    # 入力検証（純粋関数）。不備は例外ではなく結果として得る（R5 系）。
    validation = validate_contact_input(fields)
    if not validation.is_valid:
        # 送信せず不備対象項目を添えて検証失敗を返す（R5-2〜R5-6, R5-1）。
        return ValidationError(fields=validation.invalid_fields)

    # 検証成功後、4 項目のみを明示的に取り出して Contact_Payload を構築する。
    # 余剰フィールドは検証で不備扱いとなるためここには到達せず、4 項目以外が
    # 送信内容へ流入しないことを保証する（GDPR データ最小化、R5-1, R9-5）。
    payload = ContactPayload(
        full_name=fields["full_name"],
        email=fields["email"],
        phone_number=fields["phone_number"],
        message=fields["message"],
    )

    try:
        # 検証成功時のみ送信を実行する（R4-4）。認証情報は渡さない（R13-2）。
        email_sender.send(payload, from_addr, to_addr)
    except Exception as exc:
        # 例外を握りつぶさず exc_info 付きで明示記録し、失敗として伝播する。
        # 成功応答は返さない（フォールバック禁止、R6-4, R6-5, R12-5）。
        # 個人データ（payload の内容）はログに出力しない（GDPR、R9-5）。
        logger.error("SES 送信に失敗しました。", exc_info=True)
        return SendFailed(error=str(exc))

    # 送信成功（R6-6）。
    return Success()
