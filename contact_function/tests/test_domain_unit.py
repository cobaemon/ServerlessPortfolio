"""ドメイン層の例示ベース単体テストと認証非依存の静的検査.

本モジュールは tasks.md 1.7 に対応し、ドメイン純粋ロジック
（`validators.validate_contact_input` / `send_contact.send_contact`）の
検証境界・特殊文字・空白・エラー条件を「具体的な例」で決定的に検証する。
プロパティテスト（Hypothesis による網羅検証）は task 1.4〜1.6 の責務であり、
本モジュールは概念の異なる例示ベース（edge/error cases）を担う
（出典: tasks.md 1.7、design.md「Testing Strategy」）。

検証対象要件:
    - R5-2: 必須項目の未送信・空文字・空白のみを不備（MISSING）とする。
    - R5-3: メールアドレスの電子メール形式不正を不備（INVALID_EMAIL）とする。
    - R5-4: 電話番号が数字以外を含む場合を不備（NON_DIGIT）とする
      （既存 ContactForm と整合する `str.isdigit()` 基準、出典: validators.py）。
    - R5-6: 各項目の最大文字数上限超過を不備（TOO_LONG）とする。
    - R13-2: ドメイン公開インターフェースが認証情報を引数に取らない
      （Cognito-ready、認証層は外側で後付け可能。出典: design.md C3, ports.py）。

テスト方針（出典: design.md「Testing Strategy」、requirements.md R4-1/R4-2）:
    - Django をロードしない。ドメイン純粋ロジックのみを対象とする。
    - 標準ライブラリ `unittest` を用いた決定的な例示ケース（非 PBT）。
    - フォールバック禁止: 期待を明示アサートし、問題を握りつぶさない。
    - 送信副作用は task 1.4 で確立した共有ハーネス `RecordingEmailSender`
      （抽象 `ports.EmailSender` 実装）を再利用する（依存性逆転・重複排除）。

実行コマンド（プロジェクトルートから、Django 非ロード）:
    python -m unittest contact_function.tests.test_domain_unit -v
"""

from __future__ import annotations

import inspect
import unittest
from collections.abc import Callable

from contact_function.domain.contact_payload import ContactPayload
from contact_function.domain.ports import ConfigProvider, EmailSender
from contact_function.domain.send_contact import (
    Success,
    ValidationError,
    send_contact,
)
from contact_function.domain.validators import (
    ValidationErrorReason,
    validate_contact_input,
)

# task 1.4 で確立した共有テストハーネスを再利用する（重複排除・単一責務）。
# `RecordingEmailSender` は抽象ポート `ports.EmailSender` を実装する記録用
# テストダブルであり、実送信の副作用を持たない（出典: test_property_valid_payload.py）。
from contact_function.tests.test_property_valid_payload import RecordingEmailSender

# 各項目の最大文字数（出典: validators.py `_MAX_LENGTHS`、design.md DM1）。
# 本モジュールでは境界値の算出根拠を明示するため定数として再掲する。
_MAX_FULL_NAME = 100
_MAX_EMAIL = 254
_MAX_PHONE = 20
_MAX_MESSAGE = 5000

# 送信元・宛先アドレス（設定値由来の代表値）。境界・エラー系の検証では
# 引き渡しの有無・不備対象項目に着目するため固定値を用いる（出典: DM4）。
_FROM_ADDR = "noreply@example.com"
_TO_ADDR = "owner@example.com"


def _base_valid_fields() -> dict[str, str]:
    """全 4 項目が検証を通過する基準入力を返すヘルパー.

    個別テストは本基準辞書の 1 項目のみを差し替えることで、対象項目の不備を
    他項目のノイズなく分離検証する（テストの独立性・可読性向上）。

    Returns:
        dict[str, str]: 検証を通過する 4 項目（full_name, email,
            phone_number, message）の入力辞書。
    """
    # いずれの値も strip 後非空・上限以下・形式適合であり検証を通過する
    # （出典: validators.py 検証規則、R5-2〜R5-4, R5-6）。
    return {
        "full_name": "山田 太郎",
        "email": "taro@example.com",
        "phone_number": "0312345678",
        "message": "お問い合わせ本文です。",
    }


