"""Contact_Function の Lambda/HTTP アダプタ層（handler）モジュール.

API Gateway プロキシ統合イベントを受領し、問い合わせ POST を処理する外側
（アダプタ層）のエントリポイントを提供する。クリーンアーキテクチャの依存方向
（外→内）に従い、本モジュールは adapters 層（具象 `SsmConfigProvider` /
`SesEmailSender`）と domain 層（抽象ポート・ユースケース `send_contact`）に依存
するが、domain 層は本モジュールに依存しない（出典: design.md「Components and
Interfaces > C3」依存規則、requirements.md R4-6）。

Django を含めず・ロードしない（出典: requirements.md R4-1, R4-2、design.md C3）。
本モジュールは標準ライブラリ・adapters 層・domain 層のみを import する。

責務（出典: design.md C3, C7, DM2, Error Handling、requirements.md R4-1, R4-2,
R6-5, R6-6, R8-1〜R8-5）:
    1. API Gateway プロキシ統合イベント（`headers`, `body`, `httpMethod`,
       `isBase64Encoded`）→ 問い合わせ入力（DTO=フィールド辞書）への変換。
    2. CORS（POST/OPTIONS）: OPTIONS プリフライトへの応答と、許可オリジン設定値
       からの CORS 応答ヘッダ供給。許可メソッドは POST/OPTIONS（design.md C7,
       requirements.md R8-5）。
    3. Origin 検証: リクエストの `Origin` ヘッダを
       `ConfigProvider.get_allowed_origins()` の許可リストと照合し、一致時のみ
       後続を継続する。不一致・欠落・空は HTTP 4xx（`OriginRejected`）で拒否し、
       Email_Sender へ引き渡さない（requirements.md R8-1, R8-2, R8-3, R8-4）。
    4. ハニーポット判定: 隠しフィールド（本実装の採用名 `website`。下記参照）に
       空でない値が存在する場合は HTTP 4xx（`HoneypotRejected`）で拒否し、
       Contact_Payload に含めず（4 項目のみ）Email_Sender へ引き渡さない。隠し
       フィールドは収集・保存しない（requirements.md R8-6, R9-5、design.md C7）。
    5. ユースケース呼び出し: `send_contact(fields, from_addr, to_addr,
       email_sender)` を呼ぶ。`fields` は 4 項目のみ（ハニーポット等の非内容
       フィールドを除去して渡す。出典: 本タスク指示、requirements.md R5-1,
       R9-5、design.md DM1）。`from_addr` / `to_addr` は `ConfigProvider` から
       取得する（ハードコード禁止、requirements.md R6-7）。
    6. 応答生成（`ContactResult`→HTTP マッピング、design.md DM2）: Success=200 系、
       ValidationError=400 系（不備対象項目を応答に含める）、OriginRejected /
       HoneypotRejected=4xx、SendFailed=500 系。

入力ボディ形式（本タスク指示に基づき採用形式を明記）:
    - Content-Type が `application/json` を含む場合は JSON オブジェクトとして
      解釈する（キー・値ともに文字列であることを要求。ゼロトラスト検証）。
    - それ以外（既定）は `application/x-www-form-urlencoded`（form-encoded）と
      して解釈する。これは現行 Django フォーム（`portfolio/forms.py`、
      `ContactForm` の POST 送信）と整合する既定形式である（出典: E-5）。

ハニーポットの隠しフィールド名（本タスク指示に基づき名称を明記）:
    - 採用名 `website`。人間には非表示、ボットが自動入力しやすい慣例的な名称で
      あり、当該フィールドに値が入っていれば自動投稿とみなす（出典: design.md
      C7 ハニーポット）。当該フィールドは Contact_Payload の 4 項目に含めず、
      個人データとして収集・保存しない（requirements.md R9-5, R5-1）。

依存性逆転・テスト容易性（出典: 本タスク指示、design.md C3、第二原則3）:
    - 実際のイベント処理は `handle_contact_request(event, config_provider,
      email_sender)` が担い、依存（`ConfigProvider` / `EmailSender`）を引数で
      受け取る（composition root は Lambda エントリポイント側）。
    - Lambda エントリポイント `lambda_handler(event, context)` が本番用の具象
      （`SsmConfigProvider` / `SesEmailSender`）を組み立てて委譲する。

フォールバック禁止（出典: 第三原則3、requirements.md R6-4, R12-5）:
    - エラーは握りつぶさず明示的に扱い、成功応答にしない。設定値欠落・送信失敗・
      不正ボディはそれぞれ適切な HTTP ステータスで応答し、明示ログを残す。
    - 個人データはログに出力しない（GDPR、requirements.md R9-5）。
"""

