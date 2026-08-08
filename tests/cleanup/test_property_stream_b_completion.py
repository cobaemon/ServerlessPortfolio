"""Property 6（系統 B 完了判定の全区分成立と AWS 側双方成立）のプロパティテスト.

Feature: legacy-asset-cleanup, Property 6: *For any* 適用済み区分集合と任意の AwsSmtpState について、Completion_Judgment が系統 B を完了と判定するのは、適用済み区分集合が 8 区分すべてと一致し、かつ AWS 側の照会が実施済みであり、かつ削除完了対象と不在確認対象の和集合が対象 6 件と一致する場合に限る。また不在確認が成立した対象に対しては削除操作の実行許可が与えられない。ここでの 8 区分のうち `B-1_prod_settings` は、基準 1 の除去に加えて基準 17（prod の `EMAIL_BACKEND` の console バックエンド明示設定）を含む（出典: C8 の「変更単位のスコープに関する整合注記」、DM6）。したがって本プロパティが判定する「8 区分すべての適用」は基準 17 の適用を含む。

本モジュールは design.md「Correctness Properties > Property 6」および tasks.md 3.7 を
検証する（出典: `.kiro/specs/legacy-asset-cleanup/design.md:643-646`、同 design.md:740 の
プロパティ対応表 `Property 6 | tests/cleanup/test_property_stream_b_completion.py`、
同 tasks.md「3.7 系統 B 完了判定のプロパティテストを書く」）。

**Validates: Requirements 4.9, 4.10, 4.14, 4.15, 4.16, 4.17**

    - R4-9: 基準 1 から基準 8 および基準 17 の変更を同一の変更単位として適用する
      （出典: requirements.md:220）。
    - R4-10: 基準 1 から基準 8 および基準 17 の一部のみが適用された状態は未完了と
      して記録し、残余の変更を適用するまで完了と扱わない（同 requirements.md:221）。
    - R4-14: 系統 B の完了判定は、基準 1 から基準 8 および基準 17 の適用完了と、
      基準 13 に定める対象 AWS リソースに対する承認済み Destructive_Operation の完了
      および不在確認の双方が成立した場合にのみ成立する（同 requirements.md:225）。
    - R4-15: AWS 側不在確認が成立していない間、系統 B を未完了として記録する
      （同 requirements.md:226）。
    - R4-16: 照会時点で対象 AWS リソースが既に不在であった場合、当該リソースに対する
      Destructive_Operation を実行せず、不在を照会コマンドの結果として記録し、基準 14 の
      不在確認を成立として扱う（同 requirements.md:227）。
    - R4-17: 除去後の `config/settings/prod.py` は
      `django.core.mail.backends.console.EmailBackend` を単一の `EMAIL_BACKEND` 値として
      明示設定する（同 requirements.md:228）。本判定では区分 `B-1_prod_settings` が
      基準 1 の除去と基準 17 の明示設定の双方を担うため、`applied` が 8 区分すべてと
      一致することが R4-17 の適用を含む（出典: design.md:646、同 C8「変更単位のスコープ
      に関する整合注記」、`scripts/cleanup/models.py` の `STREAM_B_SEGMENTS`）。

検証対象（tasks.md 3.5 実装、design.md C5）:
    - `scripts/cleanup/completion.py` の
      `is_stream_b_complete(applied: frozenset[str], aws_state: AwsSmtpState) -> bool`。
      AWS 照会・コマンド実行・ファイル I/O を行わないため Django のセットアップを
      必要としない（出典: 同モジュール docstring「設計上の制約」「副作用: なし」）。

プロパティ本文第 2 文の担当コンポーネント（design.md の責務分担に従う）:
    Property 6 の第 2 文「また不在確認が成立した対象に対しては削除操作の実行許可が
    与えられない」は、design.md 上で C11 Approval_Gate（`scripts/cleanup/approval.py`）
    と運用手順が担う。design.md C5 が `is_stream_b_complete` へ与える責務は
    「『系統 B が完了したか』のみを判定する」ことであり、削除操作の実行許可判定は
    C11 の `is_executable` が担う（出典: design.md C5「責務」、同 C11
    「インターフェース」「停止規則」「運用手順」）。したがって本モジュールは第 2 文を
    検証対象に含めない。第 2 文の検証は Property 10
    （`tests/cleanup/test_property_approval_gate.py`）が担う（出典: design.md
    「Testing Strategy」のプロパティ対応表）。

入力域（生成器が引く範囲。要件が定める記録の値域に対応する）:
    - `applied`: 系統 B の変更区分の集合であり、R4-9 / R4-10 が定める区分は
      `STREAM_B_SEGMENTS`（基準 1〜8 および基準 17 を 8 区分へ写したもの。出典:
      requirements.md:220、:221、design.md DM6）である。したがって生成器は
      `STREAM_B_SEGMENTS` の部分集合を引く。
    - `expected_targets`: R4-13 が定める対象 6 件（出典: requirements.md:224、
      design.md DM6 `STREAM_B_AWS_TARGETS`）に固定する。
    - `absent_targets` / `deleted_targets`: R4-13 の対象 6 件の部分集合であり、かつ
      互いに素である。R4-16 は照会時点で不在であった対象について
      Destructive_Operation を実行しないことを定めるため（出典: requirements.md:227）、
      同一対象が「不在確認済み」かつ「削除完了」となる記録は要件の下で成立しない。
    - `queried`: 真偽の双方を引く。偽の場合は記録された集合の内容にかかわらず未完了で
      ある（R4-15 は無条件。出典: requirements.md:226）。
    - R4-16 により、不在確認が成立した対象は削除完了対象と同等に和集合へ算入される。
      したがって削除を 1 件も実施していない状態（`deleted_targets` が空）でも完了と
      なり得る（出典: requirements.md:227）。

独立オラクル方針（出典: tasks.md 3.7、design.md「Testing Strategy」）:
    期待値は `is_stream_b_complete` の制御フローを写さず、design.md:646 の本文および
    requirements.md:220-228 の基準本文から 3 条件の論理積として本モジュール内で独立に
    算出する（`_expected_complete`）。8 区分・6 対象の集合そのものは
    `scripts/cleanup/models.py` の `STREAM_B_SEGMENTS` / `STREAM_B_AWS_TARGETS` を
    import して再利用し、テスト側での二重定義（区分名・対象名の再列挙）を避ける
    （第三原則2 整合性、指示による明示要件）。

ライセンス注記（第二原則6・要ライセンス確認）:
    Hypothesis は Mozilla Public License 2.0（MPL-2.0）で配布される（出典:
    `requirements-dev.txt:18` の `hypothesis==6.158.0` および同ファイル 6-14 行の
    ライセンス注記、公式リポジトリ LICENSE.txt）。開発・テスト時のみ使用し、改変せず
    Lambda 配布物へ同梱しないため、MPL-2.0 のソース開示義務の実務的対象外である
    （非配布・非改変）。

実行コマンド（プロジェクトルートから）:
    $env:DJANGO_SETTINGS_MODULE="config.settings.dev"; python manage.py test tests.cleanup.test_property_stream_b_completion
  もしくは（Django 非ロードでも実行可能）:
    python -m unittest tests.cleanup.test_property_stream_b_completion -v
"""