def _reasons_for(
    fields: dict[str, str], field: str
) -> tuple[ValidationErrorReason, ...]:
    """指定フィールドに対して検出された不備理由を出現順で返すヘルパー.

    Args:
        fields: 検証対象の入力辞書。
        field: 不備理由を抽出する対象フィールド名。

    Returns:
        tuple[ValidationErrorReason, ...]: 対象フィールドに紐づく不備理由の列
            （検出が無ければ空タプル）。
    """
    # validate_contact_input の結果から対象フィールドの違反理由のみを抽出する。
    result = validate_contact_input(fields)
    return tuple(v.reason for v in result.violations if v.field == field)


class BoundaryLengthTests(unittest.TestCase):
    """最大文字数境界の例示検証（R5-6）.

    各項目について「上限ちょうど（有効）」と「上限 +1（TOO_LONG）」の 2 点を
    検証する。上限ちょうどが有効であることを確認することで off-by-one を防ぐ。
    """

    def test_full_name_at_max_is_valid(self) -> None:
        """full_name が上限 100 文字ちょうどのとき検証を通過する（R5-6 境界）."""
        # 上限ちょうど（100 文字）は超過ではないため不備が生じない。
        fields = _base_valid_fields()
        fields["full_name"] = "a" * _MAX_FULL_NAME
        self.assertTrue(validate_contact_input(fields).is_valid)

    def test_full_name_over_max_is_too_long(self) -> None:
        """full_name が上限 +1（101 文字）のとき TOO_LONG となる（R5-6）."""
        # 上限を 1 文字超過した場合に TOO_LONG が報告される。
        fields = _base_valid_fields()
        fields["full_name"] = "a" * (_MAX_FULL_NAME + 1)
        self.assertEqual(
            _reasons_for(fields, "full_name"), (ValidationErrorReason.TOO_LONG,)
        )

    def test_email_at_max_is_valid(self) -> None:
        """email が上限 254 文字ちょうどかつ形式適合のとき検証を通過する（R5-6 境界）."""
        # 固定サフィックス "@example.com"（12 文字）を除いた長さでローカル部を構成し、
        # 合計をちょうど 254 文字にする（形式は正規表現に適合）。
        suffix = "@example.com"
        local = "a" * (_MAX_EMAIL - len(suffix))
        email = local + suffix
        # 構築値が上限ちょうどであることを前提として明示する（テストの自己検証）。
        self.assertEqual(len(email), _MAX_EMAIL)
        fields = _base_valid_fields()
        fields["email"] = email
        self.assertTrue(validate_contact_input(fields).is_valid)

    def test_email_over_max_is_too_long(self) -> None:
        """email が上限 +1（255 文字）のとき TOO_LONG となる（R5-6）.

        形式は適合させ、長さ超過のみを不備要因とする。検証順序は
        「MISSING → TOO_LONG → 形式」であり長さ超過が先に評価される
        （出典: validators.py `_validate_field`）。
        """
        suffix = "@example.com"
        local = "a" * (_MAX_EMAIL + 1 - len(suffix))
        email = local + suffix
        self.assertEqual(len(email), _MAX_EMAIL + 1)
        fields = _base_valid_fields()
        fields["email"] = email
        self.assertEqual(
            _reasons_for(fields, "email"), (ValidationErrorReason.TOO_LONG,)
        )

    def test_phone_number_at_max_is_valid(self) -> None:
        """phone_number が上限 20 桁ちょうど（数字のみ）のとき検証を通過する（R5-6 境界）."""
        fields = _base_valid_fields()
        fields["phone_number"] = "1" * _MAX_PHONE
        self.assertTrue(validate_contact_input(fields).is_valid)

    def test_phone_number_over_max_is_too_long(self) -> None:
        """phone_number が上限 +1（21 桁）のとき TOO_LONG となる（R5-6）."""
        fields = _base_valid_fields()
        fields["phone_number"] = "1" * (_MAX_PHONE + 1)
        self.assertEqual(
            _reasons_for(fields, "phone_number"), (ValidationErrorReason.TOO_LONG,)
        )

    def test_message_at_max_is_valid(self) -> None:
        """message が上限 5000 文字ちょうどのとき検証を通過する（R5-6 境界）."""
        fields = _base_valid_fields()
        fields["message"] = "m" * _MAX_MESSAGE
        self.assertTrue(validate_contact_input(fields).is_valid)

    def test_message_over_max_is_too_long(self) -> None:
        """message が上限 +1（5001 文字）のとき TOO_LONG となる（R5-6）."""
        fields = _base_valid_fields()
        fields["message"] = "m" * (_MAX_MESSAGE + 1)
        self.assertEqual(
            _reasons_for(fields, "message"), (ValidationErrorReason.TOO_LONG,)
        )


