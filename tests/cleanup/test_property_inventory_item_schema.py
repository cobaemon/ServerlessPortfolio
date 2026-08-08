"""Property 1（Inventory 項目のスキーマ不変条件）のプロパティテスト.

Feature: legacy-asset-cleanup, Property 1: *For any* Legacy_Asset_Item について、Inventory_Validator が適合（違反 0 件）と判定するのは、出典 3 要素（`source_path` / `source_lines` / `detection_command`）がいずれも非空であり、`stream` が `A` / `B` / `D` のうち単一の値であり、`disposition` が `除去対象` / `保全対象` / `undetermined` のうち単一の値であり、`confirmation` が `None` のときは `disposition` が `undetermined` であり、かつ `confirmation` が非 `None` のときは `result` が `除去対象` / `保全対象` のうち単一の値で `evidence_command` が非空である（R5-8。値域の根拠は DM1）場合に限る。

本モジュールは design.md「Correctness Properties > Property 1」および tasks.md 1.3 を
検証する（出典: `.kiro/specs/legacy-asset-cleanup/design.md:613-616`、
同 tasks.md「1.3 Inventory 項目スキーマのプロパティテストを書く」、
同 design.md「Testing Strategy」のプロパティ対応表
`Property 1 | tests/cleanup/test_property_inventory_item_schema.py`）。

**Validates: Requirements 1.1, 1.2, 1.3, 1.6**

    - R1-1: Legacy_Asset_Inventory は各項目についてファイルパス、行番号、および
      検出に用いた実行コマンドを出典として記録する（出典: requirements.md
      Requirement 1 基準 1）。
    - R1-2: 各項目を系統 A / B / D のいずれか 1 つに分類する（同 基準 2）。
    - R1-3: 各項目の扱いを「除去対象」「保全対象」「undetermined」のいずれか
      1 つとして記録する（同 基準 3）。
    - R1-6: 参照有無の確認結果が得られていない項目の扱いは `undetermined` と
      する（同 基準 6）。

検証対象（tasks.md 1.2 実装、design.md C2）:
    - `scripts/cleanup/inventory.py` の `validate_item(item) -> tuple[str, ...]`
      （空タプル＝適合。違反文字列は `"<条項識別子>: <キー>: <内容>"` 形式）。

双方向の検証（プロパティ本文の「〜である場合に限る」= 必要十分条件）:
    1. 出典 3 要素・`stream`・`disposition`・R1-6 の 4 条件すべてを満たす項目に対して
       `validate_item` は空タプル（適合）を返す。
    2. いずれか 1 つ以上に違反する項目に対して `validate_item` は非空タプル
       （不適合）を返す。

検証しない事項（受入基準・Property 1 が規定しないため対象外とする）:
    - どの条項識別子として報告するか、および違反文字列の形式・内容。Property 1 は
      適合／不適合の判定（適合述語）を定めるのみであり、requirements.md にも報告
      文面を定める受入基準は存在しない。
    - `confirmation` が非 `None` のときの `result` 値域と `evidence_command` の非空
      （Property 1 本文の第 5 条件、R5-8）。本モジュールの生成器は `Confirmation` を
      生成する際に必ず非空の `evidence_command` を与えるため、当該条件の不適合方向は
      本モジュールの入力域に現れない。`Confirmation` の値域そのものの検証は
      Property 11（`tests/cleanup/test_property_confirmation_update.py`）および
      C2 の適用側（C13）が扱う。

入力域（空白の扱い。design.md の検証内容に一致させる）:
    - `validate_item` は空白のみの文字列を空（欠落）として扱う（出典:
      `scripts/cleanup/inventory.py` の `_is_blank` は `value.strip()` の真偽で
      判定する）。本テストの生成器および独立オラクルも同一の解釈（`strip()` 後が
      空なら欠落）を採る。

ライセンス注記（第二原則6・要ライセンス確認）:
    - Hypothesis は Mozilla Public License 2.0（MPL-2.0）で配布される（出典:
      `requirements-dev.txt:18` の `hypothesis==6.158.0` および同ファイルの
      ライセンス注記、公式リポジトリ LICENSE.txt）。開発・テスト時のみ使用し、
      改変せず Lambda 配布物へ同梱しないため、MPL-2.0 のソース開示義務の実務的
      対象外である（非配布・非改変）。

テスト方針（出典: design.md「Testing Strategy」、既存前例
`portfolio/tests/test_property_csp_allowlist.py`）:
    - 単一プロパティを 1 テストで実装し、`@settings(max_examples=...)` は
      design.md が求める 100 反復以上とする。
    - 検証対象 `scripts/cleanup/inventory.py` は Django 非依存であるため Django の
      セットアップを行わない（出典: design.md「Testing Strategy」
      「Property 1〜8、10、11 の対象モジュールは Django 非依存であるため Django の
      セットアップを行わない」）。
    - 期待値（適合可否と違反条項集合）は実装の定数を再利用せず、requirements.md の
      基準文面を出典として本モジュール内に独立定義する（実装のバグを実装由来の
      定数で見逃さないため）。
    - フォールバック禁止: 期待を明示アサートし、差異を握りつぶさない。

実行コマンド（プロジェクトルートから）:
    $env:DJANGO_SETTINGS_MODULE="config.settings.dev"; python manage.py test tests.cleanup.test_property_inventory_item_schema
  もしくは（Django 非ロードでも実行可能）:
    python -m unittest tests.cleanup.test_property_inventory_item_schema -v
"""