from __future__ import annotations

import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

# 検証対象（tasks.md 3.5 実装、design.md C5）と入力値型・定数（design.md DM6）。
from scripts.cleanup.completion import is_stream_b_complete
from scripts.cleanup.models import (
    STREAM_B_AWS_TARGETS,
    STREAM_B_SEGMENTS,
    AwsSmtpState,
)

# 区分名・対象名は `scripts/cleanup/models.py` の定数を再利用する（再列挙しない）。
# 生成器の `sampled_from` へ渡すため、決定的な順序を持つタプルへ変換する。
_SEGMENTS: tuple[str, ...] = tuple(sorted(STREAM_B_SEGMENTS))
_TARGETS: tuple[str, ...] = tuple(sorted(STREAM_B_AWS_TARGETS))

# design.md DM6 が定める区分数（8）と対象数（6）。集合サイズの前提が崩れると本テストの
# 網羅性の主張（7 区分適用・1 件不足の境界検査）が成り立たなくなるため明示的に検査する
# （出典: requirements.md:220（基準 1〜8 + 基準 17 = 8 区分）、:224（対象 6 件））。
_EXPECTED_SEGMENT_COUNT = 8
_EXPECTED_TARGET_COUNT = 6


def _expected_complete(applied: frozenset[str], aws_state: AwsSmtpState) -> bool:
    """design.md:646 の本文から系統 B 完了の期待値を独立に算出する.

    3 条件の論理積として算出し、`is_stream_b_complete` の実装分岐を参照しない
    （出典: design.md:646、requirements.md:220、:221、:225、:226、:227）。
        - 条件 1（R4-9 / R4-10 / R4-17）: 適用済み区分集合が 8 区分すべてと一致する。
        - 条件 2（R4-15）: AWS 側の照会が実施済みである。
        - 条件 3（R4-14 / R4-16）: 削除完了対象と不在確認対象の和集合が対象 6 件と
          一致する。

    Args:
        applied: 適用済みの系統 B 変更区分の集合。
        aws_state: AWS 側状態（DM6 の `AwsSmtpState`）。

    Returns:
        bool: 3 条件がすべて成立する場合のみ True。

    例外:
        送出しない。
    """
    # 条件 1: 8 区分すべてとの一致（真部分集合は未完了。requirements.md:221）。
    all_segments_applied = applied == STREAM_B_SEGMENTS
    # 条件 2: 照会実施済み（暗黙の真偽変換を行わず同一性で判定する。requirements.md:226）。
    aws_queried = aws_state.queried is True
    # 条件 3: 和集合が対象 6 件と一致（不在確認は削除完了と同等に算入。requirements.md:227）。
    union_settled = (
        aws_state.absent_targets | aws_state.deleted_targets
    ) == STREAM_B_AWS_TARGETS
    return all_segments_applied and aws_queried and union_settled


