"""Property 7（ハニーポット発火時は Email_Sender へ引き渡さない）のプロパティテスト.

本モジュールは design.md「Correctness Properties > Property 7」を検証する
（出典: design.md 行412-416、tasks.md 2.5）。
    Property 7: ハニーポット発火時は Email_Sender へ引き渡さない

検証対象（Validates: Requirements 8.6, 9.5）:
    - R8-6: 問い合わせ経路の乱用（ボット自動投稿）に対する保護。ハニーポットの
      隠しフィールドに空でない値がある場合は自動投稿と判定し拒否する
      （出典: design.md C7「ハニーポット」、Error Handling 行428、DM2
      `HoneypotRejected` 行273）。
    - R9-5: GDPR データ最小化。ハニーポットの隠しフィールドは Contact_Payload の
      4 項目（full_name, email, phone_number, message）に含めず、個人データとして
      収集・処理しない（出典: design.md DM1 行264、C7 行223）。

対象実装（本タスク指示に従い実際の handler API に整合させる）:
    - `contact_function.handler.handle_contact_request(event, config_provider,
      email_sender)`: API Gateway プロキシ統合イベントを処理する本体（依存注入
      可能。出典: handler.py）。
    - ハニーポット隠しフィールド名は handler が採用する `website`
      （`handler._HONEYPOT_FIELD_NAME`）。テストは当該定数を import して実装と
      同期させ、名称のハードコードによる乖離を避ける（出典: handler.py
      `_HONEYPOT_FIELD_NAME = "website"`）。
    - handler はヘッダの `origin` を許可リストと照合し、一致時のみ後続へ継続する
      （不一致/欠落/空は Origin 拒否）。本テストは Origin 拒否ではなくハニーポット
      挙動を分離検証するため、常に許可リストに含まれる Origin を供給する
      （出典: handler.py Origin 検証、design.md C7）。
    - ハニーポット発火時、handler は Contact_Payload を構築せず Email_Sender へ
      引き渡さずに HTTP 4xx（403 `honeypot_rejected`）を返す（出典: handler.py
      `_result_to_response(HoneypotRejected(), ...)`、DM2 行273）。

テスト方針（出典: design.md「Testing Strategy」行451-458、tasks.md 2.5）:
    - PBT ライブラリは Hypothesis（MPL-2.0。ライセンスは requirements-dev.txt に
      明記済み。tasks 1.4 で確認済みの共有前提）。
    - Django をロードしない。handler・adapters・domain の純粋ロジックのみを対象と
      する（出典: requirements.md R4-1, R4-2）。
    - 単一プロパティを 1 テストで実装し、最小 100 反復（@settings(max_examples=
      100, deadline=None)）。
    - フォールバック禁止: 生成・検証で問題を握りつぶさず、期待を明示アサートする。

共有ハーネス再利用（tasks 1.4 が確立、tasks 2.5 で再利用）:
    - `RecordingEmailSender`: `ports.EmailSender` を実装する記録用テストダブル。
      ハニーポット発火時に呼ばれないこと（非引き渡し）を `calls` で検証する。
    - `valid_contact_fields()`: 4 項目すべてが検証制約を満たす入力を生成する
      Hypothesis 合成ストラテジ。「otherwise valid input」の生成に再利用する。

イベントボディ形式（本テストの採用形式）:
    - Content-Type を `application/json` とし、handler の JSON 解釈経路
      （`_parse_body`）を用いる。JSON はキー・値ともに文字列で往復が厳密であり、
      form-encoded の記号往復差異を避けて生成入力を忠実に handler へ渡せる
      （出典: handler.py `_parse_body` JSON 経路）。

実行コマンド（プロジェクトルートから、Django 非ロード）:
    python -m unittest contact_function.tests.test_property_honeypot -v
"""

from __future__ import annotations

import dataclasses
import json
import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

from contact_function.domain.contact_payload import ContactPayload
from contact_function.domain.ports import ConfigProvider
from contact_function.handler import _HONEYPOT_FIELD_NAME, handle_contact_request
from contact_function.tests.test_property_valid_payload import (
    RecordingEmailSender,
    valid_contact_fields,
)

# 許可リストに含める Origin（テスト固定値）。Origin 拒否経路を避けハニーポット
# 挙動を分離検証するため、供給する Origin と設定プロバイダの許可 Origin を一致
# させる（出典: handler.py Origin 検証、design.md C7）。
_ALLOWED_ORIGIN = "https://allowed.example.com"

