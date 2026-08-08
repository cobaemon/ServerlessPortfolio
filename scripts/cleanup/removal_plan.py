"""旧資産除去（legacy-asset-cleanup）判定層の Removal_Plan.

目的:
    Legacy_Asset_Inventory から「今このコミットで触ってよい項目」のみを決める。
    判定に用いるのは引数として渡された値だけであり、ファイル I/O・`subprocess`・
    Django・boto3 を一切用いない（出典:
    `.kiro/specs/legacy-asset-cleanup/design.md` C3「Removal_Plan」、
    同「Architecture > 依存方向」、同 tasks.md 3.1）。

出典:
    - `.kiro/specs/legacy-asset-cleanup/design.md` C3（関数シグネチャ・責務・
      不変条件）、同 Property 3「非除去対象の除去保留と変更範囲の限定」、
      同「Error Handling」の「参照有無の確認が未実施 → `undetermined` として記録
      し、除去を保留（Property 3 / 7）」。
    - `.kiro/specs/legacy-asset-cleanup/requirements.md` Requirement 3 基準 7、
      Requirement 5 基準 9、Requirement 6 基準 6・基準 8、Requirement 9 基準 4。
    - `scripts/cleanup/models.py`（DM1〜DM6 の不変値型）および
      `scripts/cleanup/inventory.py`（`DISPOSITION_*` 定数）。本モジュールは型と
      定数を再定義せず再利用する。

設計上の制約（出典: `.kiro/steering/principles.md` 第二原則5、第三原則3、
`AGENTS.md` 実装原則）:
    - フォールバックを実装しない。`除去対象` 以外の項目を暗黙に計画へ含めず、
      `tracked_paths` 外のパスを暗黙に落とさない。計画から外した項目はすべて
      `RemovalPlan.excluded` に条項識別子付きで記録し、除外を無記録にしない。
    - 本モジュールは「何に触ってよいか」のみを判定する（単一責務）。除去済み計上
      と系統 B 完了判定は `completion.py`、非退行判定は
      `removal_verification.py` が担う（出典: design.md「Architecture > 依存方向」
      の「モジュール分割は責務単位とする」、同 C4、C5）。

`RemovalPlan` を本モジュールで定義した理由（未解決の設計差分。第一原則3・7）:
    design.md C3 は戻り値型として `RemovalPlan` を宣言するが、同 Data Models
    （DM1〜DM6）に `RemovalPlan` のフィールド定義は存在せず、tasks.md 1.1 の
    `scripts/cleanup/models.py` の実装対象にも含まれていない（出典:
    `.kiro/specs/legacy-asset-cleanup/design.md` C3 のインターフェース節と
    「Data Models」節、`.kiro/specs/legacy-asset-cleanup/tasks.md` タスク 1.1 の
    列挙、`scripts/cleanup/models.py`）。したがって共有モデル（DM1〜DM6）を
    勝手に増やさず、C3 の不変条件から導出できる範囲に限って本モジュール内で
    定義する。各フィールドの導出根拠は `RemovalPlan` の docstring に記す。

本モジュールが判定しない事項:
    - Inventory の構造的不変条件（R1-1〜R1-8）。`inventory.py` の
      `validate_inventory` が担い、C13 が判定前に必ず適用する（出典: design.md
      C13「ゼロトラスト」）。
    - `source_lines` が実ファイルの実体と一致するか（R1-5。ファイル I/O を伴う
      ため design.md C13 の `--verify-lines` が担う）。
    - `tracked_paths` が実際の git 追跡状態と一致するか（`git ls-files` の実行は
      design.md C13 の責務）。
"""

from __future__ import annotations

from dataclasses import dataclass

from .inventory import (
    DISPOSITION_PRESERVED,
    DISPOSITION_REMOVAL_TARGET,
    DISPOSITION_UNDETERMINED,
)
from .models import Inventory, LegacyAssetItem


@dataclass(frozen=True)
class RemovalPlan:
    """除去計画（design.md C3 の戻り値型）.

    design.md の Data Models（DM1〜DM6）に本型の定義が存在しないため、
    フィールドは C3 が明示する責務と不変条件からのみ導出した（導出根拠を各
    フィールドに併記する）。設計に記述のない振る舞い・フィールドは追加しない。

    属性:
        items: 計画に含める項目。C3 の責務「Inventory から『今このコミットで触って
            よい項目』を決める」および同関数説明「`disposition` が除去対象で、かつ
            変更先が git 追跡下にある項目のみを計画へ含める」から導出。C3 の不変
            条件「計画 ∩ (`保全対象` ∪ `undetermined`) = ∅」が言う「計画」の実体で
            あり、Property 3 が検査する対象でもある。
        paths: 計画の変更対象パス集合。C3 の不変条件「計画の変更対象パス ⊆
            `tracked_paths`」の主語をそのまま保持する。`items` の各
            `source_path` から構成する（DM1 の `LegacyAssetItem` が持つ唯一の
            パス要素が `source_path` であるため。出典: design.md DM1）。
        excluded: 計画から外した項目の記録。各要素は
            `"<条項識別子>: <キー>: <内容>"` の形式（`inventory.py` の違反列挙と
            同一様式）。除外を無記録にしないために保持する。導出根拠は
            R9-4（`undetermined` 項目の除去保留）、R3-7 / R6-8（変更対象を git
            追跡下のファイルに限定）、R5-9（本 spec の除去対象から系統 C を除外）、
            および C3 の不変条件「計画 ∩ (`保全対象` ∪ `undetermined`) = ∅」。
            フォールバック禁止（第三原則3）により、除外は必ずこの記録として
            表面化させる。
    """

    items: tuple[LegacyAssetItem, ...]
    paths: frozenset[str]
    excluded: tuple[str, ...]


