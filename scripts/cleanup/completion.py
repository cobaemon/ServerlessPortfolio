"""旧資産除去（legacy-asset-cleanup）判定層の Completion_Judgment.

目的:
    「ある項目を除去済みとして計上してよいか」（R9-5、R2-9、R7-10）と
    「系統 B（SMTP 経路）が完了したか」（R4-9、R4-10、R4-14、R4-15、R4-16、
    R4-17）の 2 点のみを判定する。判定に用いるのは引数として渡された値だけで
    あり、残存走査コマンド（`git ls-files` / `git grep`）の実行、AWS 側の照会、
    ファイル I/O、`subprocess`、Django、boto3 を一切用いない（出典:
    `.kiro/specs/legacy-asset-cleanup/design.md` C5「Completion_Judgment」、
    同「Architecture > 依存方向」、同 tasks.md 3.5）。

出典:
    - `.kiro/specs/legacy-asset-cleanup/design.md` C5（`is_removed` /
      `is_stream_b_complete` のシグネチャと責務）、同 DM6（`STREAM_B_SEGMENTS`、
      `STREAM_B_AWS_TARGETS`、`AwsSmtpState` と完了条件
      「`queried` が真、かつ `absent_targets | deleted_targets ==
      expected_targets`、かつ `applied == STREAM_B_SEGMENTS`」）、
      同 C8「変更単位のスコープに関する整合注記」（区分 `B-1_prod_settings` が
      基準 1 の除去と基準 17 の `EMAIL_BACKEND` 明示設定の双方を担い、区分数は
      8 のままであること）、同 Property 5 / Property 6、同「Error Handling」の
      「系統 B の部分適用」行。
    - `.kiro/specs/legacy-asset-cleanup/requirements.md` Requirement 2 基準 9、
      Requirement 4 基準 9・10・14・15・16・17、Requirement 7 基準 10、
      Requirement 9 基準 5。
    - `scripts/cleanup/models.py`（DM1 / DM3 / DM6 の不変値型と定数
      `STREAM_B_SEGMENTS` / `STREAM_B_AWS_TARGETS`。型と定数を再定義せず再利用
      する）。
    - `scripts/cleanup/inventory.py`（`DISPOSITION_REMOVAL_TARGET`。R1-3 の扱い
      語彙を二重定義しないため import する。出典: `.kiro/steering/principles.md`
      第三原則1・2）。
    - `scripts/cleanup/removal_verification.py`（`VerificationResult` の生成元。
      本モジュールは適合判定を再実装せず `conformant` を消費するだけである）。

責務の範囲（単一責務。出典: design.md「Architecture > 依存方向」、同 C5）:
    - 本モジュールは 2 つの完了判定のみを担う。
    - 非退行レコードの適合評価は `removal_verification.py`（C4）、除去計画は
      `removal_plan.py`（C3）、Inventory の構造検証は `inventory.py`（C2）、
      破壊的操作の実行許可は `approval.py`（C11）、残存走査コマンドの実行と
      入出力は `cli.py`（C13、tasks.md 5.1）が担う。責務を重複させない。

設計上の制約（出典: `.kiro/steering/principles.md` 第二原則5、第三原則3）:
    - 標準ライブラリのみに依存する（本モジュールは標準ライブラリの import も
      不要である）。
    - フォールバックを実装しない。未確認・未照会の状態を完了と見せ得る既定値を
      置かない。矛盾した入力は `ValueError` として表面化させる。
    - 真偽値の判定は同一性比較（`is True`）で行い、暗黙の真偽変換で完了側へ
      倒さない（`scripts/cleanup/approval.py` の `is_executable` と同一方針。
      第二原則2 ゼロトラスト）。

設計の空白に対する判断（design.md C5 は不正入力の扱いを定めていないため、
本モジュールで方針を明記する。出典: `scripts/cleanup/inventory.py`
`apply_confirmation` および `scripts/cleanup/dependency_audit.py` `decide` が
矛盾入力に対して `ValueError` を送出する先例）:
    - `ValueError` を送出する入力（矛盾・不能値であり、記録側の誤りを示す）:
        - `residual_matches` が負値、または真偽値。
        - `verification.conformant` が真であるのに `violations` が非空
          （適合の主張と不適合条項の記録が両立しない。C4 の `evaluate` は
          `conformant = not violations` を保つ）。
        - `applied` が `STREAM_B_SEGMENTS` に存在しない区分を含む。
        - `aws_state.expected_targets` が `STREAM_B_AWS_TARGETS` と一致しない
          （R4-13 が対象 6 件を定めるため、期待集合を縮小して完了を成立させる
          ことを許さない）。
        - `absent_targets` または `deleted_targets` が `expected_targets` に
          含まれない対象を含む。
    - `ValueError` を送出せず偽を返す入力（完了と誤認する危険がなく、かつ設計に
      定めのない条件を判定へ追加しないため）:
        - `verification.conformant` が偽で `violations` が空。結論は「除去済みで
          ない」であり、条項の記録漏れは C4 側および記録側（tasks.md 13.1）の
          問題として残る。
        - `item.disposition` が R1-3 の 3 値以外。値域の検証は
          `inventory.py` の `validate_item`（R1-3）が担い、C13 は判定前に
          `validate_inventory` を通すことを設計上の前提とする（design.md C13）。
          本モジュールは「`除去対象` と一致するか」のみを見る。
        - `aws_state.queried` が偽である場合（`absent_targets` /
          `deleted_targets` の記録有無を問わず）。R4-15 は照会未成立の間の系統 B
          を未完了とすることを無条件に求めるため、偽を返す判定を優先する。
        - `absent_targets` と `deleted_targets` が重複する場合。DM6 の完了条件は
          和集合の一致のみを定め、両集合の排他性を求めていない。重複は R4-16 の
          運用（照会時点で不在の対象へ削除を実行しない）に反する記録の矛盾を
          示唆するが、いずれの記録も「対象が現存しない」ことを意味するため完了
          判定の結論を変えない。R4-16 の実行抑止は `approval.py`（C11）と運用
          手順が担う（設計に定めのない条件を判定へ追加しない。第二原則1）。

対応要件: R2-9、R4-9、R4-10、R4-14、R4-15、R4-16、R4-17、R7-10、R9-5
（出典: `.kiro/specs/legacy-asset-cleanup/requirements.md`）。
"""