# 設定値由来の送信元・宛先（テスト固定値）。ハニーポット非発火（制御ケース）で
# handler が設定値を取得し送信へ継続する経路を成立させるために用いる
# （出典: handler.py `get_from_address`/`get_to_address`、DM4）。
_FROM_ADDR = "noreply@example.com"
_TO_ADDR = "owner@example.com"

# handler が期待する HTTP ステータスと応答本文キー（出典: handler.py
# `_result_to_response`、DM2 行273/行266）。
_STATUS_HONEYPOT_REJECTED = 403
_STATUS_SUCCESS = 200
_ERROR_HONEYPOT = "honeypot_rejected"

# Contact_Payload の 4 項目（GDPR データ最小化、出典: DM1、handler
# `_CONTENT_FIELDS`）。構造的不変条件の検証に用いる。
_CONTENT_FIELD_NAMES = ("full_name", "email", "phone_number", "message")


class FakeConfigProvider(ConfigProvider):
    """`ports.ConfigProvider` を実装するテスト用の設定プロバイダ（依存注入用）.

    Parameter Store 等の外部 I/O を持たず、テストが指定した許可 Origin・送信元・
    宛先を返す（依存性逆転・クリーンアーキテクチャ、出典: design.md C3、
    ports.py `ConfigProvider`）。ハニーポット挙動の分離検証に必要な設定のみを
    供給し、フォールバックはしない（欠落を模擬する責務は本テストにはない）。
    """

    def __init__(
        self, allowed_origins: tuple[str, ...], from_addr: str, to_addr: str
    ) -> None:
        """許可 Origin・送信元・宛先を保持して初期化する.

        Args:
            allowed_origins: 許可 Origin の不変な列（handler が Origin 照合に用いる）。
            from_addr: SES 送信元アドレス（設定値由来）。
            to_addr: SES 宛先アドレス（設定値由来）。
        """
        # テスト指定の設定値をそのまま保持する（外部取得・既定値補完はしない）。
        self._allowed_origins = allowed_origins
        self._from_addr = from_addr
        self._to_addr = to_addr

    def get_from_address(self) -> str:
        """SES 送信元アドレスを返す（出典: ports.ConfigProvider）."""
        return self._from_addr

    def get_to_address(self) -> str:
        """SES 宛先アドレスを返す（出典: ports.ConfigProvider）."""
        return self._to_addr

    def get_allowed_origins(self) -> tuple[str, ...]:
        """許可 Origin の不変な列を返す（出典: ports.ConfigProvider）."""
        return self._allowed_origins


@st.composite
def _fired_honeypot_value(draw: st.DrawFn) -> str:
    """ハニーポット発火となる「strip 後非空」の隠しフィールド値を生成する.

    handler の判定は `honeypot_value.strip() != ""`（出典: handler.py
    ハニーポット判定）。先頭に空白でない印字可能 ASCII（コードポイント 33〜126）
    を 1 文字固定で置くことで、末尾に空白が続いても strip 後が必ず非空となり、
    発火（拒否）を確実にする（決めつけを避け、判定条件を満たすことを保証する）。

    Args:
        draw: Hypothesis の draw 関数。

    Returns:
        str: strip 後が非空となる隠しフィールド値（発火する値）。
    """
    # 先頭 1 文字は空白でない印字可能 ASCII に固定する（strip 後非空を保証）。
    head = draw(st.characters(min_codepoint=33, max_codepoint=126))
    # 残りは任意テキスト（記号・空白・多言語文字を含み得る、任意値の網羅）。
    tail = draw(st.text(max_size=50))
    return head + tail


def _empty_honeypot_value() -> st.SearchStrategy[str]:
    """ハニーポット非発火となる「strip 後空」の隠しフィールド値を生成する.

    空文字または空白のみ（半角空白・タブ・改行・復帰）で構成し、handler の
    `strip() != ""` 判定で発火しないことを保証する（制御ケース用。判定が
    「空でない値」に特化していることを示す対照）。

    Returns:
        SearchStrategy[str]: strip 後が空となる隠しフィールド値。
    """
    # 空白類のみからなる文字列（空文字を含む）。strip すると必ず空になる。
    return st.text(alphabet=" \t\r\n", max_size=5)


