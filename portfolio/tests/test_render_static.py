"""`render_static` コマンドおよびハニーポット非収集の単体テスト（例ベース）.

本モジュールは tasks.md サブタスク 4.5 を検証する例ベース単体テストを実装する
（出典: tasks.md「4.5 `render_static` の単体テストを作成」、`_Requirements: 3.6,
9.5, 5.1`）。プロパティテストではなく、具体例による検証である。

検証対象と要件対応:
    1. `render_static` のビルド中断・部分同期なし（Requirement 3.6）
       - IF ある Supported_Language の Prerendered_Page 生成が失敗した場合、THEN
         Build_Pipeline はビルドを失敗として扱い、失敗した言語を明示するエラーを
         出力し、S3 への部分同期を行わず既存の配信状態を保全する
         （出典: requirements.md R3-6、design.md C2「いずれかの言語で生成失敗時は
         非ゼロ終了しビルドを失敗させる（部分同期しない）」）。
       - 本テストは、1 言語のレンダリング失敗を注入し、(a) コマンドが
         `CommandError` で中断（＝非ゼロ終了に相当）し、(b) エラーに失敗言語名を
         含み、(c) 出力先（STATIC_ROOT）に部分生成物が一切書き出されない
         （部分同期の原因となる部分出力が生じない）ことを検証する。

    2. ハニーポット隠しフィールドの非収集・非送信（Requirements 9.5, 5.1）
       - R9-5: Contact_Function は GDPR データ最小化に従い Contact_Payload の
         4 項目のみを収集する。
       - R5-1: Contact_Payload は 4 項目のみを受領対象とし、これら以外の
         フィールド（例: ハニーポット隠しフィールド）を送信内容として処理しない
         （出典: requirements.md R5-1, R9-5、design.md C7, DM1）。
       - 本テストは例ベースで、(a) ハニーポット隠しフィールド `website` に値が
         ある場合は 4xx 拒否となり Email_Sender へ引き渡されない（送信内容として
         処理されない）こと、(b) 正常送信時に Email_Sender へ渡る Contact_Payload
         が 4 項目のみで構成され、ハニーポットフィールドを属性として保持しない
         こと、(c) `ContactPayload` の型が 4 項目のみを持つことを検証する。

テスト方針（出典: design.md「Testing Strategy > 単体/例ベーステスト」、
兄弟テスト portfolio/tests/test_regression.py の SimpleTestCase 様式）:
    - DB を要しないため `SimpleTestCase` を用いる。
    - `render_static` の失敗注入は `render_to_string` をモックし、対象言語の
      レンダリング時のみ例外を送出する（実挙動＝二段階方式の中断を検証）。
    - フォールバック禁止: 期待を明示アサートし、問題を握りつぶさない。
    - 個人データはアサーションに用いる値も含めテスト用ダミーに限定する。

実行コマンド（プロジェクトルートから）:
    python manage.py test portfolio.tests.test_render_static
"""

from __future__ import annotations

import dataclasses
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings
from django.utils import translation

from contact_function.domain.contact_payload import ContactPayload
from contact_function.domain.ports import ConfigProvider, EmailSender
from contact_function.handler import handle_contact_request

# 失敗を注入する対象言語（settings.LANGUAGES の中間言語を選び、先行言語が
# 成功済みでも部分出力が書き出されないことを確認する。出典: base.py LANGUAGES
# = ja, en, fr, es, ru, zh-hans, ar）。
_FAILING_LANGUAGE = "fr"

# レンダリング成功言語で返すダミー HTML（インライン script/style を含まないため
# CSP ハッシュは空になり、CSP 生成は正常に完了する。出典: _csp_hash.py）。
_DUMMY_HTML = "<!doctype html><html><head></head><body>dummy</body></html>"

# CSP 生成に必要な CloudFront ドメイン（dev 設定には未定義のためテストで注入する。
# 出典: prod.py AWS_S3_CUSTOM_DOMAIN、render_static._resolve_cloudfront_domain）。
_TEST_CLOUDFRONT_DOMAIN = "static.example.test"

# ハニーポット隠しフィールド名（採用名。出典: contact_function/handler.py
# `_HONEYPOT_FIELD_NAME = "website"`、design.md C7）。
_HONEYPOT_FIELD_NAME = "website"

# テストで用いる許可 Origin（ゼロトラスト検証を通過させるためのダミー値）。
_ALLOWED_ORIGIN = "https://portfolio.example.test"


def _make_render_side_effect(failing_language: str):
    """指定言語のレンダリング時のみ例外を送出する `render_to_string` 差替関数を返す.

    `render_static._render_language_page` は `translation.override(language)` の
    文脈内で `render_to_string` を呼ぶため、差替関数側では現在有効な言語を
    `translation.get_language()` で判定し、対象言語のときだけ失敗させる
    （出典: portfolio/management/commands/render_static.py の描画ループ）。

    Args:
        failing_language: レンダリング失敗を注入する言語コード。

    Returns:
        Callable: `render_to_string(template_name, context=None, ...)` 互換の
            差替関数。対象言語では `RuntimeError` を送出し、それ以外では
            ダミー HTML を返す。
    """

    def _side_effect(template_name, context=None, *args, **kwargs):
        """対象言語のみ失敗し、他言語ではダミー HTML を返す差替本体."""
        # 現在有効化されている言語を取得する（override 文脈内で呼ばれる）。
        current_language = translation.get_language()
        if current_language == failing_language:
            # 対象言語のレンダリング失敗を注入する（フォールバックせず送出）。
            raise RuntimeError("injected render failure")
        # 成功言語ではダミー HTML を返す（後続の CSP 生成も正常完了する）。
        return _DUMMY_HTML

    return _side_effect


