"""Property 3（非除去対象の除去保留と変更範囲の限定）のプロパティテスト.

Feature: legacy-asset-cleanup, Property 3: *For any* Inventory と任意の git 追跡パス集合について、Removal_Plan が生成する除去計画は、`disposition` が `保全対象` または `undetermined` の項目を 1 件も含まず、かつ計画に含まれる全項目の変更対象パスが git 追跡パス集合の部分集合である。

本モジュールは design.md「Correctness Properties > Property 3」および tasks.md 3.2 を
検証する（出典: `.kiro/specs/legacy-asset-cleanup/design.md:625-628`、
同 tasks.md「3.2 除去計画のプロパティテストを書く」、
同 design.md「Testing Strategy」のプロパティ対応表
`Property 3 | tests/cleanup/test_property_removal_plan.py`）。

**Validates: Requirements 3.7, 5.7, 5.9, 6.6, 6.8, 9.4**

    - R3-7: 系統 A の除去は変更対象を git 追跡下のファイルに限定する（出典:
      requirements.md Requirement 3 基準 7）。
    - R5-7: ビルド時依存の最小集合が確定していない間、当該範囲を `undetermined`
      と記録する（同 Requirement 5 基準 7）。
    - R5-9: 本 spec の除去対象は系統 C の対象を除外する（同 Requirement 5 基準 9）。
    - R6-6: `body_account_modal` ブロックの扱いについて Approver の判断が得られて
      いない間、当該ブロックを `undetermined` と記録する（同 Requirement 6 基準 6）。
    - R6-8: 系統 A の除去は変更対象を git 追跡下のファイルに限定する（同
      Requirement 6 基準 8）。
    - R9-4: ある項目が `undetermined` の状態にある場合、当該項目に対する除去を
      保留する（同 Requirement 9 基準 4）。

検証対象（tasks.md 3.1 実装、design.md C3）:
    - `scripts/cleanup/removal_plan.py` の
      `build_removal_plan(inventory, tracked_paths) -> RemovalPlan`。

検証する不変条件（Property 3 は普遍的不変条件であり、双条件ではない）:
    1. 計画（`RemovalPlan.items`）に `disposition` が `保全対象` または
       `undetermined` の項目を 1 件も含まない。あわせて `Inventory.preserved`
       （系統 C）の項目が計画へ混入しないこと（R5-9）を検証する。
    2. 計画の変更対象パス集合が `tracked_paths` の部分集合であり、かつ計画に含まれる
       全項目の変更対象パスが `tracked_paths` に含まれる（R3-7、R6-8）。

検証しない事項（受入基準から導出できないため対象外とする）:
    - 除外記録（実装の `RemovalPlan.excluded` に相当するフィールド）の内容・件数・
      形式。design.md DM7 は `RemovalPlan` を `items` と `change_target_paths` の
      2 要素で定義し、除外記録フィールドについて「要件から導出できないため、本設計
      では要求しない。当該フィールドが実装に存在する場合、それは要件に対応しない
      実装上の付加であり、受入基準の検証対象として扱わない」と明記する（出典:
      design.md DM7「除外記録フィールドを設けない理由」）。`undetermined` である
      事実とその理由の記録は Inventory 側が担う（R5-7、R6-6、R9-1、R9-2）。

入力域（Property 3 と design.md が定める範囲）:
    - 項目の「変更対象パス」は `LegacyAssetItem.source_path` である（出典: design.md
      DM7「『変更対象パス』に用いるフィールド」が `source_path` を明示的に指定する、
      および Property 3 本文「計画に含まれる全項目の変更対象パス（DM7 により
      `source_path`）」）。
    - `build_removal_plan` は例外を送出しない（出典:
      `scripts/cleanup/removal_plan.py` の `build_removal_plan` docstring「例外:
      送出しない」）。したがって本テストは `disposition` に R1-3 の 3 値以外
      （不正値）を含む入力も生成し、不変条件が保たれることを検証する。
    - `PreservedAssetItem.disposition` は `保全対象` 固定である（R1-8。出典:
      design.md DM1）。したがって生成器は当該値のみを与える。
    - キーは `items` と `preserved` を同一名前空間として一意である。design.md C2 は
      Inventory 文書全体の検証内容に「キー重複」を含め、C13 は判定前に必ず C2 の
      スキーマ検証を通すことを定める（出典: design.md C2「検証内容」、同 C13
      「ゼロトラスト」、`scripts/cleanup/inventory.py` の `validate_inventory` が
      `items` + `preserved` を同一名前空間として重複を報告する実装）。したがって
      両名前空間でキーが衝突する入力は `build_removal_plan` の妥当な入力域に含まれ
      ない。生成器は接頭辞（`item_` / `preserved_`）により両名前空間を分離する。

ライセンス注記（第二原則6・要ライセンス確認）:
    - Hypothesis は Mozilla Public License 2.0（MPL-2.0）で配布される（出典:
      `requirements-dev.txt:18` の `hypothesis==6.158.0` および同ファイル 6-14 行の
      ライセンス注記、公式リポジトリ LICENSE.txt）。開発・テスト時のみ使用し、
      改変せず Lambda 配布物へ同梱しないため、MPL-2.0 のソース開示義務の実務的
      対象外である（非配布・非改変）。

テスト方針（出典: design.md「Testing Strategy」、既存前例
`portfolio/tests/test_property_csp_allowlist.py`、兄弟テスト
`tests/cleanup/test_property_inventory_item_schema.py`）:
    - 単一プロパティを 1 テストで実装し、`@settings(max_examples=...)` は design.md
      が求める 100 反復以上とする。
    - 検証対象 `scripts/cleanup/removal_plan.py` は Django 非依存であるため Django の
      セットアップを行わない（出典: design.md「Testing Strategy」）。
    - 期待値（扱い 3 値）は実装の定数を再利用せず、requirements.md の基準文面を
      出典として本モジュール内に独立定義する（実装のバグを実装由来の定数で
      見逃さないため）。
    - `tracked_paths` は生成項目の `source_path` と重複する場合と重複しない場合の
      双方を生成し、追跡外パスによる除外経路も走らせる。
    - フォールバック禁止: 期待を明示アサートし、差異を握りつぶさない。

実行コマンド（プロジェクトルートから）:
    $env:DJANGO_SETTINGS_MODULE="config.settings.dev"; python manage.py test tests.cleanup.test_property_removal_plan
  もしくは（Django 非ロードでも実行可能）:
    python -m unittest tests.cleanup.test_property_removal_plan -v
"""

