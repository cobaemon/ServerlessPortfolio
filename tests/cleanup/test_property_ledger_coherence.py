"""Property 8（Dependency_Manifest と License_Ledger の集合一致）のプロパティテスト.

Feature: legacy-asset-cleanup, Property 8: *For any* Dependency_Manifest の記載名集合と License_Ledger の記載名集合の組について、Dependency_Audit が整合と判定するのは、大文字小文字とハイフン／アンダースコアを正規化した両集合が完全に一致する場合に限り、不一致のときは差分がどちらの側にあるかが列挙される。

本モジュールは design.md「Correctness Properties > Property 8」および tasks.md 4.3 を
検証する（出典: `.kiro/specs/legacy-asset-cleanup/design.md:655-658`、
同 tasks.md「4.3 台帳整合のプロパティテストを書く」、
同 design.md「Testing Strategy」のプロパティ対応表
`Property 8 | tests/cleanup/test_property_ledger_coherence.py`（design.md:742））。

**Validates: Requirements 7.7**

    - R7-7: Dependency_Manifest から dependency を除去した時、License_Ledger
      (`docs/external-assets.md`) から当該 dependency の行を除去し、
      Dependency_Manifest の記載集合と License_Ledger の記載集合を一致させる
      （出典: `.kiro/specs/legacy-asset-cleanup/requirements.md:282` Requirement 7
      基準 7）。本テストは「一致しているか」の**判定側**（design.md C10 の
      `check_ledger_coherence`）を検証する。実ファイルの編集は tasks.md 12.2 の
      範囲であり本モジュールの対象外である。

検証対象（tasks.md 4.1 実装、design.md C10）:
    - `scripts/cleanup/dependency_audit.py` の
      `check_ledger_coherence(manifest_names, ledger_names) -> LedgerCoherenceReport`
    - 同モジュールの `normalize_package_name(name) -> str`（例示テストでのみ直接
      呼び出す。プロパティテストでは独立オラクルを用いる。後述）

検証する内容（Property 8 は双条件＋列挙要件の 2 部構成）:
    1. **双条件**: `coherent` が真であるのは、正規化後の両集合が完全一致する場合に
       限る（必要十分）。
    2. **列挙**: 不一致のとき、`manifest_only` が「正規化後 manifest − 正規化後
       ledger」、`ledger_only` が「正規化後 ledger − 正規化後 manifest」と集合として
       一致する。差分がどちらの側にあるかが判別できる。

検証しない事項（受入基準・Property 8 が規定しないため対象外とする）:
    - `manifest_only` / `ledger_only` の列挙順序と重複の有無。design.md DM5 は両者を
      `tuple[str, ...]` として宣言するのみで順序を規定せず、Property 8 も「差分が
      どちらの側にあるかが列挙される」ことのみを定める（出典: design.md DM5
      `LedgerCoherenceReport`、同 Property 8 本文）。したがって本モジュールは両者を
      集合として比較する。
    - design.md C10 が挙げる 2 変換（小文字化、ハイフン／アンダースコアの統一）以外の
      変換が行われないこと。C10 は行う変換を挙げるが、それ以外の変換を行わないことを
      閉じた形で定めていないため、変換の不在は受入基準として検証しない。

独立オラクル（実装のバグを実装由来の関数で見逃さないため。第一原則1・2）:
    正規化の期待値は `normalize_package_name` を呼ばず、本モジュール内の
    `_normalize_expected`（小文字化と `_` → `-` 置換のみ）で独立に算出する。
    したがって正規化そのものの欠陥（変換漏れ・過剰変換）も検出できる。

入力域（Property 8 と design.md C10 が定める範囲）:
    - 正規化は design.md C10 が挙げる 2 変換（小文字化、ハイフン／アンダースコアの
      統一）である（出典: design.md C10「正規化」、同 Property 8 本文「大文字小文字と
      ハイフン／アンダースコアを正規化した両集合」）。本モジュールの生成器は当該
      2 変換で同一へ写る表記差のみを与える。
    - `manifest_only` / `ledger_only` は**正規化後**の表記を保持する。複数の元表記が
      同一の正規化名へ写り得るため元表記は一意に復元できない（出典: Property 8 が
      正規化後の集合について差分を述べていること、`scripts/cleanup/
      dependency_audit.py` の `check_ledger_coherence` docstring）。
    - `coherent` は両差分がともに空のときに限り真である（Property 8 の双条件）。
    - `check_ledger_coherence` は例外を送出しない（出典: 同 docstring「例外:
      送出しない（差分は戻り値で表現する）」）。

実体で確認した表記差（本テストが例示として固定検証する事実。第一原則3）:
    - `requirements.txt:27` は `pyjwt`、`docs/external-assets.md:43` は `PyJWT`
      （design.md C10 が挙げる差異。両ファイルの実体で行番号・表記を確認済み）。
    - `requirements.txt:10` は `django`、`docs/external-assets.md:26` は `Django`
      （tasks.md 4.1 実施時に追加確認された同種の差異。両ファイルの実体で
      行番号・表記を確認済み）。

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
    - 生成器は次の全経路を踏む: 同一集合、素な集合、部分重複、大文字小文字のみの
      差、アンダースコア／ハイフンのみの差、複数の異表記が同一正規化名へ畳み込ま
      れる場合（畳み込みの取り扱いを検証する重要経路）。
    - フォールバック禁止: 期待を明示アサートし、差異を握りつぶさない。

実行コマンド（プロジェクトルートから）:
    $env:DJANGO_SETTINGS_MODULE="config.settings.dev"; python manage.py test tests.cleanup.test_property_ledger_coherence
  もしくは（Django 非ロードでも実行可能）:
    python -m unittest tests.cleanup.test_property_ledger_coherence -v
"""