class _RecordingEmailSender(EmailSender):
    """送信呼び出しを記録するテスト用の Email_Sender 実装.

    実際の SES 送信を行わず、`send` が受領した Contact_Payload と呼び出し回数を
    記録する。これにより「Email_Sender へ引き渡されたか」「引き渡された内容が
    4 項目のみか」を検証できる（出典: design.md DM3 EmailSender ポート）。
    """

    def __init__(self) -> None:
        """記録用の状態を初期化する."""
        # send が呼ばれた回数（0 のままなら未引き渡し）。
        self.call_count = 0
        # 最後に受領した Contact_Payload（未呼び出しなら None）。
        self.last_payload: ContactPayload | None = None

    def send(self, payload: ContactPayload, from_addr: str, to_addr: str) -> None:
        """受領した Contact_Payload と呼び出しを記録する（送信はしない）."""
        # 引き渡し内容と回数を記録する。例外は送出しない（成功送信を模す）。
        self.call_count += 1
        self.last_payload = payload


class _StubConfigProvider(ConfigProvider):
    """許可 Origin・送信元/宛先を固定値で返すテスト用 ConfigProvider.

    Parameter Store へアクセスせず、Origin 検証と送信元/宛先取得を通過させる
    ための最小スタブ（出典: design.md DM4、handler の依存注入）。
    """

    def get_from_address(self) -> str:
        """テスト用の送信元アドレスを返す."""
        return "from@example.test"

    def get_to_address(self) -> str:
        """テスト用の宛先アドレスを返す."""
        return "to@example.test"

    def get_allowed_origins(self) -> tuple[str, ...]:
        """テスト用の許可 Origin 一覧を返す."""
        return (_ALLOWED_ORIGIN,)


def _build_post_event(fields: dict[str, str]) -> dict[str, object]:
    """許可 Origin 付き form-encoded の問い合わせ POST イベントを構築する.

    Args:
        fields: リクエストボディに含めるフィールド名→値のマッピング。

    Returns:
        dict[str, object]: API Gateway プロキシ統合形式のイベント。
    """
    # form-encoded ボディを構築する（現行 Django フォーム互換の既定形式）。
    body = "&".join(f"{key}={value}" for key, value in fields.items())
    return {
        "httpMethod": "POST",
        # Origin を許可リスト内の値にし、Origin 検証を通過させる。
        "headers": {
            "Origin": _ALLOWED_ORIGIN,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        "body": body,
        "isBase64Encoded": False,
    }


class RenderStaticBuildInterruptionTests(SimpleTestCase):
    """`render_static` の 1 言語生成失敗時のビルド中断・部分同期なしを検証する."""

    def test_single_language_failure_aborts_build_without_partial_output(self) -> None:
        """1 言語の生成失敗でビルドが中断し失敗言語を明示、部分出力を残さないこと.

        Validates: Requirements 3.6

        中間言語 `fr` のレンダリング失敗を注入し、(a) `CommandError` で中断する
        （非ゼロ終了に相当）、(b) エラーに失敗言語名を含む、(c) STATIC_ROOT に
        生成物が一切書き出されない（部分同期の原因となる部分出力が生じない）
        ことを検証する（出典: requirements.md R3-6、design.md C2）。
        """
        # STATIC_ROOT を独立した一時ディレクトリへ差し替え、書き出しの有無を観測する。
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir)
            with override_settings(
                STATIC_ROOT=str(output_root),
                AWS_S3_CUSTOM_DOMAIN=_TEST_CLOUDFRONT_DOMAIN,
            ):
                # 対象言語 `fr` のみレンダリング失敗を注入する。
                side_effect = _make_render_side_effect(_FAILING_LANGUAGE)
                with patch(
                    "portfolio.management.commands.render_static.render_to_string",
                    side_effect=side_effect,
                ):
                    # (a) ビルド中断: CommandError が送出されること。
                    with self.assertRaises(CommandError) as raised:
                        call_command("render_static")

            # (b) エラーメッセージに失敗言語名が含まれること（失敗言語の明示、R3-6）。
            self.assertIn(
                _FAILING_LANGUAGE,
                str(raised.exception),
                msg=f"エラーに失敗言語 '{_FAILING_LANGUAGE}' が明示されていない: "
                f"{raised.exception!r}",
            )

            # (c) 部分同期なし: STATIC_ROOT にファイルが一切書き出されていないこと。
            #     先行言語（ja, en）は成功済みだが、二段階方式により全言語成功前は
            #     書き出さないため、部分出力（部分同期の原因）が残らない（R3-6）。
            written_files = [p for p in output_root.rglob("*") if p.is_file()]
            self.assertEqual(
                written_files,
                [],
                msg=f"部分出力が書き出されている（部分同期の恐れ）: {written_files!r}",
            )


