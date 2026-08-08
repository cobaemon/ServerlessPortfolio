"""Property 5（除去済み計上の三条件同時成立）のプロパティテスト.

Feature: legacy-asset-cleanup, Property 5: *For any* Legacy_Asset_Item・任意の残存一致件数・任意の VerificationResult の組について、Completion_Judgment が「除去済み」と判定するのは、`disposition` が `除去対象` であり、残存一致件数が 0 であり、かつ VerificationResult が適合である 3 条件が同時に成立する場合に限る。

本モジュールは design.md「Correctness Properties > Property 5」および tasks.md 3.6 を
検証する（出典: `.kiro/specs/legacy-asset-cleanup/design.md:637-641`、
同 tasks.md「3.6 除去済み計上のプロパティテストを書く」、
同 design.md「Testing Strategy」のプロパティ対応表
`Property 5 | tests/cleanup/test_property_removal_completion.py`（design.md:739））。

**Validates: Requirements 2.9, 7.10, 9.5**

    - R2-9: 基準 1 から基準 6 のいずれかの確認が不適合となった場合、当該除去を
      適用前の状態へ復帰させ、不適合の内容と出典を記録し、当該除去を未完了として
      扱う（出典: requirements.md:189）。本テストは「不適合な `VerificationResult`
      では除去済みと計上されない」ことを検証する。復帰そのものは git 操作であり
      判定層の対象外である（出典: `scripts/cleanup/completion.py` の `is_removed`
      docstring）。
    - R7-10: 依存グラフ解決または `pip install -r requirements.txt` が非ゼロ終了
      した場合、失敗内容と出典を記録し Dependency_Manifest を変更前の状態へ復帰
      させる（出典: requirements.md:285）。系統 D の除去も同じ
      `VerificationResult` を通して評価されるため、不適合時に除去済みと計上され
      ないことが本プロパティで担保される（出典: `scripts/cleanup/completion.py`
      の `is_removed` docstring「Dependency_Manifest 変更時の R7-9 経由の適合
      （R7-10 の復帰対象判断）も同じ `VerificationResult` を通じて評価される」）。
    - R9-5: 除去完了の判定は、扱いが「除去対象」であり、除去確認コマンドで一致
      0 件となり、かつ Requirement 2 の基準 1 から基準 6 の確認がすべて適合した
      項目のみを「除去済み」として計上する（出典: requirements.md:313）。

検証対象（tasks.md 3.5 実装、design.md C5）:
    - `scripts/cleanup/completion.py` の
      `is_removed(item, residual_matches, verification) -> bool`。
    - 同モジュールの `is_stream_b_complete` は Property 6
      （`tests/cleanup/test_property_stream_b_completion.py`、tasks.md 3.7）の
      対象であり、本モジュールでは検証しない（1 モジュール 1 プロパティ。出典:
      design.md「Testing Strategy」のプロパティ対応表）。

検証する不変条件（Property 5 は「〜場合に限る」＝双条件（iff）である）:
    `is_removed(item, residual_matches, verification)` が真であることは、次の
    3 条件の同時成立と同値である。
        1. `item.disposition == "除去対象"`
        2. `residual_matches == 0`
        3. `verification.conformant is True`
    本テストは 3 条件を実装から独立に評価した期待値（oracle）を組み立て、戻り値と
    完全一致することを検査する。3 条件のいずれか 1 つのみを偽にした場合も含め、
    真偽値の 8 通りの組合せをすべて踏む（`test_all_eight_condition_combinations`）。

入力域（生成器が引く範囲。R9-5 が定める三条件の入力域に対応する）:
    R9-5 は除去完了の判定を「扱いが『除去対象』であり、除去確認コマンドで一致 0 件と
    なり、かつ Requirement 2 の基準 1 から基準 6 の確認がすべて適合した項目」と定める
    （出典: requirements.md:313）。生成器はこの三条件が張る入力域から値を引く。
    - `disposition`: R1-3 の 3 値（出典: requirements.md Requirement 1 基準 3）および
      3 値以外。値域そのものの検証は `scripts/cleanup/inventory.py` の `validate_item`
      が担うため（出典: design.md C2「検証内容」）、本モジュールは 3 値以外に対して
      `除去対象` との不一致（偽）が返ることのみを検査する。
    - `residual_matches`: R9-5 が数える「除去確認コマンドの一致件数」であり、0 以上の
      整数（境界 0 と 1 を含む。出典: requirements.md:313）。
    - `verification`: C4（`scripts/cleanup/removal_verification.py` の `evaluate`）の
      出力空間と一致する値、すなわち不変条件 `conformant == (violations == ())` を
      満たす `VerificationResult`（出典: design.md Property 4、DM3
      `VerificationResult`）。

ライセンス注記（第二原則6・要ライセンス確認）:
    - Hypothesis は Mozilla Public License 2.0（MPL-2.0）で配布される（出典:
      `requirements-dev.txt:7-9` のライセンス注記、`requirements-dev.txt:17` の
      `License-Expression = MPL-2.0` 確認記録、同 `:18` の
      `hypothesis==6.158.0`）。開発・テスト時のみ使用し、改変せず Lambda 配布物へ
      同梱しないため、MPL-2.0 のソース開示義務の実務的対象外である（非配布・非改変）。

テスト方針（出典: design.md「Testing Strategy」、既存前例
`portfolio/tests/test_property_csp_allowlist.py`、兄弟テスト
`tests/cleanup/test_property_removal_plan.py`）:
    - 単一プロパティを 1 テストで実装し、`@settings(max_examples=...)` は design.md
      が求める 100 反復以上とする。
    - 検証対象 `scripts/cleanup/completion.py` は Django 非依存であるため Django の
      セットアップを行わない（出典: design.md「Testing Strategy」）。
    - 期待値（扱い 3 値・残存 0 件）は実装の定数（`DISPOSITION_REMOVAL_TARGET` /
      `EXPECTED_RESIDUAL_MATCHES`）を再利用せず、requirements.md の基準文面を出典
      として本モジュール内に独立定義する（実装のバグを実装由来の定数で見逃さない
      ため）。
    - フォールバック禁止: 期待を明示アサートし、差異を握りつぶさない。

実行コマンド（プロジェクトルートから）:
    $env:DJANGO_SETTINGS_MODULE="config.settings.dev"; python manage.py test tests.cleanup.test_property_removal_completion
  もしくは（Django 非ロードでも実行可能）:
    python -m unittest tests.cleanup.test_property_removal_completion -v
"""