def _build_event(body_fields: dict[str, str], origin: str) -> dict[str, object]:
    """API Gateway プロキシ統合イベント（POST・JSON ボディ）を組み立てる.

    handler の実 API に整合する最小構成のイベントを生成する。ボディは JSON
    （Content-Type: application/json）で厳密に往復させ、生成入力を忠実に渡す
    （出典: handler.py `_parse_body` JSON 経路、`handle_contact_request`）。

    Args:
        body_fields: リクエストボディへ載せるフィールド辞書（4 項目に加え、
            ハニーポット隠しフィールドを含み得る）。
        origin: リクエストの Origin ヘッダ値（許可リスト一致を前提に供給）。

    Returns:
        dict[str, object]: `httpMethod`/`headers`/`body`/`isBase64Encoded` を
            備えたプロキシ統合イベント。
    """
    return {
        # 動的経路は POST のみ（出典: handler.py メソッド判定）。
        "httpMethod": "POST",
        # Origin と Content-Type を供給する（キーの大小は handler が正規化する）。
        "headers": {
            "Origin": origin,
            "Content-Type": "application/json",
        },
        # JSON 文字列ボディ。非 ASCII を保持するため ensure_ascii=False とする。
        "body": json.dumps(body_fields, ensure_ascii=False),
        # base64 エンコードは用いない。
        "isBase64Encoded": False,
    }


