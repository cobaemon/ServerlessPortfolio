"""Property 1 のプロパティテストと tasks 1.5〜2.6 で再利用する共有テストハーネス.

本モジュールは design.md「Correctness Properties > Property 1」を検証する
（出典: design.md 行376-381、tasks.md 1.4）。
    Property 1: 有効な Contact_Payload は検証を通過し Email_Sender へ引き渡される

検証対象（Validates: Requirements 4.4, 5.1）:
    - R4-4: 検証成功時のみ Email_Sender へ引き渡す（出典: design.md C3, DM3）。
    - R5-1: 4 項目（full_name, email, phone_number, message）のみを送信内容として
      扱う（GDPR データ最小化、出典: design.md DM1）。

テスト方針（出典: design.md「Testing Strategy」行451-454）:
    - PBT ライブラリは Hypothesis（MPL-2.0。ライセンスは requirements-dev.txt に明記）。
    - 単一プロパティを 1 テストで実装し、最小 100 反復（@settings(max_examples=100)）。
    - Django をロードしない（R4-1/R4-2）。ドメイン純粋ロジックのみを対象とする。
    - フォールバック禁止: 生成・検証で問題を握りつぶさず、期待を明示アサートする。

共有ハーネス（tasks 1.5〜2.6 で再利用可能）:
    - `RecordingEmailSender`: ドメイン抽象 `ports.EmailSender` を実装する記録用の
      テストダブル（クリーンアーキテクチャ: テストは具体でなく抽象に依存する）。
    - `valid_contact_fields()`: 全 4 項目が検証制約を満たす入力を生成する Hypothesis
      合成ストラテジ。後続タスクが「有効入力」の生成に再利用する。

実行コマンド（プロジェクトルートから、Django 非ロード）:
    python -m unittest contact_function.tests.test_property_valid_payload
"""

from __future__ import annotations

import string
import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

from contact_function.domain.contact_payload import ContactPayload
from contact_function.domain.ports import EmailSender
from contact_function.domain.send_contact import Success, send_contact
from contact_function.domain.validators import validate_contact_input


class RecordingEmailSender(EmailSender):
    """`ports.EmailSender` を実装する記録用テストダブル（共有ハーネス）.

    ドメイン抽象にのみ依存し（依存性逆転・クリーンアーキテクチャ、出典:
    design.md C3, DM3）、`send` の受領引数を出現順に記録する。実送信の副作用は
    持たない。送信失敗の模擬はここでは行わない（失敗系は Property 4 / task 1.6 の
    責務。単一責務の分離、出典: design.md 行394-399）。
    """

    def __init__(self) -> None:
        """呼び出し記録用の内部状態を初期化する."""
        # send が受領した (payload, from_addr, to_addr) を出現順に保持する。
        self.calls: list[tuple[ContactPayload, str, str]] = []

    def send(self, payload: ContactPayload, from_addr: str, to_addr: str) -> None:
        """検証済み Payload の引き渡しを記録する（実送信は行わない）.

        Args:
            payload: 引き渡された Contact_Payload。
            from_addr: 送信元アドレス（設定値由来）。
            to_addr: 宛先アドレス（設定値由来）。

        Returns:
            None: 記録のみを行い値を返さない（ポート契約に整合、出典: ports.py）。
        """
        # 受領引数をそのまま記録し、引き渡し内容の検証を可能にする。
        self.calls.append((payload, from_addr, to_addr))


# 各項目の最大文字数（出典: validators.py `_MAX_LENGTHS`、design.md DM1）。
_MAX_FULL_NAME = 100
_MAX_EMAIL = 254
_MAX_PHONE = 20
_MAX_MESSAGE = 5000

# email の各構成部（ローカル部・ドメイン部・TLD）に用いる安全な英数字集合。
# 空白と '@' を含まないため検証正規表現 ^[^@\s]+@[^@\s]+\.[^@\s]+$ に必ず適合する
# （出典: validators.py `_EMAIL_PATTERN`、R5-3）。
_EMAIL_ATOM_ALPHABET = string.ascii_letters + string.digits

# email 各部の最大長。3 部 + 区切り 2 文字（'@' と '.'）の合計が上限 _MAX_EMAIL を
# 超えないよう、上限から区切り 2 文字を引いた値を 3 等分して算出する
# （(254-2)//3 = 84、84*3 + 2 = 254 <= 254、出典: DM1）。
_EMAIL_ATOM_MAX = (_MAX_EMAIL - 2) // 3

# 送信元・宛先アドレス（設定値由来の代表値）。Property 1 は Payload の引き渡しを
# 対象とするため固定値を用い、引き渡し時に不変で転送されることを確認する。
_FROM_ADDR = "noreply@example.com"
_TO_ADDR = "owner@example.com"


def _text_with_visible_char(max_size: int) -> st.SearchStrategy[str]:
    """先頭に可視 ASCII 文字を 1 つ持ち、長さが max_size 以下の文字列を生成する.

    validators.py は `value.strip() == ""` を MISSING とみなすため、strip 後も
    空にならないことを保証する必要がある（出典: validators.py `_validate_field`、
    R5-2）。先頭を可視文字（空白でない印字可能 ASCII）に固定することで、末尾に
    空白文字が続いても strip 結果が非空となることを保証する。

    Args:
        max_size: 生成文字列の最大長（この値以下を保証する）。

    Returns:
        SearchStrategy[str]: strip 後非空かつ長さ max_size 以下の文字列ストラテジ。
    """
    # 先頭 1 文字は空白でない印字可能 ASCII（コードポイント 33〜126）に固定する。
    head = st.characters(min_codepoint=33, max_codepoint=126)
    # 残りは任意テキスト。合計で max_size を超えないよう後段で切り詰める。
    tail = st.text(max_size=max_size - 1)
    # 先頭可視文字 + 任意テキストを結合し、長さ上限を厳守するため切り詰める。
    # 先頭文字は index 0 に必ず残るため strip 後非空が保たれる。
    return st.builds(
        lambda head_ch, tail_str: (head_ch + tail_str)[:max_size], head, tail
    )


