"""Property 4（非退行判定の全条件同時成立）のプロパティテスト.

本モジュールは design.md「Correctness Properties > Property 4」および tasks.md 3.4 を
検証する（出典: `.kiro/specs/legacy-asset-cleanup/tasks.md` 3.4「非退行判定のプロパティ
テストを書く」、`.kiro/specs/legacy-asset-cleanup/design.md:631-634`）。

    Feature: legacy-asset-cleanup, Property 4: 非退行判定の全条件同時成立
    *For any* NonRegressionRecord について、Removal_Verification が適合と判定するのは、
    `tests_passed >= 133` かつ `tests_failed == 0` かつ `tests_errored == 0` かつ 4 種の
    終了コード（`django_check` / `control_platform` / `self_test` / `non_regression`）が
    すべて 0 かつ `prerendered_pages == 7` かつ `manifest_files == 1` かつ
    `len(content_security_policy) >= 1` かつ `commands` が非空 のすべてが同時に成立する
    場合に限り、いずれかが不成立なら対応する条項が違反として列挙される。

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.10, 10.6**

検証対象モジュール（tasks.md 3.3 実装、出典: `scripts/cleanup/removal_verification.py`）:
    - `evaluate(record: NonRegressionRecord) -> VerificationResult`
      requirements.md Requirement 2 基準 1〜6 および基準 10 の同時成立を判定し、不適合な
      条項の識別子を列挙する。コマンド実行・ファイル I/O を行わないため Django の
      セットアップを必要としない（出典: 同モジュール docstring「設計上の制約」）。

条項識別子と要件の対応（出典: requirements.md:181-186、:190、:327、design.md C4）:
    | 条項 | 判定条件 | 要件出典 |
    | --- | --- | --- |
    | `R2-1` | `tests_passed >= 133` かつ `tests_failed == 0` かつ `tests_errored == 0` | requirements.md:181（Requirement 2 基準 1） |
    | `R2-2` | `django_check_exit_code == 0` | requirements.md:182（基準 2） |
    | `R2-3` | `control_platform_exit_code == 0` かつ `self_test_exit_code == 0` | requirements.md:183（基準 3。Control_Platform_Self_Test は 2 コマンド構成） |
    | `R2-4` | `non_regression_exit_code == 0` | requirements.md:184（基準 4） |
    | `R2-5` | `prerendered_pages == 7` かつ `manifest_files == 1` | requirements.md:185（基準 5） |
    | `R2-6` | `len(content_security_policy) >= 1` | requirements.md:186（基準 6） |
    | `R2-10` | `commands` が非空 | requirements.md:190（基準 10） |

R10-6（開発記録は Requirement 2 で取得した非退行確認結果を含む。出典:
requirements.md:327）は独立した条項識別子を持たない。design.md C4 の判定条項一覧に
R10-6 は列挙されておらず、記録内容の充足は基準 10 が定める `commands` / 終了コード /
pass・failure・error 件数に依拠するため、本テストは R10-6 の内容を `R2-10` による判定と
して検証し、`"R10-6"` を期待値に用いない（出典: design.md C4、
`scripts/cleanup/removal_verification.py` の条項対応表）。

独立オラクル方針（出典: tasks.md 3.4、design.md「Testing Strategy」）:
    期待違反集合は、`evaluate` の制御フローを写すのではなく、requirements.md の各基準を
    「条項識別子 → その基準に属する述語列」の表として本テスト内に再宣言し、述語が 1 つ
    でも偽なら当該条項を違反とする形で独立に算出する（`_expected_violations`）。閾値
    （133 / 0 / 7 / 1 / 1 / 1）は `scripts/cleanup/removal_verification.py` の
    モジュール定数を再利用し、テスト側での二重管理（ハードコード）を避ける
    （第三原則2 整合性）。

ライセンス注記（第二原則6・要ライセンス確認）:
    Hypothesis は Mozilla Public License 2.0（MPL-2.0）で配布される（出典:
    `requirements-dev.txt:18` の `hypothesis==6.158.0`、公式リポジトリ LICENSE.txt）。
    非配布・非改変での開発・テスト利用であり、MPL-2.0 のソース開示義務の実務的対象外
    である。

実行コマンド（プロジェクトルートから）:
    $env:DJANGO_SETTINGS_MODULE="config.settings.dev"; python manage.py test tests.cleanup.test_property_non_regression_evaluation
  もしくは（Django 非ロードでも実行可能）:
    python -m unittest tests.cleanup.test_property_non_regression_evaluation -v
"""