from __future__ import annotations

import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

# 検証対象（tasks.md 4.1 実装、design.md C10）と戻り値型（design.md DM5）。
from scripts.cleanup.dependency_audit import (
    check_ledger_coherence,
    normalize_package_name,
)
from scripts.cleanup.models import LedgerCoherenceReport

# ---------------------------------------------------------------------------
# 生成器の素材（すべて正規化の不動点。すなわち `_normalize_expected` を適用しても
# 変化しない表記であり、変異させた各表記が確実に元の名前へ写ることを保証する）
# ---------------------------------------------------------------------------

# 実在するパッケージ名（出典: `requirements.txt`。`django`:10、`django-allauth`:11、
# `django-otp`:14、`mangum`:20、`pillow-avif-plugin`:24、`psycopg2-binary`:25、
# `pyjwt`:27、`python-dateutil`:28、`whitenoise`:41）を素材とする。いずれも
# `_normalize_expected` の不動点であり、変異させた各表記が確実に元の名前へ写る。
_NORMALIZED_NAME_POOL: tuple[str, ...] = (
    "django",
    "django-allauth",
    "django-otp",
    "mangum",
    "pillow-avif-plugin",
    "psycopg2-binary",
    "pyjwt",
    "python-dateutil",
    "whitenoise",
)


def _normalize_expected(name: str) -> str:
    """期待値算出用の独立した正規化オラクル（実装関数を呼ばない）.

    引数:
        name: 正規化前のパッケージ名。

    戻り値:
        小文字化し、アンダースコア（`_`）をハイフン（`-`）へ置換した名前。

    例外:
        送出しない。

    design.md C10「正規化」が定める 2 変換（小文字化、ハイフン／アンダースコアの
    統一）のみを実装する。`scripts.cleanup.dependency_audit.normalize_package_name`
    を呼び出さないため、実装側の正規化に欠陥がある場合も検出できる（第一原則1・2）。
    """
    return name.lower().replace("_", "-")