from __future__ import annotations

import string
import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

# 検証対象（tasks.md 1.2 実装、design.md C2）と入力値型（design.md DM1）。
from scripts.cleanup.inventory import validate_item
from scripts.cleanup.models import Confirmation, LegacyAssetItem

# ---------------------------------------------------------------------------
# 期待値の独立定義（requirements.md の基準文面を出典とし、実装定数を再利用しない）
# ---------------------------------------------------------------------------

# R1-2 の系統 3 値（出典: requirements.md Requirement 1 基準 2「系統 A
# （Repository_Local_Removal）、系統 B（Configuration_Coherent_Removal）、
# 系統 D（Dependency_Removal）のいずれか 1 つに分類する」）。
_EXPECTED_STREAMS: frozenset[str] = frozenset({"A", "B", "D"})

# R1-3 の扱い 3 値（出典: requirements.md Requirement 1 基準 3）。
_EXPECTED_DISPOSITION_UNDETERMINED = "undetermined"
_EXPECTED_DISPOSITIONS: frozenset[str] = frozenset({
    "除去対象",
    "保全対象",
    _EXPECTED_DISPOSITION_UNDETERMINED,
})

# 出典 3 要素のフィールド名（出典: requirements.md Requirement 1 基準 1、
# design.md DM1 の `LegacyAssetItem`）。
_SOURCE_FIELDS: tuple[str, ...] = ("source_path", "source_lines", "detection_command")

# 生成に用いる非空白文字の集合。出典値は実体としてパス・行番号・コマンドを表すため
# 記号を含む広めの ASCII を用いる（空白文字は含めない。空白は後段で任意に付加する）。
_NON_BLANK_ALPHABET = (
    string.ascii_letters + string.digits + "-_./:,|=*'\"()[]{}$#@!?+~^"
)

# 空白のみ（= 欠落として扱われる）値に用いる文字集合。`str.strip()` が除去する
# 文字であることを前提とする（半角空白・タブ・改行・復帰・垂直タブ・改頁・全角空白）。
_WHITESPACE_ALPHABET = " \t\n\r\v\f\u3000"

# `key` に用いる文字集合（Inventory 正本のキー表記に倣う。出典:
# `docs/legacy-asset-inventory.json` の各 `key`）。
_KEY_ALPHABET = string.ascii_letters + string.digits + "_"

# R1-2 に違反する値の固定候補（境界値: 空文字列、空白のみ、前後空白付き、
# 大文字小文字違い、未定義値、複数値の連結）。
_INVALID_STREAM_FIXTURES: tuple[str, ...] = (
    "",
    " ",
    "C",
    "a",
    "b",
    "d",
    "AB",
    "A ",
    " A",
    "A,B",
    "系統A",
)

# R1-3 に違反する値の固定候補（同様の境界値）。
_INVALID_DISPOSITION_FIXTURES: tuple[str, ...] = (
    "",
    " ",
    "除去",
    "除去対象 ",
    " 保全対象",
    "保全",
    "Undetermined",
    "UNDETERMINED",
    "undetermined ",
    "unknown",
    "除去対象/保全対象",
)


def _is_blank(value: str) -> bool:
    """文字列が欠落（空または空白のみ）かを独立に判定する.

    Args:
        value: 判定対象の文字列。

    Returns:
        bool: `strip()` 後が空文字列であれば True。

    Raises:
        送出しない。

    実装の `_is_blank` を再利用せず、本モジュール冒頭の「入力域」（空白のみは欠落）に
    従って独立に定義する。
    """
    return not value.strip()


