"""Email_Sender（Amazon SES v2 直連携）実装モジュール.

問い合わせメールを Amazon SES v2 `SendEmail` API で送信する具象アダプタを提供する。
ドメイン層の抽象ポート `contact_function.domain.ports.EmailSender` を実装し、依存方向は
adapters → domain の一方向のみとする（依存性逆転、出典: design.md「Components and
Interfaces > C3」依存規則, DM3、requirements.md R4-6）。SMTP を廃し SESv2 へ直連携する
（出典: design.md C4「SES 直連携」、requirements.md R6-1）。

設計上の遵守事項:
  - 送信元／宛先アドレスは呼び出し元（設定値由来）から引数で受領し、コードに
    ハードコードしない（出典: design.md DM3, C4、requirements.md R6-7）。
  - 送信失敗時は例外を握りつぶさず `logger.error(..., exc_info=True)` で明示ログ記録した
    うえで呼び出し元へ例外を伝播する（フォールバック禁止、出典: design.md DM3, C4,
    Error Handling、requirements.md R6-4、第三原則3）。現行 `portfolio/forms.py`
    `ContactForm.send_email` は例外時に `False` を返す握りつぶし実装（出典: E-5）であり、
    本実装ではこれを行わない。
  - 個人データ（Contact_Payload の内容: 氏名・メール・電話・本文）はログに出力しない
    （GDPR データ最小化、出典: requirements.md R9-5、design.md C4 失敗時ログ方針）。
  - リージョンは実行環境（Lambda の `AWS_REGION` 等）から boto3 が解決するため本コードで
    指定しない（ハードコード回避、出典: design.md C4、requirements.md R6-7）。なお SES の
    identity 検証は ap-northeast-1 前提（出典: design.md C4）。
  - Django・handler 層に依存しない（クリーンアーキテクチャ、出典: design.md C3、
    requirements.md R4-1, R4-2）。

外部ライセンス（第二原則6・実行前原則の遵守）:
  - 本モジュールは AWS SDK for Python（boto3 / botocore）を使用する。
  - boto3 のライセンスは Apache License 2.0（環境内 `importlib.metadata` により
    `License: Apache-2.0` を確認済み、boto3 1.42.63）。Apache-2.0 は本用途での
    利用・再配布を許諾する。
"""

import logging

import boto3  # AWS SDK for Python（ライセンス: Apache License 2.0、着手時に確認済み）
from botocore.exceptions import BotoCoreError, ClientError

from contact_function.domain.contact_payload import ContactPayload
from contact_function.domain.ports import EmailSender

# ロガーはモジュール単位で取得する（出典: coding-conventions.md「logger = logging.getLogger(__name__)」）
logger = logging.getLogger(__name__)

# SES v2 クライアントのサービス名（AWS SDK の契約であり設定値ではない）。
# 出典: boto3 SESv2（`sesv2`）クライアント、design.md C4「SESv2 SendEmail」。
_SES_SERVICE_NAME = "sesv2"

# メール本文の文字セット。日本語（多バイト）を正しく送信するため UTF-8 を明示する。
_CHARSET_UTF8 = "UTF-8"