from __future__ import annotations

import string
import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

# 検証対象（tasks.md 3.1 実装、design.md C3）と入力値型（design.md DM1・DM2）。
from scripts.cleanup.models import (
    Confirmation,
    Inventory,
    LegacyAssetItem,
    PreservedAssetItem,
    UndeterminedNote,
)
from scripts.cleanup.removal_plan import RemovalPlan, build_removal_plan

# ---------------------------------------------------------------------------
# 期待値の独立定義（requirements.md の基準文面を出典とし、実装定数を再利用しない）
# ---------------------------------------------------------------------------

# R1-3 の扱い 3 値（出典: requirements.md Requirement 1 基準 3「各項目の扱いを
# 「除去対象」「保全対象」「undetermined」のいずれか 1 つとして記録する」）。
_DISPOSITION_REMOVAL_TARGET = "除去対象"
_DISPOSITION_PRESERVED = "保全対象"
_DISPOSITION_UNDETERMINED = "undetermined"

# 計画へ含めてはならない扱い（出典: design.md Property 3 の本文「`disposition` が
# `保全対象` または `undetermined` の項目を 1 件も含まず」、R9-4、R5-7、R6-6）。
_FORBIDDEN_IN_PLAN: frozenset[str] = frozenset({
    _DISPOSITION_PRESERVED,
    _DISPOSITION_UNDETERMINED,
})