@st.composite
def _applied_segments(draw: st.DrawFn) -> frozenset[str]:
    """適用済み区分集合を `STREAM_B_SEGMENTS` の部分集合として生成する.

    Args:
        draw: Hypothesis の draw 関数。

    Returns:
        frozenset[str]: 8 区分すべて（完了側）、8 区分から 1 区分を欠いた集合
            （境界: 7 区分の部分適用）、または任意の部分集合（空集合を含む）。

    完全一致の事例が生成されない反復ばかりでは Property 6 の「完了と判定する」側を
    検査できないため、`full` モードを明示的に混在させる。
    """
    mode = draw(st.sampled_from(("full", "one_missing", "arbitrary")))
    if mode == "full":
        # 8 区分すべて適用（R4-17 を含む。出典: design.md:646）。
        return STREAM_B_SEGMENTS
    if mode == "one_missing":
        # 7 区分のみ適用（R4-10 の部分適用。完了直前の境界）。
        missing = draw(st.sampled_from(_SEGMENTS))
        return STREAM_B_SEGMENTS - {missing}
    # 任意の部分集合（空集合および中間の部分適用）。
    return frozenset(
        draw(
            st.lists(st.sampled_from(_SEGMENTS), min_size=0, max_size=len(_SEGMENTS))
        )
    )