from __future__ import annotations

import string
import unittest
from typing import Callable

from hypothesis import given, settings
from hypothesis import strategies as st

from scripts.cleanup.models import NonRegressionRecord
from scripts.cleanup.removal_verification import (
    BASELINE_TESTS_PASSED,
    CLAUSE_CONTENT_SECURITY_POLICY,
    CLAUSE_CONTROL_PLATFORM_SELF_TEST,
    CLAUSE_DJANGO_CHECK,
    CLAUSE_NON_REGRESSION_CHECK,
    CLAUSE_PRERENDER,
    CLAUSE_RECORD_CONTENT,
    CLAUSE_TEST_SUITE,
    EXPECTED_EXIT_CODE,
    EXPECTED_MANIFEST_FILES,
    EXPECTED_PRERENDERED_PAGES,
    EXPECTED_TESTS_ERRORED,
    EXPECTED_TESTS_FAILED,
    MIN_COMMANDS,
    MIN_CONTENT_SECURITY_POLICY_LENGTH,
    evaluate,
)

# 判定対象の条項識別子の集合（出典: requirements.md Requirement 2 の基準 1〜6・基準 10、
# design.md C4「判定条件」）。design.md DM3 は `VerificationResult.violations` を
# 「不適合条項の識別子」を保持する平文のタプルとして宣言するのみで、列挙順序を規定して
# いないため、本モジュールは順序を検査せず集合として比較する。
_CLAUSES: tuple[str, ...] = (
    CLAUSE_TEST_SUITE,
    CLAUSE_DJANGO_CHECK,
    CLAUSE_CONTROL_PLATFORM_SELF_TEST,
    CLAUSE_NON_REGRESSION_CHECK,
    CLAUSE_PRERENDER,
    CLAUSE_CONTENT_SECURITY_POLICY,
    CLAUSE_RECORD_CONTENT,
)

# 独立オラクルの規則表: 条項識別子 → その基準に属する述語列。requirements.md の各基準
# 本文（:181-186、:190）を述語へ直訳したものであり、`evaluate` の実装分岐を参照しない。
_CLAUSE_PREDICATES: tuple[
    tuple[str, tuple[Callable[[NonRegressionRecord], bool], ...]], ...
] = (
    (
        # 基準 1（requirements.md:181）: pass 件数が Baseline 以上、failure 0 件、error 0 件。
        CLAUSE_TEST_SUITE,
        (
            lambda r: r.tests_passed >= BASELINE_TESTS_PASSED,
            lambda r: r.tests_failed == EXPECTED_TESTS_FAILED,
            lambda r: r.tests_errored == EXPECTED_TESTS_ERRORED,
        ),
    ),
    (
        # 基準 2（requirements.md:182）: `manage.py check --fail-level WARNING` が終了コード 0。
        CLAUSE_DJANGO_CHECK,
        (lambda r: r.django_check_exit_code == EXPECTED_EXIT_CODE,),
    ),
    (
        # 基準 3（requirements.md:183）: Control_Platform_Self_Test の 2 コマンドが終了コード 0。
        CLAUSE_CONTROL_PLATFORM_SELF_TEST,
        (
            lambda r: r.control_platform_exit_code == EXPECTED_EXIT_CODE,
            lambda r: r.self_test_exit_code == EXPECTED_EXIT_CODE,
        ),
    ),
    (
        # 基準 4（requirements.md:184）: `non_regression_check` が終了コード 0。
        CLAUSE_NON_REGRESSION_CHECK,
        (lambda r: r.non_regression_exit_code == EXPECTED_EXIT_CODE,),
    ),
    (
        # 基準 5（requirements.md:185）: Prerendered_Page 7 件、manifest 1 件。
        CLAUSE_PRERENDER,
        (
            lambda r: r.prerendered_pages == EXPECTED_PRERENDERED_PAGES,
            lambda r: r.manifest_files == EXPECTED_MANIFEST_FILES,
        ),
    ),
    (
        # 基準 6（requirements.md:186）: CSP 値が 1 文字以上。
        CLAUSE_CONTENT_SECURITY_POLICY,
        (
            lambda r: len(r.content_security_policy)
            >= MIN_CONTENT_SECURITY_POLICY_LENGTH,
        ),
    ),
    (
        # 基準 10（requirements.md:190）: 記録は実行したコマンドを含む（非空）。
        CLAUSE_RECORD_CONTENT,
        (lambda r: len(r.commands) >= MIN_COMMANDS,),
    ),
)