@st.composite
def valid_contact_fields(draw: st.DrawFn) -> dict[str, str]:
    """全 4 項目が検証制約を満たす問い合わせ入力を生成する合成ストラテジ（共有ハーネス）.

    生成規則（出典: validators.py 検証規則、design.md DM1、R5-1〜R5-4, R5-6）:
        - full_name: strip 後非空、長さ 100 以下。
        - email: 正規表現 ^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$ に適合、長さ 254 以下。
        - phone_number: ASCII 数字のみ（str.isdigit() が True）、長さ 20 以下。
        - message: strip 後非空、長さ 5000 以下。
    4 項目のみを含み、余剰フィールドを含めない（R5-1、GDPR データ最小化）。

    Args:
        draw: Hypothesis の draw 関数（合成ストラテジ内で値を取得する）。

    Returns:
        dict[str, str]: 検証を通過する 4 項目の入力辞書。
    """
    # full_name: 可視先頭文字で strip 非空を保証しつつ上限 100 以内。
    full_name = draw(_text_with_visible_char(_MAX_FULL_NAME))

    # email: ローカル部・ドメイン部・TLD を英数字で生成し local@dom.tld を構成する。
    local = draw(
        st.text(alphabet=_EMAIL_ATOM_ALPHABET, min_size=1, max_size=_EMAIL_ATOM_MAX)
    )
    domain = draw(
        st.text(alphabet=_EMAIL_ATOM_ALPHABET, min_size=1, max_size=_EMAIL_ATOM_MAX)
    )
    tld = draw(
        st.text(alphabet=_EMAIL_ATOM_ALPHABET, min_size=1, max_size=_EMAIL_ATOM_MAX)
    )
    email = f"{local}@{domain}.{tld}"

    # phone_number: ASCII 数字のみ・非空・上限 20（str.isdigit() が True を保証）。
    phone_number = draw(
        st.text(alphabet=string.digits, min_size=1, max_size=_MAX_PHONE)
    )

    # message: 可視先頭文字で strip 非空を保証しつつ上限 5000 以内。
    message = draw(_text_with_visible_char(_MAX_MESSAGE))

    # 4 項目のみを返す（余剰フィールドを含めない、R5-1）。
    return {
        "full_name": full_name,
        "email": email,
        "phone_number": phone_number,
        "message": message,
    }


class ValidPayloadProperty(unittest.TestCase):
    """Property 1 のプロパティテストを保持するテストケース."""

    # 最小 100 反復（出典: design.md 行452）。生成データ（最大 5000 文字の message
    # 等）による実行時間のばらつきで per-example の締切超過が誤検知を招くのを避ける
    # ため deadline を無効化する（検証ロジックは決定的でありエラーは握りつぶさない）。
    @settings(max_examples=100, deadline=None)
    @given(fields=valid_contact_fields())
    def test_valid_payload_passes_validation_and_is_handed_off(
        self, fields: dict[str, str]
    ) -> None:
        """Feature: cost-performance-optimization, Property 1: 有効な Contact_Payload は検証を通過し Email_Sender へ引き渡される

        Validates: Requirements 4.4, 5.1

        制約を満たす任意の 4 項目入力について、(1) 入力検証が成功し、(2) 検証済み
        Contact_Payload が Email_Sender へちょうど 1 回、4 項目そのままの値で
        引き渡され、(3) 結果が Success となることを検証する（出典: design.md
        行379-381、send_contact.py）。
        """
        # (1) 検証の成功を明示的に確認する（Property の「検証は成功し」に対応）。
        validation = validate_contact_input(fields)
        self.assertTrue(
            validation.is_valid,
            msg=f"有効入力が検証を通過しなかった: {validation.violations!r}",
        )

        # 記録用 Email_Sender を注入してユースケースを実行する（依存性逆転）。
        sender = RecordingEmailSender()
        result = send_contact(
            fields=fields,
            from_addr=_FROM_ADDR,
            to_addr=_TO_ADDR,
            email_sender=sender,
        )

        # (3) 結果は Success（送信成功、出典: R6-6、send_contact.py）。
        self.assertIsInstance(result, Success)

        # (2) Email_Sender へちょうど 1 回引き渡されたこと（引き渡しの発生）。
        self.assertEqual(len(sender.calls), 1, msg="送信はちょうど 1 回行われるべき")

        # 引き渡された Payload と転送された from/to を検証する。
        handed_payload, handed_from, handed_to = sender.calls[0]
        # 4 項目が入力そのままで構築されていること（4 項目限定・値の一致、R5-1）。
        self.assertEqual(
            handed_payload,
            ContactPayload(
                full_name=fields["full_name"],
                email=fields["email"],
                phone_number=fields["phone_number"],
                message=fields["message"],
            ),
        )
        # 送信元・宛先が不変で転送されること（設定値由来、出典: DM3/DM4）。
        self.assertEqual(handed_from, _FROM_ADDR)
        self.assertEqual(handed_to, _TO_ADDR)


if __name__ == "__main__":
    # 単体実行用エントリ（`python -m unittest` による探索でも実行可能）。
    unittest.main()