@st.composite
def _aws_smtp_states(draw: st.DrawFn) -> AwsSmtpState:
    """`AwsSmtpState` を `STREAM_B_AWS_TARGETS` の範囲内で生成する.

    Args:
        draw: Hypothesis の draw 関数。

    Returns:
        AwsSmtpState: `expected_targets` は `STREAM_B_AWS_TARGETS` に固定し、
            `absent_targets` / `deleted_targets` は同集合の互いに素な部分集合とする
            （本モジュール冒頭の「入力域」。R4-16 により同一対象が双方へ属する記録は
            要件の下で成立しない）。次の形状を明示的に混在させる。
                - `all_absent`: 全 6 件が不在確認済み、削除は 0 件（R4-16）。
                - `all_deleted`: 全 6 件が削除完了、不在確認は 0 件（R4-14）。
                - `partition`: 各対象をいずれか一方へ排他的に振り分け、和集合が 6 件と
                  一致する混在形。
                - `arbitrary`: 各対象を不在確認側・削除完了側・いずれにも属さない、の
                  3 通りへ振り分けた形（和集合が 6 件に届かない不足形を含む）。
    """
    coverage = draw(
        st.sampled_from(("all_absent", "all_deleted", "partition", "arbitrary"))
    )

    if coverage == "all_absent":
        # 削除を 1 件も実施していない成立形（R4-16。requirements.md:227）。
        absent = STREAM_B_AWS_TARGETS
        deleted: frozenset[str] = frozenset()
    elif coverage == "all_deleted":
        # 全件を承認済み削除で解消した成立形（R4-14。requirements.md:225）。
        absent = frozenset()
        deleted = STREAM_B_AWS_TARGETS
    elif coverage == "partition":
        # 各対象を不在確認側／削除完了側へ排他的に振り分ける（和集合は 6 件）。
        assignment = draw(
            st.lists(st.booleans(), min_size=len(_TARGETS), max_size=len(_TARGETS))
        )
        absent = frozenset(
            target for target, to_absent in zip(_TARGETS, assignment) if to_absent
        )
        deleted = frozenset(
            target for target, to_absent in zip(_TARGETS, assignment) if not to_absent
        )
    else:
        # 各対象を「不在確認側」「削除完了側」「いずれにも属さない（未確認）」の 3 通りへ
        # 振り分ける。和集合が 6 件に届かない不足形が現れる一方、R4-16 により成立しない
        # 重複（同一対象が双方に属する記録）は生成しない（出典: requirements.md:227）。
        assignment = draw(
            st.lists(
                st.sampled_from(("absent", "deleted", "unsettled")),
                min_size=len(_TARGETS),
                max_size=len(_TARGETS),
            )
        )
        absent = frozenset(
            target for target, side in zip(_TARGETS, assignment) if side == "absent"
        )
        deleted = frozenset(
            target for target, side in zip(_TARGETS, assignment) if side == "deleted"
        )

    return AwsSmtpState(
        queried=draw(st.booleans()),
        absent_targets=absent,
        deleted_targets=deleted,
        expected_targets=STREAM_B_AWS_TARGETS,
    )


def _complete_state(**overrides: object) -> AwsSmtpState:
    """完了条件を満たす `AwsSmtpState` を作り、指定フィールドのみ差し替える.

    Args:
        **overrides: 差し替えるフィールド名と値。

    Returns:
        AwsSmtpState: 照会済みかつ和集合が対象 6 件と一致する状態（`overrides` 適用後）。

    例外:
        送出しない。
    """
    # 既定値は全件不在確認（R4-16 の成立形。requirements.md:227）。
    base: dict[str, object] = {
        "queried": True,
        "absent_targets": STREAM_B_AWS_TARGETS,
        "deleted_targets": frozenset(),
        "expected_targets": STREAM_B_AWS_TARGETS,
    }
    base.update(overrides)
    return AwsSmtpState(**base)  # type: ignore[arg-type]


