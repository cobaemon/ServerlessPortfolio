"""Property 7（依存除去判定の規則順序と判定根拠）のプロパティテスト.

Feature: legacy-asset-cleanup, Property 7: *For any* DependencyCandidate について、Dependency_Audit は次の規則を上から順に評価し、最初に一致した規則で判定を確定する（C10 の「判定規則」と同順）。1. `direct_reference_sources` が非空（直接参照あり）→ `保持`。判定根拠に一致箇所を記録する。2. 規則 1 に一致せず、`transitive_checked` が真かつ `required_by` が非空 → `保持`。判定根拠に要求元パッケージ名を記録する。3. 規則 1〜2 に一致せず、`transitive_checked` が偽 → `undetermined`。4. 規則 1〜3 に一致せず（`transitive_checked` 真かつ `required_by` 空）、`direct_reference_checked` が偽 → `undetermined`。5. 規則 1〜4 のいずれにも一致しない → `除去対象`。上記 5 規則は排他かつ網羅であり、いかなる組合せに対しても結論は一意に定まる。

本モジュールは design.md「Correctness Properties > Property 7」および tasks.md 4.2 を
検証する（出典: `.kiro/specs/legacy-asset-cleanup/design.md`「Property 7: 依存除去判定の
規則順序と判定根拠」、同 tasks.md「4.2 依存除去判定のプロパティテストを書く」、
同 design.md「Testing Strategy」のプロパティ対応表
`Property 7 | tests/cleanup/test_property_dependency_decision.py`）。

**Validates: Requirements 7.1, 7.3, 7.4, 7.5, 1.6**

    - R7-1: ある dependency が Direct_Dependency として参照されるかを `git grep`
      により確認し、結果を出典付きで記録する（出典: requirements.md Requirement 7
      基準 1）。本テストでは確認実施状態
      （`DependencyCandidate.direct_reference_checked`）と一致箇所
      （`direct_reference_sources`）が判定へ反映されることを検証する。
    - R7-3: Transitive_Dependency として要求されることが確認された場合、当該
      dependency を Dependency_Manifest に保持し、Transitive_Dependency である旨と
      要求元パッケージ名を記録する（同基準 3）。
    - R7-4: Transitive_Dependency としての要求有無が確認されていない場合、扱いを
      `undetermined` と記録し除去を保留する（同基準 4）。
    - R7-5: Direct_Dependency としても Transitive_Dependency としても要求されない
      ことが確認された時、当該 dependency の行を Dependency_Manifest から除去する
      （同基準 5。すなわち判定は `除去対象`）。

検証対象（tasks.md 4.1 実装、design.md C10）:
    - `scripts/cleanup/dependency_audit.py` の
      `decide(candidate: DependencyCandidate) -> DependencyDecision`。

検証する内容（決定表全域を独立オラクルで検査する）:
    1. `除去対象` となるのは「両確認が実施済みかつ双方の結果集合が空」の場合に
       限る（Property 7 前半の「限る」＝双条件）。
    2. 直接参照の一致が 1 件以上、または要求元が 1 件以上のとき `保持` となる。
       要求元により `保持` が決まる領域では、判定根拠へ全要求元パッケージ名が
       含まれる（R7-3）。
    3. 残余領域（規則 3・規則 4。いずれかの確認が未実施で、かつ確認結果が 0 件）
       では `undetermined` となる（R7-4、R1-6）。
    オラクルは実装の分岐を写さず、`(直接参照あり, 要求元あり, 直接確認済み,
    推移確認済み)` の 4 ビット組から期待値を引く**明示的決定表**
    （`_DECISION_TABLE`）として本モジュール内に独立定義する。

判定規則の適用に関する設計上の根拠（出典: design.md Property 7、同 C10「判定規則」）:
    - **規則の評価順序が Property 7 の一部である**: design.md Property 7 は 5 規則を
      「上から順に評価し、最初に一致した規則で判定を確定する」と定め、5 規則が排他かつ
      網羅であること、およびいかなる組合せに対しても結論が一意に定まることを明記する。
      したがって `required_by` が非空かつ `direct_reference_checked` が偽である領域は
      規則 2 で `保持` に確定する（`_DECISION_TABLE` の `(False, True, False, True)`
      行）。
    - **判定根拠に要求元名を要求する領域は規則 2 に限る**: design.md Property 7 は
      「要求元パッケージ名が判定根拠に記録されるのは規則 2 の領域（
      `direct_reference_sources` が空かつ `transitive_checked` 真かつ `required_by` が
      非空）に限る」と定め、規則 1 の領域（直接参照あり、かつ `required_by` も非空と
      なる重複領域）の判定根拠に要求元名が含まれることを要求しない。本テストは
      `_REQUIRED_BY_DRIVEN_KEYS`（規則 2 の領域）に限って要求元名の包含を検査する。
    - `DISPOSITION_RETAINED` は R1-3 の扱い 3 値に含まれない依存判定固有の値である
      （出典: `scripts/cleanup/dependency_audit.py` の `DISPOSITION_RETAINED`
      コメント）。

入力域（生成器が引く範囲）:
    DM5 の `DependencyCandidate` は確認の実施状態（`direct_reference_checked` /
    `transitive_checked`）と確認結果（`direct_reference_sources` / `required_by`）を
    別のフィールドとして保持する。未実施の確認に結果が存在する組は事実として矛盾する
    ため（R7-1 / R7-2 が定める確認の実施と記録の関係。出典: requirements.md:277、:278）、
    生成器は確認が未実施の側の結果集合を空タプルに固定し、当該組を生成しない。
    したがって `_DECISION_TABLE` は矛盾のない 9 通りの組合せのみを保持する。

ライセンス注記（第二原則6・要ライセンス確認）:
    - Hypothesis は Mozilla Public License 2.0（MPL-2.0）で配布される（出典:
      `requirements-dev.txt:18` の `hypothesis==6.158.0` および同ファイル 6-13 行の
      ライセンス注記、公式リポジトリ LICENSE.txt）。開発・テスト時のみ使用し、
      改変せず Lambda 配布物へ同梱しないため、MPL-2.0 のソース開示義務の実務的
      対象外である（非配布・非改変）。

テスト方針（出典: design.md「Testing Strategy」、既存前例
`portfolio/tests/test_property_csp_allowlist.py`、兄弟テスト
`tests/cleanup/test_property_removal_plan.py`）:
    - 単一プロパティを 1 テストで実装し、`@settings(max_examples=...)` は design.md
      が求める 100 反復以上とする。
    - 検証対象 `scripts/cleanup/dependency_audit.py` は Django 非依存であるため
      Django のセットアップを行わない。
    - 扱い語彙は実装の定数を import して用いる（tasks.md 4.2 の指示）。ただし
      定数値そのものが requirements.md / design.md の文面と一致することを
      別テストで固定し、定数の取り違えを実装由来の値で見逃さないようにする。
    - フォールバック禁止: 期待を明示アサートし、差異を握りつぶさない。

実行コマンド（プロジェクトルートから）:
    $env:DJANGO_SETTINGS_MODULE="config.settings.dev"; python manage.py test tests.cleanup.test_property_dependency_decision
  もしくは（Django 非ロードでも実行可能）:
    python -m unittest tests.cleanup.test_property_dependency_decision -v
"""