class MissingRequiredFieldTests(unittest.TestCase):
    """必須項目の未送信・空文字・空白のみの例示検証（R5-2）.

    validators.py は `value is None or value.strip() == ""` を MISSING とみなす
    （出典: `_validate_field`）。空白のみ入力も空として扱う挙動を検証する。
    """

    def test_empty_string_is_missing_for_each_field(self) -> None:
        """各必須項目が空文字のとき MISSING となる（R5-2）."""
        # 4 項目それぞれを空文字に差し替え、対象項目に MISSING が出ることを確認する。
        for field in ("full_name", "email", "phone_number", "message"):
            with self.subTest(field=field):
                fields = _base_valid_fields()
                fields[field] = ""
                self.assertEqual(
                    _reasons_for(fields, field), (ValidationErrorReason.MISSING,)
                )

    def test_whitespace_only_is_missing_for_each_field(self) -> None:
        """各必須項目が空白のみ（半角/全角/タブ/改行）のとき MISSING となる（R5-2）."""
        # strip 後に空となる代表的な空白文字列。全角スペースも strip 対象。
        whitespace_values = (" ", "\t", "\n", "   \t\n ", "\u3000")
        for field in ("full_name", "email", "phone_number", "message"):
            for value in whitespace_values:
                with self.subTest(field=field, value=repr(value)):
                    fields = _base_valid_fields()
                    fields[field] = value
                    self.assertEqual(
                        _reasons_for(fields, field),
                        (ValidationErrorReason.MISSING,),
                    )

    def test_missing_key_is_missing(self) -> None:
        """必須キー自体が欠落（None 相当）のとき MISSING となる（R5-2）."""
        # キーを削除して未送信を再現する（fields.get(field) が None を返す）。
        fields = _base_valid_fields()
        del fields["message"]
        self.assertEqual(
            _reasons_for(fields, "message"), (ValidationErrorReason.MISSING,)
        )


class EmailFormatTests(unittest.TestCase):
    """メールアドレス形式の例示検証（R5-3）.

    検証パターンは `^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$`（出典: validators.py
    `_EMAIL_PATTERN`）。'@' の欠落・ドメインのドット欠落・空白混入・
    ローカル部/ドメイン部の欠落を不正例として検証する。
    """

    def test_valid_email_passes(self) -> None:
        """代表的な有効メールアドレスが検証を通過する（R5-3）."""
        fields = _base_valid_fields()
        fields["email"] = "foo.bar@example.co.jp"
        self.assertTrue(validate_contact_input(fields).is_valid)

    def test_invalid_email_formats_are_rejected(self) -> None:
        """形式不正なメールアドレスが INVALID_EMAIL となる（R5-3）."""
        # いずれも正規表現に適合しない代表的な不正形式（長さは上限以内）。
        invalid_emails = (
            "no-at-sign",           # '@' が無い
            "foo@bar",              # ドメインにドットが無い
            "@example.com",         # ローカル部が空
            "foo@.com",             # ドメイン部（ドット前）が空
            "foo@example.",         # TLD（ドット後）が空
            "foo bar@example.com",  # ローカル部に空白混入
            "foo@ex ample.com",     # ドメインに空白混入
            "foo@@example.com",     # '@' が複数
        )
        for email in invalid_emails:
            with self.subTest(email=email):
                fields = _base_valid_fields()
                fields["email"] = email
                self.assertEqual(
                    _reasons_for(fields, "email"),
                    (ValidationErrorReason.INVALID_EMAIL,),
                )