from __future__ import annotations

import string
import unittest

from hypothesis import event, given, settings
from hypothesis import strategies as st

# 検証対象（tasks.md 3.5 実装、design.md C5）と入力値型（design.md DM1・DM3）。
from scripts.cleanup.completion import is_removed
from scripts.cleanup.models import Confirmation, LegacyAssetItem, VerificationResult

# ---------------------------------------------------------------------------
# 期待値の独立定義（requirements.md の基準文面を出典とし、実装定数を再利用しない）
# ---------------------------------------------------------------------------

# R1-3 の扱い 3 値（出典: requirements.md Requirement 1 基準 3「各項目の扱いを
# 「除去対象」「保全対象」「undetermined」のいずれか 1 つとして記録する」）。
_DISPOSITION_REMOVAL_TARGET = "除去対象"
_DISPOSITION_PRESERVED = "保全対象"
_DISPOSITION_UNDETERMINED = "undetermined"

# R9-5 が求める残存一致件数（出典: requirements.md:313「除去確認コマンドで一致
# 0 件となり」）。
_EXPECTED_RESIDUAL_MATCHES = 0

# `disposition` に与える R1-3 の 3 値以外（不正値）の固定候補。境界値として空文字列、
# 空白のみ、前後空白付き、大文字小文字違い、複数値の連結を含める。R9-5 の条件 1 は
# 「扱いが『除去対象』であること」のみを求めるため、不正値は `除去対象` と不一致
# （偽）として扱われる（出典: requirements.md:313。値域の検証は design.md C2 の
# `validate_item` の責務。本モジュール冒頭の「入力域」）。
_INVALID_DISPOSITION_FIXTURES: tuple[str, ...] = (
    "",
    " ",
    "除去対象 ",
    " 除去対象",
    "保全対象 ",
    "Undetermined",
    "UNDETERMINED",
    "除去対象/保全対象",
)

# `stream` の 3 値（出典: requirements.md Requirement 1 基準 2）。Property 5 は
# `stream` に依存しないが、DM1 として妥当な値域を与える。
_STREAMS: tuple[str, ...] = ("A", "B", "D")

# `VerificationResult.violations` に与える条項識別子の候補（出典: design.md C4
# 「不適合時は条項識別子（例 `"R2-1"`）を `violations` へ列挙する」、
# `scripts/cleanup/removal_verification.py` の条項識別子定義）。
_VIOLATION_CLAUSES: tuple[str, ...] = (
    "R2-1",
    "R2-2",
    "R2-3",
    "R2-4",
    "R2-5",
    "R2-6",
    "R2-10",
)