from __future__ import annotations

import dataclasses
import string
import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

# 検証対象（tasks.md 4.1 実装、design.md C10）と扱い語彙の定数。
from scripts.cleanup.dependency_audit import (
    DISPOSITION_RETAINED,
    JUDGEMENT_TARGET_DEPENDENCIES,
    decide,
)
from scripts.cleanup.inventory import (
    DISPOSITION_REMOVAL_TARGET,
    DISPOSITION_UNDETERMINED,
)
from scripts.cleanup.models import DependencyCandidate, DependencyDecision

# ---------------------------------------------------------------------------
# 独立オラクル: 判定の決定表（実装の分岐を写さない）
# ---------------------------------------------------------------------------

# 決定表のキーは 4 ビット組
#   (直接参照の一致が 1 件以上, 要求元が 1 件以上, 直接参照の確認実施済み,
#    推移要求の確認実施済み)
# であり、値は design.md Property 7 の 5 規則を上から順に評価して得られる扱い
# である。各行にどの規則で確定するかを示す。未実施の確認に結果が存在する組合せ
# （確認済みフラグが偽なのに結果集合が非空）は事実として矛盾するため表に含めない
# （本モジュール冒頭の「入力域」を参照）。
_DECISION_TABLE: dict[tuple[bool, bool, bool, bool], str] = {
    # --- 直接参照なし・要求元なし ---
    # 規則 5: 両確認が実施済みで双方 0 件のときに限り除去対象（R7-5）。
    (False, False, True, True): DISPOSITION_REMOVAL_TARGET,
    # 規則 3: 推移要求の確認が未実施（R7-4）。
    (False, False, True, False): DISPOSITION_UNDETERMINED,
    # 規則 4: 推移要求は確認済みで要求元 0 件だが、直接参照の確認が未実施（R7-5 の
    # 除去要件のうち Direct_Dependency 側が未成立。R1-6）。
    (False, False, False, True): DISPOSITION_UNDETERMINED,
    # 規則 3: 推移要求の確認が未実施（R7-4）。
    (False, False, False, False): DISPOSITION_UNDETERMINED,
    # --- 直接参照なし・要求元あり（規則 2 の領域。R7-3） ---
    (False, True, True, True): DISPOSITION_RETAINED,
    # 規則 2 は直接参照の確認状態を条件に含めないため、未実施でも結論は保持
    # （出典: design.md Property 7 規則 2、C10「判定規則」）。
    (False, True, False, True): DISPOSITION_RETAINED,
    # --- 直接参照あり（規則 1 の領域。R7-1 の確認結果により保持） ---
    (True, False, True, True): DISPOSITION_RETAINED,
    (True, False, True, False): DISPOSITION_RETAINED,
    # --- 直接参照あり・要求元あり（規則 1 の重複領域。判定根拠への要求元名の記録は
    #     Property 7 が要求しない。冒頭参照） ---
    (True, True, True, True): DISPOSITION_RETAINED,
}