import base64
import json
import logging
from collections.abc import Mapping
from urllib.parse import parse_qsl

from contact_function.adapters.config_provider import (
    ConfigurationError,
    SsmConfigProvider,
)
from contact_function.adapters.ses_email_sender import SesEmailSender
from contact_function.domain.ports import ConfigProvider, EmailSender
from contact_function.domain.send_contact import (
    ContactResult,
    HoneypotRejected,
    OriginRejected,
    SendFailed,
    Success,
    ValidationError,
    send_contact,
)

# ロガーはモジュール単位で取得する（出典: coding-conventions.md
# 「logger = logging.getLogger(__name__)」パターン）。
logger = logging.getLogger(__name__)

# Contact_Payload の 4 項目（これ以外は送信内容として処理しない。GDPR データ
# 最小化、出典: requirements.md R5-1, R9-5、design.md DM1）。
_CONTENT_FIELDS: tuple[str, ...] = ("full_name", "email", "phone_number", "message")

# ハニーポットの隠しフィールド名（採用名。ボット自動投稿排除用。出典: design.md
# C7、本タスク指示「名称を決めて docstring に明記」）。
_HONEYPOT_FIELD_NAME = "website"

# 許可する HTTP メソッド（表示は静的配信のため、動的経路は POST とプリフライト
# の OPTIONS のみ。出典: design.md C7、requirements.md R8-5）。
_METHOD_POST = "POST"
_METHOD_OPTIONS = "OPTIONS"
_ALLOWED_METHODS_HEADER_VALUE = "POST, OPTIONS"

# CORS プリフライトで許可するリクエストヘッダ（問い合わせ送信に必要な最小限）。
_ALLOWED_HEADERS_HEADER_VALUE = "Content-Type"

# CORS プリフライトのキャッシュ秒数（過度な再プリフライトを避けるための最小設定）。
_PREFLIGHT_MAX_AGE_SECONDS = "600"

# JSON ボディ判定に用いる Content-Type の部分文字列。
_CONTENT_TYPE_JSON = "application/json"


def _normalize_headers(headers: object) -> dict[str, str]:
    """イベントのヘッダをキー小文字化した辞書へ正規化する.

    API Gateway のヘッダはキーの大文字小文字が保証されないため、大文字小文字を
    区別せず参照できるよう小文字キーへ正規化する（ゼロトラスト検証の前処理）。

    Args:
        headers: イベントの `headers`（辞書または None を想定。型不定の外部入力）。

    Returns:
        dict[str, str]: 小文字キーの文字列ヘッダ辞書。値が文字列でないもの・
            `headers` が辞書でない場合は空辞書を返す（後続で欠落として扱う）。
    """
    # 外部入力のため型を厳密に検証する。辞書以外は空として扱う（欠落扱い）。
    if not isinstance(headers, Mapping):
        return {}
    normalized: dict[str, str] = {}
    for key, value in headers.items():
        # キー・値がともに文字列のもののみ採用する（不正な型は無視して欠落扱い）。
        if isinstance(key, str) and isinstance(value, str):
            normalized[key.lower()] = value
    return normalized


