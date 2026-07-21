"""設定値プロバイダ（AWS Systems Manager Parameter Store）実装モジュール.

Contact_Function が必要とする設定値（SES 送信元／宛先アドレス、問い合わせ POST の
許可 Origin）を AWS Systems Manager Parameter Store から取得する具象アダプタを
提供する。ドメイン層の抽象ポート `contact_function.domain.ports.ConfigProvider`
を実装し、依存方向は adapters → domain の一方向のみとする（依存性逆転、
出典: design.md「Components and Interfaces > C3」依存規則、requirements.md R4-6）。

パラメータパスは design.md「Data Models > DM4」に定義された次のキーを用いる
（出典: design.md DM4、`template.yaml` の SSM 参照定義）。
  - `/${Env}/portfolio/parameter/default_from_email` : SES 送信元
  - `/${Env}/portfolio/parameter/default_to_mail`     : SES 宛先
  - `/${Env}/portfolio/parameter/csrf_trusted_origins`: 許可 Origin / CORS

設計上の遵守事項:
  - 設定値および環境名はコードにハードコードしない（出典: requirements.md R6-7、
    第三原則・共通解釈規則）。値は環境変数と Parameter Store からのみ取得する。
  - 設定値が欠落・空・取得失敗の場合はフォールバックせず、専用例外
    `ConfigurationError` を送出して明示的に失敗させる（フォールバック禁止、
    出典: design.md「Error Handling」設定値欠落行、requirements.md R6-7、第三原則3）。
    これは現行 `config/settings/prod.py` の `ImproperlyConfigured` パターンと同等の
    意図だが、Contact_Function は Django 非依存のため Django は import しない
    （出典: requirements.md R4-1, R4-2）。
  - Django・handler 層に依存しない（クリーンアーキテクチャ、出典: design.md C3）。

外部ライセンス（第二原則6・実行前原則の遵守）:
  - 本モジュールは AWS SDK for Python（boto3 / botocore）を使用する。
  - boto3 のライセンスは Apache License 2.0（環境内 `importlib.metadata` により
    `License: Apache-2.0` を確認済み、boto3 1.42.63）。Apache-2.0 は本用途での
    利用・再配布を許諾する。
"""

import logging
import os

import boto3  # AWS SDK for Python（ライセンス: Apache License 2.0、着手時に確認済み）
from botocore.exceptions import BotoCoreError, ClientError

from contact_function.domain.ports import ConfigProvider

# ロガーはモジュール単位で取得する（出典: coding-conventions.md「logger = logging.getLogger(__name__)」）
logger = logging.getLogger(__name__)

# 環境名を供給する環境変数名（値そのものはハードコードせず環境から取得する）。
# 出典: design.md DM4 のパス `/${Env}/...`、`template.yaml` `Env`/`ENV` 定義。
_ENV_VARIABLE_NAME = "ENV"

# Parameter Store のパス構成要素（設計 DM4 の契約であり設定値そのものではない）。
# 出典: design.md「Data Models > DM4」、`template.yaml` の SSM 参照定義。
_PARAMETER_PATH_TEMPLATE = "/{env}/portfolio/parameter/{name}"
_PARAM_NAME_FROM_EMAIL = "default_from_email"
_PARAM_NAME_TO_EMAIL = "default_to_mail"
_PARAM_NAME_TRUSTED_ORIGINS = "csrf_trusted_origins"

# `csrf_trusted_origins` は複数値をカンマ区切りで格納する（現行 `config/settings/prod.py`
# の `CSRF_TRUSTED_ORIGINS = csrf_trusted_origins.split(",")` と整合、requirements.md R8-1）。
_ORIGIN_DELIMITER = ","


class ConfigurationError(Exception):
    """設定値の欠落・空・取得失敗を表す専用例外.

    フォールバック禁止の原則に基づき、設定値を安全な既定値で代替せず本例外を
    送出して明示的に失敗させるために用いる（出典: design.md「Error Handling」、
    requirements.md R6-7、第三原則3）。Django の `ImproperlyConfigured` に相当する
    意図を、Django 非依存で表現する（出典: requirements.md R4-1, R4-2）。
    """


