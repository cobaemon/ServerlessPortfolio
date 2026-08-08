"""旧資産除去（legacy-asset-cleanup）判定層の Inventory_Validator.

目的:
    Legacy_Asset_Inventory（正本: `docs/legacy-asset-inventory.json`）の構造的
    不変条件のみを検証し、確認結果による扱いの確定更新を提供する。判定に用いる
    のは引数として渡された値だけであり、ファイル I/O・`subprocess`・Django・
    boto3 を一切用いない（出典:
    `.kiro/specs/legacy-asset-cleanup/design.md` C2「Inventory_Validator」、
    同「Architecture > 依存方向」、同 tasks.md 1.2）。

出典:
    - `.kiro/specs/legacy-asset-cleanup/design.md` C2（関数シグネチャと検証内容）、
      同 DM2（必須キー表: 由来 E-3 / E-4 / E-5 / E-6 / E-7 / E-8 / E-9 および
      本設計の新規検出）、同 Property 1 / Property 2 / Property 11。
    - `.kiro/specs/legacy-asset-cleanup/requirements.md` Requirement 1 基準
      1〜8、Requirement 5 基準 8、Requirement 7 基準 11、Requirement 9 基準
      1〜3。
    - `scripts/cleanup/models.py`（DM1〜DM6 の不変値型。本モジュールは型と定数を
      再定義せず再利用する）。

設計上の制約（出典: `.kiro/steering/principles.md` 第二原則5、第三原則3）:
    - 検証は違反文字列のタプルを返す形とし、空タプルを「適合」とする。違反文字列
      には対象キーと条項識別子（例 `R1-1`）を含め、どの基準に対する違反かを出典
      可能な形で残す。
    - フォールバックを実装しない。不正入力を黙って正規化せず、未確定状態に既定値
      を与えない。`apply_confirmation` は確定できない入力に対して `ValueError` を
      送出する。
    - 本モジュールは構造検証と確定更新のみを担う（単一責務）。除去計画は
      `removal_plan.py`、非退行判定は `removal_verification.py`、完了判定は
      `completion.py` が担う（出典: design.md C3〜C5）。

本モジュールが検証しない事項（design.md C2「検証内容」に列挙がないため、判定を
追加せず設計の範囲に留める）:
    - `Inventory.revision` の形式および非空性。
    - `PreservedAssetItem` の出典 3 要素の非空性（`disposition` の固定のみ検証する）。
    - `UndeterminedNote.reason` / `pending_check` の非空性。
    - 行番号が実ファイルの実体と一致するか（R1-5。ファイル I/O を伴うため
      design.md C13 の `--verify-lines` が担う）。
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import replace

from .models import Confirmation, Inventory, LegacyAssetItem, PreservedAssetItem

# ---------------------------------------------------------------------------
# 排他値の定義（R1-2、R1-3）
# ---------------------------------------------------------------------------

# R1-2 は各項目を系統 A / B / D のいずれか 1 つに分類することを求める（出典:
# requirements.md Requirement 1 基準 2）。系統 C は `PreservedAssetItem` として
# 別集合に保持するため本集合に含めない（出典: design.md DM1 の注記）。
VALID_STREAMS: frozenset[str] = frozenset({"A", "B", "D"})

# R1-3 の扱い 3 値（出典: requirements.md Requirement 1 基準 3）。
DISPOSITION_REMOVAL_TARGET = "除去対象"
DISPOSITION_PRESERVED = "保全対象"
DISPOSITION_UNDETERMINED = "undetermined"

VALID_DISPOSITIONS: frozenset[str] = frozenset({
    DISPOSITION_REMOVAL_TARGET,
    DISPOSITION_PRESERVED,
    DISPOSITION_UNDETERMINED,
})

# R5-8 は確定時の更新先を「保全対象」または「除去対象」に限定する（出典:
# requirements.md Requirement 5 基準 8）。`undetermined` は確定先ではない。
CONFIRMABLE_DISPOSITIONS: frozenset[str] = frozenset({
    DISPOSITION_REMOVAL_TARGET,
    DISPOSITION_PRESERVED,
})

# ---------------------------------------------------------------------------
# 必須キー集合（出典: design.md DM2「必須キー集合」表）
# ---------------------------------------------------------------------------

# 由来 E-3（Django on Lambda 残骸）。`Inventory.items` に含むことを要求する（R1-4）。
REQUIRED_ITEM_KEYS_E3: frozenset[str] = frozenset({
    "asgi_lambda",
    "aws_sam_build_toml",
    "gitignore_aws_sam",
    "dep_mangum",
})

# 由来 E-4（SMTP 経路）。`Inventory.items` に含むことを要求する（R1-4）。
REQUIRED_ITEM_KEYS_E4: frozenset[str] = frozenset({
    "prod_smtp_required",
    "prod_smtp_comment",
    "dev_smtp_block",
    "forms_smtp_log",
    "forms_send_email_fallback",
    "buildspec_smtp_export",
    "buildspec_smtp_comment",
    "docs_configuration_smtp",
    "docs_staging_policy_smtp",
    "test_regression_smtp_env",
    "aws_smtp_parameters",
    "aws_smtp_secret_keys",
})

# 由来 E-5（系統 C の保全対象）。`Inventory.preserved` に含み、かつ扱いを
# 「保全対象」に固定することを要求する（R1-8）。
REQUIRED_PRESERVED_KEYS_E5: frozenset[str] = frozenset({
    "views_top",
    "views_contact",
    "urls_portfolio",
    "contactform_fields",
    "templates_base",
    "templates_index",
})

# 由来 E-6（無効化済み認証のデッドコードと未使用 import）。`Inventory.items` に
# 含むことを要求する（R1-4）。
REQUIRED_ITEM_KEYS_E6: frozenset[str] = frozenset({
    "base_unused_imports",
    "base_installed_apps_comments",
    "base_middleware_comments",
    "base_templates_comment",
    "base_auth_comment_block",
    "urls_comments",
    "template_account_modal",
})

# 由来 E-7（判定対象の dependency 12 件）。`Inventory.items` に含むことを要求する
# （R1-4、R7-11）。`dep_mangum` は E-3 とも重複して列挙されるが、これは集合として
# の包含要求であり、Inventory 内でのキー重複（別途検証）とは別事項である。
REQUIRED_ITEM_KEYS_E7: frozenset[str] = frozenset({
    "dep_awsgi",
    "dep_django_allauth",
    "dep_django_otp",
    "dep_gunicorn",
    "dep_httptools",
    "dep_mangum",
    "dep_psycopg2_binary",
    "dep_pyjwt",
    "dep_qrcode",
    "dep_uvloop",
    "dep_websockets",
    "dep_werkzeug",
})

# 由来 E-8。`Inventory.items` に含み、かつ扱いを `undetermined` に固定することを
# 要求する（R1-7）。
REQUIRED_ITEM_KEYS_E8: frozenset[str] = frozenset({
    "prod_oauth_required",
    "steering_inconsistency",
    "base_debug_print",
})

# 由来 E-9 のうち requirements.md Requirement 9 基準 1 に対応するキー。
# `Inventory.undetermined_notes` に含むことを要求する。
REQUIRED_NOTE_KEYS_E9_CRITERION_1: frozenset[str] = frozenset({
    "outputs_apiurl_external_users",
    "sam_build_toml_dependency",
    "prerender_minimal_set",
    "aws_smtp_key_existence",
    "transitive_dependency_need",
})

# 由来 E-9 のうち requirements.md Requirement 9 基準 2 に対応するキー
# （`samconfig.toml:9` の `AllowedOrigin` / `AllowedHosts`）。
REQUIRED_NOTE_KEYS_E9_CRITERION_2: frozenset[str] = frozenset({
    "samconfig_allowed_origin",
    "samconfig_allowed_hosts",
})

REQUIRED_NOTE_KEYS_E9: frozenset[str] = (
    REQUIRED_NOTE_KEYS_E9_CRITERION_1 | REQUIRED_NOTE_KEYS_E9_CRITERION_2
)

# 本設計（design.md）作成時に新たに検出した項目。既存受入基準に対応する条項が
# ないため、条項識別子は DM2 の表に基づく `DM2-新規検出` を用いる（出典:
# design.md DM2 表の「本設計の新規検出」行、`.kiro/steering/principles.md`
# 第一原則1-3）。
REQUIRED_ITEM_KEYS_NEW_DETECTION: frozenset[str] = frozenset({
    "base_contrib_sites",
    "template_two_factor_url",
    "docs_deployment_time_record",
    "prod_email_backend_policy",
})

# `Inventory.items` に対する必須キー集合と、欠落時に報告する条項識別子の対応。
# 条項識別子は design.md DM2 表の「要件」列に一致させる。
_REQUIRED_ITEM_KEY_SETS: tuple[tuple[str, frozenset[str]], ...] = (
    ("R1-4", REQUIRED_ITEM_KEYS_E3),
    ("R1-4", REQUIRED_ITEM_KEYS_E4),
    ("R1-4", REQUIRED_ITEM_KEYS_E6),
    ("R1-4,R7-11", REQUIRED_ITEM_KEYS_E7),
    ("R1-7", REQUIRED_ITEM_KEYS_E8),
    ("DM2-新規検出", REQUIRED_ITEM_KEYS_NEW_DETECTION),
)

# `Inventory.undetermined_notes` に対する必須キー集合と条項識別子の対応。
_REQUIRED_NOTE_KEY_SETS: tuple[tuple[str, frozenset[str]], ...] = (
    ("R9-1", REQUIRED_NOTE_KEYS_E9_CRITERION_1),
    ("R9-2", REQUIRED_NOTE_KEYS_E9_CRITERION_2),
)


def _is_blank(value: str) -> bool:
    """文字列が空または空白のみかを判定する（内部関数）.

    引数:
        value: 判定対象の文字列。

    戻り値:
        空文字列または空白文字のみの場合 True。

    例外:
        送出しない。

    空白のみの値を非空として通すと出典として機能しないため、空白のみも欠落として
    扱う。判定のみを行い値の書き換えは行わない（第三原則3 フォールバック禁止）。
    """
    return not value.strip()


def _duplicated_keys(keys: Iterable[str]) -> tuple[str, ...]:
    """重複して出現するキーを昇順で返す（内部関数）.

    引数:
        keys: 検査対象のキー列。

    戻り値:
        2 回以上出現したキーの昇順タプル。重複がなければ空タプル。

    例外:
        送出しない。
    """
    counts = Counter(keys)
    return tuple(sorted(key for key, count in counts.items() if count > 1))


def validate_item(item: LegacyAssetItem) -> tuple[str, ...]:
    """1 項目の不変条件違反を列挙する（空タプル＝適合）.

    検証内容（出典: design.md C2「検証内容」、同 Property 1）:
        - R1-1: 出典 3 要素（`source_path` / `source_lines` / `detection_command`）
          がいずれも非空であること。
        - R1-2: `stream` が `A` / `B` / `D` のうち単一の値であること。
        - R1-3: `disposition` が `除去対象` / `保全対象` / `undetermined` のうち
          単一の値であること。
        - R1-6: `confirmation` が `None`（未確認）のとき `disposition` が
          `undetermined` であること。
        - R9-3: `confirmation` が存在するとき `evidence_command` が非空であること
          （確認結果は確認に用いた実行コマンドを出典として伴う。R5-8、R9-3。
          `scripts/cleanup/models.py` の `Confirmation.evidence_command` の
          「非空必須」に対応する）。

    引数:
        item: 検証対象の `LegacyAssetItem`。

    戻り値:
        違反文字列のタプル。各要素は `"<条項識別子>: <キー>: <内容>"` の形式で、
        対象キーと条項を識別できる。適合時は空タプル。

    例外:
        送出しない（違反は戻り値で表現する）。
    """
    violations: list[str] = []

    # R1-1: 出典 3 要素。どの要素が欠落したかを個別に列挙する。
    for field_name, value in (
        ("source_path", item.source_path),
        ("source_lines", item.source_lines),
        ("detection_command", item.detection_command),
    ):
        if _is_blank(value):
            violations.append(f"R1-1: {item.key}: {field_name} が空である")

    # R1-2: 系統は A / B / D の排他 1 値。
    if item.stream not in VALID_STREAMS:
        violations.append(
            f"R1-2: {item.key}: stream が A/B/D のいずれでもない（{item.stream!r}）"
        )

    # R1-3: 扱いは 3 値の排他 1 値。
    if item.disposition not in VALID_DISPOSITIONS:
        violations.append(
            f"R1-3: {item.key}: disposition が 除去対象/保全対象/undetermined の"
            f"いずれでもない（{item.disposition!r}）"
        )

    if item.confirmation is None:
        # R1-6: 確認結果が得られていない項目の扱いは undetermined でなければならない。
        if item.disposition != DISPOSITION_UNDETERMINED:
            violations.append(
                f"R1-6: {item.key}: confirmation が None であるのに disposition が "
                f"undetermined ではない（{item.disposition!r}）"
            )
    elif _is_blank(item.confirmation.evidence_command):
        # R9-3 / R5-8: 確認結果には確認に用いた実行コマンドを出典として付す。
        violations.append(
            f"R9-3: {item.key}: confirmation.evidence_command が空である"
        )

    return tuple(violations)


def _validate_preserved_item(item: PreservedAssetItem) -> tuple[str, ...]:
    """系統 C の保全対象 1 項目の扱い固定を検証する（内部関数）.

    引数:
        item: 検証対象の `PreservedAssetItem`。

    戻り値:
        違反文字列のタプル。適合時は空タプル。

    例外:
        送出しない（違反は戻り値で表現する）。

    R1-8 は系統 C の対象を扱い「保全対象」として含むことを求める（出典:
    requirements.md Requirement 1 基準 8、design.md DM1 の
    `PreservedAssetItem.disposition` の「保全対象 固定」）。
    """
    if item.disposition != DISPOSITION_PRESERVED:
        return (
            f"R1-8: {item.key}: preserved の disposition が 保全対象 ではない"
            f"（{item.disposition!r}）",
        )
    return ()


def validate_inventory(inventory: Inventory) -> tuple[str, ...]:
    """必須キー網羅・扱い固定・キー重複を含む文書全体の違反を列挙する.

    検証内容（出典: design.md C2「検証内容」、同 DM2「必須キー集合」表、
    同 Property 2）:
        - 各 `items` 要素について `validate_item` の全違反。
        - 各 `preserved` 要素の `disposition` が `保全対象` であること（R1-8）。
        - `items` が E-3 / E-4 / E-6 / E-7 由来および本設計の新規検出キーを包含
          すること（R1-4、R7-11）。
        - `items` が E-8 由来 3 キーを包含し、その `disposition` が
          `undetermined` に固定されていること（R1-7）。
        - `preserved` が E-5 由来キーを包含すること（R1-8）。
        - `undetermined_notes` が E-9 由来キーを包含すること（R9-1、R9-2）。
        - キー重複がないこと（正本の一意性。design.md C1「正本は 1 つに限定する」）。
          `items` と `preserved` は同一の項目キー名前空間として扱う。
          `undetermined_notes` は `UndeterminedNote.key` が対応する項目キーを指す
          （design.md DM1）ため、項目側との一致は重複と見なさず、注記集合内の重複
          のみを検査する。

    引数:
        inventory: 検証対象の `Inventory`。

    戻り値:
        違反文字列のタプル。各要素は `"<条項識別子>: <キー>: <内容>"` の形式。
        適合時は空タプル。

    例外:
        送出しない（違反は戻り値で表現する）。
    """
    violations: list[str] = []

    # 項目単位の不変条件（R1-1〜R1-3、R1-6、R9-3）を先に列挙する。
    for item in inventory.items:
        violations.extend(validate_item(item))
    for preserved_item in inventory.preserved:
        violations.extend(_validate_preserved_item(preserved_item))

    item_keys = tuple(item.key for item in inventory.items)
    preserved_keys = tuple(item.key for item in inventory.preserved)
    note_keys = tuple(note.key for note in inventory.undetermined_notes)

    item_key_set = frozenset(item_keys)
    preserved_key_set = frozenset(preserved_keys)
    note_key_set = frozenset(note_keys)

    # 必須キーの包含。欠落キーは昇順で列挙し、報告順を決定的にする。
    for clause, required_keys in _REQUIRED_ITEM_KEY_SETS:
        for key in sorted(required_keys - item_key_set):
            violations.append(f"{clause}: {key}: 必須キーが items に存在しない")

    for key in sorted(REQUIRED_PRESERVED_KEYS_E5 - preserved_key_set):
        violations.append(f"R1-8: {key}: 必須キーが preserved に存在しない")

    for clause, required_keys in _REQUIRED_NOTE_KEY_SETS:
        for key in sorted(required_keys - note_key_set):
            violations.append(
                f"{clause}: {key}: 必須キーが undetermined_notes に存在しない"
            )

    # R1-7: E-8 由来キーの扱いは undetermined 固定。重複登録がある場合も全出現を
    # 検査するため、キー集合ではなく items を走査する。
    for item in inventory.items:
        if (
            item.key in REQUIRED_ITEM_KEYS_E8
            and item.disposition != DISPOSITION_UNDETERMINED
        ):
            violations.append(
                f"R1-7: {item.key}: E-8 由来キーの disposition が undetermined "
                f"ではない（{item.disposition!r}）"
            )

    # キー重複（正本の一意性）。
    for key in _duplicated_keys(item_keys + preserved_keys):
        violations.append(
            f"DM2-キー重複: {key}: items / preserved でキーが重複している"
        )
    for key in _duplicated_keys(note_keys):
        violations.append(
            f"DM2-キー重複: {key}: undetermined_notes でキーが重複している"
        )

    return tuple(violations)


def apply_confirmation(
    item: LegacyAssetItem, confirmation: Confirmation
) -> LegacyAssetItem:
    """確認結果で扱いを undetermined から確定へ更新する（冪等・単調）.

    R5-8 は「`undetermined` から『保全対象』または『除去対象』へ更新し、確定に
    用いた実行コマンドを出典として付す」ことを求める（出典: requirements.md
    Requirement 5 基準 8）。R9-3 は確認結果が得られた項目の記録を確認結果と出典で
    更新することを求める（同 Requirement 9 基準 3）。したがって確定先の扱いは
    `confirmation.result` が保持する値（`除去対象` または `保全対象`）とする。

    振る舞い（出典: design.md Property 11）:
        - 冪等: 2 回適用した結果は 1 回適用した結果と等しい。
        - 単調: 適用後の `disposition` は `undetermined` へ戻らない。既に確定済み
          の項目へ同一の確定値の確認結果を適用した場合、`disposition` は変えず
          確認結果のみを更新する。
        - 更新後の項目は確認に用いた実行コマンドを非空の出典として保持する。

    引数:
        item: 更新対象の `LegacyAssetItem`。
        confirmation: 適用する確認結果。`result` は `除去対象` または `保全対象`、
            `evidence_command` は非空であること。

    戻り値:
        `disposition` と `confirmation` を更新した新しい `LegacyAssetItem`
        （`dataclasses.replace` による生成。入力オブジェクトは変更しない）。

    例外:
        ValueError: 次のいずれかに該当する場合。既定値による補完を行わず矛盾を
            表面化させる（第三原則3 フォールバック禁止）。
            - `confirmation.evidence_command` が空（出典を伴わない確定。R5-8）。
            - `confirmation.result` が `除去対象` / `保全対象` のいずれでもない
              （確定先を推測で補完しない。R5-8）。
            - 既に別の値へ確定済みの項目に異なる確定値を適用しようとした
              （既存の確定を黙って上書きしない。R9-3）。
    """
    if _is_blank(confirmation.evidence_command):
        raise ValueError(
            f"R5-8 違反: {item.key}: confirmation.evidence_command が空である"
            "（確定に用いた実行コマンドを出典として付すこと）"
        )

    if confirmation.result not in CONFIRMABLE_DISPOSITIONS:
        raise ValueError(
            f"R5-8 違反: {item.key}: confirmation.result が 除去対象/保全対象 の"
            f"いずれでもない（{confirmation.result!r}）"
        )

    if item.disposition == DISPOSITION_UNDETERMINED:
        # 未確定 → 確認結果の値へ確定する（単調性: undetermined へは戻さない）。
        return replace(
            item, disposition=confirmation.result, confirmation=confirmation
        )

    if item.disposition == confirmation.result:
        # 既に同一の値へ確定済み。確認結果のみを更新する（冪等性の担保）。
        return replace(item, confirmation=confirmation)

    # 既存の確定値と異なる確定値の適用は、いずれかの記録が誤っていることを示す。
    raise ValueError(
        f"R9-3 違反: {item.key}: 確定済みの disposition（{item.disposition!r}）と"
        f"異なる確認結果（{confirmation.result!r}）は適用できない"
    )