# 規則 2 の領域（判定根拠へ全要求元名の記録を要求する領域。R7-3）。直接参照の一致が
# 0 件かつ推移要求の確認済みかつ要求元が 1 件以上の組合せ（出典: design.md
# Property 7「要求元パッケージ名が判定根拠に記録されるのは規則 2 の領域に限る」）。
_REQUIRED_BY_DRIVEN_KEYS: frozenset[tuple[bool, bool, bool, bool]] = frozenset({
    (False, True, True, True),
    (False, True, False, True),
})

# ---------------------------------------------------------------------------
# 生成器の値域（DM5 の `DependencyCandidate` の各フィールド）
# ---------------------------------------------------------------------------

# marker の値域（出典: design.md「実行環境の差異（系統 D の設計制約）」、
# `requirements.txt` の marker 付き 5 件、`scripts/cleanup/models.py` の
# `DependencyCandidate.marker` docstring）。判定は marker に依存しない。
_MARKERS: tuple[str | None, ...] = (None, "sys_platform != 'win32'")

# 解決環境の 2 値（出典: `scripts/cleanup/models.py` の
# `DependencyCandidate.resolution_environment` docstring、design.md
# 「実行環境の差異」）。
_RESOLUTION_ENVIRONMENTS: tuple[str, ...] = ("windows-venv", "docker-python312")

# 判定対象集合（R7-11）に含まれない dependency 名の固定候補。判定が集合の所属に
# 依存しないこと（`decide` docstring「本集合に含まれるか否かで振る舞いを変えない」）
# を検査するために用いる。`whitenoise` は `requirements.txt:41` に存在するが
# 判定対象 12 件には含まれない（出典: requirements.md Requirement 7 基準 6・11）。
_NON_TARGET_NAMES: tuple[str, ...] = (
    "whitenoise",
    "django",
    "sqlparse",
    "pillow",
)

# 判定対象集合の要素（決定的な順序で扱うため昇順のタプルへ変換する）。
_TARGET_NAMES: tuple[str, ...] = tuple(sorted(JUDGEMENT_TARGET_DEPENDENCIES))

# 要求元パッケージ名の固定候補（実在の要求関係に近い値を含める）。判定根拠への
# 包含検査を行うため、区切り文字（`", "`）と紛れない文字のみで構成する。
_REQUIRING_PACKAGE_NAMES: tuple[str, ...] = (
    "uvicorn",
    "django-allauth",
    "qrcode",
    "requests",
    "cryptography",
)

# 直接参照の一致箇所の固定候補（`git grep -n` 出力形式に倣う）。
_DIRECT_REFERENCE_SOURCES: tuple[str, ...] = (
    "asgi_lambda.py:6",
    "config/settings/base.py:44",
    "portfolio/forms.py:84",
    "buildspec.yml:257",
)


def _package_names() -> st.SearchStrategy[str]:
    """dependency 名を生成する（判定対象集合の内外を双方含む）.

    Returns:
        SearchStrategy[str]: 判定対象 12 件のいずれか、対象外の固定候補、または
            英小文字・数字・ハイフンから成る非空文字列。
    """
    return st.one_of(
        st.sampled_from(_TARGET_NAMES),
        st.sampled_from(_NON_TARGET_NAMES),
        st.text(
            alphabet=string.ascii_lowercase + string.digits + "-",
            min_size=1,
            max_size=12,
        ),
    )


