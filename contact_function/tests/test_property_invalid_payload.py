"""Property 2 のプロパティテスト（無効な Contact_Payload の検証）.

本モジュールは design.md「Correctness Properties」および tasks.md 1.5 が定める
Property 2 を検証する（出典: tasks.md 行 1.5、requirements.md Requirement 5）。
    Property 2: 無効な Contact_Payload は必ず 400 系エラーとなり対象項目を示し
                送信されない

検証対象（Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.6, 9.5）:
    - R5-1: 4 項目（full_name, email, phone_number, message）以外のフィールドを
      送信内容として処理しない（余剰フィールドを不備として扱う）。
    - R5-2: 必須項目の未送信・空文字は 400 系・対象項目提示・非送信。
    - R5-3: メールアドレスの電子メール形式不正は 400 系・対象項目提示・非送信。
    - R5-4: 電話番号が数字以外を含む場合は 400 系・対象項目提示・非送信。
    - R5-6: 各項目の最大文字数上限超過は 400 系・対象項目提示・非送信。
    - R9-5: GDPR データ最小化。不備入力は Email_Sender へ引き渡さない（非収集）。

ドメイン層での「400 系エラー」の表現（出典: design.md DM2, C3、send_contact.py）:
    ドメインは HTTP ステータスを持たず、検証失敗を `ValidationError(fields)` として
    返す。HTTP 400 系へのマッピングは handler 層の責務（別タスク 2.3）である。
    したがって本テストは「ユースケースが `ValidationError` を返し（=400 系へ
    マッピングされる結果）、不備対象項目を `fields` に示し、Email_Sender へ何も
    引き渡さない」ことをドメイン境界で検証する（出典: design.md C3, DM2）。

テスト方針（出典: design.md「Testing Strategy」、tasks.md 1.5）:
    - PBT ライブラリは Hypothesis（MPL-2.0。ライセンスは requirements-dev.txt に
      明記済み。本タスクでは再追加・再インストールしない）。
    - 単一プロパティを 1 テストで実装し、最小 100 反復（@settings(max_examples=100)）。
    - Django をロードしない（R4-1/R4-2）。ドメイン純粋ロジックのみを対象とする。
    - フォールバック禁止: 生成で不備を握りつぶさず、無効性を構成的に保証し、期待を
      明示アサートする。
    - 共有ハーネス（task 1.4）の `RecordingEmailSender`・`valid_contact_fields` を
      再利用し、有効入力を 1 箇所だけ変異させて「無効入力」を構成する。

実行コマンド（プロジェクトルートから、Django 非ロード）:
    python -m unittest contact_function.tests.test_property_invalid_payload
"""

from __future__ import annotations

import string
import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

from contact_function.domain.send_contact import ValidationError, send_contact
from contact_function.domain.validators import validate_contact_input

# task 1.4 が確立した共有ハーネスを再利用する（再定義しない、DRY・一貫性）。
# RecordingEmailSender: ドメイン抽象 `ports.EmailSender` を実装する記録用ダブル。
# valid_contact_fields: 全 4 項目が検証を通過する入力を生成する合成ストラテジ。
from contact_function.tests.test_property_valid_payload import (
    RecordingEmailSender,
    valid_contact_fields,
)

# 受領対象の 4 項目（出典: validators.py `_ALLOWED_FIELDS`、design.md DM1）。
# 変異対象の選択と余剰フィールド名の除外判定に用いる。
_FIELD_NAMES: tuple[str, ...] = ("full_name", "email", "phone_number", "message")

# 各項目の最大文字数上限（出典: validators.py `_MAX_LENGTHS`、design.md DM1）。
# 上限超過（TOO_LONG）を構成的に発生させるために参照する。
_MAX_LENGTHS: dict[str, int] = {
    "full_name": 100,
    "email": 254,
    "phone_number": 20,
    "message": 5000,
}

# 送信元・宛先(設定値由来の代表値)。Property 2 は「引き渡しが発生しない」ことを
# 対象とするため固定値で足りる（値そのものは検証対象でない）。
_FROM_ADDR = "noreply@example.com"
_TO_ADDR = "owner@example.com"

# strip 後に空となる空白文字集合（半角空白・タブ・改行・全角空白）。
# validators.py は `value.strip() == ""` を MISSING と判定するため、これらのみで
# 構成した値は必ず MISSING（空扱い）となる（出典: validators.py `_validate_field`）。
_WHITESPACE_ALPHABET = " \t\r\n\u3000"