class StreamBCompletionProperty(unittest.TestCase):
    """Property 6 のプロパティテストを保持するテストケース."""

    # 反復回数は tasks.md「Overview」が求める `max_examples=100` 以上を満たす 300 とする
    # （区分の部分集合 2^8 と対象集合の組合せ空間が広いため多めに探索する）。判定は
    # 決定的であり I/O を伴わないが、生成データによる per-example 締切超過の誤検知を
    # 避けるため deadline を無効化する（出典: tasks.md「Overview」、design.md
    # 「プロパティテスト」）。
    @settings(max_examples=300, deadline=None)
    @given(applied=_applied_segments(), aws_state=_aws_smtp_states())
    def test_completion_iff_all_segments_and_queried_and_union_matches_targets(
        self, applied: frozenset[str], aws_state: AwsSmtpState
    ) -> None:
        """Feature: legacy-asset-cleanup, Property 6: 系統 B 完了判定の全区分成立と AWS 側双方成立

        **Validates: Requirements 4.9, 4.10, 4.14, 4.15, 4.16, 4.17**

        任意の適用済み区分集合と任意の `AwsSmtpState`（いずれも設計上の値域内）に
        ついて、`is_stream_b_complete` が完了と判定するのは 3 条件がすべて成立する
        場合に限ることを検証する（出典: design.md:646、requirements.md:220、:221、
        :225、:226、:227、:228）。
            (1) 判定結果が独立オラクル `_expected_complete` と厳密一致する。
            (2) 完了と判定された場合、3 条件が個別にすべて成立している（いずれか
                1 条件の不成立で完了と判定されない）。
        """
        # 独立オラクル（design.md:646 の本文から算出。実装分岐を参照しない）。
        expected = _expected_complete(applied, aws_state)

        # 検証対象の実行（生成器は要件が定める記録の値域から値を引く。本モジュール冒頭の
        # 「入力域」）。
        actual = is_stream_b_complete(applied, aws_state)

        # 戻り値は真偽値であること（判定結果を真偽値以外で返さないことの確認）。
        self.assertIsInstance(
            actual,
            bool,
            msg=f"is_stream_b_complete の戻り値が bool ではない: {actual!r}",
        )

        # ---- (1) 独立オラクルとの厳密一致 ----
        self.assertEqual(
            actual,
            expected,
            msg=(
                "完了判定が独立オラクルと一致しない: "
                f"実際={actual!r} / 期待={expected!r} / "
                f"applied={tuple(sorted(applied))!r} / aws_state={aws_state!r}"
            ),
        )

        # ---- (2) 完了と判定された場合、3 条件が個別に成立していること ----
        if actual:
            self.assertEqual(
                applied,
                STREAM_B_SEGMENTS,
                msg=(
                    "8 区分すべてが適用されていない状態で完了と判定された"
                    f"（R4-10 違反）: applied={tuple(sorted(applied))!r}"
                ),
            )
            self.assertIs(
                aws_state.queried,
                True,
                msg=(
                    "AWS 側照会が未実施の状態で完了と判定された（R4-15 違反）: "
                    f"aws_state={aws_state!r}"
                ),
            )
            self.assertEqual(
                aws_state.absent_targets | aws_state.deleted_targets,
                STREAM_B_AWS_TARGETS,
                msg=(
                    "不在確認と削除完了の和集合が対象 6 件と一致しない状態で完了と"
                    f"判定された（R4-14 違反）: aws_state={aws_state!r}"
                ),
            )


