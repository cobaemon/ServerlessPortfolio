"""旧資産除去（legacy-asset-cleanup）判定層の Approval_Gate.

目的:
    AWS 側の破壊的操作（Destructive_Operation）について、実行許可の可否のみを
    判定し、提示必須項目の欠落を列挙する。判定に用いるのは引数として渡された値
    だけであり、AWS CLI の実行・`subprocess`・ファイル I/O・Django・boto3 を
    一切用いない（出典: `.kiro/specs/legacy-asset-cleanup/design.md` C11
    「Approval_Gate（Destructive_Operation）」、同「Architecture > 依存方向」、
    同 tasks.md 4.4）。

出典:
    - `.kiro/specs/legacy-asset-cleanup/design.md` C11（関数シグネチャ、許可対象
      種別、停止規則、運用手順）、同「Error Handling」の C11 に関する行
      （未承認・失敗・許可外種別の扱い）、同「機密値の取り扱い
      （ゼロトラスト・GDPR）」、同 Property 10。
    - `.kiro/specs/legacy-asset-cleanup/requirements.md` Requirement 8 基準
      1〜8。
    - `scripts/cleanup/models.py`（DM4 の `DestructiveOperationRequest` /
      `DestructiveOperationRecord` と定数 `ALLOWED_TARGET_KINDS`。本モジュールは
      型と定数を再定義せず再利用する）。

責務の範囲（単一責務。出典: design.md「Architecture > 依存方向」、同 C11）:
    - 本モジュールは「承認の有無」「対象種別の許可」「先行操作の失敗による停止」
      の 3 条件による実行許可判定と、提示必須項目の欠落列挙のみを担う。
    - AWS 操作そのもの（Parameter Store パラメータ削除、Secrets Manager キー
      削除）、実行前の現在値取得（R8-4）、実行後の不在確認（R8-5）、記録ファイル
      の作成（tasks.md 13.1）は本モジュールの責務ではない。これらは Approver
      承認と本モジュールの許可判定を前提とする運用手順として実施する（R8-1）。

機密値の取り扱い（出典: design.md「機密値の取り扱い（ゼロトラスト・GDPR）」、
`.kiro/steering/principles.md` 第二原則2、第二原則4）:
    - Secrets Manager 対象（`secrets_manager_secret_key`）の記録に平文値を
      含めない。R8-4 が求める「実行前の現在値」の記録として、DM4 の
      `pre_value_evidence` には**キー名の存在有無と取得に用いたコマンドのみ**を
      格納する。取得したシークレット JSON はキー一覧へ射影し、値を標準出力・
      記録の双方へ出さない（既存 `buildspec.yml:48` の `set +x`、
      `buildspec.yml:78` の `unset SECRET_JSON` と同一方針）。
    - Parameter Store 対象（`parameter_store_parameter`）は非機密の設定値で
      あるため、`aws ssm get-parameter` の取得値をそのまま記録する。
    - 本モジュールはシークレット値を読み取らず、引数として受け取らず、出力にも
      含めない。違反文字列に含めるのは対象識別子と条項識別子のみである。

設計上の制約（出典: `.kiro/steering/principles.md` 第三原則3、第二原則2）:
    - フォールバックを実装しない。判定不能な入力を既定値で補完せず、許可を与え
      ない方向（`False`）または違反の列挙として表面化させる。
    - 実行許可の 3 条件は design.md C11 および Property 10 に定める 3 つに限定
      する。提示内容の検証結果（`validate_request`）は許可条件に含めない
      （設計に定めのない条件を追加しない。第二原則1）。
"""

from __future__ import annotations

from .models import ALLOWED_TARGET_KINDS, DestructiveOperationRequest

# 提示必須項目のうち文字列で表される 4 項目と、欠落時に報告する条項識別子の
# 対応（出典: design.md C11「インターフェース」の docstring、requirements.md
# Requirement 8 基準 2「対象リソース識別子、実行コマンド、影響範囲、および
# 取り消し可否を提示し」、同基準 7「対象環境（staging または prod）を明記する」）。
# 取り消し可否（`reversible`）は真偽値であるため本表に含めず、個別に検査する。
_REQUIRED_TEXT_FIELDS: tuple[tuple[str, str], ...] = (
    ("R8-2", "target_identifier"),  # 対象リソース識別子（R8-2）
    ("R8-2", "command"),            # 実行コマンド（R8-2）
    ("R8-2", "impact"),             # 影響範囲（R8-2）
    ("R8-7", "environment"),        # 対象環境 staging / prod（R8-7）
)

# 対象識別子が欠落している提示に対して違反文字列へ用いる代替表記。識別子を
# 推測で補完しないことを明示するための表示専用の値であり、判定には用いない
# （第三原則3 フォールバック禁止）。
_MISSING_IDENTIFIER_LABEL = "<target_identifier 未記載>"


def _is_blank(value: str) -> bool:
    """文字列が空または空白のみかを判定する（内部関数）.

    引数:
        value: 判定対象の文字列。

    戻り値:
        空文字列または空白文字のみの場合 True。

    例外:
        送出しない。

    空白のみの値は提示内容として機能しないため欠落として扱う
    （`scripts/cleanup/inventory.py` の `_is_blank` と同一の扱いに揃える。
    第三原則1 一貫性）。
    """
    return not value.strip()