# コマンド文字列・CSP 値の生成に用いる文字集合（ASCII 英数と記号・空白の一部）。
_TEXT_ALPHABET = string.ascii_letters + string.digits + " ._-:;'\"/"


def _expected_violations(record: NonRegressionRecord) -> frozenset[str]:
    """requirements.md の基準本文から期待違反条項集合を独立に算出する.

    `_CLAUSE_PREDICATES` の表を走査し、当該条項に属する述語のいずれかが偽であれば条項を
    違反集合へ含める。`evaluate` の分岐構造を参照しないため、実装側の条件式の誤りを本
    オラクルで検出できる。戻り値を集合とするのは、design.md DM3 が `violations` の列挙
    順序を規定していないためである。

    Args:
        record: 判定対象の `NonRegressionRecord`。

    Returns:
        frozenset[str]: 違反条項識別子の集合。
    """
    violations: set[str] = set()
    for clause, predicates in _CLAUSE_PREDICATES:
        # 述語すべてが真の場合のみ当該基準は成立する（部分成立は不成立として扱う）。
        if not all(predicate(record) for predicate in predicates):
            violations.add(clause)
    return frozenset(violations)


def _exit_code() -> st.SearchStrategy[int]:
    """終了コードを境界（0）と非ゼロの双方を含めて生成する.

    Returns:
        SearchStrategy[int]: 0 および非ゼロ（負値を含む）終了コード。
    """
    # 0 と非ゼロ（1 / 2 / -1 など）を十分な頻度で生成するため sampled_from を併用する。
    return st.one_of(
        st.sampled_from((0, 1, 2, -1)),
        st.integers(min_value=-8, max_value=8),
    )


def _count_around(expected: int) -> st.SearchStrategy[int]:
    """期待値の境界（expected-1 / expected / expected+1）を含む件数を生成する.

    Args:
        expected: 基準が定める期待件数。

    Returns:
        SearchStrategy[int]: 境界近傍および広めの範囲の非負整数。
    """
    # 境界値（下限未満・一致・超過）を明示的に含め、加えて広い範囲も探索する。
    return st.one_of(
        st.sampled_from((expected - 1, expected, expected + 1)),
        st.integers(min_value=0, max_value=expected + 10),
    )


def _commands() -> st.SearchStrategy[tuple[str, ...]]:
    """実行コマンド列を空・非空の双方で生成する.

    Returns:
        SearchStrategy[tuple[str, ...]]: 空タプル（基準 10 不成立）を含むコマンド列。
    """
    return st.lists(
        st.text(alphabet=_TEXT_ALPHABET, min_size=1, max_size=40),
        min_size=0,
        max_size=3,
    ).map(tuple)


def _content_security_policy() -> st.SearchStrategy[str]:
    """CSP 値を空文字列・非空文字列の双方で生成する.

    Returns:
        SearchStrategy[str]: 空文字列（基準 6 不成立）を含む文字列。
    """
    return st.text(alphabet=_TEXT_ALPHABET, min_size=0, max_size=40)