class PhoneNumberDigitTests(unittest.TestCase):
    """電話番号の数字のみ検証の例示（R5-4）.

    validators.py は `value.isdigit()` を基準とする（既存
    ContactForm.clean_phone_number と整合、出典: validators.py コメント）。
    本テストは `str.isdigit()` の実挙動（事実）に基づいて期待値を定める。
    """

    def test_ascii_digits_pass(self) -> None:
        """ASCII 数字のみの電話番号が検証を通過する（R5-4）."""
        fields = _base_valid_fields()
        fields["phone_number"] = "0123456789"
        self.assertTrue(validate_contact_input(fields).is_valid)

    def test_non_digit_characters_are_rejected(self) -> None:
        """数字以外を含む電話番号が NON_DIGIT となる（R5-4）.

        '+'・ハイフン・空白・英字・全角スペースなど `str.isdigit()` が False を
        返す文字を含む場合を検証する（事実確認済み: いずれも isdigit()==False）。
        """
        # str.isdigit() が False となる代表的な文字を含む電話番号。
        invalid_phones = (
            "+81312345678",      # 国際プレフィックス '+'
            "03-1234-5678",      # ハイフン区切り
            "03 1234 5678",      # 空白区切り
            "03(1234)5678",      # 括弧
            "TEL12345678",       # 英字混入
            "0312345678\u3000",  # 全角スペース混入
        )
        for phone in invalid_phones:
            with self.subTest(phone=phone):
                fields = _base_valid_fields()
                fields["phone_number"] = phone
                self.assertEqual(
                    _reasons_for(fields, "phone_number"),
                    (ValidationErrorReason.NON_DIGIT,),
                )

    def test_numeric_but_non_digit_unicode_is_rejected(self) -> None:
        """`isnumeric()` が True でも `isdigit()` が False の Unicode 文字は NON_DIGIT（R5-4）.

        事実: '½'（VULGAR FRACTION ONE HALF）は isnumeric()==True かつ
        isdigit()==False（実行確認済み）。validators.py は isdigit() 基準のため
        当該文字を含む電話番号は不備となる。isdigit 基準であることを明示検証する。
        """
        # isnumeric True / isdigit False の文字を含むため NON_DIGIT となる。
        fields = _base_valid_fields()
        fields["phone_number"] = "03\u00bd12345678"
        self.assertEqual(
            _reasons_for(fields, "phone_number"),
            (ValidationErrorReason.NON_DIGIT,),
        )

    def test_isdigit_true_unicode_digits_are_accepted(self) -> None:
        """`str.isdigit()` が True の Unicode 数字は検証を通過する（R5-4 実挙動の明示）.

        事実: Arabic-Indic 数字 '٠'、上付き数字 '²'、全角数字 '３' はいずれも
        isdigit()==True（実行確認済み）。validators.py は isdigit() 基準のため、
        これらのみで構成される電話番号は不備とならない。仕様（isdigit 基準）の
        帰結を事実として明示する（誤検知防止・回帰検知のためのドキュメント的検証）。
        """
        # isdigit()==True の Unicode 数字のみで構成した電話番号は検証を通過する。
        for phone in ("\u0660\u0661\u0662", "\u00b2\u00b2", "\uff13\uff14\uff15"):
            with self.subTest(phone=phone):
                fields = _base_valid_fields()
                fields["phone_number"] = phone
                self.assertTrue(validate_contact_input(fields).is_valid)