class HoneypotProperty(unittest.TestCase):
    """Property 7 のプロパティテストと、その特異性を示す制御テストを保持する."""

    def test_contact_payload_has_only_four_fields_without_honeypot(self) -> None:
        """Contact_Payload が 4 項目のみで隠しフィールドを構造上持たないことを検証する.

        Validates: Requirements 9.5

        ハニーポット隠しフィールド（`website`）が Contact_Payload の項目集合に
        構造的に含まれないこと（4 項目限定・GDPR データ最小化）を確認する
        （出典: DM1 行264、contact_payload.py の 4 項目定義）。プロパティに依らず
        常に成り立つ不変条件であるため単一の明示アサートで検証する。
        """
        # ContactPayload の宣言フィールド名を取得する。
        field_names = tuple(f.name for f in dataclasses.fields(ContactPayload))
        # 4 項目が過不足なく一致すること（余剰フィールドを持たない）。
        self.assertEqual(field_names, _CONTENT_FIELD_NAMES)
        # ハニーポット隠しフィールド名が Contact_Payload に含まれないこと（R9-5）。
        self.assertNotIn(_HONEYPOT_FIELD_NAME, field_names)

    # 最小 100 反復（出典: design.md 行453）。生成データ（最大 5000 文字の message
    # 等）による per-example の締切超過での誤検知を避けるため deadline を無効化する
    # （判定ロジックは決定的でありエラーは握りつぶさない）。
    @settings(max_examples=100, deadline=None)
    @given(fields=valid_contact_fields(), honeypot=_fired_honeypot_value())
    def test_honeypot_fired_rejects_and_is_not_handed_off(
        self, fields: dict[str, str], honeypot: str
    ) -> None:
        """Feature: cost-performance-optimization, Property 7: ハニーポット発火時は Email_Sender へ引き渡さない

        Validates: Requirements 8.6, 9.5

        4 項目が有効な入力に対しても、ハニーポット隠しフィールドに空でない値
        （任意値）が存在する場合、handler は (1) HTTP 4xx（403 `honeypot_rejected`）
        で拒否し、(2) Email_Sender へ引き渡さず（記録用モックが 1 度も呼ばれず）、
        (3) 隠しフィールドを Contact_Payload の 4 項目に含めない（構築されない）
        ことを検証する（出典: design.md 行412-416、handler.py ハニーポット判定、
        DM2 行273、DM1 行264）。
        """
        # 記録用 Email_Sender と設定プロバイダを注入する（依存性逆転）。
        sender = RecordingEmailSender()
        config_provider = FakeConfigProvider(
            allowed_origins=(_ALLOWED_ORIGIN,),
            from_addr=_FROM_ADDR,
            to_addr=_TO_ADDR,
        )

        # 有効な 4 項目に、発火する隠しフィールド（strip 後非空）を加えたボディ。
        body_fields = dict(fields)
        body_fields[_HONEYPOT_FIELD_NAME] = honeypot

        # 許可 Origin を供給し、Origin 拒否ではなくハニーポット挙動を分離検証する。
        event = _build_event(body_fields, origin=_ALLOWED_ORIGIN)

        # handler を実行する。
        response = handle_contact_request(event, config_provider, sender)

        # (1) HTTP 4xx（403）で拒否されること。
        self.assertEqual(
            response["statusCode"],
            _STATUS_HONEYPOT_REJECTED,
            msg=f"ハニーポット発火は 4xx で拒否されるべき: {response!r}",
        )
        # 応答本文がハニーポット拒否を示すこと（他の 4xx との区別）。
        body = json.loads(response["body"])
        self.assertEqual(body.get("error"), _ERROR_HONEYPOT)

        # (2) Email_Sender へ引き渡されていないこと（非引き渡し、非収集の担保）。
        self.assertEqual(
            len(sender.calls), 0, msg="発火時は Email_Sender を呼んではならない"
        )

    @settings(max_examples=100, deadline=None)
    @given(
        fields=valid_contact_fields(),
        include_empty_honeypot=st.booleans(),
        empty_value=_empty_honeypot_value(),
    )
    def test_honeypot_absent_or_empty_allows_handoff_and_excludes_field(
        self,
        fields: dict[str, str],
        include_empty_honeypot: bool,
        empty_value: str,
    ) -> None:
        """制御（対照）ケース: 隠しフィールドが不在または空値なら発火せず引き渡される.

        Validates: Requirements 8.6, 9.5

        ハニーポット判定が「空でない値」に特化していることを示す対照検証。隠し
        フィールドが不在、または存在しても strip 後空（空白のみ）で、かつ 4 項目が
        有効・Origin 許可の場合、handler は (1) ハニーポット拒否とせず送信成功
        （HTTP 200）を返し、(2) Email_Sender へちょうど 1 回引き渡し、(3) 引き渡す
        Contact_Payload は 4 項目のみで隠しフィールドを含まないことを検証する
        （出典: handler.py ハニーポット判定・`_CONTENT_FIELDS`、DM1 行264、
        design.md C7 行223）。
        """
        # 記録用 Email_Sender と設定プロバイダを注入する（依存性逆転）。
        sender = RecordingEmailSender()
        config_provider = FakeConfigProvider(
            allowed_origins=(_ALLOWED_ORIGIN,),
            from_addr=_FROM_ADDR,
            to_addr=_TO_ADDR,
        )

        # 有効な 4 項目を基に、隠しフィールドを「不在」または「空値」で付与する。
        body_fields = dict(fields)
        if include_empty_honeypot:
            # 存在しても strip 後空なら発火しないこと（対照）を検証するため付与する。
            body_fields[_HONEYPOT_FIELD_NAME] = empty_value

        # 許可 Origin を供給する。
        event = _build_event(body_fields, origin=_ALLOWED_ORIGIN)

        # handler を実行する。
        response = handle_contact_request(event, config_provider, sender)

        # (1) ハニーポット拒否ではなく送信成功（HTTP 200）となること。
        self.assertEqual(
            response["statusCode"],
            _STATUS_SUCCESS,
            msg=f"不在/空の隠しフィールドは発火してはならない: {response!r}",
        )
        body = json.loads(response["body"])
        self.assertNotEqual(body.get("error"), _ERROR_HONEYPOT)

        # (2) Email_Sender へちょうど 1 回引き渡されること（引き渡しの発生）。
        self.assertEqual(
            len(sender.calls), 1, msg="非発火・有効入力では送信は 1 回行われるべき"
        )

        # (3) 引き渡された Contact_Payload は 4 項目のみで隠しフィールドを含まない。
        handed_payload, _handed_from, _handed_to = sender.calls[0]
        self.assertEqual(
            handed_payload,
            ContactPayload(
                full_name=fields["full_name"],
                email=fields["email"],
                phone_number=fields["phone_number"],
                message=fields["message"],
            ),
        )
        # Contact_Payload は構造上 4 項目のみで、隠しフィールド属性を持たない（R9-5）。
        payload_field_names = tuple(
            f.name for f in dataclasses.fields(handed_payload)
        )
        self.assertNotIn(_HONEYPOT_FIELD_NAME, payload_field_names)


if __name__ == "__main__":
    # 単体実行用エントリ（`python -m unittest` による探索でも実行可能）。
    unittest.main()