class SesEmailSender(EmailSender):
    """Amazon SES v2 `SendEmail` で問い合わせメールを送信する `EmailSender` 具象実装.

    ドメイン層の抽象ポート `EmailSender` を実装する（出典: design.md DM3, C4、
    requirements.md R6-1）。送信元・宛先は `send` の引数（設定値由来）で受領し、
    認証情報は引数に取らない（Cognito-ready、出典: design.md C3、requirements.md R13-2）。

    依存性逆転とテスト容易性のため、SES クライアントはコンストラクタで注入可能とする
    （SOLID / DIP、出典: 第二原則3、`config_provider.py` の注入方針と整合）。既定では
    boto3 の SESv2 クライアントを生成する。
    """

    def __init__(self, ses_client: object | None = None) -> None:
        """SES 送信アダプタを初期化する.

        Args:
            ses_client: SES v2 クライアント（依存性注入用）。None の場合は boto3 で
                生成する。リージョンは実行環境（Lambda の `AWS_REGION` 等）から boto3 が
                解決するため本コードでは指定しない（ハードコード回避、出典: design.md C4、
                requirements.md R6-7）。

        Returns:
            None: 初期化のみを行い値を返さない。
        """
        # クライアントは注入値を優先し、無ければ boto3 で生成する。
        # クライアント生成自体は認証情報を要求しない（実際の API 呼び出し時に必要）。
        self._ses_client = (
            ses_client if ses_client is not None else boto3.client(_SES_SERVICE_NAME)
        )

    def send(self, payload: ContactPayload, from_addr: str, to_addr: str) -> None:
        """検証済みの Contact_Payload を Amazon SES v2 でメール送信する.

        件名・本文は Contact_Payload の 4 項目（full_name, email, phone_number, message）
        から日本語で組み立てる（現行 `portfolio/forms.py` の送信内容と整合、出典: E-5、
        design.md C4）。認証情報は引数に取らない（出典: requirements.md R13-2）。

        Args:
            payload: 送信対象の問い合わせ内容（検証済み、出典: design.md DM1）。
            from_addr: 送信元アドレス（設定値由来、出典: DM4 `default_from_email`）。
            to_addr: 宛先アドレス（設定値由来、出典: DM4 `default_to_mail`）。

        Returns:
            None: 送信成功時は値を返さない。

        Raises:
            Exception: SES 送信に失敗した場合は例外を握りつぶさず、明示ログ記録の上で
                呼び出し元へ伝播する（フォールバック禁止、出典: design.md DM3, C4,
                Error Handling、requirements.md R6-4、第三原則3）。
        """
        # 件名・本文を 4 項目から組み立てる。本文の構成は現行フォーム送信内容
        # （氏名・メール・電話・本文の順）と整合させる（出典: portfolio/forms.py, E-5）。
        subject = self._build_subject(payload)
        body = self._build_body(payload)

        try:
            # SES v2 `SendEmail` の Simple 形式で送信する。
            # 日本語を正しく送るため件名・本文とも Charset に UTF-8 を明示する。
            self._ses_client.send_email(
                FromEmailAddress=from_addr,
                Destination={"ToAddresses": [to_addr]},
                Content={
                    "Simple": {
                        "Subject": {"Data": subject, "Charset": _CHARSET_UTF8},
                        "Body": {"Text": {"Data": body, "Charset": _CHARSET_UTF8}},
                    }
                },
            )
        except (ClientError, BotoCoreError):
            # 送信失敗（権限不足・未検証 identity・サンドボックス制限・通信失敗等）は
            # 握りつぶさず、exc_info で一次原因を明示ログ記録する。個人データ（payload の
            # 内容）はログに出力しない（GDPR、出典: requirements.md R9-5, R6-4）。
            logger.error("SES によるメール送信に失敗しました", exc_info=True)
            # 例外を呼び出し元へ伝播し、ユースケース／ハンドラ側で失敗として扱わせる
            # （フォールバック禁止、出典: requirements.md R6-4, R6-5, R12-5）。
            raise

        # 送信成功。個人データを含めず、成功事実のみを記録する（出典: R9-5）。
        logger.info("問い合わせメールを SES で送信しました")

    def _build_subject(self, payload: ContactPayload) -> str:
        """Contact_Payload から日本語のメール件名を組み立てる.

        現行 `portfolio/forms.py` の件名（`Contact form submission from {full_name}`）と
        整合する意図で、送信者氏名を含む日本語件名を構成する（出典: E-5）。

        Args:
            payload: 送信対象の問い合わせ内容（検証済み）。

        Returns:
            str: 送信者氏名を含む日本語のメール件名。
        """
        # 送信者氏名を件名に含め、問い合わせ由来であることを明示する。
        return f"お問い合わせフォームからの送信: {payload.full_name}"

    def _build_body(self, payload: ContactPayload) -> str:
        """Contact_Payload の 4 項目から日本語のメール本文を組み立てる.

        本文の項目構成（氏名・メール・電話・本文）は現行 `portfolio/forms.py` の
        送信内容と整合させる（出典: E-5、design.md C4）。

        Args:
            payload: 送信対象の問い合わせ内容（検証済み、4 項目）。

        Returns:
            str: 4 項目を含む日本語のメール本文（テキスト形式）。
        """
        # 現行フォーム送信内容と同じ項目順（氏名→メール→電話→本文）で本文を構成する。
        return (
            f"氏名: {payload.full_name}\n"
            f"メールアドレス: {payload.email}\n"
            f"電話番号: {payload.phone_number}\n\n"
            f"お問い合わせ内容:\n{payload.message}"
        )