@st.composite
def _candidates(draw: st.DrawFn) -> DependencyCandidate:
    """矛盾のない `DependencyCandidate` を生成する（決定表の全行を踏み得る）.

    Args:
        draw: Hypothesis の draw 関数。

    Returns:
        DependencyCandidate: 確認実施状態と確認結果が矛盾しない候補。確認が
            未実施（フラグが偽）の側の結果集合は必ず空タプルとする（本モジュール
            冒頭の「入力域」を参照）。確認済みの側は 0 件と 1 件以上の双方を生成
            する。
    """
    direct_checked = draw(st.booleans())
    transitive_checked = draw(st.booleans())

    # 確認済みの側のみ結果集合が非空となり得る（未実施の側は空タプル固定）。
    direct_sources: tuple[str, ...] = ()
    if direct_checked:
        direct_sources = tuple(
            draw(
                st.lists(
                    st.sampled_from(_DIRECT_REFERENCE_SOURCES),
                    min_size=0,
                    max_size=3,
                    unique=True,
                )
            )
        )

    required_by: tuple[str, ...] = ()
    if transitive_checked:
        required_by = tuple(
            draw(
                st.lists(
                    st.sampled_from(_REQUIRING_PACKAGE_NAMES),
                    min_size=0,
                    max_size=3,
                    unique=True,
                )
            )
        )

    return DependencyCandidate(
        name=draw(_package_names()),
        manifest_line=draw(st.integers(min_value=1, max_value=60)),
        marker=draw(st.sampled_from(_MARKERS)),
        direct_reference_checked=direct_checked,
        direct_reference_sources=direct_sources,
        transitive_checked=transitive_checked,
        required_by=required_by,
        resolution_environment=draw(st.sampled_from(_RESOLUTION_ENVIRONMENTS)),
    )


def _table_key(candidate: DependencyCandidate) -> tuple[bool, bool, bool, bool]:
    """候補から決定表のキー（4 ビット組）を作る.

    Args:
        candidate: 判定対象の候補。

    Returns:
        tuple[bool, bool, bool, bool]: (直接参照の一致が 1 件以上, 要求元が 1 件
            以上, 直接参照の確認実施済み, 推移要求の確認実施済み)。

    例外:
        送出しない。
    """
    return (
        bool(candidate.direct_reference_sources),
        bool(candidate.required_by),
        candidate.direct_reference_checked,
        candidate.transitive_checked,
    )


def _alternative_name(name: str) -> str:
    """判定対象集合の所属を反転させた別名を返す（所属非依存性の検査用）.

    Args:
        name: 元の dependency 名。

    Returns:
        str: 元の名前が判定対象集合（R7-11）に含まれる場合は対象外の名前、
            含まれない場合は対象の名前。

    例外:
        送出しない。
    """
    if name in JUDGEMENT_TARGET_DEPENDENCIES:
        # 対象外の固定候補のうち、判定対象集合に含まれないことが確実な値を返す。
        return _NON_TARGET_NAMES[0]
    return _TARGET_NAMES[0]


