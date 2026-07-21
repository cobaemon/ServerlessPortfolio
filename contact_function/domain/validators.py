"""Contact_Payload 入力検証を担う純粋関数モジュール.

問い合わせ入力（氏名・メールアドレス・電話番号・メッセージの 4 項目）に対する
検証規則を、副作用を持たない純粋関数として提供する（出典: design.md
「Data Models > DM1 検証規則」、requirements.md R5-1〜R5-4, R5-6）。

本モジュールはドメイン最内層に属し、Django・adapters 層・handler 層・I/O・
認証情報のいずれにも依存しない（出典: design.md C3、requirements.md R4-6,
R13-2）。純粋関数であることにより、後続タスクのプロパティテスト（design.md
「Correctness Properties > Property 2」）で入力バリエーションを網羅検証できる。

検証結果は不備の対象項目とその理由を保持する構造化オブジェクト
（`ValidationResult`）として返す。HTTP ステータスへのマッピングは行わない
（それは handler 層の責務。出典: design.md C3, DM2）。想定内の検証不備に対して
例外は送出せず結果として返す（フォールバック禁止・エラー握りつぶし禁止、
出典: 第三原則3、requirements.md R6-4, R12-5）。
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

# 受領対象の 4 項目（これ以外は送信内容として処理しない、出典: R5-1, DM1）。
# タプルで定義し、検証順序を固定して結果を決定的にする。
_ALLOWED_FIELDS: tuple[str, ...] = ("full_name", "email", "phone_number", "message")

# 各項目の最大文字数上限（出典: design.md DM1「最大文字数（design 確定）」）。
# full_name / phone_number は既存 ContactForm の max_length を踏襲し、
# email=254（RFC 5321 実務上限）と message=5000 は DM1 で明文化した上限値。
_MAX_LENGTHS: Mapping[str, int] = {
    "full_name": 100,
    "email": 254,
    "phone_number": 20,
    "message": 5000,
}

# 電子メール形式の検証パターン（外部依存を持たない純粋な正規表現）。
# ローカル部・ドメイン部に空白と '@' を含まず、ドメインに少なくとも 1 つの
# ドット（TLD 区切り）を要求する実務的な形式検証（出典: R5-3）。
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ValidationErrorReason(Enum):
    """検証不備の理由を表す列挙型.

    HTTP ステータスへ変換せず、不備の種別のみを機械可読な値として表現する
    （HTTP マッピングは handler 層の責務、出典: design.md C3, DM2）。
    """

    # 必須項目が未送信または空文字である（出典: requirements.md R5-2）。
    MISSING = "missing"
    # 項目が最大文字数上限を超過している（出典: requirements.md R5-6）。
    TOO_LONG = "too_long"
    # メールアドレスが電子メール形式として不正である（出典: requirements.md R5-3）。
    INVALID_EMAIL = "invalid_email"
    # 電話番号が数字以外の文字を含む（出典: requirements.md R5-4）。
    NON_DIGIT = "non_digit"
    # 4 項目以外の余剰フィールドが含まれる（出典: requirements.md R5-1）。
    UNEXPECTED_FIELD = "unexpected_field"


@dataclass(frozen=True, slots=True)
class FieldViolation:
    """単一の検証不備を表す不変オブジェクト.

    Attributes:
        field: 不備の対象となったフィールド名。
        reason: 不備の理由（`ValidationErrorReason`）。
    """

    # 不備の対象フィールド名（4 項目のいずれか、または余剰フィールド名）。
    field: str
    # 不備の理由。
    reason: ValidationErrorReason


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """入力検証の結果を表す不変オブジェクト.

    検出したすべての不備を `violations` に保持する。不備が無い場合は空であり、
    `is_valid` が True を返す。HTTP マッピングは行わない（出典: design.md C3）。

    Attributes:
        violations: 検出した不備の不変な列（不備が無い場合は空タプル）。
    """

    # 検出した不備の一覧（順序は固定・決定的）。
    violations: tuple[FieldViolation, ...]

    @property
    def is_valid(self) -> bool:
        """検証が成功したか（不備が 1 件も無いか）を返す.

        Returns:
            bool: 不備が存在しない場合 True、存在する場合 False。
        """
        # 不備が 1 件も無い場合のみ有効とみなす。
        return not self.violations

    @property
    def invalid_fields(self) -> tuple[str, ...]:
        """不備の対象フィールド名を重複なく出現順で返す.

        後続のユースケース（design.md DM2 `ValidationError(fields)`）へ
        不備対象項目を引き渡すための補助アクセサ（出典: R5-2〜R5-6, R5-1）。

        Returns:
            tuple[str, ...]: 不備対象フィールド名の重複を除いた列。
        """
        # 出現順を維持しつつ重複を排除する。
        seen: list[str] = []
        for violation in self.violations:
            if violation.field not in seen:
                seen.append(violation.field)
        return tuple(seen)


def _validate_field(field: str, value: str | None) -> FieldViolation | None:
    """単一の必須項目を検証し、不備があれば `FieldViolation` を返す純粋関数.

    検証順序は「未送信/空文字 → 最大文字数超過 → 項目固有の形式」で固定し、
    結果を決定的にする。構造的上限（文字数）を形式チェックより先に評価する。

    Args:
        field: 対象フィールド名（`_ALLOWED_FIELDS` のいずれか）。
        value: 対象フィールドの値。キーが存在しない場合は None。

    Returns:
        FieldViolation | None: 不備があれば理由を含む `FieldViolation`、
            不備が無ければ None。
    """
    # 未送信（キー無し=None）または空文字（前後空白を除去した結果が空）を
    # 「不備」とみなす。空白のみの入力を空として扱うのは既存 Django CharField の
    # strip 既定挙動およびゼロトラスト検証と整合させるため（出典: R5-2、
    # 第二原則2、第三原則1）。
    if value is None or value.strip() == "":
        return FieldViolation(field, ValidationErrorReason.MISSING)

    # 最大文字数上限の超過チェック（出典: R5-6, DM1）。
    if len(value) > _MAX_LENGTHS[field]:
        return FieldViolation(field, ValidationErrorReason.TOO_LONG)

    # メールアドレスの電子メール形式チェック（出典: R5-3）。
    if field == "email" and _EMAIL_PATTERN.match(value) is None:
        return FieldViolation(field, ValidationErrorReason.INVALID_EMAIL)

    # 電話番号の数字のみチェック。既存 ContactForm.clean_phone_number の
    # `isdigit()` に整合させる（出典: R5-4、portfolio/forms.py、第三原則1）。
    if field == "phone_number" and not value.isdigit():
        return FieldViolation(field, ValidationErrorReason.NON_DIGIT)

    # 不備なし。
    return None


def validate_contact_input(fields: Mapping[str, str]) -> ValidationResult:
    """問い合わせ入力（4 項目）を検証し構造化した結果を返す純粋関数.

    検証規則（出典: design.md DM1、requirements.md R5-1〜R5-4, R5-6）:
        - 4 項目以外の余剰フィールドは送信内容として処理せず不備として報告する
          （R5-1）。
        - 各必須項目の未送信/空文字を不備とする（R5-2）。
        - メールアドレスの電子メール形式不正を不備とする（R5-3）。
        - 電話番号が数字以外を含む場合を不備とする（R5-4）。
        - 各項目の最大文字数上限超過を不備とする（R5-6）。

    本関数は副作用を持たず、HTTP マッピングを行わない（handler 層の責務、
    出典: design.md C3）。想定内の不備に対して例外を送出せず結果として返す
    （フォールバック禁止、出典: 第三原則3、R6-4, R12-5）。

    ハニーポットの隠しフィールドは本関数の入力に含めない（handler 層で除去・
    判定する。出典: design.md C7, DM1）。したがって 4 項目以外のキーはすべて
    余剰フィールドとして扱う。

    Args:
        fields: 問い合わせ入力のフィールド名から値へのマッピング。
            handler 層がリクエストから変換し、ハニーポット等の非内容フィールドを
            除去した上で渡す（出典: design.md C3, C7）。

    Returns:
        ValidationResult: 検出した不備の一覧を保持する結果。不備が無ければ
            `is_valid` が True を返す。
    """
    violations: list[FieldViolation] = []

    # 4 項目以外の余剰フィールドを検出する（送信内容として処理しない、R5-1）。
    for key in fields:
        if key not in _ALLOWED_FIELDS:
            violations.append(
                FieldViolation(key, ValidationErrorReason.UNEXPECTED_FIELD)
            )

    # 4 項目を固定順で検証し、不備があれば収集する（決定的な結果順序）。
    for field in _ALLOWED_FIELDS:
        violation = _validate_field(field, fields.get(field))
        if violation is not None:
            violations.append(violation)

    return ValidationResult(violations=tuple(violations))