def build_removal_plan(
    inventory: Inventory, tracked_paths: frozenset[str]
) -> RemovalPlan:
    """`disposition` が除去対象で、かつ変更先が git 追跡下にある項目のみを計画へ含める.

    判定規則（出典: design.md C3、同 Property 3）:
        - `disposition` が `除去対象` かつ `source_path` が `tracked_paths` に含まれる
          項目のみを `RemovalPlan.items` へ含める。
        - `disposition` が `保全対象` または `undetermined` の項目は計画へ含めず、
          除外記録へ回す（C3 の不変条件、R9-4、R6-6）。
        - `disposition` が `除去対象` でも `source_path` が `tracked_paths` に含まれ
          ない項目は計画へ含めず、除外記録へ回す（R3-7、R6-8）。暗黙に落とさない。
        - `Inventory.preserved`（系統 C）は本 spec の除去対象から除外されるため
          （R5-9）、計画へ含めず除外記録へ回す。型が `PreservedAssetItem` であり
          `items` と別集合であることによる構造的除外を、記録として明示する。
        - `disposition` が R1-3 の 3 値のいずれでもない項目は計画へ含めず、条項
          `R1-3` の除外記録へ回す。値を推測で正規化しない（第三原則3）。構造検証
          自体は `inventory.py` の `validate_inventory` が担う。

    変更対象パスの取り方: DM1 の `LegacyAssetItem` が持つパス要素は
    `source_path` のみであるため（出典: design.md DM1）、C3 が言う「変更先」は
    `source_path` として扱う。

    引数:
        inventory: 判定対象の `Inventory`。呼び出し側は事前に
            `inventory.validate_inventory` を適用済みであること（出典: design.md
            C13「ゼロトラスト」）。
        tracked_paths: git 追跡下のパス集合（`git ls-files` の結果。取得は
            design.md C13 の責務）。

    戻り値:
        `RemovalPlan`。`items` は `inventory.items` の並び順を保ち、`excluded` は
        `inventory.items` → `inventory.preserved` の走査順で記録するため、同一入力
        に対して結果は決定的である。

    例外:
        送出しない（除外は戻り値の `excluded` で表現する）。

    事後条件（C3 の不変条件。Property 3 が検査する）:
        - `items` に `disposition` が `保全対象` または `undetermined` の項目を
          含まない。
        - `paths` ⊆ `tracked_paths`。
    """
    planned: list[LegacyAssetItem] = []
    excluded: list[str] = []

    for item in inventory.items:
        if item.disposition == DISPOSITION_REMOVAL_TARGET:
            if item.source_path in tracked_paths:
                planned.append(item)
            else:
                # R3-7 / R6-8: 変更対象を git 追跡下のファイルに限定する。追跡外の
                # パスは計画に載せられないため、黙って落とさず除外として記録する。
                excluded.append(
                    f"R3-7,R6-8: {item.key}: 変更対象パス "
                    f"{item.source_path!r} が git 追跡パス集合に含まれないため"
                    "計画へ含めない"
                )
        elif item.disposition == DISPOSITION_UNDETERMINED:
            # R9-4: undetermined の項目に対する除去は保留する（R5-7、R6-6 の
            # 保留状態もここに集まる）。
            excluded.append(
                f"R9-4: {item.key}: disposition が undetermined であるため"
                "除去を保留する"
            )
        elif item.disposition == DISPOSITION_PRESERVED:
            # C3 の不変条件「計画 ∩ (保全対象 ∪ undetermined) = ∅」。
            excluded.append(
                f"C3-不変条件: {item.key}: disposition が 保全対象 であるため"
                "計画へ含めない"
            )
        else:
            # R1-3 の 3 値以外は判定不能な入力である。既定値へ寄せず、除外理由を
            # 条項付きで残して表面化させる（第三原則3 フォールバック禁止）。
            excluded.append(
                f"R1-3: {item.key}: disposition が 除去対象/保全対象/undetermined の"
                f"いずれでもない（{item.disposition!r}）ため計画へ含めない"
            )

    for preserved_item in inventory.preserved:
        # R5-9: 本 spec の除去対象は系統 C を除外する。型による構造的除外を記録と
        # しても明示し、除外が無記録にならないようにする。
        excluded.append(
            f"R5-9: {preserved_item.key}: 系統 C の保全対象は本 spec の除去対象から"
            "除外する"
        )

    return RemovalPlan(
        items=tuple(planned),
        paths=frozenset(item.source_path for item in planned),
        excluded=tuple(excluded),
    )