# `stream` の 3 値（出典: requirements.md Requirement 1 基準 2）。Property 3 は
# `stream` に依存しないが、Inventory として妥当な値域を与える。
_STREAMS: tuple[str, ...] = ("A", "B", "D")

# `disposition` に与える不正値の固定候補（R1-3 の 3 値以外。境界値: 空文字列、
# 空白のみ、前後空白付き、大文字小文字違い、複数値の連結）。実装は不正値を推測で
# 正規化せず計画から外すことを前提とする（本モジュール冒頭の「入力域」）。
_INVALID_DISPOSITION_FIXTURES: tuple[str, ...] = (
    "",
    " ",
    "除去対象 ",
    " 保全対象",
    "Undetermined",
    "UNDETERMINED",
    "unknown",
    "除去対象/保全対象",
)

# `key` に用いる文字集合（Inventory 正本のキー表記に倣う。出典:
# `docs/legacy-asset-inventory.json` の各 `key`）。
_KEY_ALPHABET = string.ascii_letters + string.digits + "_"

# `items` 側と `preserved` 側のキー名前空間を分離する接頭辞。design.md C2 が求める
# キー一意性（`items` + `preserved` を同一名前空間として扱う）を入力側で満たすために
# 用いる（本モジュール冒頭の「入力域」を参照）。
_ITEM_KEY_PREFIX = "item_"
_PRESERVED_KEY_PREFIX = "preserved_"

# `undetermined_notes` のキー接頭辞。`validate_inventory` は同集合を `items` /
# `preserved` とは別名前空間として扱うため衝突制約はないが、生成値の由来を明確に
# するため独立した接頭辞を用いる（出典: `scripts/cleanup/inventory.py` の
# `validate_inventory` docstring）。
_NOTE_KEY_PREFIX = "note_"

# 変更対象パスに用いる候補集合。`tracked_paths` との重複を生じさせるため、Inventory
# 正本に実在するパス（出典: `docs/legacy-asset-inventory.json` の `source_path`、
# requirements.md E-3 / E-4 / E-6 の対象ファイル）を含める固定プールを用いる。
_PATH_POOL: tuple[str, ...] = (
    "asgi_lambda.py",
    ".aws-sam/build.toml",
    ".gitignore",
    "config/settings/base.py",
    "config/settings/prod.py",
    "config/settings/dev.py",
    "config/urls.py",
    "portfolio/forms.py",
    "portfolio/views.py",
    "buildspec.yml",
    "requirements.txt",
    "docs/configuration.md",
    "templates/portfolio_base.html",
)

# `tracked_paths` にのみ現れるパス候補。追跡パス集合が計画のパス集合の真の上位集合
# となる場合を作るため、`_PATH_POOL` と重複しない値のみで構成する。
_TRACKED_ONLY_PATH_POOL: tuple[str, ...] = (
    "manage.py",
    "template.yaml",
    "docs/architecture.md",
    "portfolio/urls.py",
)

# 追跡外パスの固定候補（`tracked_paths` の生成経路に含めない値。生成物・未追跡
# ファイル名および空文字列を用い、追跡外による除外経路を確実に踏ませる）。
_UNTRACKED_PATH_POOL: tuple[str, ...] = (
    "staticfiles/prerender_manifest.json",
    ".aws-sam/build/template.yaml",
    "untracked/generated.tmp",
    "",
)


def _non_blank_text(max_size: int = 40) -> st.SearchStrategy[str]:
    """出典要素などに用いる非空文字列を生成する.

    Args:
        max_size: 生成する文字列の最大長。

    Returns:
        SearchStrategy[str]: 1 文字以上の ASCII 文字列。
    """
    alphabet = string.ascii_letters + string.digits + "-_./,|=*'\"()[]"
    return st.text(alphabet=alphabet, min_size=1, max_size=max_size)