@st.composite
def _non_regression_record(draw: st.DrawFn) -> NonRegressionRecord:
    """`NonRegressionRecord` を境界値中心に生成する（適合例も一定割合で含む）.

    無作為生成のみでは全条件同時成立（適合）の事例がほぼ出現しないため、適合値のみで
    構成するモードを明示的に混在させ、Property 4 の「適合と判定する」側も検証できるよう
    にする。各フィールドの型は design.md DM3 の `NonRegressionRecord` の宣言（件数と
    終了コードは `int`、`content_security_policy` は `str`、`commands` は
    `tuple[str, ...]`）に従い、`None` は生成しない。

    Args:
        draw: Hypothesis の draw 関数。

    Returns:
        NonRegressionRecord: 生成された非退行確認記録。
    """
    # 系統は DM3 の 3 値（出典: scripts/cleanup/models.py の `stream` docstring）。
    stream = draw(st.sampled_from(("A", "B", "D")))

    # 適合モード: 全基準を満たす値のみを生成する（適合側の検証を確実に行う）。
    conformant_mode = draw(st.booleans())
    if conformant_mode:
        return NonRegressionRecord(
            stream=stream,
            # 非空コマンド列（基準 10 成立）。
            commands=draw(
                st.lists(
                    st.text(alphabet=_TEXT_ALPHABET, min_size=1, max_size=40),
                    min_size=MIN_COMMANDS,
                    max_size=3,
                ).map(tuple)
            ),
            # Baseline 以上（133 / 134 / それ以上）。
            tests_passed=draw(
                st.integers(
                    min_value=BASELINE_TESTS_PASSED,
                    max_value=BASELINE_TESTS_PASSED + 10,
                )
            ),
            tests_failed=EXPECTED_TESTS_FAILED,
            tests_errored=EXPECTED_TESTS_ERRORED,
            django_check_exit_code=EXPECTED_EXIT_CODE,
            control_platform_exit_code=EXPECTED_EXIT_CODE,
            self_test_exit_code=EXPECTED_EXIT_CODE,
            non_regression_exit_code=EXPECTED_EXIT_CODE,
            prerendered_pages=EXPECTED_PRERENDERED_PAGES,
            manifest_files=EXPECTED_MANIFEST_FILES,
            # 非空 CSP 値（基準 6 成立）。
            content_security_policy=draw(
                st.text(
                    alphabet=_TEXT_ALPHABET,
                    min_size=MIN_CONTENT_SECURITY_POLICY_LENGTH,
                    max_size=40,
                )
            ),
        )

    # 自由モード: 各フィールドを境界値中心に独立生成する（不適合の任意組み合わせを含む）。
    return NonRegressionRecord(
        stream=stream,
        commands=draw(_commands()),
        tests_passed=draw(_count_around(BASELINE_TESTS_PASSED)),
        tests_failed=draw(_count_around(EXPECTED_TESTS_FAILED)),
        tests_errored=draw(_count_around(EXPECTED_TESTS_ERRORED)),
        django_check_exit_code=draw(_exit_code()),
        control_platform_exit_code=draw(_exit_code()),
        self_test_exit_code=draw(_exit_code()),
        non_regression_exit_code=draw(_exit_code()),
        prerendered_pages=draw(_count_around(EXPECTED_PRERENDERED_PAGES)),
        manifest_files=draw(_count_around(EXPECTED_MANIFEST_FILES)),
        content_security_policy=draw(_content_security_policy()),
    )