def _parse_body(raw_body: object, is_base64: bool, content_type: str) -> dict[str, str]:
    """イベントの `body` を問い合わせ入力の文字列辞書へ変換する.

    採用形式（モジュール docstring に明記）:
        - Content-Type が `application/json` を含む場合は JSON オブジェクトとして
          解釈し、キー・値がともに文字列であることを要求する（ゼロトラスト）。
        - それ以外は form-encoded として解釈する（現行 Django フォーム互換、
          出典: E-5）。

    Args:
        raw_body: イベントの `body`（文字列または None を想定。外部入力）。
        is_base64: `isBase64Encoded` の値。True の場合は base64 復号する。
        content_type: 小文字化済みの Content-Type ヘッダ値（無い場合は空文字）。

    Returns:
        dict[str, str]: フィールド名から値への辞書。`body` が無い場合は空辞書。

    Raises:
        ValueError: ボディが不正（base64 復号失敗、UTF-8 デコード失敗、JSON 解析
            失敗、JSON がオブジェクトでない、キー/値が文字列でない）な場合。
            呼び出し元で HTTP 400 に対応付ける（フォールバック禁止、明示的失敗）。
    """
    # ボディ未指定は空入力として扱う（後続の検証で必須項目欠落として 400 になる）。
    if raw_body is None:
        return {}
    # 外部入力のため文字列であることを検証する。
    if not isinstance(raw_body, str):
        raise ValueError("リクエストボディが文字列ではありません。")

    text = raw_body
    if is_base64:
        try:
            # base64 エンコードされたボディを復号し UTF-8 として解釈する。
            text = base64.b64decode(raw_body).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as error:
            # 復号・デコード失敗は握りつぶさず明示的に失敗させる（フォールバック禁止）。
            raise ValueError("ボディの base64 復号に失敗しました。") from error

    # JSON 形式（Content-Type 明示時）。
    if _CONTENT_TYPE_JSON in content_type:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError("JSON ボディの解析に失敗しました。") from error
        # トップレベルはオブジェクト（辞書）であることを要求する（ゼロトラスト）。
        if not isinstance(parsed, dict):
            raise ValueError("JSON ボディはオブジェクトである必要があります。")
        result: dict[str, str] = {}
        for key, value in parsed.items():
            # キー・値がともに文字列であることを要求する（型の暗黙変換をしない）。
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError(
                    "JSON ボディは文字列キーと文字列値のみを許可します。"
                )
            result[key] = value
        return result

    # 既定: form-encoded（現行 Django フォーム互換、出典: E-5）。
    # keep_blank_values=True で空値も保持し、必須項目の空文字検証（R5-2）に委ねる。
    return dict(parse_qsl(text, keep_blank_values=True))


def _build_cors_headers(allowed_origin: str | None) -> dict[str, str]:
    """CORS 応答ヘッダを組み立てる（許可オリジン設定値から供給）.

    許可された Origin に対してのみ `Access-Control-Allow-Origin` を反映する。
    許可されていない場合は ACAO を付与しない（ブラウザ側でブロックさせる）。

    Args:
        allowed_origin: 応答に反映する許可済み Origin。許可対象外・欠落時は None。

    Returns:
        dict[str, str]: CORS 応答ヘッダ。`allowed_origin` が None の場合は
            オリジン非依存のヘッダのみを返し `Access-Control-Allow-Origin` を含めない。
    """
    # 許可メソッド・許可ヘッダ・キャッシュ秒数は常に返す（CORS 契約の明示）。
    headers: dict[str, str] = {
        "Access-Control-Allow-Methods": _ALLOWED_METHODS_HEADER_VALUE,
        "Access-Control-Allow-Headers": _ALLOWED_HEADERS_HEADER_VALUE,
        "Access-Control-Max-Age": _PREFLIGHT_MAX_AGE_SECONDS,
        # Origin ごとに応答が変わるため Vary を明示し、キャッシュ汚染を防ぐ。
        "Vary": "Origin",
    }
    if allowed_origin is not None:
        # 許可済み Origin のみを反映する（ワイルドカードは使わない、ゼロトラスト）。
        headers["Access-Control-Allow-Origin"] = allowed_origin
    return headers


def _build_response(
    status_code: int, body: dict[str, object], cors_headers: dict[str, str]
) -> dict[str, object]:
    """API Gateway プロキシ統合形式の HTTP 応答を組み立てる.

    Args:
        status_code: HTTP ステータスコード。
        body: JSON 応答ボディ（辞書）。
        cors_headers: 応答へ付与する CORS ヘッダ。

    Returns:
        dict[str, object]: `{"statusCode", "headers", "body"}` 形式の応答。
    """
    # Content-Type を明示し、CORS ヘッダを統合する。
    headers: dict[str, str] = {"Content-Type": "application/json"}
    headers.update(cors_headers)
    return {
        "statusCode": status_code,
        "headers": headers,
        # ボディは JSON 文字列化する。日本語を保持するため ensure_ascii=False。
        "body": json.dumps(body, ensure_ascii=False),
    }