@st.composite
def invalid_contact_fields(draw: st.DrawFn) -> tuple[dict[str, str], frozenset[str]]:
    """1 箇所だけ無効化した問い合わせ入力と、その不備対象項目集合を生成する.

    有効入力（`valid_contact_fields`）を基点に、次のいずれか 1 種類の変異を適用し、
    「無効な Contact_Payload」を構成的に生成する（無効性をフィルタ頼みにせず構成で
    保証する。フォールバック禁止、出典: 第三原則3）。返り値の第 2 要素は、その入力に
    対して検証結果へ現れることを期待する不備対象フィールド名の集合である。

    変異種別（出典: requirements.md 5.1〜5.6、tasks.md 1.5）:
        - missing_empty: 4 項目のいずれかを未送信（キー削除）・空文字・空白のみに
          する（R5-2）。
        - invalid_email: email を電子メール形式に適合しない値にする（R5-3）。
        - non_digit_phone: phone_number に数字以外の文字を含める（R5-4）。
        - over_max_length: 4 項目のいずれかを最大文字数上限超過にする（R5-6）。
        - extra_field: 4 項目以外の余剰フィールドを追加する（R5-1）。

    Args:
        draw: Hypothesis の draw 関数（合成ストラテジ内で値を取得する）。

    Returns:
        tuple[dict[str, str], frozenset[str]]: 無効入力の辞書と、検証結果に現れる
            ことを期待する不備対象フィールド名の集合。
    """
    # 有効な 4 項目を基点として取得する（この時点では全項目が検証を通過する）。
    base = draw(valid_contact_fields())
    # 適用する変異種別を一様に選ぶ（各無効カテゴリを網羅的に生成する）。
    kind = draw(
        st.sampled_from(
            [
                "missing_empty",
                "invalid_email",
                "non_digit_phone",
                "over_max_length",
                "extra_field",
            ]
        )
    )

    if kind == "missing_empty":
        # 必須項目の未送信・空文字・空白のみを構成する（R5-2）。
        target = draw(st.sampled_from(_FIELD_NAMES))
        variant = draw(st.sampled_from(["remove", "empty", "whitespace"]))
        fields = dict(base)
        if variant == "remove":
            # キー自体を削除する（validators は None を MISSING と判定する）。
            del fields[target]
        elif variant == "empty":
            # 空文字（strip 後も空）。
            fields[target] = ""
        else:
            # 空白のみ（strip 後に空となることを空白集合で保証する）。
            fields[target] = draw(
                st.text(alphabet=_WHITESPACE_ALPHABET, min_size=1, max_size=5)
            )
        # 不備対象は変異した当該項目のみ（他 3 項目は有効なまま）。
        return fields, frozenset({target})

    if kind == "invalid_email":
        # email を電子メール形式に適合しない値にする（R5-3）。
        # 英字のみ・非空・上限内の値は '@' を含まないため正規表現に必ず不適合。
        # かつ strip 後非空・上限内のため MISSING/TOO_LONG に先行して INVALID_EMAIL
        # となる（出典: validators.py `_validate_field` の判定順）。
        fields = dict(base)
        fields["email"] = draw(
            st.text(alphabet=string.ascii_letters, min_size=1, max_size=100)
        )
        return fields, frozenset({"email"})

    if kind == "non_digit_phone":
        # phone_number に数字以外の文字を必ず 1 つ以上含める（R5-4）。
        # 前後の数字列の間に英字を 1 文字挿入し、上限 20 以内に切り詰める。英字は
        # 先頭 20 文字以内に必ず残る（prefix は最大 19 文字）ため str.isdigit() は
        # 必ず False となる。strip 後も非空・上限内のため NON_DIGIT に到達する。
        prefix = draw(
            st.text(alphabet=string.digits, max_size=_MAX_LENGTHS["phone_number"] - 1)
        )
        suffix = draw(
            st.text(alphabet=string.digits, max_size=_MAX_LENGTHS["phone_number"] - 1)
        )
        letter = draw(st.sampled_from(string.ascii_letters))
        fields = dict(base)
        fields["phone_number"] = (prefix + letter + suffix)[
            : _MAX_LENGTHS["phone_number"]
        ]
        return fields, frozenset({"phone_number"})

    if kind == "over_max_length":
        # 4 項目のいずれかを最大文字数上限超過にする（R5-6）。
        target = draw(st.sampled_from(_FIELD_NAMES))
        # 上限を 1〜10 文字だけ超過させる。可視文字 'a' で strip 後非空を保証し、
        # 文字数チェック（形式チェックより先）が TOO_LONG を返すことを保証する。
        overflow = draw(st.integers(min_value=1, max_value=10))
        fields = dict(base)
        fields[target] = "a" * (_MAX_LENGTHS[target] + overflow)
        return fields, frozenset({target})

    # kind == "extra_field": 4 項目以外の余剰フィールドを追加する（R5-1）。
    # 4 項目名と衝突しない任意のキー名を生成する（衝突しないことをフィルタで保証）。
    extra_key = draw(
        st.text(alphabet=string.ascii_letters + "_", min_size=1, max_size=15).filter(
            lambda key: key not in _FIELD_NAMES
        )
    )
    fields = dict(base)
    # 値は任意（余剰フィールドは値の内容を問わず不備として扱われる）。
    fields[extra_key] = draw(st.text(max_size=20))
    # 4 項目は有効なままであり、不備対象は追加した余剰フィールドのみ。
    return fields, frozenset({extra_key})