# 残存一致件数として与える代表値（0 件・1 件・それ以上）。R9-5 の境界は 0 と 1 の
# 間にあるため、双方および大きい値を必ず含める。
_RESIDUAL_FIXTURES: tuple[int, ...] = (0, 1, 2, 7, 133)


def _non_blank_text(max_size: int = 40) -> st.SearchStrategy[str]:
    """出典要素などに用いる非空文字列を生成する.

    Args:
        max_size: 生成する文字列の最大長。

    Returns:
        SearchStrategy[str]: 1 文字以上の ASCII 文字列。
    """
    alphabet = string.ascii_letters + string.digits + "-_./,|=*'\"()[]"
    return st.text(alphabet=alphabet, min_size=1, max_size=max_size)


def _fixed_item(disposition: str) -> LegacyAssetItem:
    """指定した `disposition` を持つ固定内容の `LegacyAssetItem` を組み立てる.

    Args:
        disposition: 項目の扱い。R1-3 の 3 値および 3 値以外を受け付ける（値域の
            検証は `scripts/cleanup/inventory.py` の `validate_item` の責務。
            本モジュール冒頭の「入力域」）。

    Returns:
        LegacyAssetItem: Property 5 の判定に影響しないフィールドを Inventory 正本の
            実在項目（系統 A の `asgi_lambda.py`。出典: requirements.md E-3、
            `docs/legacy-asset-inventory.json`）に倣って固定した項目。

    例外:
        送出しない。
    """
    return LegacyAssetItem(
        key="A1.asgi_lambda",
        description="Django on Lambda の残骸（Mangum handler）",
        stream="A",
        disposition=disposition,
        source_path="asgi_lambda.py",
        source_lines="6,9,12",
        detection_command="git grep -n 'asgi_lambda'",
        confirmation=None,
        removal_check_command="git ls-files -- asgi_lambda.py",
        approver_decision_required=False,
    )


def _expected_is_removed(
    item: LegacyAssetItem,
    residual_matches: int,
    verification: VerificationResult,
) -> bool:
    """R9-5 の三条件を実装から独立に評価した期待値を返す（oracle）.

    Args:
        item: 判定対象の項目。
        residual_matches: 除去確認コマンドの一致件数。
        verification: 非退行判定の結果。

    Returns:
        bool: 「扱いが `除去対象`」「残存一致 0 件」「非退行判定が適合」の 3 条件が
            同時成立する場合のみ True（出典: requirements.md:313、design.md:639）。

    例外:
        送出しない。

    本関数は `scripts/cleanup/completion.py` の定数・分岐を参照せず、
    requirements.md の基準文面のみを根拠に構成する（実装のバグを実装由来の定数で
    見逃さないため）。真偽の判定は同一性比較で行い、暗黙の真偽変換を用いない。
    """
    return (
        item.disposition == _DISPOSITION_REMOVAL_TARGET
        and residual_matches == _EXPECTED_RESIDUAL_MATCHES
        and verification.conformant is True
    )


def _dispositions() -> st.SearchStrategy[str]:
    """`disposition` の値を生成する（R1-3 の 3 値と 3 値以外の双方）.

    Returns:
        SearchStrategy[str]: R1-3 の 3 値、固定の不正値候補、または任意の ASCII
            文字列。

    `除去対象` の生成頻度を確保するため 3 値の抽出候補に当該値を 2 回含める
    （条件 1 が真となる例が生成されない反復ばかりでは双条件の一方を検査できない）。
    """
    return st.one_of(
        st.sampled_from(
            (
                _DISPOSITION_REMOVAL_TARGET,
                _DISPOSITION_REMOVAL_TARGET,
                _DISPOSITION_PRESERVED,
                _DISPOSITION_UNDETERMINED,
            )
        ),
        st.sampled_from(_INVALID_DISPOSITION_FIXTURES),
        st.text(alphabet=string.ascii_letters, min_size=0, max_size=8),
    )