def _keys(prefix: str) -> st.SearchStrategy[str]:
    """Inventory 項目キーを名前空間の接頭辞付きで生成する.

    Args:
        prefix: 名前空間を分離する接頭辞（`_ITEM_KEY_PREFIX` /
            `_PRESERVED_KEY_PREFIX`）。design.md C2 のキー一意性を入力側で満たす
            ため、`items` 側と `preserved` 側で異なる接頭辞を用いる。

    Returns:
        SearchStrategy[str]: 接頭辞に英数字とアンダースコアの非空文字列を連結した
            キー。
    """
    return st.text(alphabet=_KEY_ALPHABET, min_size=1, max_size=16).map(
        lambda suffix: f"{prefix}{suffix}"
    )


def _dispositions() -> st.SearchStrategy[str]:
    """`disposition` の値を生成する（3 値と不正値の双方）.

    Returns:
        SearchStrategy[str]: R1-3 の 3 値、固定の不正値候補、または任意文字列。

    `除去対象` の生成頻度を確保するため 3 値の抽出候補に当該値を 2 回含める
    （計画へ含まれる項目が生成されない反復ばかりでは不変条件 2 を検査できない）。
    """
    return st.one_of(
        # 3 値（うち `除去対象` は計画へ含まれ得る唯一の値）。
        st.sampled_from(
            (
                _DISPOSITION_REMOVAL_TARGET,
                _DISPOSITION_REMOVAL_TARGET,
                _DISPOSITION_PRESERVED,
                _DISPOSITION_UNDETERMINED,
            )
        ),
        # R1-3 の 3 値以外（不正値）。
        st.sampled_from(_INVALID_DISPOSITION_FIXTURES),
        st.text(alphabet=string.ascii_letters, min_size=0, max_size=8),
    )


def _source_paths() -> st.SearchStrategy[str]:
    """項目の変更対象パス（`source_path`）を生成する.

    Returns:
        SearchStrategy[str]: 固定プールのパス、追跡外候補のパス、または任意文字列。
            `tracked_paths` と重複する場合・重複しない場合の双方を作るため、
            3 経路を併用する。
    """
    return st.one_of(
        st.sampled_from(_PATH_POOL),
        st.sampled_from(_UNTRACKED_PATH_POOL),
        _non_blank_text(max_size=24),
    )


def _confirmations() -> st.SearchStrategy[Confirmation | None]:
    """`confirmation` の値を生成する（`None` と確認結果ありの双方）.

    Returns:
        SearchStrategy[Confirmation | None]: `None`（未確認）、または非空の
            `evidence_command` を持つ `Confirmation`。

    Property 3 は `confirmation` に依存しないが、DM1 の値域を踏むため双方を与える。
    """
    return st.one_of(
        st.none(),
        st.builds(
            Confirmation,
            result=st.sampled_from(
                (_DISPOSITION_REMOVAL_TARGET, _DISPOSITION_PRESERVED)
            ),
            evidence_command=_non_blank_text(max_size=24),
        ),
    )


@st.composite
def _legacy_asset_items(draw: st.DrawFn) -> LegacyAssetItem:
    """`Inventory.items` の 1 項目を生成する（扱い・パスの適合／不適合双方）.

    Args:
        draw: Hypothesis の draw 関数。

    Returns:
        LegacyAssetItem: `disposition` が 3 値または不正値、`source_path` が
            追跡下・追跡外の双方を取り得る項目。
    """
    return LegacyAssetItem(
        key=draw(_keys(_ITEM_KEY_PREFIX)),
        description=draw(st.text(max_size=16)),
        stream=draw(st.sampled_from(_STREAMS)),
        disposition=draw(_dispositions()),
        source_path=draw(_source_paths()),
        source_lines=draw(_non_blank_text(max_size=12)),
        detection_command=draw(_non_blank_text(max_size=24)),
        confirmation=draw(_confirmations()),
        removal_check_command=draw(st.one_of(st.none(), _non_blank_text(max_size=24))),
        approver_decision_required=draw(st.booleans()),
    )


