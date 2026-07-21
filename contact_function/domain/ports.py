"""ドメイン層のポート（抽象インターフェース）を定義するモジュール.

依存性逆転の原則（DIP）に基づき、ドメイン層が必要とする外部機能を抽象として
宣言する。具体実装（SES 送信・Parameter Store 取得）は adapters 層が提供し、
handler 層が注入する（出典: design.md「Components and Interfaces > C3」、
requirements.md R4-6）。

本モジュールは Django・adapters 層・handler 層に依存しない。また、いずれの
ポートも認証情報を引数に取らない（Cognito-ready、認証層は外側で後付け可能。
出典: design.md C3「Cognito-ready」、requirements.md R13-2）。
"""

from abc import ABC, abstractmethod

from contact_function.domain.contact_payload import ContactPayload


class EmailSender(ABC):
    """問い合わせメール送信のポート（抽象）.

    具体実装は Amazon SES v2 `SendEmail` を用いる `adapters/ses_email_sender.py`
    （別タスク）が担う（出典: design.md「Data Models > DM3」, C4）。
    ドメイン層は本抽象にのみ依存する（依存性逆転、出典: requirements.md R4-6）。
    """

    @abstractmethod
    def send(self, payload: ContactPayload, from_addr: str, to_addr: str) -> None:
        """検証済みの Contact_Payload をメール送信する.

        認証情報は引数に取らない。送信元・宛先は設定値から取得した値を受領する
        （出典: design.md DM3, DM4、requirements.md R6-7, R13-2）。

        Args:
            payload: 送信対象の問い合わせ内容（検証済み）。
            from_addr: 送信元アドレス（設定値由来）。
            to_addr: 宛先アドレス（設定値由来）。

        Returns:
            None: 送信成功時は値を返さない。

        Raises:
            Exception: 送信に失敗した場合は例外を送出する。呼び出し元はこれを
                握りつぶさず明示的に記録・伝播する（フォールバック禁止、
                出典: design.md DM3, Error Handling、requirements.md R6-4, R12-5）。
        """
        raise NotImplementedError


class ConfigProvider(ABC):
    """設定値取得のポート（抽象）.

    送信元・宛先アドレスおよび許可 Origin を設定値（Parameter Store 等）から
    取得する。具体実装は `adapters/config_provider.py`（別タスク）が担う
    （出典: design.md「Data Models > DM4」, C3）。設定値はコードにハードコード
    しない（出典: requirements.md R6-7）。取得できない場合は各メソッドが例外を
    送出する（フォールバック禁止、出典: 第三原則3、design.md Error Handling）。
    認証情報は引数に取らない（出典: requirements.md R13-2）。
    """

    @abstractmethod
    def get_from_address(self) -> str:
        """SES 送信元アドレスを取得する.

        Returns:
            str: 送信元アドレス（出典: DM4 `default_from_email`）。

        Raises:
            Exception: 設定値が欠落している場合は例外を送出する
                （フォールバック禁止、出典: requirements.md R6-7）。
        """
        raise NotImplementedError

    @abstractmethod
    def get_to_address(self) -> str:
        """SES 宛先アドレスを取得する.

        Returns:
            str: 宛先アドレス（出典: DM4 `default_to_mail`）。

        Raises:
            Exception: 設定値が欠落している場合は例外を送出する
                （フォールバック禁止、出典: requirements.md R6-7）。
        """
        raise NotImplementedError

    @abstractmethod
    def get_allowed_origins(self) -> tuple[str, ...]:
        """問い合わせ POST の許可 Origin 一覧を取得する.

        Returns:
            tuple[str, ...]: 許可 Origin の不変な列
                （出典: DM4 `csrf_trusted_origins`、requirements.md R8-1）。

        Raises:
            Exception: 設定値が欠落している場合は例外を送出する
                （フォールバック禁止、出典: requirements.md R6-7）。
        """
        raise NotImplementedError