class SsmConfigProvider(ConfigProvider):
    """Parameter Store から設定値を取得する `ConfigProvider` 具象実装.

    ドメイン層の抽象ポート `ConfigProvider` を実装し、SES 送信元／宛先および
    許可 Origin を AWS Systems Manager Parameter Store から取得する
    （出典: design.md C3, DM4、requirements.md R6-7, R8-1）。

    依存性逆転とテスト容易性のため、環境名と SSM クライアントはコンストラクタで
    注入可能とする（SOLID / DIP、出典: 第二原則3）。既定では環境変数 `ENV` から
    環境名を解決し、boto3 の SSM クライアントを生成する。
    """

    def __init__(self, env: str | None = None, ssm_client: object | None = None) -> None:
        """設定値プロバイダを初期化する.

        Args:
            env: 環境名（dev/prod 等）。None の場合は環境変数 `ENV` から取得する。
                値をハードコードしないため既定のフォールバック値は設けない
                （出典: requirements.md R6-7、第三原則3）。
            ssm_client: SSM クライアント（依存性注入用）。None の場合は boto3 で
                生成する。リージョンは実行環境（Lambda の `AWS_REGION` 等）から
                boto3 が解決するため本コードでは指定しない（ハードコード回避）。

        Raises:
            ConfigurationError: `env` が None かつ環境変数 `ENV` が未設定または空の
                場合。フォールバックせず明示的に失敗させる
                （出典: design.md Error Handling、requirements.md R6-7）。
        """
        # 環境名を解決する。明示引数を優先し、無ければ環境変数 `ENV` から取得する。
        resolved_env = env if env is not None else os.environ.get(_ENV_VARIABLE_NAME)

        # 環境名の欠落・空は既定値で埋めず、明示的に失敗させる（フォールバック禁止）。
        if not resolved_env or not resolved_env.strip():
            # 欠落した設定要素（環境変数名）を明示してエラー原因を追跡可能にする。
            raise ConfigurationError(
                f"環境名を解決できません。環境変数 '{_ENV_VARIABLE_NAME}' を設定してください"
                "（フォールバック禁止、出典: requirements.md R6-7、design.md Error Handling）。"
            )

        # 前後空白を除去した環境名を保持する（パス構築時の不整合を防ぐ）。
        self._env = resolved_env.strip()

        # SSM クライアントは注入値を優先し、無ければ boto3 で生成する。
        # クライアント生成自体は認証情報を要求しない（実際の API 呼び出し時に必要）。
        self._ssm_client = ssm_client if ssm_client is not None else boto3.client("ssm")

    def get_from_address(self) -> str:
        """SES 送信元アドレスを Parameter Store から取得する.

        Returns:
            str: 送信元アドレス（出典: DM4 `default_from_email`）。

        Raises:
            ConfigurationError: 設定値が欠落・空・取得失敗の場合
                （フォールバック禁止、出典: requirements.md R6-7）。
        """
        return self._get_required_parameter(_PARAM_NAME_FROM_EMAIL)

    def get_to_address(self) -> str:
        """SES 宛先アドレスを Parameter Store から取得する.

        Returns:
            str: 宛先アドレス（出典: DM4 `default_to_mail`）。

        Raises:
            ConfigurationError: 設定値が欠落・空・取得失敗の場合
                （フォールバック禁止、出典: requirements.md R6-7）。
        """
        return self._get_required_parameter(_PARAM_NAME_TO_EMAIL)

    def get_allowed_origins(self) -> tuple[str, ...]:
        """問い合わせ POST の許可 Origin 一覧を Parameter Store から取得する.

        `csrf_trusted_origins` はカンマ区切りの複数値として格納されているため、
        分割・前後空白除去・空要素除去を行い不変な tuple へ整形する
        （出典: DM4 `csrf_trusted_origins`、requirements.md R8-1、
        `config/settings/prod.py` の split 整形と整合）。

        Returns:
            tuple[str, ...]: 許可 Origin の不変な列（1 件以上）。

        Raises:
            ConfigurationError: 設定値が欠落・空・取得失敗の場合、または分割後に
                有効な Origin が 1 件も得られない場合（フォールバック禁止、
                出典: requirements.md R6-7, R8-1）。
        """
        # 生の設定値（カンマ区切り文字列）を取得する。欠落・空は下位で例外送出。
        raw_value = self._get_required_parameter(_PARAM_NAME_TRUSTED_ORIGINS)

        # カンマで分割し、各要素の前後空白を除去したうえで空要素を除外する。
        origins = tuple(
            origin.strip()
            for origin in raw_value.split(_ORIGIN_DELIMITER)
            if origin.strip()
        )

        # 分割後に有効な Origin が 1 件も無い場合は既定値で埋めず明示的に失敗させる。
        if not origins:
            path = self._build_parameter_path(_PARAM_NAME_TRUSTED_ORIGINS)
            raise ConfigurationError(
                f"許可 Origin が空です（パス: '{path}'）。カンマ区切りで 1 件以上を"
                "設定してください（フォールバック禁止、出典: requirements.md R8-1, R6-7）。"
            )

        return origins

    def _build_parameter_path(self, name: str) -> str:
        """パラメータ名から Parameter Store の完全パスを構築する.

        Args:
            name: パラメータ名（例: `default_from_email`）。

        Returns:
            str: `/{Env}/portfolio/parameter/{name}` 形式の完全パス（出典: DM4）。
        """
        # 環境名は初期化時に検証済みのため、ここでは形式構築のみを行う。
        return _PARAMETER_PATH_TEMPLATE.format(env=self._env, name=name)

    def _get_required_parameter(self, name: str) -> str:
        """指定パラメータの値を取得し、欠落・空・失敗時は例外を送出する.

        Args:
            name: パラメータ名（例: `default_to_mail`）。

        Returns:
            str: 前後空白を除去したパラメータ値（非空）。

        Raises:
            ConfigurationError: パラメータが存在しない・値が空・取得に失敗した場合
                （フォールバック禁止、出典: requirements.md R6-7、design.md Error Handling）。
        """
        # DM4 のパス設計に従い完全パスを構築する。
        path = self._build_parameter_path(name)

        try:
            # Parameter Store から単一パラメータを取得する。
            # SecureString ではなく String 型のため復号は不要（出典: `template.yaml` の型定義）。
            response = self._ssm_client.get_parameter(Name=path)
        except (ClientError, BotoCoreError) as error:
            # 取得失敗（未登録・権限不足・通信失敗等）は握りつぶさず、欠落パスを明示して
            # 例外を送出する（フォールバック禁止、出典: requirements.md R6-7）。
            # exc_info で一次原因を明示ログ記録する（出典: design.md Error Handling）。
            logger.error("Parameter Store の取得に失敗しました（パス: %s）", path, exc_info=True)
            raise ConfigurationError(
                f"設定値の取得に失敗しました（パス: '{path}'）"
                "（フォールバック禁止、出典: requirements.md R6-7、design.md Error Handling）。"
            ) from error

        # 応答から値を取り出す。API 応答形状は {"Parameter": {"Value": ...}}。
        value = response.get("Parameter", {}).get("Value")

        # 値の欠落・空（空白のみを含む）は既定値で埋めず明示的に失敗させる。
        if value is None or not value.strip():
            raise ConfigurationError(
                f"設定値が空です（パス: '{path}'）。値を設定してください"
                "（フォールバック禁止、出典: requirements.md R6-7、design.md Error Handling）。"
            )

        # 前後空白を除去した値を返す。
        return value.strip()