@st.composite
def _preserved_items(draw: st.DrawFn) -> PreservedAssetItem:
    """`Inventory.preserved` の 1 項目（系統 C）を生成する.

    Args:
        draw: Hypothesis の draw 関数。

    Returns:
        PreservedAssetItem: `disposition` は `保全対象` 固定（R1-8。本モジュール
            冒頭の「入力域」）。`source_path` は追跡下パスと一致し得る値を与え、
            追跡状態に関わらず計画へ混入しないことを検査できるようにする。
    """
    return PreservedAssetItem(
        key=draw(_keys(_PRESERVED_KEY_PREFIX)),
        description=draw(st.text(max_size=16)),
        disposition=_DISPOSITION_PRESERVED,
        source_path=draw(st.sampled_from(_PATH_POOL)),
        source_lines=draw(_non_blank_text(max_size=12)),
        detection_command=draw(_non_blank_text(max_size=24)),
        build_time_dependency=draw(_non_blank_text(max_size=24)),
    )


@st.composite
def _undetermined_notes(draw: st.DrawFn) -> UndeterminedNote:
    """`Inventory.undetermined_notes` の 1 件を生成する.

    Args:
        draw: Hypothesis の draw 関数。

    Returns:
        UndeterminedNote: Property 3 の判定に影響しないことを確認する目的で
            任意値を与える。
    """
    return UndeterminedNote(
        key=draw(_keys(_NOTE_KEY_PREFIX)),
        reason=draw(st.text(max_size=16)),
        pending_check=draw(_non_blank_text(max_size=24)),
    )


@st.composite
def _plan_scenarios(draw: st.DrawFn) -> tuple[Inventory, frozenset[str]]:
    """Inventory と git 追跡パス集合の組を生成する.

    Args:
        draw: Hypothesis の draw 関数。

    Returns:
        tuple[Inventory, frozenset[str]]: 任意の Inventory と任意の追跡パス集合。
            追跡パス集合は (a) 生成項目の `source_path` から抽出した部分集合、
            (b) 固定プールの部分集合、(c) 項目と無関係なパスの部分集合 の合成とし、
            項目パスと重複する場合と重複しない場合の双方を確保する。空集合も許容
            する（全項目が追跡外となる境界）。
    """
    items = tuple(draw(st.lists(_legacy_asset_items(), min_size=0, max_size=8)))
    preserved = tuple(draw(st.lists(_preserved_items(), min_size=0, max_size=4)))
    notes = tuple(draw(st.lists(_undetermined_notes(), min_size=0, max_size=3)))

    inventory = Inventory(
        revision=draw(st.text(alphabet=string.hexdigits, min_size=1, max_size=7)),
        items=items,
        preserved=preserved,
        undetermined_notes=notes,
    )

    # (a) 生成項目の `source_path` の部分集合（追跡下となる経路。空集合も含む）。
    item_paths = sorted({item.source_path for item in items})
    if item_paths:
        overlapping = draw(
            st.lists(st.sampled_from(item_paths), min_size=0, max_size=len(item_paths))
        )
    else:
        # 項目が 0 件の場合は抽出元が空であり `sampled_from` を適用できない。
        overlapping = []

    # (b) 固定プールの部分集合（項目と一致する場合も一致しない場合もある）。
    pool_paths = draw(st.lists(st.sampled_from(_PATH_POOL), min_size=0, max_size=5))

    # (c) 項目パスと無関係な追跡パス（追跡パス集合が計画パス集合の真の上位集合と
    #     なる場合を作る）。
    tracked_only = draw(
        st.lists(st.sampled_from(_TRACKED_ONLY_PATH_POOL), min_size=0, max_size=3)
    )

    tracked_paths = (
        frozenset(overlapping) | frozenset(pool_paths) | frozenset(tracked_only)
    )
    return inventory, tracked_paths