def _normalized_set(names: frozenset[str]) -> frozenset[str]:
    """名前集合を独立オラクルで正規化した集合を返す.

    引数:
        names: 正規化前の名前集合。

    戻り値:
        正規化後の名前集合（複数の元表記が同一へ畳み込まれ得る）。

    例外:
        送出しない。
    """
    return frozenset(_normalize_expected(name) for name in names)


@st.composite
def _spellings(draw: st.DrawFn, base: str) -> str:
    """正規化すると `base` へ一致する表記を 1 件生成する.

    引数:
        draw: Hypothesis の draw 関数。
        base: 正規化の不動点である基準名（`_NORMALIZED_NAME_POOL` の要素）。

    戻り値:
        `base` の各英字を任意に大文字化し、各ハイフンを任意にアンダースコアへ
        置換した表記。`_normalize_expected` を適用すると `base` に一致する。

    例外:
        送出しない。

    1 文字ごとに変異の有無を draw するため、同一 `base` から「表記が完全一致する
    場合」「大文字小文字のみ異なる場合」「アンダースコア／ハイフンのみ異なる場合」
    「両方が異なる場合」のすべてが生成される。
    """
    characters: list[str] = []
    for character in base:
        if character == "-" and draw(st.booleans()):
            # ハイフン／アンダースコアのみの差を作る経路。
            characters.append("_")
        elif character.isalpha() and draw(st.booleans()):
            # 大文字小文字のみの差を作る経路（`PyJWT` / `pyjwt` に相当）。
            characters.append(character.upper())
        else:
            characters.append(character)
    return "".join(characters)


@st.composite
def _ledger_scenarios(draw: st.DrawFn) -> tuple[frozenset[str], frozenset[str]]:
    """Dependency_Manifest 側と License_Ledger 側の記載名集合の組を生成する.

    引数:
        draw: Hypothesis の draw 関数。

    戻り値:
        `(manifest_names, ledger_names)` の組。

    例外:
        送出しない。

    生成経路（Property 8 の双条件と列挙要件の双方を検査するため、以下を網羅する）:
        - 基準名ごとに掲載側を `both` / `manifest` / `ledger` から選ぶことで、
          同一集合・素な集合・部分重複のいずれもが生成される。
        - `both` の場合は両側で独立に表記を変異させるため、実体が一致していても
          表記が異なる入力（`Django` / `django`、`pillow_avif_plugin` /
          `pillow-avif-plugin`）が生成される。
        - 1 つの基準名から最大 3 件の異表記を同一側へ与えるため、複数の元表記が
          同一の正規化名へ畳み込まれる入力が生成される（畳み込みの取り扱いを
          検証する重要経路）。
        - 最後に一定割合で ledger 側を manifest 側と同一の集合へ置き換え、
          両集合が文字列レベルで完全一致する境界も踏む。
        - 空集合（両側 0 件）も許容する（差分なしかつ一致の境界）。
    """
    bases = draw(
        st.lists(
            st.sampled_from(_NORMALIZED_NAME_POOL),
            min_size=0,
            max_size=6,
            unique=True,
        )
    )

    manifest: set[str] = set()
    ledger: set[str] = set()
    for base in bases:
        side = draw(st.sampled_from(("both", "both", "manifest", "ledger")))
        if side in ("both", "manifest"):
            for _ in range(draw(st.integers(min_value=1, max_value=3))):
                manifest.add(draw(_spellings(base)))
        if side in ("both", "ledger"):
            for _ in range(draw(st.integers(min_value=1, max_value=3))):
                ledger.add(draw(_spellings(base)))

    # 文字列レベルで完全一致する経路（4 回に 1 回程度）。
    if draw(st.sampled_from((False, False, False, True))):
        ledger = set(manifest)

    return frozenset(manifest), frozenset(ledger)