class DependencyDecisionProperty(unittest.TestCase):
    """Property 7 のプロパティテストを保持するテストケース."""

    def test_disposition_vocabulary_matches_specification(self) -> None:
        """扱い語彙の定数が requirements.md / design.md の文面と一致することを固定する.

        実装の定数を import して期待値に用いるため（tasks.md 4.2 の指示）、定数
        自体の取り違えを検出できるよう、文面の literal を本テストで固定する
        （出典: requirements.md Requirement 1 基準 3、design.md C10「判定規則」、
        同 Property 7 本文）。
        """
        self.assertEqual(DISPOSITION_REMOVAL_TARGET, "除去対象")
        self.assertEqual(DISPOSITION_RETAINED, "保持")
        self.assertEqual(DISPOSITION_UNDETERMINED, "undetermined")

    # 反復回数は design.md「Testing Strategy」が求める 100 反復以上とし、決定表
    # 9 行 × marker 2 値 × 解決環境 2 値 × 名前の所属 2 通りを十分に踏むため 300 と
    # する。生成データによる per-example の締切超過による誤検知を避けるため
    # deadline を無効化する（判定は決定的であり、失敗は握りつぶさない）。
    @settings(max_examples=300, deadline=None)
    @given(candidate=_candidates())
    def test_decide_matches_decision_table(
        self, candidate: DependencyCandidate
    ) -> None:
        """Feature: legacy-asset-cleanup, Property 7: 依存除去判定の規則順序と判定根拠

        **Validates: Requirements 7.1, 7.3, 7.4, 7.5, 1.6**

        *For any* DependencyCandidate について、`decide` の判定が独立オラクル
        （`_DECISION_TABLE`）と一致すること、すなわち (1) 規則 1（直接参照あり）
        および規則 2（推移要求確認済みで要求元あり）の領域では `保持` であり、
        規則 2 の領域では判定根拠へ全要求元名が含まれ（R7-1、R7-3）、(2) 規則 3・
        規則 4 の領域（いずれかの確認が未実施）では `undetermined` であり（R7-4、
        R1-6）、(3) `除去対象` となるのは規則 5 の領域（両確認が実施済みで双方
        0 件）に限る（R7-5）ことを検証する。あわせて判定が判定対象集合（R7-11）への
        所属に依存しないことを検証する。
        """
        key = _table_key(candidate)

        # 生成器が矛盾入力を作っていないこと（決定表に存在するキーであること）。
        self.assertIn(
            key,
            _DECISION_TABLE,
            msg=(
                "生成器が決定表に存在しない組合せを生成した（矛盾入力の可能性）: "
                f"key={key!r}, candidate={candidate!r}"
            ),
        )
        expected = _DECISION_TABLE[key]

        decision = decide(candidate)

        # 戻り値型（出典: design.md DM5、`scripts/cleanup/models.py`）。
        self.assertIsInstance(
            decision,
            DependencyDecision,
            msg=f"decide の戻り値が DependencyDecision ではない: {decision!r}",
        )

        # ---- (1)(2)(3) 決定表との一致（Property 7 全域） ----
        self.assertEqual(
            decision.disposition,
            expected,
            msg=(
                "判定が決定表と一致しない: "
                f"key=(direct_sources={key[0]}, required_by={key[1]}, "
                f"direct_checked={key[2]}, transitive_checked={key[3]}), "
                f"expected={expected!r}, actual={decision.disposition!r}, "
                f"reason={decision.reason!r}, candidate={candidate!r}"
            ),
        )

        # 判定結果は対象名を保持する（記録の追跡可能性。R7-1、R7-3 の記録要件）。
        self.assertEqual(
            decision.name,
            candidate.name,
            msg=(
                "判定結果の name が候補の name と一致しない: "
                f"decision={decision!r}, candidate={candidate!r}"
            ),
        )

        # 判定根拠は常に非空である（判定根拠の記録要件。R7-1〜R7-5 の「記録する」）。
        self.assertNotEqual(
            decision.reason.strip(),
            "",
            msg=f"判定根拠が空である: decision={decision!r}, candidate={candidate!r}",
        )

        # ---- (2) 要求元により保持が決まる領域では全要求元名を判定根拠へ含める（R7-3） ----
        if key in _REQUIRED_BY_DRIVEN_KEYS:
            for requiring_name in candidate.required_by:
                self.assertIn(
                    requiring_name,
                    decision.reason,
                    msg=(
                        "保持の判定根拠に要求元パッケージ名が含まれない（R7-3 違反）: "
                        f"missing={requiring_name!r}, reason={decision.reason!r}, "
                        f"required_by={candidate.required_by!r}"
                    ),
                )

        # ---- 判定は判定対象集合（R7-11）への所属に依存しない ----
        # 名前のみを差し替えた候補で再判定し、扱いが変わらないことを確認する。R7-11 は
        # 判定対象の集合を定めるだけであり、集合への所属によって扱いを変えることを
        # 求めていない（出典: requirements.md:286）。判定根拠の文字列そのものは
        # Property 7 が規則 2 の領域における要求元名の記録以外を規定しないため比較
        # しない。
        renamed = dataclasses.replace(
            candidate, name=_alternative_name(candidate.name)
        )
        renamed_decision = decide(renamed)
        self.assertEqual(
            renamed_decision.disposition,
            decision.disposition,
            msg=(
                "判定が判定対象集合への所属に依存している: "
                f"original={decision!r}, renamed={renamed_decision!r}, "
                f"candidate={candidate!r}"
            ),
        )


if __name__ == "__main__":
    # 単体実行用エントリ（`python -m unittest` による探索でも実行可能）。
    unittest.main()