class HoneypotNotCollectedTests(SimpleTestCase):
    """ハニーポット隠しフィールドが 4 項目に含まれず送信内容化しないことを検証する."""

    def test_contact_payload_type_has_only_four_fields(self) -> None:
        """`ContactPayload` が 4 項目のみを持ち、ハニーポット項目を含まないこと.

        Validates: Requirements 5.1, 9.5

        値オブジェクトの構造として 4 項目（full_name, email, phone_number,
        message）のみを保持し、ハニーポット隠しフィールド名を属性に持たない
        ことを検証する（出典: requirements.md R5-1, R9-5、design.md DM1）。
        """
        # dataclass のフィールド名を取得し、4 項目限定であることを確認する。
        field_names = tuple(f.name for f in dataclasses.fields(ContactPayload))
        self.assertEqual(
            field_names,
            ("full_name", "email", "phone_number", "message"),
            msg=f"Contact_Payload が 4 項目限定でない: {field_names!r}",
        )
        # ハニーポットフィールド名が Contact_Payload の項目に含まれないこと。
        self.assertNotIn(
            _HONEYPOT_FIELD_NAME,
            field_names,
            msg="ハニーポット項目が Contact_Payload に含まれている",
        )

    def test_honeypot_value_rejects_and_is_not_sent(self) -> None:
        """ハニーポットに値がある場合は 4xx 拒否かつ Email_Sender へ非引き渡し.

        Validates: Requirements 5.1, 9.5

        隠しフィールド `website` に値を含む POST は自動投稿として 4xx 拒否され、
        Email_Sender へ引き渡されない（送信内容として処理されない）ことを
        検証する（出典: requirements.md R5-1, R9-5、design.md C7, DM1）。
        """
        # 4 項目は正常値だが、ハニーポット `website` に値を入れて自動投稿を模す。
        event = _build_post_event(
            {
                "full_name": "Tester",
                "email": "tester@example.test",
                "phone_number": "0123456789",
                "message": "hello",
                _HONEYPOT_FIELD_NAME: "bot-injected-value",
            }
        )
        email_sender = _RecordingEmailSender()

        # handler を依存注入で実行する（Parameter Store・SES へはアクセスしない）。
        response = handle_contact_request(event, _StubConfigProvider(), email_sender)

        # 4xx 拒否であること（ハニーポット発火は 403）。
        self.assertEqual(
            response["statusCode"],
            403,
            msg=f"ハニーポット発火が 4xx 拒否になっていない: {response!r}",
        )
        # Email_Sender へ引き渡されていないこと（送信内容として処理されない、R5-1）。
        self.assertEqual(
            email_sender.call_count,
            0,
            msg="ハニーポット発火にもかかわらず Email_Sender へ引き渡された",
        )

    def test_honeypot_field_not_part_of_sent_payload(self) -> None:
        """正常送信時、Email_Sender へ渡る Payload が 4 項目のみでハニーポットを含まないこと.

        Validates: Requirements 5.1, 9.5

        ハニーポットフィールドを空で含む正常 POST（人間の送信を模す）で、
        Email_Sender へ引き渡される Contact_Payload が 4 項目のみで構成され、
        ハニーポット項目を属性として保持しないことを検証する（送信内容として
        処理されない、出典: requirements.md R5-1, R9-5、design.md DM1）。
        """
        # 人間の送信ではハニーポットは空。加えて 4 項目は正常値を与える。
        event = _build_post_event(
            {
                "full_name": "Tester",
                "email": "tester@example.test",
                "phone_number": "0123456789",
                "message": "hello",
                # 空のハニーポットは非発火（送信へ進む）。値は送信内容化しない。
                _HONEYPOT_FIELD_NAME: "",
            }
        )
        email_sender = _RecordingEmailSender()

        # handler を依存注入で実行する。
        response = handle_contact_request(event, _StubConfigProvider(), email_sender)

        # 正常送信は 200 系であること。
        self.assertEqual(
            response["statusCode"],
            200,
            msg=f"正常送信が 200 系になっていない: {response!r}",
        )
        # Email_Sender へ 1 回引き渡されたこと。
        self.assertEqual(email_sender.call_count, 1)

        # 引き渡された Contact_Payload が 4 項目のみで、ハニーポット項目を持たないこと。
        payload = email_sender.last_payload
        self.assertIsInstance(payload, ContactPayload)
        self.assertFalse(
            hasattr(payload, _HONEYPOT_FIELD_NAME),
            msg="Contact_Payload がハニーポット項目を属性として保持している",
        )
        # 4 項目の値が入力どおりであること（送信内容が 4 項目に限定されている）。
        self.assertEqual(payload.full_name, "Tester")
        self.assertEqual(payload.email, "tester@example.test")
        self.assertEqual(payload.phone_number, "0123456789")
        self.assertEqual(payload.message, "hello")
