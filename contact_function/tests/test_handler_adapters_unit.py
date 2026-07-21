"""アダプタ/ハンドラの例示ベース単体テストと非同梱・依存方向の静的検査.

本モジュールは tasks.md 2.6 に対応し、次の 2 系統を「具体的な例」および
「静的検査」で決定的に検証する（プロパティテストではない。出典: tasks.md 2.6、
design.md「Testing Strategy > 単体/例ベーステスト」）。

1. handler（`contact_function.handler.handle_contact_request`）の外側振る舞いの
   例示検証:
     - Origin 検証（許可/非許可/欠落/空）と Email_Sender への引き渡し有無
       （出典: requirements.md R8-1, R8-2, R8-3, R8-4、design.md C7, DM2）。
     - CORS（`Access-Control-Allow-Origin`/`-Methods` 等の付与）および OPTIONS
       プリフライトが送信を行わずに応答すること
       （出典: requirements.md R8-5、design.md C7）。
     - 応答マッピング: 検証失敗=400、SES 送信失敗（失敗するダブルを注入）=500、
       成功=200（出典: requirements.md R5-2〜R5-6, R6-5, R6-6、design.md DM2）。

2. 静的検査:
     - Django 非同梱スモーク: Contact_Function の各モジュールを import しても
       `django` が読み込まれないこと（実行時に Django をロードしない）を
       サブプロセスで `sys.modules` を検査して確認する
       （出典: requirements.md R4-1, R4-2、design.md C3）。
       備考（事実）: 本 .venv には Django がインストールされている（確認済み。
       `importlib.util.find_spec('django')` が非 None）。そのため「未インストール
       ゆえに import 成功が非依存を示す」という論法は本環境では成立しない。よって
       import 後に `sys.modules` へ `django` が入っていないことを能動的に検証する
       方式を採る（インストール有無に依存しない堅牢な検査）。
     - 依存方向検査（R4-6）: `contact_function/domain/` 配下の各 `.py` を標準
       ライブラリ `ast` で解析し、import 文が `django` / `contact_function.adapters`
       / `contact_function.handler` を参照しないことを検証する
       （クリーンアーキテクチャ: 依存は外→内の一方向。domain は adapters/handler/
       Django に依存しない。出典: requirements.md R4-6、design.md C3 依存規則）。
       依存方向規則（日本語で明記）:
         「ドメイン層（domain/）は、アダプタ層（adapters/）・ハンドラ層
          （handler.py）・フレームワーク（Django）へ依存してはならない。
          これらへの import が 1 つでも存在すれば依存方向違反とする。」

テスト方針（出典: design.md「Testing Strategy」、requirements.md R4-1/R4-2）:
    - 標準ライブラリ `unittest` を用いた決定的な例示・静的検査（非 PBT）。
    - handler への依存（`ConfigProvider` / `EmailSender`）は具象ではなくテスト
      ダブル（抽象実装）を注入する（依存性逆転、AWS を呼ばない）。
    - task 1.4 で確立した共有ハーネス `RecordingEmailSender`（抽象
      `ports.EmailSender` 実装）を再利用する（重複排除・単一責務）。
    - フォールバック禁止: 期待を明示アサートし、問題を握りつぶさない。
    - 追加の重量級依存（import-linter 等）は導入せず、`ast` 標準ライブラリで
      依存方向検査を自己完結させる（ライセンス精査回避・第二原則6）。

実行コマンド（プロジェクトルートから、Django 非ロード）:
    python -m unittest contact_function.tests.test_handler_adapters_unit -v
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import unittest
from pathlib import Path
from urllib.parse import urlencode

from contact_function.domain.contact_payload import ContactPayload
from contact_function.domain.ports import ConfigProvider, EmailSender
from contact_function.handler import handle_contact_request

# task 1.4 で確立した共有テストハーネスを再利用する（重複排除・単一責務）。
# `RecordingEmailSender` は抽象ポート `ports.EmailSender` を実装する記録用ダブル
# であり、実送信の副作用を持たない（出典: test_property_valid_payload.py）。
from contact_function.tests.test_property_valid_payload import RecordingEmailSender

# プロジェクトルート（本ファイル→tests→contact_function→ルート の 3 階層上）。
# サブプロセスでの import 検査時に cwd として与え、`contact_function` パッケージを
# 解決可能にする（出典: __init__.py の実行コマンド、パッケージ配置）。
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ドメイン層ディレクトリ（依存方向検査の対象。出典: design.md C3 依存規則）。
_DOMAIN_DIR = _PROJECT_ROOT / "contact_function" / "domain"

# 許可 Origin の代表値（設定値由来を模した固定値）。実際の設定は Parameter Store
# から取得するが、本テストはテストダブルで供給する（出典: design.md DM4, C7）。
_ALLOWED_ORIGIN = "https://serverless.portfolio.cobaemon.com"
_OTHER_ALLOWED_ORIGIN = "https://example.com"

# SES 送信元・宛先の代表値（設定値由来。ハードコードではなくダブルが供給する）。
_FROM_ADDR = "noreply@example.com"
_TO_ADDR = "owner@example.com"


class FakeConfigProvider(ConfigProvider):
    """`ports.ConfigProvider` を実装するテスト用の設定プロバイダ（抽象実装）.

    AWS Parameter Store を呼ばず、既知の許可 Origin 一覧・送信元/宛先アドレスを
    返す（クリーンアーキテクチャ: テストは具体でなく抽象に依存する。出典:
    design.md C3, DM4）。フォールバックを行わず、初期化時に与えた値をそのまま
    返す（既定値での暗黙補完をしない）。
    """

    def __init__(
        self,
        allowed_origins: tuple[str, ...] = (_ALLOWED_ORIGIN, _OTHER_ALLOWED_ORIGIN),
        from_addr: str = _FROM_ADDR,
        to_addr: str = _TO_ADDR,
    ) -> None:
        """既知の設定値でプロバイダを初期化する.

        Args:
            allowed_origins: 許可 Origin の不変な列（既定は 2 件）。
            from_addr: SES 送信元アドレス。
            to_addr: SES 宛先アドレス。
        """
        # 与えられた設定値を保持する（暗黙の既定補完をしない）。
        self._allowed_origins = allowed_origins
        self._from_addr = from_addr
        self._to_addr = to_addr

    def get_from_address(self) -> str:
        """SES 送信元アドレスを返す（出典: DM4 default_from_email）."""
        return self._from_addr

    def get_to_address(self) -> str:
        """SES 宛先アドレスを返す（出典: DM4 default_to_mail）."""
        return self._to_addr

    def get_allowed_origins(self) -> tuple[str, ...]:
        """許可 Origin 一覧を返す（出典: DM4 csrf_trusted_origins、R8-1）."""
        return self._allowed_origins


class FailingEmailSender(EmailSender):
    """常に送信に失敗する（例外を送出する）テスト用の Email_Sender.

    SES 送信失敗を模擬し、handler が失敗を握りつぶさず 500 系へマッピングする
    ことを検証するために用いる（出典: requirements.md R6-4, R6-5, R12-5、
    design.md DM2 SendFailed）。実 AWS は呼ばない。
    """

    def send(self, payload: ContactPayload, from_addr: str, to_addr: str) -> None:
        """送信を試みず、送信失敗を表す例外を送出する.

        Args:
            payload: 送信対象の Contact_Payload（本ダブルでは未使用）。
            from_addr: 送信元アドレス（本ダブルでは未使用）。
            to_addr: 宛先アドレス（本ダブルでは未使用）。

        Raises:
            RuntimeError: SES 送信失敗を模擬するため常に送出する。
        """
        # SES クライアントが送出する例外（ClientError/BotoCoreError 等）に相当する
        # 失敗を模擬する。send_contact 側は Exception を捕捉し SendFailed を返す。
        raise RuntimeError("SES 送信失敗（テスト用の模擬例外）")


def _valid_form_body() -> str:
    """検証を通過する 4 項目の form-encoded ボディを構築するヘルパー.

    Returns:
        str: `application/x-www-form-urlencoded` 形式のボディ文字列
            （現行 Django フォーム互換の既定形式、出典: E-5、handler.py）。
    """
    # いずれも strip 後非空・上限以下・形式適合であり検証を通過する 4 項目。
    return urlencode(
        {
            "full_name": "山田 太郎",
            "email": "taro@example.com",
            "phone_number": "0312345678",
            "message": "お問い合わせ本文です。",
        }
    )


def _post_event(
    origin: str | None,
    body: str,
    *,
    include_origin_key: bool = True,
    content_type: str = "application/x-www-form-urlencoded",
) -> dict[str, object]:
    """API Gateway プロキシ統合形式の POST イベントを構築するヘルパー.

    Args:
        origin: リクエストの Origin ヘッダ値（空文字も可）。
        body: リクエストボディ。
        include_origin_key: False の場合は Origin ヘッダ自体を含めない（欠落を再現）。
        content_type: Content-Type ヘッダ値（既定は form-encoded）。

    Returns:
        dict[str, object]: `httpMethod`/`headers`/`body`/`isBase64Encoded` を持つ
            イベント辞書。
    """
    # ヘッダはキー大小混在でも handler 側で小文字正規化される点を検証するため、
    # あえて元の表記（Origin/Content-Type）で与える。
    headers: dict[str, str] = {"Content-Type": content_type}
    if include_origin_key and origin is not None:
        headers["Origin"] = origin
    return {
        "httpMethod": "POST",
        "headers": headers,
        "body": body,
        "isBase64Encoded": False,
    }


def _options_event(
    origin: str | None, *, include_origin_key: bool = True
) -> dict[str, object]:
    """CORS プリフライト（OPTIONS）イベントを構築するヘルパー.

    Args:
        origin: リクエストの Origin ヘッダ値。
        include_origin_key: False の場合は Origin ヘッダ自体を含めない。

    Returns:
        dict[str, object]: OPTIONS メソッドのイベント辞書。
    """
    headers: dict[str, str] = {}
    if include_origin_key and origin is not None:
        headers["Origin"] = origin
    return {
        "httpMethod": "OPTIONS",
        "headers": headers,
        "body": None,
        "isBase64Encoded": False,
    }


def _parse_body(response: dict[str, object]) -> dict[str, object]:
    """応答の JSON ボディ文字列を辞書へ復元するヘルパー.

    Args:
        response: handler が返した応答辞書。

    Returns:
        dict[str, object]: JSON ボディを復元した辞書。
    """
    # handler は body を JSON 文字列で返すため復元して内容を検証する。
    body = response["body"]
    assert isinstance(body, str)
    parsed = json.loads(body)
    assert isinstance(parsed, dict)
    return parsed


class OriginValidationTests(unittest.TestCase):
    """Origin 検証と Email_Sender 引き渡し有無の例示検証（R8-1〜R8-4）."""

    def test_allowlisted_origin_post_is_handed_off_and_returns_200(self) -> None:
        """許可 Origin の POST は検証・送信へ継続し 200 を返す（R8-1）."""
        # 許可 Origin かつ有効入力のため送信が 1 回行われ 200 となる。
        sender = RecordingEmailSender()
        response = handle_contact_request(
            _post_event(_ALLOWED_ORIGIN, _valid_form_body()),
            FakeConfigProvider(),
            sender,
        )
        self.assertEqual(response["statusCode"], 200)
        # Email_Sender へちょうど 1 回引き渡されること（継続の証拠、R8-1）。
        self.assertEqual(len(sender.calls), 1)
        # 引き渡し先の送信元/宛先が設定値どおりであること（ハードコードでない）。
        _, handed_from, handed_to = sender.calls[0]
        self.assertEqual(handed_from, _FROM_ADDR)
        self.assertEqual(handed_to, _TO_ADDR)

    def test_non_allowlisted_origin_post_is_rejected_4xx_no_handoff(self) -> None:
        """非許可 Origin の POST は 4xx で拒否され送信しない（R8-2）."""
        sender = RecordingEmailSender()
        response = handle_contact_request(
            _post_event("https://evil.example.net", _valid_form_body()),
            FakeConfigProvider(),
            sender,
        )
        # 4xx（403）かつ origin_rejected。Email_Sender へ引き渡さない（R8-2）。
        self.assertEqual(response["statusCode"], 403)
        self.assertEqual(_parse_body(response)["error"], "origin_rejected")
        self.assertEqual(len(sender.calls), 0)
        # 非許可 Origin には Access-Control-Allow-Origin を付与しない（ゼロトラスト）。
        self.assertNotIn("Access-Control-Allow-Origin", response["headers"])

    def test_missing_origin_post_is_rejected_4xx_no_handoff(self) -> None:
        """Origin 欠落の POST は 4xx で拒否され送信しない（R8-3）."""
        sender = RecordingEmailSender()
        response = handle_contact_request(
            _post_event(None, _valid_form_body(), include_origin_key=False),
            FakeConfigProvider(),
            sender,
        )
        self.assertEqual(response["statusCode"], 403)
        self.assertEqual(_parse_body(response)["error"], "origin_rejected")
        self.assertEqual(len(sender.calls), 0)

    def test_empty_origin_post_is_rejected_4xx_no_handoff(self) -> None:
        """Origin が空文字の POST は 4xx で拒否され送信しない（R8-3）."""
        sender = RecordingEmailSender()
        response = handle_contact_request(
            _post_event("", _valid_form_body()),
            FakeConfigProvider(),
            sender,
        )
        self.assertEqual(response["statusCode"], 403)
        self.assertEqual(_parse_body(response)["error"], "origin_rejected")
        self.assertEqual(len(sender.calls), 0)


class CorsTests(unittest.TestCase):
    """CORS 応答ヘッダおよび OPTIONS プリフライトの例示検証（R8-5、design.md C7）."""

    def test_allowed_post_response_includes_cors_headers(self) -> None:
        """許可 Origin の POST 応答に CORS ヘッダ（ACAO/Methods）が付与される（R8-5）."""
        response = handle_contact_request(
            _post_event(_ALLOWED_ORIGIN, _valid_form_body()),
            FakeConfigProvider(),
            RecordingEmailSender(),
        )
        headers = response["headers"]
        assert isinstance(headers, dict)
        # 許可 Origin をそのまま反映する（ワイルドカードを使わない、ゼロトラスト）。
        self.assertEqual(headers["Access-Control-Allow-Origin"], _ALLOWED_ORIGIN)
        # 許可メソッドは POST/OPTIONS（表示は静的配信のため、出典: design.md C7）。
        self.assertEqual(headers["Access-Control-Allow-Methods"], "POST, OPTIONS")
        # Origin 依存応答のため Vary: Origin を明示（キャッシュ汚染防止）。
        self.assertEqual(headers["Vary"], "Origin")

    def test_options_preflight_allowed_origin_returns_204_without_sending(
        self,
    ) -> None:
        """許可 Origin の OPTIONS プリフライトは送信せず 204 + CORS で応答する（R8-5）."""
        sender = RecordingEmailSender()
        response = handle_contact_request(
            _options_event(_ALLOWED_ORIGIN),
            FakeConfigProvider(),
            sender,
        )
        # プリフライトは No Content（204）で応答し、メール送信を行わない。
        self.assertEqual(response["statusCode"], 204)
        self.assertEqual(len(sender.calls), 0)
        headers = response["headers"]
        assert isinstance(headers, dict)
        self.assertEqual(headers["Access-Control-Allow-Origin"], _ALLOWED_ORIGIN)
        self.assertEqual(headers["Access-Control-Allow-Methods"], "POST, OPTIONS")

    def test_options_preflight_disallowed_origin_is_rejected_without_sending(
        self,
    ) -> None:
        """非許可 Origin の OPTIONS プリフライトは 4xx 拒否され送信しない（R8-2, R8-5）."""
        sender = RecordingEmailSender()
        response = handle_contact_request(
            _options_event("https://evil.example.net"),
            FakeConfigProvider(),
            sender,
        )
        # 非許可 Origin のプリフライトは 403 で拒否し、ACAO を付与しない。
        self.assertEqual(response["statusCode"], 403)
        self.assertEqual(len(sender.calls), 0)
        self.assertNotIn("Access-Control-Allow-Origin", response["headers"])


class ResponseMappingTests(unittest.TestCase):
    """ContactResult→HTTP 応答マッピングの例示検証（design.md DM2）."""

    def test_validation_error_maps_to_400_and_does_not_send(self) -> None:
        """検証失敗（空 email）は 400 を返し送信しない（R5-2, R5-3、DM2）."""
        # email を空にして検証失敗を発生させる（許可 Origin で Origin 検証は通過）。
        body = urlencode(
            {
                "full_name": "山田 太郎",
                "email": "",
                "phone_number": "0312345678",
                "message": "本文です。",
            }
        )
        sender = RecordingEmailSender()
        response = handle_contact_request(
            _post_event(_ALLOWED_ORIGIN, body),
            FakeConfigProvider(),
            sender,
        )
        self.assertEqual(response["statusCode"], 400)
        parsed = _parse_body(response)
        self.assertEqual(parsed["error"], "validation_error")
        # 不備対象項目（email）が応答に含まれること（R5-2/R5-3）。
        self.assertIn("email", parsed["fields"])
        # 検証失敗時は送信しない（R4-4）。
        self.assertEqual(len(sender.calls), 0)

    def test_ses_failure_maps_to_500(self) -> None:
        """SES 送信失敗（失敗ダブル注入）は 500 を返し握りつぶさない（R6-4, R6-5）."""
        # 有効入力・許可 Origin だが Email_Sender が例外送出 → SendFailed → 500。
        # handler.py・send_contact.py は失敗時に logger.error(exc_info=True) で
        # 明示記録する（フォールバック禁止）。ログ出力自体はテスト観点外だが、
        # 成功応答にならず 500 となる（握りつぶし不在）ことを検証する。
        response = handle_contact_request(
            _post_event(_ALLOWED_ORIGIN, _valid_form_body()),
            FakeConfigProvider(),
            FailingEmailSender(),
        )
        self.assertEqual(response["statusCode"], 500)
        self.assertEqual(_parse_body(response)["error"], "send_failed")

    def test_success_maps_to_200(self) -> None:
        """有効入力・許可 Origin・送信成功は 200 を返す（R6-6、DM2）."""
        response = handle_contact_request(
            _post_event(_ALLOWED_ORIGIN, _valid_form_body()),
            FakeConfigProvider(),
            RecordingEmailSender(),
        )
        self.assertEqual(response["statusCode"], 200)
        # 成功メッセージ（個人データを含まない汎用メッセージ）を返す。
        self.assertIn("message", _parse_body(response))


class DjangoNonBundlingSmokeTests(unittest.TestCase):
    """Django 非同梱スモーク: 各モジュール import で django をロードしない（R4-1, R4-2）.

    本 .venv には Django がインストールされている（確認済み）。そのため import
    成功だけでは非依存を示せない。よってサブプロセスで対象モジュールを import した
    後に `sys.modules` へ `django`（または `django.*`）が存在しないことを検証する
    （インストール有無に依存しない堅牢な検査。出典: requirements.md R4-1, R4-2、
    design.md C3）。
    """

    # 検査対象の Contact_Function モジュール（handler は adapters/domain を推移的に
    # import するため最も網羅的だが、各層を個別にも検査して層ごとの非依存を示す）。
    _MODULES_UNDER_TEST: tuple[str, ...] = (
        "contact_function.handler",
        "contact_function.adapters.config_provider",
        "contact_function.adapters.ses_email_sender",
        "contact_function.domain.send_contact",
        "contact_function.domain.validators",
        "contact_function.domain.contact_payload",
        "contact_function.domain.ports",
    )

    def test_importing_modules_does_not_load_django(self) -> None:
        """各モジュールを import しても sys.modules に django が現れない（R4-1, R4-2）."""
        for module_name in self._MODULES_UNDER_TEST:
            with self.subTest(module=module_name):
                # サブプロセスで対象モジュールを import し、django のロード有無を判定。
                # 判定結果を stdout に明示出力し、親プロセスで検査する（握りつぶさない）。
                code = (
                    "import sys\n"
                    f"import {module_name}\n"
                    "loaded = sorted("
                    "m for m in sys.modules "
                    "if m == 'django' or m.startswith('django.'))\n"
                    "print('DJANGO_LOADED=' + ','.join(loaded))\n"
                )
                completed = subprocess.run(
                    [sys.executable, "-c", code],
                    cwd=str(_PROJECT_ROOT),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                # import 自体が失敗した場合はスタックトレースを添えて明示的に失敗させる。
                self.assertEqual(
                    completed.returncode,
                    0,
                    msg=(
                        f"{module_name} の import に失敗しました。"
                        f"stderr:\n{completed.stderr}"
                    ),
                )
                # 出力を検証し、django が 1 つでもロードされていれば違反として失敗。
                self.assertIn("DJANGO_LOADED=", completed.stdout)
                loaded_line = next(
                    line
                    for line in completed.stdout.splitlines()
                    if line.startswith("DJANGO_LOADED=")
                )
                loaded_value = loaded_line.split("=", 1)[1]
                self.assertEqual(
                    loaded_value,
                    "",
                    msg=(
                        f"{module_name} の import で Django がロードされました "
                        f"（R4-1/R4-2 違反）: {loaded_value}"
                    ),
                )


class DomainDependencyDirectionTests(unittest.TestCase):
    """依存方向検査（R4-6）: domain/ が adapters・handler・Django を import しない.

    依存方向規則（日本語で明記）:
        ドメイン層（`contact_function/domain/`）は、アダプタ層
        （`contact_function.adapters`）・ハンドラ層（`contact_function.handler`）・
        フレームワーク（`django`）へ依存してはならない。これらへの import が 1 つ
        でも存在すれば依存方向違反とする（クリーンアーキテクチャ: 依存は外→内の
        一方向。出典: requirements.md R4-6、design.md C3 依存規則）。

    追加の重量級依存（import-linter 等）は導入せず、標準ライブラリ `ast` で
    import 文を静的解析して自己完結的に検査する（第二原則6: ライセンス精査回避）。
    """

    # 依存してはならない対象の接頭辞（完全一致または `<prefix>.` で始まる import）。
    _FORBIDDEN_PREFIXES: tuple[str, ...] = (
        "django",
        "contact_function.adapters",
        "contact_function.handler",
    )

    def _collect_imported_modules(self, source: str, filename: str) -> set[str]:
        """Python ソースを ast で解析し、import される module 名の集合を返す.

        `import a.b.c` は `a.b.c` を、`from a.b import x` は `a.b` を収集する。
        相対 import（`from . import x`）は module が None または level>0 となるため、
        domain 内相対参照として扱い外部依存には計上しない（本 domain は絶対 import
        を用いるが、堅牢性のため相対 import も安全側で無視する）。

        Args:
            source: 解析対象の Python ソースコード。
            filename: エラーメッセージ用のファイル名。

        Returns:
            set[str]: import される module 名（ドット区切りの完全名）の集合。
        """
        # ast.parse は構文エラー時に例外を送出する。握りつぶさず呼び出し元へ伝播。
        tree = ast.parse(source, filename=filename)
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                # `import a.b.c[, ...]` の各エイリアス名を収集する。
                for alias in node.names:
                    modules.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                # 相対 import（level>0）や module 欠落は外部依存に計上しない。
                if node.level == 0 and node.module is not None:
                    modules.add(node.module)
        return modules

    def _is_forbidden(self, module_name: str) -> bool:
        """module 名が禁止接頭辞のいずれかに一致するか判定する.

        Args:
            module_name: 判定対象の module 名（完全名）。

        Returns:
            bool: 禁止対象なら True。
        """
        # 完全一致または `<prefix>.` で始まる場合を禁止とみなす
        # （例: 'django' と 'django.conf' の双方を捕捉する）。
        for prefix in self._FORBIDDEN_PREFIXES:
            if module_name == prefix or module_name.startswith(prefix + "."):
                return True
        return False

    def test_domain_files_exist(self) -> None:
        """検査対象の domain ソースが 1 つ以上存在する（検査の空振り防止）."""
        # __pycache__ 等を除いた domain 配下の .py が検出できることを確認する。
        py_files = list(_DOMAIN_DIR.glob("*.py"))
        self.assertGreater(
            len(py_files),
            0,
            msg=f"domain ソースが見つかりません: {_DOMAIN_DIR}",
        )

    def test_domain_does_not_import_adapters_handler_or_django(self) -> None:
        """domain/ の全 .py が adapters・handler・Django を import しない（R4-6）."""
        # domain 配下の各 .py を解析し、禁止対象への import が無いことを検証する。
        for path in sorted(_DOMAIN_DIR.glob("*.py")):
            with self.subTest(file=path.name):
                source = path.read_text(encoding="utf-8")
                imported = self._collect_imported_modules(source, str(path))
                # 禁止対象に該当する import を抽出する。
                violations = sorted(
                    name for name in imported if self._is_forbidden(name)
                )
                self.assertEqual(
                    violations,
                    [],
                    msg=(
                        f"{path.name} が依存方向規則に違反しています（R4-6）。"
                        f"禁止対象への import: {violations}"
                    ),
                )


if __name__ == "__main__":
    # 単体実行用エントリ（`python -m unittest` による探索でも実行可能）。
    unittest.main()