def is_executable(
    request: DestructiveOperationRequest, preceding_failed: bool
) -> bool:
    """承認・対象種別・先行操作の 3 条件が同時成立する場合のみ True を返す.

    実行許可条件（3 条件の同時成立に限る。出典: design.md C11「許可対象種別」
    「停止規則」、同「Error Handling」の C11 の 3 行、同 Property 10）:
        - R8-3: `request.approved` が真であること。承認が得られていない間は
          実行を保留し、提示内容を Approver へ再提示する。
        - R8-8: `request.target_kind` が `ALLOWED_TARGET_KINDS`
          （`parameter_store_parameter` / `secrets_manager_secret_key`）の
          いずれかであること。許可 2 種以外は常に拒否する。
        - R8-6: `preceding_failed` が偽であること。破壊的操作が 1 件失敗した
          時点で後続の全操作の実行許可を偽にする（停止規則）。

    引数:
        request: 判定対象の `DestructiveOperationRequest`。
        preceding_failed: 先行する破壊的操作が失敗しているか。失敗している場合
            （True）は、他の 2 条件が成立していても許可しない。呼び出し側は
            `DestructiveOperationRecord.error` が `None` 以外である操作が
            1 件でも存在する場合に True を渡す（出典: `models.py` DM4 の
            `error` の記述、R8-6）。

    戻り値:
        3 条件がすべて成立する場合のみ True。それ以外は False。

    例外:
        送出しない（許可の可否を戻り値で表現する）。

    注記:
        - 真偽値の判定は同一性比較（`is True` / `is False`）で行う。真偽値以外の
          値が渡された場合に暗黙の真偽変換で許可を与えないためであり、判定不能な
          入力に対しては許可を与えない方向へ倒す（第二原則2 ゼロトラスト、
          第三原則3 フォールバック禁止）。
        - `validate_request` の結果は許可条件に含めない。design.md C11 および
          Property 10 が定める許可条件は上記 3 条件であり、設計に定めのない
          条件を追加しない（第二原則1）。提示内容の欠落検証は運用手順の提示
          段階（R8-2）で `validate_request` により別途行う。
        - 本関数は AWS 操作を実行せず、実行可否の判断のみを返す。実際の削除は
          Approver 承認を前提とする運用手順として実施する（R8-1）。
    """
    # R8-3: Approver 承認。真偽値の True 以外（未承認、非真偽値）は許可しない。
    approved = request.approved is True
    # R8-8: 対象種別を許可 2 種に限定する。
    target_allowed = request.target_kind in ALLOWED_TARGET_KINDS
    # R8-6: 停止規則。先行操作が失敗していない（明示的な False）ことを要求する。
    not_stopped = preceding_failed is False

    return approved and target_allowed and not_stopped


def validate_request(request: DestructiveOperationRequest) -> tuple[str, ...]:
    """提示必須項目の欠落を列挙する（空タプル＝適合）.

    検証内容（出典: design.md C11「インターフェース」、同 Property 10、
    requirements.md Requirement 8 基準 2・基準 7）:
        - R8-2: `target_identifier`（対象リソース識別子）が非空であること。
        - R8-2: `command`（実行コマンド）が非空であること。
        - R8-2: `impact`（影響範囲）が非空であること。
        - R8-2: `reversible`（取り消し可否）が真偽値として提示されていること。
        - R8-7: `environment`（対象環境 staging / prod）が非空であること。

    引数:
        request: 検証対象の `DestructiveOperationRequest`。

    戻り値:
        違反文字列のタプル。各要素は `"<条項識別子>: <キー>: <内容>"` の形式で、
        `<キー>` は対象リソース識別子（欠落時は `"<target_identifier 未記載>"`）
        とする（`scripts/cleanup/inventory.py` の違反文字列形式に揃える。
        第三原則1 一貫性）。適合時は空タプル。

    例外:
        送出しない（違反は戻り値で表現する）。

    注記:
        - 本関数は「欠落」のみを検証する。対象種別が許可 2 種のいずれかである
          こと（R8-8）と承認の有無（R8-3）は `is_executable` が判定する
          （出典: design.md C11、同「Error Handling」）。環境値が
          `staging` / `prod` のいずれかであるかの値検証は design.md C11 の
          検証内容に定めがないため実装しない（設計の範囲に留める。第二原則1）。
        - 違反文字列にシークレット値を含めない。含めるのは対象識別子と条項識別子
          のみである（design.md「機密値の取り扱い」）。
    """
    violations: list[str] = []

    # 違反文字列の <キー> に用いる対象識別子。欠落時も違反を報告できるよう、
    # 表示専用の代替表記へ切り替える（値の補完は行わない）。
    key = (
        _MISSING_IDENTIFIER_LABEL
        if _is_blank(request.target_identifier)
        else request.target_identifier.strip()
    )

    # R8-2 / R8-7: 文字列で提示される 4 項目の欠落。どの項目が欠落したかを
    # 個別に列挙する。
    for clause, field_name in _REQUIRED_TEXT_FIELDS:
        if _is_blank(getattr(request, field_name)):
            violations.append(f"{clause}: {key}: {field_name} が空である")

    # R8-2: 取り消し可否は真偽値で提示する。真偽値以外（外部入力の JSON で
    # 項目が欠落した場合の None など）は提示欠落として扱い、暗黙の真偽変換で
    # 取り消し可否を推測しない（第二原則2 ゼロトラスト、第三原則3）。
    if not isinstance(request.reversible, bool):
        violations.append(
            f"R8-2: {key}: reversible が真偽値で提示されていない"
            f"（{request.reversible!r}）"
        )

    return tuple(violations)