def _conformant_record(**overrides: object) -> NonRegressionRecord:
    """全基準を満たす `NonRegressionRecord` を作り、指定フィールドのみ差し替える.

    Args:
        **overrides: 差し替えるフィールド名と値。

    Returns:
        NonRegressionRecord: 適合記録（`overrides` の適用後）。
    """
    # 適合値の基準セット（出典: requirements.md:181-186、:190 の各期待値）。
    base: dict[str, object] = {
        "stream": "A",
        "commands": ("python manage.py test",),
        "tests_passed": BASELINE_TESTS_PASSED,
        "tests_failed": EXPECTED_TESTS_FAILED,
        "tests_errored": EXPECTED_TESTS_ERRORED,
        "django_check_exit_code": EXPECTED_EXIT_CODE,
        "control_platform_exit_code": EXPECTED_EXIT_CODE,
        "self_test_exit_code": EXPECTED_EXIT_CODE,
        "non_regression_exit_code": EXPECTED_EXIT_CODE,
        "prerendered_pages": EXPECTED_PRERENDERED_PAGES,
        "manifest_files": EXPECTED_MANIFEST_FILES,
        "content_security_policy": "default-src 'self'",
    }
    base.update(overrides)
    return NonRegressionRecord(**base)  # type: ignore[arg-type]


class NonRegressionEvaluationProperty(unittest.TestCase):
    """Property 4 のプロパティテストを保持するテストケース."""

    # 反復回数は tasks.md「Overview」が求める `max_examples=100` 以上を満たす 300 とする
    # （不適合の組み合わせ空間が広いため多めに探索する）。判定は決定的であり I/O を
    # 伴わないが、生成データによる per-example 締切超過の誤検知を避けるため deadline を
    # 無効化する（出典: tasks.md「Overview」、design.md「プロパティテスト」）。
    @settings(max_examples=300, deadline=None)
    @given(record=_non_regression_record())
    def test_conformance_iff_all_conditions_and_violations_enumerated(
        self, record: NonRegressionRecord
    ) -> None:
        """Feature: legacy-asset-cleanup, Property 4: 非退行判定の全条件同時成立

        Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.10, 10.6

        任意の `NonRegressionRecord` について次を検証する（出典: design.md:634、
        requirements.md:181-186、:190、:327）。
            (1) 全条件が同時成立する記録では `conformant is True` かつ
                `violations == ()`。
            (2) いずれかの条件が不成立の記録では `conformant is False`。
            (3) 違反条項の集合が独立オラクルの算出結果と一致する（不成立の基準に対応する
                条項のみが列挙される）。design.md DM3 は `violations` の列挙順序を規定
                していないため、順序は検査しない。
        """
        # 独立オラクルによる期待違反集合（requirements.md の基準本文から算出）。
        expected = _expected_violations(record)

        # 検証対象の判定を実行する。
        result = evaluate(record)

        # ---- (3) 違反条項の集合一致（順序は design.md DM3 が規定しないため検査しない） ----
        self.assertEqual(
            set(result.violations),
            set(expected),
            msg=(
                f"違反条項の集合が独立オラクルと一致しない: "
                f"実際={result.violations!r} / 期待={tuple(sorted(expected))!r} / "
                f"記録={record!r}"
            ),
        )
        # 列挙される条項は Requirement 2 の基準に対応する既知の識別子のみであること
        # （出典: design.md Property 4「対応する条項が違反として列挙される」）。
        for clause in result.violations:
            self.assertIn(
                clause,
                _CLAUSES,
                msg=f"未知の条項識別子が列挙された: {clause!r}",
            )

        if expected == frozenset():
            # ---- (1) 全条件同時成立 ⇒ 適合かつ違反なし ----
            self.assertTrue(
                result.conformant,
                msg=f"全条件成立の記録が適合と判定されなかった: {record!r}",
            )
            self.assertEqual(
                result.violations,
                (),
                msg=f"全条件成立の記録で違反が列挙された: {result.violations!r}",
            )
        else:
            # ---- (2) 1 つでも不成立 ⇒ 不適合 ----
            self.assertFalse(
                result.conformant,
                msg=(
                    f"条件不成立（期待違反={expected!r}）の記録が適合と判定された: "
                    f"{record!r}"
                ),
            )

        # `conformant` は `violations` が空であることと同値（design.md C4 / Property 4）。
        self.assertEqual(
            result.conformant,
            result.violations == (),
            msg=(
                f"conformant と violations の整合が崩れている: "
                f"conformant={result.conformant!r} / violations={result.violations!r}"
            ),
        )