def _residual_matches() -> st.SearchStrategy[int]:
    """残存一致件数を生成する（0 以上の整数。真偽値を含まない）.

    Returns:
        SearchStrategy[int]: 0、代表値、広域の正値の 3 経路を併用した 0 以上の整数。
            R9-5 が数える「除去確認コマンドの一致件数」の入力域である（出典:
            requirements.md:313。本モジュール冒頭の「入力域」）。

    境界値 0（条件 2 が真）の生成頻度を確保するため `st.just(0)` を独立した経路
    として与える。
    """
    return st.one_of(
        st.just(_EXPECTED_RESIDUAL_MATCHES),
        st.sampled_from(_RESIDUAL_FIXTURES),
        st.integers(min_value=0, max_value=10**6),
    )


@st.composite
def _verification_results(draw: st.DrawFn) -> VerificationResult:
    """`VerificationResult` を生成する（適合・不適合の双方）.

    Args:
        draw: Hypothesis の draw 関数。

    Returns:
        VerificationResult: 不変条件 `conformant == (violations == ())` を満たす値。
            C4（`scripts/cleanup/removal_verification.py` の `evaluate`）は
            `conformant = not violations` を保つため、この不変条件は実際の生成元の
            出力空間と一致する（出典: design.md Property 4、DM3
            `VerificationResult`。本モジュール冒頭の「入力域」）。
    """
    violations = tuple(
        draw(
            st.lists(
                st.sampled_from(_VIOLATION_CLAUSES),
                min_size=0,
                max_size=4,
                unique=True,
            )
        )
    )
    # 適合は violations が空であることと同値（出典: design.md Property 4、
    # `scripts/cleanup/removal_verification.py` の `evaluate` の戻り値）。
    return VerificationResult(conformant=not violations, violations=violations)