def _non_blank_text() -> st.SearchStrategy[str]:
    """非空（空白のみでない）文字列を生成する.

    Returns:
        SearchStrategy[str]: 非空白文字を 1 文字以上含む文字列。前後に空白が
            付く場合も含める（`strip()` 後が非空であることは保証される）。
    """
    core = st.text(alphabet=_NON_BLANK_ALPHABET, min_size=1, max_size=40)
    padding = st.text(alphabet=_WHITESPACE_ALPHABET, min_size=0, max_size=2)
    # 前後の空白は `strip()` で除去されるため、結合後も欠落とはならない。
    return st.builds(
        lambda left, core_text, right: left + core_text + right,
        padding,
        core,
        padding,
    )


def _blank_text() -> st.SearchStrategy[str]:
    """欠落（空文字列または空白のみ）となる文字列を生成する.

    Returns:
        SearchStrategy[str]: 空文字列、または空白文字のみから成る文字列。
    """
    return st.text(alphabet=_WHITESPACE_ALPHABET, min_size=0, max_size=4)


def _source_field_value() -> st.SearchStrategy[str]:
    """出典 3 要素の 1 要素の値を生成する（非空・欠落の双方）.

    Returns:
        SearchStrategy[str]: 非空文字列または欠落文字列。R1-1 の適合・不適合の
            双方を生成するため、欠落側の生成経路を明示的に確保する。
    """
    return st.one_of(_non_blank_text(), _blank_text())


def _stream_value() -> st.SearchStrategy[str]:
    """`stream` の値を生成する（R1-2 の適合値と不適合値の双方）.

    Returns:
        SearchStrategy[str]: `A` / `B` / `D`、固定の不適合候補、または任意文字列。
    """
    return st.one_of(
        st.sampled_from(sorted(_EXPECTED_STREAMS)),
        st.sampled_from(_INVALID_STREAM_FIXTURES),
        st.text(alphabet=_NON_BLANK_ALPHABET, min_size=1, max_size=8),
    )


def _disposition_value() -> st.SearchStrategy[str]:
    """`disposition` の値を生成する（R1-3 の適合値と不適合値の双方）.

    Returns:
        SearchStrategy[str]: 扱い 3 値、固定の不適合候補、または任意文字列。
    """
    return st.one_of(
        st.sampled_from(sorted(_EXPECTED_DISPOSITIONS)),
        st.sampled_from(_INVALID_DISPOSITION_FIXTURES),
        st.text(alphabet=_NON_BLANK_ALPHABET, min_size=1, max_size=12),
    )


def _confirmation_value() -> st.SearchStrategy[Confirmation | None]:
    """`confirmation` の値を生成する（`None` と確認結果ありの双方）.

    Returns:
        SearchStrategy[Confirmation | None]: `None`（未確認）、または
            `evidence_command` が非空の `Confirmation`。

    `evidence_command` を必ず非空とするのは、本モジュールの検証対象を 4 条件
    （出典 3 要素・`stream`・`disposition`・R1-6）に限るためである（本モジュール
    冒頭の「検証しない事項」を参照）。
    """
    confirmations = st.builds(
        Confirmation,
        # `result` は Property 1 の検証対象ではないため、扱い 3 値と任意文字列の
        # 双方を与え、判定が `result` に依存しないことも同時に通す。
        result=st.one_of(
            st.sampled_from(sorted(_EXPECTED_DISPOSITIONS)),
            st.text(alphabet=_NON_BLANK_ALPHABET, min_size=0, max_size=12),
        ),
        evidence_command=_non_blank_text(),
    )
    return st.one_of(st.none(), confirmations)


@st.composite
def _legacy_asset_items(draw: st.DrawFn) -> LegacyAssetItem:
    """Property 1 の適合項目・不適合項目の双方を生成する.

    Args:
        draw: Hypothesis の draw 関数。

    Returns:
        LegacyAssetItem: 出典 3 要素・`stream`・`disposition`・`confirmation` の
            各値を独立に生成した項目。4 条件すべてを満たす場合（適合）と、
            1 つ以上に違反する場合（不適合）の双方が生成される。

    `description` / `removal_check_command` / `approver_decision_required` は
    Property 1 の検証対象外であり、判定へ影響しないことを確認する目的で任意値を
    与える。
    """
    return LegacyAssetItem(
        key=draw(st.text(alphabet=_KEY_ALPHABET, min_size=1, max_size=20)),
        description=draw(st.text(max_size=20)),
        stream=draw(_stream_value()),
        disposition=draw(_disposition_value()),
        source_path=draw(_source_field_value()),
        source_lines=draw(_source_field_value()),
        detection_command=draw(_source_field_value()),
        confirmation=draw(_confirmation_value()),
        removal_check_command=draw(st.one_of(st.none(), st.text(max_size=20))),
        approver_decision_required=draw(st.booleans()),
    )