class NonRegressionEvaluationExampleTests(unittest.TestCase):
    """条項ごとの単一違反と適合例を検証する例示テスト（境界値の明示確認）."""

    def test_fully_conformant_record_is_conformant(self) -> None:
        """全基準を満たす記録が適合と判定され、違反が列挙されないこと（R2-1〜R2-6、R2-10）."""
        result = evaluate(_conformant_record())
        self.assertTrue(result.conformant)
        self.assertEqual(result.violations, ())

    def test_single_clause_violations(self) -> None:
        """各基準を 1 つずつ不成立にした記録が、対応する条項のみを列挙すること."""
        # (差し替えフィールド, 期待違反条項) の組。境界値（132 / 6 / 8 / 0 / 2 など）を用いる。
        cases: tuple[tuple[dict[str, object], str], ...] = (
            ({"tests_passed": BASELINE_TESTS_PASSED - 1}, CLAUSE_TEST_SUITE),
            ({"tests_failed": 1}, CLAUSE_TEST_SUITE),
            ({"tests_errored": 1}, CLAUSE_TEST_SUITE),
            ({"django_check_exit_code": 1}, CLAUSE_DJANGO_CHECK),
            ({"control_platform_exit_code": 1}, CLAUSE_CONTROL_PLATFORM_SELF_TEST),
            ({"self_test_exit_code": 2}, CLAUSE_CONTROL_PLATFORM_SELF_TEST),
            ({"non_regression_exit_code": 1}, CLAUSE_NON_REGRESSION_CHECK),
            ({"prerendered_pages": EXPECTED_PRERENDERED_PAGES - 1}, CLAUSE_PRERENDER),
            ({"prerendered_pages": EXPECTED_PRERENDERED_PAGES + 1}, CLAUSE_PRERENDER),
            ({"manifest_files": 0}, CLAUSE_PRERENDER),
            ({"manifest_files": 2}, CLAUSE_PRERENDER),
            ({"content_security_policy": ""}, CLAUSE_CONTENT_SECURITY_POLICY),
            ({"commands": ()}, CLAUSE_RECORD_CONTENT),
        )
        for overrides, clause in cases:
            with self.subTest(overrides=overrides):
                result = evaluate(_conformant_record(**overrides))
                self.assertFalse(result.conformant)
                self.assertEqual(result.violations, (clause,))

    def test_baseline_boundary_is_inclusive(self) -> None:
        """`tests_passed` は Baseline 133 件と一致する場合も適合であること（R2-1「以上」）."""
        # 境界値 133（一致）と 134（超過）はいずれも基準 1 を満たす（requirements.md:181）。
        for passed in (BASELINE_TESTS_PASSED, BASELINE_TESTS_PASSED + 1):
            with self.subTest(tests_passed=passed):
                result = evaluate(_conformant_record(tests_passed=passed))
                self.assertTrue(result.conformant)
                self.assertEqual(result.violations, ())

    def test_all_clauses_violated_simultaneously(self) -> None:
        """全基準が不成立の記録が全条項を列挙すること（順序は DM3 が規定しないため不問）."""
        result = evaluate(
            _conformant_record(
                tests_passed=BASELINE_TESTS_PASSED - 1,
                tests_failed=1,
                tests_errored=1,
                django_check_exit_code=1,
                control_platform_exit_code=1,
                self_test_exit_code=1,
                non_regression_exit_code=1,
                prerendered_pages=0,
                manifest_files=0,
                content_security_policy="",
                commands=(),
            )
        )
        self.assertFalse(result.conformant)
        self.assertEqual(set(result.violations), set(_CLAUSES))


if __name__ == "__main__":
    # 単体実行用エントリ（`python -m unittest` による探索でも実行可能）。
    unittest.main()