def _confirmations() -> st.SearchStrategy[Confirmation | None]:
    """`confirmation` の値を生成する（`None` と確認結果ありの双方）.

    Returns:
        SearchStrategy[Confirmation | None]: `None`（未確認）、または非空の
            `evidence_command` を持つ `Confirmation`。

    Property 5 は `confirmation` に依存しないが、DM1 の値域を踏むため双方を与える。
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
    """判定対象の `LegacyAssetItem` を生成する（扱いは 3 値と 3 値以外の双方）.

    Args:
        draw: Hypothesis の draw 関数。

    Returns:
        LegacyAssetItem: `disposition` が R1-3 の 3 値または 3 値以外を取り得る項目。
            他フィールドは Property 5 の判定に影響しないことを確認する目的で任意値を
            与える。
    """
    return LegacyAssetItem(
        key=draw(
            st.text(
                alphabet=string.ascii_letters + string.digits + "_.",
                min_size=1,
                max_size=16,
            )
        ),
        description=draw(st.text(max_size=16)),
        stream=draw(st.sampled_from(_STREAMS)),
        disposition=draw(_dispositions()),
        source_path=draw(_non_blank_text(max_size=24)),
        source_lines=draw(_non_blank_text(max_size=12)),
        detection_command=draw(_non_blank_text(max_size=24)),
        confirmation=draw(_confirmations()),
        removal_check_command=draw(st.one_of(st.none(), _non_blank_text(max_size=24))),
        approver_decision_required=draw(st.booleans()),
    )


class RemovalCompletionProperty(unittest.TestCase):
    """Property 5 のプロパティテストを保持するテストケース."""

    # 反復回数は design.md「Testing Strategy」が求める 100 反復以上とし、扱い 3 値
    # ＋不正値・残存件数の境界・適合／不適合の組合せを十分に踏むため 200 とする。
    # 生成データによる per-example の締切超過による誤検知を避けるため deadline を
    # 無効化する（判定は決定的であり、失敗は握りつぶさない）。
    @settings(max_examples=200, deadline=None)
    @given(
        item=_legacy_asset_items(),
        residual_matches=_residual_matches(),
        verification=_verification_results(),
    )
    def test_is_removed_iff_three_conditions_hold(
        self,
        item: LegacyAssetItem,
        residual_matches: int,
        verification: VerificationResult,
    ) -> None:
        """Feature: legacy-asset-cleanup, Property 5: 除去済み計上の三条件同時成立

        **Validates: Requirements 2.9, 7.10, 9.5**

        *For any* Legacy_Asset_Item・任意の残存一致件数・任意の VerificationResult
        の組について、`is_removed` が真を返すことが「`disposition` が `除去対象`」
        「残存一致件数が 0」「VerificationResult が適合」の 3 条件の同時成立と同値
        （双条件）であることを検証する。
        """
        expected = _expected_is_removed(item, residual_matches, verification)

        # 検証対象の実行（生成器は R9-5 の三条件が張る入力域から値を引く。本モジュール
        # 冒頭の「入力域」）。
        actual = is_removed(item, residual_matches, verification)

        # 3 条件の真偽組合せの被覆状況を Hypothesis の統計へ記録する（8 通りの被覆
        # 自体は `test_all_eight_condition_combinations` が決定的に検査する）。
        event(
            "conditions="
            f"{item.disposition == _DISPOSITION_REMOVAL_TARGET:d}"
            f"{residual_matches == _EXPECTED_RESIDUAL_MATCHES:d}"
            f"{verification.conformant is True:d}"
        )

        # 戻り値は真偽値でなければならない（暗黙の真偽変換で比較を通さない）。
        self.assertIsInstance(
            actual,
            bool,
            msg=f"is_removed の戻り値が bool ではない: {actual!r}",
        )
        self.assertIs(
            actual,
            expected,
            msg=(
                "is_removed が三条件の同時成立と一致しない: "
                f"disposition={item.disposition!r}, "
                f"residual_matches={residual_matches!r}, "
                f"conformant={verification.conformant!r}, "
                f"violations={verification.violations!r}, "
                f"expected={expected!r}, actual={actual!r}"
            ),
        )

    def test_all_eight_condition_combinations(self) -> None:
        """三条件の真偽 8 通りすべてで判定が期待と一致することを決定的に検査する.

        **Validates: Requirements 2.9, 7.10, 9.5**

        各条件を独立に偽化した組合せ（2^3 = 8 通り）を列挙し、`is_removed` が
        oracle と一致すること、および真となるのが 3 条件すべて真の場合に限ること
        （双条件の右向き含意）を検証する。残存一致件数は偽側で 1 件および 1 件超の
        双方を用いる（境界 0/1 と大きい値の被覆。出典: requirements.md:313）。
        """
        # 条件 1 を偽にする値: R1-3 の 3 値のうち `除去対象` 以外、および 3 値以外
        # （値域の検証は inventory.validate_item の責務。本モジュール冒頭の「入力域」）。
        false_dispositions = (
            _DISPOSITION_PRESERVED,
            _DISPOSITION_UNDETERMINED,
            "Undetermined",
        )
        # 条件 2 を偽にする値: 1 件（境界）および 1 件超。
        false_residuals = (1, 42)
        # 条件 3 の真値・偽値（いずれも C4 の出力空間に一致する組合せ）。
        conformant = VerificationResult(conformant=True, violations=())
        non_conformant = VerificationResult(conformant=False, violations=("R2-1",))

        # 真と判定された組合せの件数。3 条件すべて真の 1 件のみとなること（真側の
        # 生成値も 1 通りずつ）を後段で検査する。
        true_count = 0
        for condition_1 in (True, False):
            for condition_2 in (True, False):
                for condition_3 in (True, False):
                    dispositions = (
                        (_DISPOSITION_REMOVAL_TARGET,)
                        if condition_1
                        else false_dispositions
                    )
                    residuals = (
                        (_EXPECTED_RESIDUAL_MATCHES,)
                        if condition_2
                        else false_residuals
                    )
                    verification = conformant if condition_3 else non_conformant
                    expected = condition_1 and condition_2 and condition_3

                    for disposition in dispositions:
                        for residual in residuals:
                            item = _fixed_item(disposition)
                            # oracle との二重確認（列挙した期待値が oracle と乖離
                            # していないことを検査し、期待値の誤りを握りつぶさない）。
                            self.assertIs(
                                _expected_is_removed(item, residual, verification),
                                expected,
                                msg=(
                                    "列挙した期待値が oracle と一致しない: "
                                    f"disposition={disposition!r}, "
                                    f"residual_matches={residual!r}, "
                                    f"verification={verification!r}"
                                ),
                            )
                            with self.subTest(
                                disposition=disposition,
                                residual_matches=residual,
                                conformant=verification.conformant,
                            ):
                                self.assertIs(
                                    is_removed(item, residual, verification),
                                    expected,
                                    msg=(
                                        "三条件の組合せに対する判定が期待と一致しない: "
                                        f"disposition={disposition!r}, "
                                        f"residual_matches={residual!r}, "
                                        f"verification={verification!r}"
                                    ),
                                )
                            if expected:
                                true_count += 1

        self.assertEqual(
            true_count,
            1,
            msg=f"真と判定された組合せ件数が 1 件ではない: {true_count}",
        )


if __name__ == "__main__":
    # 単体実行用エントリ（`python -m unittest` による探索でも実行可能）。
    unittest.main()