def _result_to_response(
    result: ContactResult, cors_headers: dict[str, str]
) -> dict[str, object]:
    """`ContactResult` を HTTP 応答へマッピングする（design.md DM2）.

    マッピング（出典: design.md DM2、requirements.md R5-2〜R5-6, R6-5, R6-6,
    R8-2, R8-3, R8-6）:
        - Success           → 200
        - ValidationError   → 400（不備対象項目を応答に含める）
        - OriginRejected    → 403（4xx）
        - HoneypotRejected  → 403（4xx）
        - SendFailed        → 500

    Args:
        result: ユースケースまたは handler が生成した処理結果。
        cors_headers: 応答へ付与する CORS ヘッダ。

    Returns:
        dict[str, object]: HTTP 応答（API Gateway プロキシ統合形式）。

    Raises:
        TypeError: 未知の `ContactResult` サブタイプが渡された場合。網羅漏れを
            握りつぶさず明示的に失敗させる（フォールバック禁止、第三原則3）。
    """
    # 送信成功（R6-6）。
    if isinstance(result, Success):
        return _build_response(
            200, {"message": "問い合わせを受け付けました。"}, cors_headers
        )
    # 入力検証失敗（R5-2〜R5-6）。不備対象項目を応答に含める。
    if isinstance(result, ValidationError):
        return _build_response(
            400,
            {"error": "validation_error", "fields": list(result.fields)},
            cors_headers,
        )
    # Origin 不正・欠落・空（R8-2, R8-3）。
    if isinstance(result, OriginRejected):
        return _build_response(403, {"error": "origin_rejected"}, cors_headers)
    # ハニーポット発火（R8-6）。
    if isinstance(result, HoneypotRejected):
        return _build_response(403, {"error": "honeypot_rejected"}, cors_headers)
    # SES 送信失敗（R6-5）。個人データを含めない汎用メッセージのみ返す。
    if isinstance(result, SendFailed):
        return _build_response(500, {"error": "send_failed"}, cors_headers)

    # 網羅漏れ（未知の結果型）は握りつぶさず明示的に失敗させる（フォールバック禁止）。
    raise TypeError(f"未知の ContactResult 型です: {type(result)!r}")