class StreamBCompletionExampleTests(unittest.TestCase):
    """完了成立形と各条件の個別不成立を検証する例示テスト（境界値の明示確認）."""

    def test_segment_and_target_counts_match_design(self) -> None:
        """DM6 の区分数 8 と対象数 6 が保たれていること（本テストの網羅性の前提）."""
        # 出典: requirements.md:220（基準 1〜8 + 基準 17 を 8 区分へ写す）、:224（対象 6 件）、
        # design.md DM6、`scripts/cleanup/models.py` の各定数。
        self.assertEqual(len(STREAM_B_SEGMENTS), _EXPECTED_SEGMENT_COUNT)
        self.assertEqual(len(STREAM_B_AWS_TARGETS), _EXPECTED_TARGET_COUNT)
        # 区分 `B-1_prod_settings` は基準 1 の除去と基準 17 の明示設定の双方を担う
        # （出典: design.md:646、同 C8、`scripts/cleanup/models.py` の該当コメント）。
        self.assertIn("B-1_prod_settings", STREAM_B_SEGMENTS)

    def test_all_absent_state_is_complete(self) -> None:
        """全 6 件が不在確認済み・削除 0 件でも完了となること（R4-16）."""
        # requirements.md:227 は不在を基準 14 の不在確認成立として扱うことを定める。
        state = _complete_state(
            absent_targets=STREAM_B_AWS_TARGETS, deleted_targets=frozenset()
        )
        self.assertTrue(is_stream_b_complete(STREAM_B_SEGMENTS, state))

    def test_all_deleted_state_is_complete(self) -> None:
        """全 6 件が削除完了・不在確認 0 件で完了となること（R4-14）."""
        state = _complete_state(
            absent_targets=frozenset(), deleted_targets=STREAM_B_AWS_TARGETS
        )
        self.assertTrue(is_stream_b_complete(STREAM_B_SEGMENTS, state))

    def test_mixed_state_is_complete(self) -> None:
        """不在確認と削除完了の混在で和集合が 6 件と一致すれば完了となること（R4-14、R4-16）."""
        # 対象 6 件を 2 件（不在確認）と 4 件（削除完了）へ排他的に分割する。
        absent = frozenset(_TARGETS[:2])
        deleted = frozenset(_TARGETS[2:])
        state = _complete_state(absent_targets=absent, deleted_targets=deleted)
        self.assertTrue(is_stream_b_complete(STREAM_B_SEGMENTS, state))

    def test_seven_of_eight_segments_is_incomplete(self) -> None:
        """8 区分のうち 1 区分でも欠けていれば完了としないこと（R4-10）."""
        # 8 通りすべての「7 区分適用」を検査する（部分適用の境界。requirements.md:221）。
        for missing in _SEGMENTS:
            with self.subTest(missing=missing):
                applied = STREAM_B_SEGMENTS - {missing}
                self.assertFalse(
                    is_stream_b_complete(applied, _complete_state()),
                    msg=f"区分 {missing!r} が未適用でも完了と判定された",
                )

    def test_empty_applied_is_incomplete(self) -> None:
        """適用済み区分が 0 件の場合は完了としないこと（R4-10）."""
        self.assertFalse(is_stream_b_complete(frozenset(), _complete_state()))

    def test_not_queried_is_incomplete(self) -> None:
        """照会未実施の場合、記録内容にかかわらず完了としないこと（R4-15）."""
        # 記録上は和集合が 6 件と一致していても、照会未実施なら未完了である
        # （requirements.md:226 は無条件。本モジュール冒頭の「入力域」）。
        for absent, deleted in (
            (STREAM_B_AWS_TARGETS, frozenset()),
            (frozenset(), STREAM_B_AWS_TARGETS),
            (frozenset(_TARGETS[:3]), frozenset(_TARGETS[3:])),
        ):
            with self.subTest(absent=sorted(absent), deleted=sorted(deleted)):
                state = _complete_state(
                    queried=False, absent_targets=absent, deleted_targets=deleted
                )
                self.assertFalse(is_stream_b_complete(STREAM_B_SEGMENTS, state))

    def test_union_short_of_targets_is_incomplete(self) -> None:
        """和集合が対象 6 件に届かない場合は完了としないこと（R4-14）."""
        # 0 件（全件不足）から 5 件（1 件不足）までの不足形を検査する。
        for size in range(len(_TARGETS)):
            with self.subTest(union_size=size):
                state = _complete_state(
                    absent_targets=frozenset(_TARGETS[:size]),
                    deleted_targets=frozenset(),
                )
                self.assertFalse(is_stream_b_complete(STREAM_B_SEGMENTS, state))

    def test_single_missing_target_is_incomplete(self) -> None:
        """対象 6 件のうち 1 件でも未確認なら完了としないこと（R4-14 の境界）."""
        for missing in _TARGETS:
            with self.subTest(missing=missing):
                remaining = sorted(STREAM_B_AWS_TARGETS - {missing})
                # 残り 5 件を不在確認側と削除完了側へ分けても和集合は 6 件に届かない。
                state = _complete_state(
                    absent_targets=frozenset(remaining[:2]),
                    deleted_targets=frozenset(remaining[2:]),
                )
                self.assertFalse(is_stream_b_complete(STREAM_B_SEGMENTS, state))


if __name__ == "__main__":
    # 単体実行用エントリ（`python -m unittest` による探索でも実行可能）。
    unittest.main()