class SpecialCharacterTests(unittest.TestCase):
    """氏名・メッセージにおける特殊文字許容の例示（R5-2 の帰結）.

    validators.py は full_name / message に対し MISSING と TOO_LONG のみを
    検査し、文字種の制約を課さない（出典: `_validate_field`）。したがって
    記号・多言語・絵文字・改行等の特殊文字は上限以内かつ非空であれば有効。
    """

    def test_special_characters_in_full_name_are_valid(self) -> None:
        """氏名に記号・多言語文字を含んでも上限以内・非空なら有効（R5-2 帰結）."""
        # アポストロフィ・ハイフン・ダイアクリティカル・多言語・記号を含む氏名。
        fields = _base_valid_fields()
        fields["full_name"] = "O'Brien-Łukasz 山田＜太郎＞ & Co."
        self.assertTrue(validate_contact_input(fields).is_valid)

    def test_special_characters_in_message_are_valid(self) -> None:
        """メッセージに改行・絵文字・記号を含んでも上限以内・非空なら有効（R5-2 帰結）."""
        # 改行・タブ・絵文字・各種記号を含む本文（先頭は可視文字で strip 後非空）。
        fields = _base_valid_fields()
        fields["message"] = "件名: テスト\n本文に <tag> & \"引用\" \U0001F600 を含む。\t終わり"
        self.assertTrue(validate_contact_input(fields).is_valid)


class SendContactErrorConditionTests(unittest.TestCase):
    """send_contact ユースケースのエラー条件の例示検証（R5-2〜R5-6）.

    検証失敗時は送信せず `ValidationError`（不備対象項目付）を返し、
    Email_Sender を呼び出さないことを確認する（フォールバック禁止、
    出典: send_contact.py、R4-4）。成功系も 1 件確認し対比する。
    """

    def test_validation_failure_returns_error_and_does_not_send(self) -> None:
        """不備入力では ValidationError を返し送信しない（R5-2 系）."""
        # email を空文字にして検証失敗を発生させる。
        fields = _base_valid_fields()
        fields["email"] = ""
        sender = RecordingEmailSender()
        result = send_contact(
            fields=fields,
            from_addr=_FROM_ADDR,
            to_addr=_TO_ADDR,
            email_sender=sender,
        )
        # 結果は ValidationError であり、不備対象に email を含む。
        self.assertIsInstance(result, ValidationError)
        assert isinstance(result, ValidationError)  # 型絞り込み（fields 参照のため）
        self.assertIn("email", result.fields)
        # 検証失敗時は Email_Sender が一切呼ばれない（送信抑止、R4-4）。
        self.assertEqual(len(sender.calls), 0)

    def test_valid_input_returns_success_and_sends_once(self) -> None:
        """有効入力では Success を返し送信をちょうど 1 回行う（R6-6 対比）."""
        fields = _base_valid_fields()
        sender = RecordingEmailSender()
        result = send_contact(
            fields=fields,
            from_addr=_FROM_ADDR,
            to_addr=_TO_ADDR,
            email_sender=sender,
        )
        self.assertIsInstance(result, Success)
        self.assertEqual(len(sender.calls), 1)