class InvalidPayloadProperty(unittest.TestCase):
    """Property 2 のプロパティテストを保持するテストケース."""

    # 最小 100 反復（出典: tasks.md 1.5「100+ 反復」）。生成データ（上限超過時に
    # 最大 5010 文字の値等）による実行時間のばらつきで per-example の締切超過が
    # 誤検知を招くのを避けるため deadline を無効化する（検証ロジックは決定的で
    # あり、エラーは握りつぶさない）。
    @settings(max_examples=100, deadline=None)
    @given(case=invalid_contact_fields())
    def test_invalid_payload_is_rejected_with_offending_fields_and_not_sent(
        self, case: tuple[dict[str, str], frozenset[str]]
    ) -> None:
        """Feature: cost-performance-optimization, Property 2: 無効な Contact_Payload は必ず 400 系エラーとなり対象項目を示し送信されない

        Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.6, 9.5

        1 箇所を無効化した任意の入力について、(1) 入力検証が失敗し不備対象項目を
        示すこと、(2) ユースケースが 400 系へマッピングされる `ValidationError`
        を返し、その `fields` に不備対象項目を含むこと、(3) Email_Sender へ何も
        引き渡さない（非送信・非収集）こと、を検証する（出典: design.md DM2,
        C3、requirements.md 5.1〜5.6, 9.5）。
        """
        # 生成された無効入力と、期待される不備対象項目集合を取り出す。
        fields, expected_fields = case

        # (1) 検証は必ず失敗し、不備対象項目に期待項目を含むことを確認する。
        validation = validate_contact_input(fields)
        self.assertFalse(
            validation.is_valid,
            msg=f"無効入力が検証を通過してしまった: {fields!r}",
        )
        # 検証結果の不備対象項目に、変異した項目（期待項目）が含まれること（R5-2〜5-6, 5-1）。
        self.assertTrue(
            expected_fields.issubset(set(validation.invalid_fields)),
            msg=(
                f"期待した不備対象項目 {set(expected_fields)!r} が検証結果 "
                f"{set(validation.invalid_fields)!r} に含まれない"
            ),
        )

        # 記録用 Email_Sender を注入してユースケースを実行する（依存性逆転）。
        sender = RecordingEmailSender()
        result = send_contact(
            fields=fields,
            from_addr=_FROM_ADDR,
            to_addr=_TO_ADDR,
            email_sender=sender,
        )

        # (2) 結果は ValidationError（HTTP 400 系へマッピングされる結果、DM2）。
        self.assertIsInstance(
            result,
            ValidationError,
            msg=f"無効入力に対し ValidationError 以外が返った: {result!r}",
        )
        # 型絞り込み後、不備対象項目が示されていること（対象項目提示、R5-2〜5-6, 5-1）。
        assert isinstance(result, ValidationError)  # 型チェッカ向けの明示的絞り込み。
        self.assertTrue(
            result.fields,
            msg="ValidationError が不備対象項目を 1 つも示していない",
        )
        self.assertTrue(
            expected_fields.issubset(set(result.fields)),
            msg=(
                f"期待した不備対象項目 {set(expected_fields)!r} が結果 "
                f"{set(result.fields)!r} に示されていない"
            ),
        )

        # (3) Email_Sender へは一切引き渡されない（非送信・GDPR 非収集、R9-5）。
        self.assertEqual(
            sender.calls,
            [],
            msg="無効入力にもかかわらず Email_Sender へ引き渡しが発生した",
        )


if __name__ == "__main__":
    # 単体実行用エントリ（`python -m unittest` による探索でも実行可能）。
    unittest.main()