def _expected_violated_clauses(item: LegacyAssetItem) -> frozenset[str]:
    """Property 1 の 4 条件に対する違反条項識別子の集合を独立に算出する.

    Args:
        item: 判定対象の項目。

    Returns:
        frozenset[str]: 違反した条項識別子の集合（空集合＝適合）。

    Raises:
        送出しない。

    算出規則（出典: requirements.md Requirement 1 基準 1・2・3・6）:
        - `R1-1`: 出典 3 要素のいずれかが欠落している。
        - `R1-2`: `stream` が `A` / `B` / `D` のいずれでもない。
        - `R1-3`: `disposition` が扱い 3 値のいずれでもない。
        - `R1-6`: `confirmation` が `None` かつ `disposition` が
          `undetermined` でない。
    """
    clauses: set[str] = set()

    # R1-1: 出典 3 要素の非空。1 要素でも欠落すれば違反。
    for field_name in _SOURCE_FIELDS:
        if _is_blank(getattr(item, field_name)):
            clauses.add("R1-1")

    # R1-2: 系統の排他 1 値。
    if item.stream not in _EXPECTED_STREAMS:
        clauses.add("R1-2")

    # R1-3: 扱いの排他 1 値。
    if item.disposition not in _EXPECTED_DISPOSITIONS:
        clauses.add("R1-3")

    # R1-6: 未確認項目の扱いは undetermined 固定。`disposition` が扱い 3 値の
    # いずれでもない場合も「undetermined ではない」ため R1-3 と併発する。
    if (
        item.confirmation is None
        and item.disposition != _EXPECTED_DISPOSITION_UNDETERMINED
    ):
        clauses.add("R1-6")

    return frozenset(clauses)


class InventoryItemSchemaProperty(unittest.TestCase):
    """Property 1 のプロパティテストを保持するテストケース."""

    # 反復回数は design.md「Testing Strategy」が求める 100 反復以上とし、4 条件の
    # 組合せ（2^4 の適合／不適合パターン）を十分に踏むため 200 とする。生成データに
    # よる per-example の締切超過による誤検知を避けるため deadline を無効化する
    # （判定は決定的であり、失敗は握りつぶさない）。
    @settings(max_examples=200, deadline=None)
    @given(item=_legacy_asset_items())
    def test_validate_item_conforms_iff_all_schema_conditions_hold(
        self, item: LegacyAssetItem
    ) -> None:
        """Feature: legacy-asset-cleanup, Property 1: Inventory 項目のスキーマ不変条件

        **Validates: Requirements 1.1, 1.2, 1.3, 1.6**

        *For any* Legacy_Asset_Item について、`validate_item` が適合（違反 0 件）と
        判定するのは、出典 3 要素（`source_path` / `source_lines` /
        `detection_command`）がいずれも非空であり、`stream` が `A` / `B` / `D` の
        うち単一の値であり、`disposition` が `除去対象` / `保全対象` /
        `undetermined` のうち単一の値であり、かつ `confirmation` が `None` のときは
        `disposition` が `undetermined` である場合に限ることを、双方向で検証する。
        報告内容（条項識別子・文面）は検証しない（本モジュール冒頭の
        「検証しない事項」）。
        """
        # 期待値（違反条項集合）を実装非依存に算出する。
        expected_clauses = _expected_violated_clauses(item)

        # 検証対象の実行。
        violations = validate_item(item)

        # 戻り値の型は違反文字列のタプル（出典: design.md C2 のシグネチャ）。
        self.assertIsInstance(
            violations,
            tuple,
            msg=f"validate_item の戻り値が tuple ではない: {violations!r}",
        )

        if not expected_clauses:
            # ---- 方向 1: 4 条件すべてを満たす項目は適合（空タプル）----
            self.assertEqual(
                violations,
                (),
                msg=(
                    "4 条件すべてを満たす項目が適合と判定されなかった: "
                    f"item={item!r}, violations={violations!r}"
                ),
            )
        else:
            # ---- 方向 2: 1 つ以上に違反する項目は非空タプル ----
            self.assertNotEqual(
                violations,
                (),
                msg=(
                    "条件に違反する項目が適合と判定された: "
                    f"item={item!r}, expected_clauses={sorted(expected_clauses)}"
                ),
            )
            # どの条項として報告するか、および違反文字列の形式は Property 1 も
            # requirements.md の受入基準も規定しないため検証しない（Property 1 は
            # 適合／不適合の判定を定める適合述語である）。


if __name__ == "__main__":
    # 単体実行用エントリ（`python -m unittest` による探索でも実行可能）。
    unittest.main()