class AuthIndependenceTests(unittest.TestCase):
    """ドメイン公開インターフェースが認証情報を引数に取らない静的検査（R13-2）.

    Cognito-ready（認証層は外側で後付け可能）を担保するため、ドメイン層の
    公開呼び出し可能物のパラメータ名に認証情報を示す語が含まれないことを
    `inspect.signature` で静的に検査する（出典: design.md C3「Cognito-ready」、
    ports.py、requirements.md R13-2）。

    検査対象の認証情報関連語（部分一致・大小無視）:
        token / jwt / cognito / auth / credential / credentials / user_id /
        userid / principal / session / secret / password / apikey / api_key /
        bearer / oauth / claim / identity
    上記集合はゼロトラストの観点で「認証・認可・セッションに関わる引数」を
    列挙したものであり、いずれか 1 語でも含まれれば違反とみなす。
    """

    # 認証情報を示すと判断する語の集合（小文字・部分一致で照合する）。
    # ゼロトラストの観点から認証・認可・資格情報・セッションを広く捕捉する。
    _AUTH_TERMS: tuple[str, ...] = (
        "token",
        "jwt",
        "cognito",
        "auth",
        "credential",
        "credentials",
        "user_id",
        "userid",
        "principal",
        "session",
        "secret",
        "password",
        "apikey",
        "api_key",
        "bearer",
        "oauth",
        "claim",
        "identity",
    )

    def _assert_no_auth_params(self, callable_obj: Callable[..., object]) -> None:
        """呼び出し可能物のパラメータ名に認証情報語が含まれないことを表明する.

        Args:
            callable_obj: 検査対象の関数・メソッド・クラス（`__init__` を検査）。
        """
        # inspect.signature はクラスに対して __init__ のシグネチャを返すため、
        # 関数・メソッド・dataclass のいずれも同一の方法で検査できる。
        signature = inspect.signature(callable_obj)
        for name in signature.parameters:
            # self は検査対象外（メソッドの受け手であり引数ではない）。
            if name == "self":
                continue
            lowered = name.lower()
            for term in self._AUTH_TERMS:
                # 部分一致で認証情報語を含む場合は R13-2 違反として失敗させる。
                self.assertNotIn(
                    term,
                    lowered,
                    msg=(
                        f"{callable_obj!r} のパラメータ '{name}' が認証情報語 "
                        f"'{term}' を含む（R13-2 違反）。"
                    ),
                )

    def test_validate_contact_input_takes_no_auth_params(self) -> None:
        """validate_contact_input が認証情報を引数に取らない（R13-2）."""
        self._assert_no_auth_params(validate_contact_input)

    def test_send_contact_takes_no_auth_params(self) -> None:
        """send_contact が認証情報を引数に取らない（R13-2）.

        期待される引数は fields / from_addr / to_addr / email_sender のみで
        あり、認証情報を含まない（出典: send_contact.py シグネチャ）。
        """
        self._assert_no_auth_params(send_contact)
        # 期待パラメータ集合を明示し、想定外引数の混入も検知する（回帰防止）。
        params = tuple(inspect.signature(send_contact).parameters)
        self.assertEqual(
            params, ("fields", "from_addr", "to_addr", "email_sender")
        )

    def test_email_sender_send_takes_no_auth_params(self) -> None:
        """EmailSender.send が認証情報を引数に取らない（R13-2、ports.py 明記）."""
        self._assert_no_auth_params(EmailSender.send)

    def test_config_provider_methods_take_no_auth_params(self) -> None:
        """ConfigProvider の全公開メソッドが認証情報を引数に取らない（R13-2）."""
        for method in (
            ConfigProvider.get_from_address,
            ConfigProvider.get_to_address,
            ConfigProvider.get_allowed_origins,
        ):
            with self.subTest(method=method.__name__):
                self._assert_no_auth_params(method)

    def test_contact_payload_fields_have_no_auth_params(self) -> None:
        """ContactPayload が保持する項目に認証情報が含まれない（R13-2, GDPR）.

        dataclass の __init__ シグネチャ（= 保持項目）を検査し、4 項目
        （full_name, email, phone_number, message）のみで認証情報を含まない
        ことを確認する（出典: contact_payload.py、DM1）。
        """
        self._assert_no_auth_params(ContactPayload)
        # 保持項目がデータ最小化された 4 項目のみであることを明示する。
        params = tuple(inspect.signature(ContactPayload).parameters)
        self.assertEqual(
            params, ("full_name", "email", "phone_number", "message")
        )


if __name__ == "__main__":
    # 単体実行用エントリ（`python -m unittest` による探索でも実行可能）。
    unittest.main()