class LedgerCoherenceProperty(unittest.TestCase):
    """Property 8 のプロパティテストと実体表記差の例示テストを保持するテストケース."""

    # 反復回数は design.md「Testing Strategy」が求める 100 反復以上とし、
    # 掲載側 3 通り × 表記変異 × 畳み込み件数の組合せを十分に踏むため 300 とする。
    # 生成データによる per-example の締切超過による誤検知を避けるため deadline を
    # 無効化する（判定は決定的であり、失敗は握りつぶさない）。
    @settings(max_examples=300, deadline=None)
    @given(scenario=_ledger_scenarios())
    def test_coherent_iff_normalized_sets_match_and_differences_are_enumerated(
        self, scenario: tuple[frozenset[str], frozenset[str]]
    ) -> None:
        """Feature: legacy-asset-cleanup, Property 8: Dependency_Manifest と License_Ledger の集合一致

        **Validates: Requirements 7.7**

        *For any* Dependency_Manifest の記載名集合と License_Ledger の記載名集合の
        組について、`check_ledger_coherence` が整合と判定するのは、独立オラクルで
        正規化した両集合が完全に一致する場合に限り（双条件）、不一致のときは差分が
        どちらの側にあるかが `manifest_only` / `ledger_only` へ列挙されること
        （集合として一致すること）を検証する。列挙順序と重複の有無は検証しない
        （本モジュール冒頭の「検証しない事項」）。
        """
        manifest_names, ledger_names = scenario

        # 検証対象の実行（例外を送出しないことは本モジュール冒頭の「入力域」）。
        report = check_ledger_coherence(manifest_names, ledger_names)

        # 戻り値型（出典: `scripts/cleanup/models.py` の `LedgerCoherenceReport`）。
        self.assertIsInstance(
            report,
            LedgerCoherenceReport,
            msg=(
                "check_ledger_coherence の戻り値が LedgerCoherenceReport ではない: "
                f"{report!r}"
            ),
        )

        # 期待値は独立オラクルで算出する（実装の正規化関数を用いない）。
        expected_manifest = _normalized_set(manifest_names)
        expected_ledger = _normalized_set(ledger_names)
        # 差分は集合として比較する（列挙順序は DM5 が規定しない。本モジュール冒頭の
        # 「検証しない事項」）。
        expected_manifest_only = expected_manifest - expected_ledger
        expected_ledger_only = expected_ledger - expected_manifest

        # ---- (1) 双条件: 整合判定は正規化後の集合一致と同値 ----
        self.assertEqual(
            report.coherent,
            expected_manifest == expected_ledger,
            msg=(
                "整合判定が正規化後の集合一致と一致しない: "
                f"coherent={report.coherent!r}, "
                f"manifest_names={sorted(manifest_names)!r}, "
                f"ledger_names={sorted(ledger_names)!r}, "
                f"normalized_manifest={sorted(expected_manifest)!r}, "
                f"normalized_ledger={sorted(expected_ledger)!r}"
            ),
        )

        # ---- (2) 列挙: 差分がどちらの側にあるかを正しく列挙する（集合として比較）----
        self.assertEqual(
            frozenset(report.manifest_only),
            expected_manifest_only,
            msg=(
                "manifest_only が「正規化後 manifest − 正規化後 ledger」と一致しない: "
                f"manifest_only={report.manifest_only!r}, "
                f"expected={sorted(expected_manifest_only)!r}, "
                f"manifest_names={sorted(manifest_names)!r}, "
                f"ledger_names={sorted(ledger_names)!r}"
            ),
        )
        self.assertEqual(
            frozenset(report.ledger_only),
            expected_ledger_only,
            msg=(
                "ledger_only が「正規化後 ledger − 正規化後 manifest」と一致しない: "
                f"ledger_only={report.ledger_only!r}, "
                f"expected={sorted(expected_ledger_only)!r}, "
                f"manifest_names={sorted(manifest_names)!r}, "
                f"ledger_names={sorted(ledger_names)!r}"
            ),
        )

        # ---- (3) 双条件の対偶側: 不一致なら少なくとも一方の差分が非空 ----
        if not report.coherent:
            self.assertTrue(
                report.manifest_only or report.ledger_only,
                msg=(
                    "不整合と判定されたのに差分が両側とも空である: "
                    f"manifest_names={sorted(manifest_names)!r}, "
                    f"ledger_names={sorted(ledger_names)!r}"
                ),
            )

    def test_real_notation_differences_are_absorbed_by_normalization(self) -> None:
        """実体に存在する 2 件の表記差が正規化により一致すること（例示テスト）.

        **Validates: Requirements 7.7**

        検証する事実（両ファイルの実体で行番号・表記を確認済み。第一原則3）:
            - `requirements.txt:27` = `pyjwt` と `docs/external-assets.md:43` =
              `PyJWT`（design.md C10 が挙げる差異）。
            - `requirements.txt:10` = `django` と `docs/external-assets.md:26` =
              `Django`（tasks.md 4.1 実施時に追加確認された同種の差異）。

        いずれも大文字小文字のみの差であり、正規化後は一致するため R7-7 の整合
        判定は真となる。表記差を正規化せずに比較すると実体が一致していても整合
        判定が偽となるため、本挙動は R7-7 の成立に必須である。
        """
        # 正規化そのものの期待値（`normalize_package_name` は表記差を吸収する）。
        self.assertEqual(normalize_package_name("PyJWT"), "pyjwt")
        self.assertEqual(normalize_package_name("Django"), "django")

        # 実体の表記をそのまま与えた集合比較（Dependency_Manifest 側は小文字表記、
        # License_Ledger 側は先頭大文字表記）。
        report = check_ledger_coherence(
            frozenset({"django", "pyjwt"}),
            frozenset({"Django", "PyJWT"}),
        )
        self.assertTrue(
            report.coherent,
            msg=(
                "実体の表記差（requirements.txt:10/27 と docs/external-assets.md:26/43）"
                f"が正規化で吸収されていない: {report!r}"
            ),
        )
        self.assertEqual(report.manifest_only, ())
        self.assertEqual(report.ledger_only, ())

    def test_underscore_difference_is_absorbed_and_spellings_collapse(self) -> None:
        """アンダースコア差の吸収と、異表記が同一の正規化名へ畳み込まれること（例示テスト）.

        **Validates: Requirements 7.7**

        検証内容:
            - `pillow_avif_plugin`（アンダースコア表記）と `pillow-avif-plugin`
              （出典: `requirements.txt:24`）が正規化後に一致すること。
            - Dependency_Manifest 側に同一正規化名へ写る 3 表記（`Django`、
              `django`、`DJANGO`）が存在し、License_Ledger 側に当該名が存在しない
              とき、`manifest_only` が正規化名の集合 `{"django"}` と一致すること
              （畳み込みの取り扱い）。列挙順序は検証しない（本モジュール冒頭の
              「検証しない事項」）。
        """
        # アンダースコア差の吸収。
        absorbed = check_ledger_coherence(
            frozenset({"pillow_avif_plugin"}),
            frozenset({"pillow-avif-plugin"}),
        )
        self.assertTrue(absorbed.coherent, msg=f"{absorbed!r}")

        # 3 表記が 1 件の正規化名へ畳み込まれ、差分集合として現れる。
        collapsed = check_ledger_coherence(
            frozenset({"Django", "django", "DJANGO"}),
            frozenset({"mangum"}),
        )
        self.assertFalse(collapsed.coherent, msg=f"{collapsed!r}")
        self.assertEqual(frozenset(collapsed.manifest_only), frozenset({"django"}))
        self.assertEqual(frozenset(collapsed.ledger_only), frozenset({"mangum"}))


if __name__ == "__main__":
    # 単体実行用エントリ（`python -m unittest` による探索でも実行可能）。
    unittest.main()