from __future__ import annotations

from .inventory import DISPOSITION_REMOVAL_TARGET
from .models import (
    STREAM_B_AWS_TARGETS,
    STREAM_B_SEGMENTS,
    AwsSmtpState,
    LegacyAssetItem,
    VerificationResult,
)

# ---------------------------------------------------------------------------
# 判定基準の定数
# ---------------------------------------------------------------------------

# R9-5 は「除去確認コマンドで一致 0 件」を除去済み計上の条件の 1 つとして定める
# （出典: requirements.md Requirement 9 基準 5、design.md Property 5）。
EXPECTED_RESIDUAL_MATCHES: int = 0

# ---------------------------------------------------------------------------
# 条項識別子（`ValueError` のメッセージに含める）
# ---------------------------------------------------------------------------

CLAUSE_REMOVAL_COMPLETION = "R9-5"       # 除去済み計上の三条件（R2-9 / R7-10 と同条件）
CLAUSE_STREAM_B_CHANGE_UNIT = "R4-9"     # 系統 B の同一変更単位（8 区分）
CLAUSE_STREAM_B_AWS_TARGETS = "R4-13"    # 対象 AWS リソース 6 件
CLAUSE_STREAM_B_COMPLETION = "R4-14"     # 系統 B の完了判定


def is_removed(
    item: LegacyAssetItem,
    residual_matches: int,
    verification: VerificationResult,
) -> bool:
    """扱い・残存 0 件・非退行適合の三条件が同時成立する場合のみ True を返す.

    判定条件（3 条件の同時成立に限る。出典: design.md C5、同 Property 5、
    requirements.md Requirement 9 基準 5、Requirement 2 基準 9、
    Requirement 7 基準 10）:
        - R9-5（扱い）: `item.disposition` が `除去対象`
          （`scripts/cleanup/inventory.py` の `DISPOSITION_REMOVAL_TARGET`）で
          あること。`保全対象` および `undetermined` は計上しない（R9-4）。
        - R9-5（残存）: `residual_matches` が 0 であること。除去確認コマンド
          （`git ls-files` / `git grep`）の一致件数であり、実行は C13 が担う。
        - R9-5（非退行）: `verification.conformant` が真であること。R2-1〜R2-6 の
          適合判定は C4（`removal_verification.evaluate`）の結果であり、本関数は
          再評価しない。不適合の場合、当該除去は未完了として扱われる（R2-9）。
          Dependency_Manifest 変更時の R7-9 経由の適合（R7-10 の復帰対象判断）も
          同じ `VerificationResult` を通じて評価される。

    引数:
        item: 判定対象の `LegacyAssetItem`。値域（R1-3）の検証は
            `inventory.validate_item` が担い、本関数は行わない。
        residual_matches: 除去確認コマンドの一致件数（0 以上の整数）。
        verification: C4 が生成した `VerificationResult`。

    戻り値:
        3 条件がすべて成立する場合のみ True。それ以外は False。

    例外:
        ValueError: 次のいずれかに該当する場合。既定値による補完を行わず矛盾を
            表面化させる（第三原則3 フォールバック禁止）。
            - `residual_matches` が真偽値である（件数を真偽値で受け取らない。
              `scripts/cleanup/approval.py` の `reversible` 検証と同一方針）。
            - `residual_matches` が負値である（一致件数として不能な値）。
            - `verification.conformant` が真であるのに `violations` が非空である
              （適合の主張と不適合条項の記録が両立しない）。
        TypeError: `residual_matches` が整数との比較に適さない場合。評価時点で
            表面化させ、本関数は捕捉しない
            （`scripts/cleanup/removal_verification.py` と同一方針）。

    副作用:
        なし。コマンド実行・ファイル I/O・入力オブジェクトの変更を行わない。
    """
    # 件数を真偽値で受け取らない。`bool` は `int` の派生型であり、`False` を 0 件、
    # `True` を 1 件として黙って解釈すると残存有無の記録誤りが判定へ紛れ込む。
    if isinstance(residual_matches, bool):
        raise ValueError(
            f"{CLAUSE_REMOVAL_COMPLETION} 違反: {item.key}: residual_matches が"
            f"真偽値である（{residual_matches!r}）"
        )

    # 一致件数は 0 以上でしかあり得ない。負値は記録側の誤りであり、0 件と同一視
    # して除去済みへ計上しない。
    if residual_matches < EXPECTED_RESIDUAL_MATCHES:
        raise ValueError(
            f"{CLAUSE_REMOVAL_COMPLETION} 違反: {item.key}: residual_matches が"
            f"負値である（{residual_matches!r}）"
        )

    # 「適合」と「不適合条項あり」は両立しない（C4 は `conformant = not
    # violations` を保つ）。この矛盾を許すと不適合な非退行結果で除去済みを計上
    # し得るため、偽へ倒さずに送出する。
    if verification.conformant is True and verification.violations:
        raise ValueError(
            f"{CLAUSE_REMOVAL_COMPLETION} 違反: {item.key}: verification が適合で"
            f"あるのに violations が非空である（{verification.violations!r}）"
        )

    # 条件 1: 扱いが 除去対象（R9-5）。
    is_removal_target = item.disposition == DISPOSITION_REMOVAL_TARGET
    # 条件 2: 残存一致 0 件（R9-5）。
    has_no_residual = residual_matches == EXPECTED_RESIDUAL_MATCHES
    # 条件 3: 非退行判定が適合（R9-5、R2-9）。暗黙の真偽変換で適合側へ倒さない。
    is_conformant = verification.conformant is True

    return is_removal_target and has_no_residual and is_conformant