class RemovalPlanScopeProperty(unittest.TestCase):
    """Property 3 のプロパティテストを保持するテストケース."""

    # 反復回数は design.md「Testing Strategy」が求める 100 反復以上とし、扱い 3 値
    # ＋不正値と追跡下／追跡外パスの組合せを十分に踏むため 200 とする。生成データに
    # よる per-example の締切超過による誤検知を避けるため deadline を無効化する
    # （判定は決定的であり、失敗は握りつぶさない）。
    @settings(max_examples=200, deadline=None)
    @given(scenario=_plan_scenarios())
    def test_plan_excludes_non_removal_targets_and_limits_paths_to_tracked(
        self, scenario: tuple[Inventory, frozenset[str]]
    ) -> None:
        """Feature: legacy-asset-cleanup, Property 3: 非除去対象の除去保留と変更範囲の限定

        **Validates: Requirements 3.7, 5.7, 5.9, 6.6, 6.8, 9.4**

        *For any* Inventory と任意の git 追跡パス集合について、`build_removal_plan`
        が生成する除去計画が (1) `disposition` が `保全対象` または `undetermined`
        の項目を 1 件も含まず（系統 C の `preserved` も含まない）、(2) 計画に含まれる
        全項目の変更対象パスが git 追跡パス集合の部分集合であることを検証する。
        """
        inventory, tracked_paths = scenario

        # 検証対象の実行（例外を送出しないことは本モジュール冒頭の「入力域」）。
        plan = build_removal_plan(inventory, tracked_paths)

        # 戻り値型（出典: `scripts/cleanup/removal_plan.py` の `RemovalPlan`）。
        self.assertIsInstance(
            plan,
            RemovalPlan,
            msg=f"build_removal_plan の戻り値が RemovalPlan ではない: {plan!r}",
        )

        # ---- (1) 非除去対象を計画へ含めないこと（Property 3 前半、R9-4/R5-7/R6-6）----
        for item in plan.items:
            self.assertNotIn(
                item.disposition,
                _FORBIDDEN_IN_PLAN,
                msg=(
                    "計画に 保全対象 / undetermined の項目が含まれる: "
                    f"key={item.key!r}, disposition={item.disposition!r}, "
                    f"tracked_paths={sorted(tracked_paths)!r}"
                ),
            )
            # C3 の判定規則「`disposition` が 除去対象 …の項目のみを計画へ含める」
            # （出典: `scripts/cleanup/removal_plan.py` の `build_removal_plan`
            # docstring）。R1-3 の 3 値以外の不正値も計画へ含めない。
            self.assertEqual(
                item.disposition,
                _DISPOSITION_REMOVAL_TARGET,
                msg=(
                    "計画に 除去対象 以外の disposition を持つ項目が含まれる: "
                    f"key={item.key!r}, disposition={item.disposition!r}"
                ),
            )

        # 系統 C（`preserved`）は本 spec の除去対象から除外される（R5-9）。同一キーの
        # 混入がないことを検査する（キーは items / preserved で一意。本モジュール
        # 冒頭の「入力域」）。
        planned_keys = frozenset(item.key for item in plan.items)
        for preserved_item in inventory.preserved:
            self.assertNotIn(
                preserved_item.key,
                planned_keys,
                msg=(
                    "系統 C の保全対象キーが計画に含まれる（R5-9 違反）: "
                    f"key={preserved_item.key!r}"
                ),
            )

        # ---- (2) 変更範囲を git 追跡パス集合へ限定（Property 3 後半、R3-7/R6-8）----
        self.assertTrue(
            plan.paths <= tracked_paths,
            msg=(
                "計画の変更対象パス集合が git 追跡パス集合の部分集合でない: "
                f"plan.paths={sorted(plan.paths)!r}, "
                f"tracked_paths={sorted(tracked_paths)!r}"
            ),
        )
        for item in plan.items:
            self.assertIn(
                item.source_path,
                tracked_paths,
                msg=(
                    "計画の項目の変更対象パスが git 追跡パス集合に含まれない: "
                    f"key={item.key!r}, source_path={item.source_path!r}, "
                    f"tracked_paths={sorted(tracked_paths)!r}"
                ),
            )

if __name__ == "__main__":
    # 単体実行用エントリ（`python -m unittest` による探索でも実行可能）。
    unittest.main()