def handle_contact_request(
    event: Mapping[str, object],
    config_provider: ConfigProvider,
    email_sender: EmailSender,
) -> dict[str, object]:
    """API Gateway プロキシ統合イベントを処理する（依存注入可能な本体）.

    依存（`ConfigProvider` / `EmailSender`）を引数で受け取り、テスト容易性を
    確保する（composition root は `lambda_handler`。出典: 本タスク指示、
    design.md C3、第二原則3）。処理順序は Origin/CORS 検証を先に行い、検証・送信
    は最後に行う（不正・クロスサイト由来 POST を早期に排除、ゼロトラスト）。

    Args:
        event: API Gateway プロキシ統合イベント（`headers`, `body`,
            `httpMethod`, `isBase64Encoded` を参照）。
        config_provider: 送信元/宛先/許可 Origin を供給する設定プロバイダ（抽象）。
        email_sender: 問い合わせメール送信の抽象ポート実装。

    Returns:
        dict[str, object]: API Gateway プロキシ統合形式の HTTP 応答
            （`statusCode`, `headers`, `body`）。
    """
    # ヘッダを小文字キーへ正規化し、大文字小文字非依存で参照する。
    headers = _normalize_headers(event.get("headers"))
    content_type = headers.get("content-type", "").lower()
    # Origin ヘッダ（欠落時は None）。
    origin = headers.get("origin")
    # HTTP メソッド（欠落・非文字列は空文字として扱い、後続で 405 になる）。
    raw_method = event.get("httpMethod")
    method = raw_method.upper() if isinstance(raw_method, str) else ""

    # 許可 Origin 一覧を設定値から取得する。欠落時はフォールバックせず 500 とする
    # （出典: design.md Error Handling 設定値欠落行、requirements.md R6-7）。
    try:
        allowed_origins = config_provider.get_allowed_origins()
    except ConfigurationError:
        # 設定値欠落・取得失敗は握りつぶさず明示ログの上 500 を返す（config_provider
        # 側で exc_info を記録済み。ここでは重複出力を避け事実のみ記録）。
        logger.error("許可 Origin 設定値の取得に失敗しました。")
        # 設定不備のため CORS ヘッダは付与できない。
        return _build_response(500, {"error": "configuration_error"}, {})

    # Origin が許可リストに含まれるか判定する（一致時のみ CORS で反映する）。
    is_origin_allowed = origin is not None and origin in allowed_origins
    # 許可時のみ ACAO に反映する Origin を決める。
    reflected_origin = origin if is_origin_allowed else None
    cors_headers = _build_cors_headers(reflected_origin)

    # CORS プリフライト（OPTIONS）への応答（出典: design.md C7、requirements.md R8-5）。
    if method == _METHOD_OPTIONS:
        if is_origin_allowed:
            # 許可 Origin のプリフライトには 204（No Content）+ CORS ヘッダで応答。
            return _build_response(204, {}, cors_headers)
        # 許可外 Origin のプリフライトは拒否する（ACAO を付与しない）。
        logger.warning("許可外 Origin からのプリフライトを拒否しました。")
        return _build_response(403, {"error": "origin_rejected"}, cors_headers)

    # POST 以外（かつ OPTIONS 以外）は許可しない（表示は静的配信、動的は POST のみ）。
    if method != _METHOD_POST:
        return _build_response(
            405, {"error": "method_not_allowed"}, cors_headers
        )

    # Origin 検証: 不一致・欠落・空は 4xx で拒否し Email_Sender へ引き渡さない
    # （出典: requirements.md R8-1, R8-2, R8-3, R8-4、design.md C7, DM2）。
    if not is_origin_allowed:
        logger.warning("許可外・欠落 Origin の問い合わせ POST を拒否しました。")
        return _result_to_response(OriginRejected(), cors_headers)

    # ボディを問い合わせ入力の文字列辞書へ変換する。不正ボディは 400 で拒否する。
    try:
        parsed = _parse_body(
            event.get("body"),
            bool(event.get("isBase64Encoded")),
            content_type,
        )
    except ValueError:
        # 不正ボディは握りつぶさず明示的に 400 とする（フォールバック禁止）。
        # 個人データを含めないため詳細値はログに出さず事実のみ記録する。
        logger.warning("不正な問い合わせボディを 400 で拒否しました。")
        return _build_response(400, {"error": "invalid_body"}, cors_headers)

    # ハニーポット判定: 隠しフィールドに空でない値があれば自動投稿として拒否する。
    # 当該フィールドは Contact_Payload に含めず収集・保存しない（出典: R8-6, R9-5、
    # design.md C7, DM1）。
    honeypot_value = parsed.get(_HONEYPOT_FIELD_NAME, "")
    if honeypot_value.strip() != "":
        logger.warning("ハニーポット発火を検出し問い合わせを拒否しました。")
        return _result_to_response(HoneypotRejected(), cors_headers)

    # 送信元・宛先アドレスを設定値から取得する（ハードコード禁止、R6-7）。
    # 欠落時はフォールバックせず 500 とする（design.md Error Handling）。
    try:
        from_addr = config_provider.get_from_address()
        to_addr = config_provider.get_to_address()
    except ConfigurationError:
        logger.error("送信元/宛先アドレス設定値の取得に失敗しました。")
        return _build_response(500, {"error": "configuration_error"}, cors_headers)

    # ユースケースへ渡すフィールドは 4 項目のみに限定する（ハニーポット等の非内容
    # フィールドを除去。出典: 本タスク指示、requirements.md R5-1, R9-5、
    # design.md DM1）。欠落項目は空文字として渡し、検証で必須不備（400）に委ねる。
    content_fields: dict[str, str] = {
        name: parsed.get(name, "") for name in _CONTENT_FIELDS
    }

    # 検証済みユースケースを呼び出す。認証情報は渡さない（Cognito-ready、R13-2）。
    # 送信失敗（例外）は send_contact 内で握りつぶさず SendFailed として返る。
    result = send_contact(content_fields, from_addr, to_addr, email_sender)

    # 処理結果を HTTP 応答へマッピングして返す（design.md DM2）。
    return _result_to_response(result, cors_headers)


def lambda_handler(event: Mapping[str, object], context: object) -> dict[str, object]:
    """Lambda エントリポイント（本番用の具象を組み立てて委譲する composition root）.

    本番用の具象アダプタ（`SsmConfigProvider` / `SesEmailSender`）を生成し、
    実処理を `handle_contact_request` へ委譲する（依存性逆転・テスト容易性の
    ため実処理本体から依存生成を分離。出典: 本タスク指示、design.md C3）。
    Django は import・ロードしない（requirements.md R4-1, R4-2）。

    Args:
        event: API Gateway プロキシ統合イベント。
        context: Lambda コンテキストオブジェクト（本処理では未使用）。

    Returns:
        dict[str, object]: API Gateway プロキシ統合形式の HTTP 応答。
    """
    # composition root: 具象依存をここでのみ生成し注入する。
    config_provider = SsmConfigProvider()
    email_sender = SesEmailSender()
    return handle_contact_request(event, config_provider, email_sender)