def is_stream_b_complete(applied: frozenset[str], aws_state: AwsSmtpState) -> bool:
    """8 区分すべての適用と AWS 側の削除完了・不在確認の双方成立のみを True とする.

    判定条件（3 条件の同時成立に限る。出典: design.md DM6「完了条件」、同 C5、
    同 Property 6、requirements.md Requirement 4 基準 9・10・14・15・16・17）:
        - R4-9 / R4-10: `applied == STREAM_B_SEGMENTS`。8 区分を同一の変更単位と
          して適用するため、部分適用（真部分集合）は完了と扱わない。区分
          `B-1_prod_settings` は基準 1 の除去（`config/settings/prod.py:72-86`）と
          基準 17 の `EMAIL_BACKEND` 明示設定の双方を含むため、本判定の「8 区分
          すべての適用」は R4-17 の適用を含む（出典: design.md C8「変更単位の
          スコープに関する整合注記」、同 DM6、requirements.md:220、:221、:225）。
        - R4-15: `aws_state.queried` が真。照会が未実施の間は他の条件が成立して
          いても未完了とする（既定値による補完を行わない）。
        - R4-14 / R4-16: `absent_targets | deleted_targets == expected_targets`。
          承認済み削除が完了した対象（R4-14）と、照会時点で既に不在であった対象
          （R4-16）は、いずれも「対象が現存しない」ことを意味する。R4-16 は不在を
          照会結果として記録し基準 14 の不在確認を成立として扱うことを定めるため、
          `absent_targets` を `deleted_targets` と同等の成立要素として和集合に
          含め、その和集合が対象 6 件と一致することを要求する。したがって削除を
          実行していない対象があっても、不在確認が成立していれば完了条件を満たす。

    引数:
        applied: 適用済みの系統 B 変更区分の集合。要素は `STREAM_B_SEGMENTS` の
            区分名。
        aws_state: AWS 側状態（DM6 の `AwsSmtpState`）。`expected_targets` には
            `STREAM_B_AWS_TARGETS`（対象 6 件）を渡す。

    戻り値:
        3 条件がすべて成立する場合のみ True。それ以外は False。

    例外:
        ValueError: 次のいずれかに該当する場合。設計上存在し得ない記録であり、
            既定値で補完せず表面化させる（第三原則3 フォールバック禁止、
            第二原則2 ゼロトラスト）。
            - `applied` が `STREAM_B_SEGMENTS` に存在しない区分を含む
              （設計外の変更区分を適用済みとして記録している。R4-9）。
            - `aws_state.expected_targets` が `STREAM_B_AWS_TARGETS` と一致しない
              （R4-13 が対象 6 件を定める。期待集合を縮小・拡張した状態で完了を
              成立させない）。
            - `aws_state.absent_targets` または `aws_state.deleted_targets` が
              `expected_targets` に含まれない対象を含む（対象外リソースの確認
              結果を完了判定へ持ち込まない。R4-13、R4-14、R4-16）。

    副作用:
        なし。AWS 照会・コマンド実行・ファイル I/O・入力オブジェクトの変更を
        行わない。削除操作の実行許可判定は `approval.py`（C11）が担う。
    """
    # 設計外の変更区分を適用済みとして記録している状態は、判定範囲（基準 1〜8
    # および基準 17）と記録の不整合であり、集合不一致による偽で覆い隠さない。
    unknown_segments = applied - STREAM_B_SEGMENTS
    if unknown_segments:
        raise ValueError(
            f"{CLAUSE_STREAM_B_CHANGE_UNIT} 違反: applied に STREAM_B_SEGMENTS 外の"
            f"区分が含まれる（{tuple(sorted(unknown_segments))!r}）"
        )

    # 期待対象集合は R4-13 が列挙する 6 件で固定である。縮小された期待集合を
    # 受け入れると、未確認の対象を残したまま完了が成立し得る。
    if aws_state.expected_targets != STREAM_B_AWS_TARGETS:
        raise ValueError(
            f"{CLAUSE_STREAM_B_AWS_TARGETS} 違反: aws_state.expected_targets が "
            f"STREAM_B_AWS_TARGETS と一致しない"
            f"（{tuple(sorted(aws_state.expected_targets))!r}）"
        )

    # 対象外リソースの不在確認・削除完了は完了判定の根拠にならない。
    for field_name, targets in (
        ("absent_targets", aws_state.absent_targets),
        ("deleted_targets", aws_state.deleted_targets),
    ):
        unknown_targets = targets - aws_state.expected_targets
        if unknown_targets:
            raise ValueError(
                f"{CLAUSE_STREAM_B_COMPLETION} 違反: aws_state.{field_name} に "
                f"expected_targets 外の対象が含まれる"
                f"（{tuple(sorted(unknown_targets))!r}）"
            )

    # 条件 1: 8 区分の完全一致（R4-9、R4-10）。部分適用は完了ではない。
    all_segments_applied = applied == STREAM_B_SEGMENTS
    # 条件 2: AWS 側照会の実施（R4-15）。暗黙の真偽変換で完了側へ倒さない。
    aws_queried = aws_state.queried is True
    # 条件 3: 削除完了と不在確認の和集合が対象 6 件と一致（R4-14、R4-16）。
    # 不在確認済み対象は削除完了と同等に扱う（R4-16）。
    aws_targets_settled = (
        aws_state.absent_targets | aws_state.deleted_targets
    ) == aws_state.expected_targets

    return all_segments_applied and aws_queried and aws_targets_settled
