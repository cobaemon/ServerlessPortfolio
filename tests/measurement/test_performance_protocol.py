"""表示パフォーマンス実測プロトコルの例ベース単体テスト（tasks.md 8.2）.

本モジュールは `scripts/measurement/performance_protocol.py` の中核ロジックが
要件 R10（`.kiro/specs/cost-performance-optimization/requirements.md`）および
design.md「Testing Strategy > 単体/例ベーステスト」に適合することを、
決定的な代表例・境界・エラー条件で検証する（出典: design「PBT 適用可否評価」＝
実測系は PBT 不適合・例ベース/スモークで担保）。

検証観点:
    1. nearest-rank パーセンタイル算出の正しさ（p50・p95）と入力検証の送出（R10-4/R10-5）。
    2. 5 回以上の試行要求（R10-1）を満たさない場合にエラーを握りつぶさず送出すること。
    3. 未実測（試行 0 件）を `undetermined` として扱い達成／未達を決めつけないこと（R10-8）。
    4. warm 状態のみで TTFB p95 を算出すること（R10-5）。
    5. 目標比較（LCP p50 ≤ 2.5 秒、warm TTFB p95 ≤ 0.8 秒）の達成／未達判定（R10-4/R10-5/R10-7）。
    6. Baseline/Post_Change 差分と、片側欠落時の `missing` 明記（R10-3/R12-4）。
    7. 試行値のゼロトラスト検証（負値・非有限値の送出、第三原則3）。

外部依存とライセンス（第二原則6）:
    - 標準ライブラリ `unittest`・`math` のみを使用し、追加の外部依存を持たない
      （既存 IaC テスト `tests/iac/*` と一貫。Python 標準ライブラリは PSF ライセンス）。

実行コマンド（プロジェクトルートから）:
    python -m unittest tests.measurement.test_performance_protocol -v
"""

from __future__ import annotations

import math
import unittest

# 検証対象モジュール（実測プロトコル本体）。値の改変は行わず振る舞いのみを検証する。
from scripts.measurement.performance_protocol import (
    LCP_P50_TARGET_SECONDS,
    METRIC_LCP_P50,
    METRIC_WARM_TTFB_P95,
    SOURCE_LCP_TARGET,
    SOURCE_WARM_TTFB_TARGET,
    WARM_TTFB_P95_TARGET_SECONDS,
    MeasurementPhase,
    MetricRecord,
    PerformanceMeasurementProtocol,
    RecordStatus,
    Trial,
    percentile_nearest_rank,
)


def _make_trial(
    index: int,
    lcp_seconds: float,
    ttfb_seconds: float,
    is_warm: bool,
) -> Trial:
    """テスト用の :class:`Trial` を生成する補助関数。

    引数:
        index        : 試行番号（1 始まり）。
        lcp_seconds  : LCP 実測値（秒）。
        ttfb_seconds : TTFB 実測値（秒）。
        is_warm      : ウォーム状態か否か。

    戻り値:
        指定値を保持する :class:`Trial`。出典文字列は試行番号から一意に決定する。
    """
    # 出典は試行番号から一意に導出し、記録の追跡性を保つ（第一原則3）。
    return Trial(
        index=index,
        lcp_seconds=lcp_seconds,
        ttfb_seconds=ttfb_seconds,
        is_warm=is_warm,
        source=f"lh-trial-{index}",
    )


class PercentileNearestRankTest(unittest.TestCase):
    """nearest-rank パーセンタイル算出の単体テスト（R10-4/R10-5）。"""

    def test_p50_returns_middle_observed_value(self) -> None:
        """5 要素の p50 は昇順 3 番目の実測値を返す（nearest-rank 定義）。"""
        # ceil(50/100 * 5) = 3 番目（1 始まり）= 昇順で 3.2。
        values = [3.6, 3.0, 3.2, 3.4, 3.1]
        self.assertEqual(percentile_nearest_rank(values, 50), 3.2)

    def test_p95_returns_highest_observed_value_for_five_samples(self) -> None:
        """5 要素の p95 は昇順 5 番目（最大）の実測値を返す。"""
        # ceil(95/100 * 5) = ceil(4.75) = 5 番目 = 昇順で 1.20。
        values = [0.95, 1.02, 0.90, 1.20, 0.88]
        self.assertEqual(percentile_nearest_rank(values, 95), 1.20)

    def test_empty_values_raises(self) -> None:
        """空列は誤った統計値を生むため明示的に送出する（フォールバック禁止）。"""
        with self.assertRaises(ValueError):
            percentile_nearest_rank([], 50)

    def test_out_of_range_percentile_raises(self) -> None:
        """0 < p ≤ 100 の範囲外は握りつぶさず送出する（ゼロトラスト検証）。"""
        with self.assertRaises(ValueError):
            percentile_nearest_rank([1.0], 0)
        with self.assertRaises(ValueError):
            percentile_nearest_rank([1.0], 100.1)


class EvaluatePhaseTest(unittest.TestCase):
    """フェーズ集計（LCP p50・warm TTFB p95）の単体テスト（R10-1/R10-5/R10-8）。"""

    def setUp(self) -> None:
        """各テストで共有する実測プロトコルを用意する。"""
        self.protocol = PerformanceMeasurementProtocol()

    def test_measured_phase_computes_lcp_p50_and_warm_ttfb_p95(self) -> None:
        """5 試行（全 warm）から LCP p50 と warm TTFB p95 を秒単位で算出する。"""
        trials = [
            _make_trial(1, 3.1, 0.95, True),
            _make_trial(2, 3.4, 1.02, True),
            _make_trial(3, 3.2, 0.90, True),
            _make_trial(4, 3.6, 1.20, True),
            _make_trial(5, 3.0, 0.88, True),
        ]
        result = self.protocol.evaluate_phase(MeasurementPhase.BASELINE, trials)
        # LCP p50 = 3.2、warm TTFB p95 = 1.20、双方 MEASURED。
        self.assertEqual(result.lcp_p50.status, RecordStatus.MEASURED)
        self.assertEqual(result.lcp_p50.value, 3.2)
        self.assertEqual(result.lcp_p50.metric, METRIC_LCP_P50)
        self.assertEqual(result.warm_ttfb_p95.status, RecordStatus.MEASURED)
        self.assertEqual(result.warm_ttfb_p95.value, 1.20)
        self.assertEqual(result.warm_ttfb_p95.metric, METRIC_WARM_TTFB_P95)
        # 単位は秒であることを明記（R10-6）。
        self.assertEqual(result.lcp_p50.unit, "秒")
        self.assertEqual(result.warm_ttfb_p95.unit, "秒")

    def test_insufficient_trials_raises(self) -> None:
        """5 回未満の試行は不完全データとして握りつぶさず送出する（R10-1）。"""
        trials = [_make_trial(1, 2.0, 0.3, True)]
        with self.assertRaises(ValueError):
            self.protocol.evaluate_phase(MeasurementPhase.BASELINE, trials)

    def test_empty_trials_yield_undetermined(self) -> None:
        """試行 0 件は未実測。達成／未達を決めつけず undetermined とする（R10-8）。"""
        result = self.protocol.evaluate_phase(MeasurementPhase.POST_CHANGE, [])
        self.assertEqual(result.lcp_p50.status, RecordStatus.UNDETERMINED)
        self.assertIsNone(result.lcp_p50.value)
        self.assertEqual(result.warm_ttfb_p95.status, RecordStatus.UNDETERMINED)
        self.assertIsNone(result.warm_ttfb_p95.value)
        # 目標比較も未実測なら達成／未達を判定しない（meets_goal=None）。
        self.assertIsNone(result.lcp_goal.meets_goal)
        self.assertIsNone(result.warm_ttfb_goal.meets_goal)

    def test_warm_ttfb_uses_only_warm_trials(self) -> None:
        """warm TTFB p95 は warm 状態の試行のみを対象とする（R10-5）。"""
        # cold 試行の TTFB を混入させても集計対象外であることを確認する。
        trials = [
            _make_trial(1, 3.1, 0.30, True),
            _make_trial(2, 3.4, 0.40, True),
            _make_trial(3, 3.2, 0.35, True),
            _make_trial(4, 3.6, 0.55, True),
            _make_trial(5, 3.0, 0.38, True),
            _make_trial(6, 3.0, 9.99, False),  # cold は warm p95 に影響しない。
        ]
        result = self.protocol.evaluate_phase(MeasurementPhase.POST_CHANGE, trials)
        self.assertEqual(result.warm_trial_count, 5)
        # warm の TTFB p95 = ceil(0.95*5)=5 番目 = 0.55（cold の 9.99 は無関係）。
        self.assertEqual(result.warm_ttfb_p95.value, 0.55)

    def test_insufficient_warm_trials_raises(self) -> None:
        """warm 状態で 5 回未満なら不完全データとして送出する（R10-1/R10-5）。"""
        # 全 5 試行だが warm は 1 件のみ → warm p95 の算出要件を満たさない。
        trials = [
            _make_trial(1, 3.1, 0.30, True),
            _make_trial(2, 3.4, 0.40, False),
            _make_trial(3, 3.2, 0.35, False),
            _make_trial(4, 3.6, 0.55, False),
            _make_trial(5, 3.0, 0.38, False),
        ]
        with self.assertRaises(ValueError):
            self.protocol.evaluate_phase(MeasurementPhase.BASELINE, trials)


class CompareToGoalTest(unittest.TestCase):
    """目標比較の単体テスト（R10-4/R10-5/R10-7/R10-8）。"""

    def setUp(self) -> None:
        """各テストで共有する実測プロトコルを用意する。"""
        self.protocol = PerformanceMeasurementProtocol()

    def _measured_record(self, metric: str, value: float) -> MetricRecord:
        """実測済みの :class:`MetricRecord` を生成する補助関数。

        引数:
            metric : 指標名。
            value  : 実測値（秒）。

        戻り値:
            状態 MEASURED の :class:`MetricRecord`。
        """
        return MetricRecord(
            metric=metric,
            value=value,
            unit="秒",
            source="テスト用実測",
            condition="テスト条件",
            status=RecordStatus.MEASURED,
        )

    def test_lcp_meets_goal_when_at_boundary(self) -> None:
        """LCP p50 が目標 2.5 秒ちょうどなら達成（≤ の境界を含む、R10-4）。"""
        record = self._measured_record(METRIC_LCP_P50, LCP_P50_TARGET_SECONDS)
        goal = self.protocol.compare_to_goal(
            record, LCP_P50_TARGET_SECONDS, SOURCE_LCP_TARGET
        )
        self.assertTrue(goal.meets_goal)
        self.assertEqual(goal.diff, 0.0)
        self.assertEqual(goal.status, RecordStatus.MEASURED)

    def test_warm_ttfb_not_meeting_goal_records_positive_diff(self) -> None:
        """warm TTFB p95 が目標 0.8 秒超過なら未達・差分は正値（R10-7）。"""
        record = self._measured_record(METRIC_WARM_TTFB_P95, 1.2)
        goal = self.protocol.compare_to_goal(
            record, WARM_TTFB_P95_TARGET_SECONDS, SOURCE_WARM_TTFB_TARGET
        )
        self.assertFalse(goal.meets_goal)
        # 差分（実測 − 目標）= 1.2 - 0.8 = 0.4（浮動小数の丸め許容）。
        self.assertAlmostEqual(goal.diff, 0.4)
        self.assertEqual(goal.target_source, SOURCE_WARM_TTFB_TARGET)

    def test_undetermined_record_yields_no_judgement(self) -> None:
        """未実測の指標は達成／未達を決めつけない（meets_goal=None、R10-8）。"""
        record = MetricRecord(
            metric=METRIC_LCP_P50,
            value=None,
            unit="秒",
            source="実測ログ未提供",
            condition="テスト条件",
            status=RecordStatus.UNDETERMINED,
        )
        goal = self.protocol.compare_to_goal(
            record, LCP_P50_TARGET_SECONDS, SOURCE_LCP_TARGET
        )
        self.assertIsNone(goal.meets_goal)
        self.assertIsNone(goal.diff)
        self.assertEqual(goal.status, RecordStatus.UNDETERMINED)


class ComparePhasesTest(unittest.TestCase):
    """Baseline/Post_Change 差分の単体テスト（R10-3/R12-4）。"""

    def setUp(self) -> None:
        """各テストで共有する実測プロトコルを用意する。"""
        self.protocol = PerformanceMeasurementProtocol()

    def _five_warm_trials(self, lcp: float, ttfb: float) -> list[Trial]:
        """同一値の warm 試行を 5 件生成する補助関数（p50/p95 が当該値になる）。

        引数:
            lcp  : 各試行に与える LCP 値（秒）。
            ttfb : 各試行に与える TTFB 値（秒）。

        戻り値:
            同一値の warm :class:`Trial` を 5 件収めたリスト。
        """
        return [_make_trial(i, lcp, ttfb, True) for i in range(1, 6)]

    def test_both_phases_measured_yield_delta(self) -> None:
        """双方実測なら差分（Post_Change − Baseline）を確定する（R10-3）。"""
        baseline = self.protocol.evaluate_phase(
            MeasurementPhase.BASELINE, self._five_warm_trials(3.2, 1.0)
        )
        post = self.protocol.evaluate_phase(
            MeasurementPhase.POST_CHANGE, self._five_warm_trials(2.0, 0.4)
        )
        deltas = {d.metric: d for d in self.protocol.compare_phases(baseline, post)}
        self.assertEqual(deltas[METRIC_LCP_P50].status, RecordStatus.MEASURED)
        # LCP: 2.0 - 3.2 = -1.2（改善）。
        self.assertAlmostEqual(deltas[METRIC_LCP_P50].delta, -1.2)
        # warm TTFB: 0.4 - 1.0 = -0.6（改善）。
        self.assertAlmostEqual(deltas[METRIC_WARM_TTFB_P95].delta, -0.6)

    def test_missing_baseline_marks_delta_missing(self) -> None:
        """片側フェーズ欠落は missing と明記し比較を確定扱いしない（R12-4）。"""
        post = self.protocol.evaluate_phase(
            MeasurementPhase.POST_CHANGE, self._five_warm_trials(2.0, 0.4)
        )
        deltas = self.protocol.compare_phases(None, post)
        for delta in deltas:
            self.assertEqual(delta.status, RecordStatus.MISSING)
            self.assertIsNone(delta.delta)


class ValidateTrialTest(unittest.TestCase):
    """試行値のゼロトラスト検証の単体テスト（第三原則3）。"""

    def setUp(self) -> None:
        """各テストで共有する実測プロトコルを用意する。"""
        self.protocol = PerformanceMeasurementProtocol()

    def test_negative_value_raises(self) -> None:
        """負値の実測は不正として握りつぶさず送出する。"""
        # 4 件は正常だが 1 件が負値 → 集計前検証で送出されることを確認する。
        trials = [
            _make_trial(1, 3.1, 0.30, True),
            _make_trial(2, 3.4, 0.40, True),
            _make_trial(3, 3.2, 0.35, True),
            _make_trial(4, 3.6, 0.55, True),
            _make_trial(5, -0.1, 0.38, True),
        ]
        with self.assertRaises(ValueError):
            self.protocol.evaluate_phase(MeasurementPhase.BASELINE, trials)

    def test_non_finite_value_raises(self) -> None:
        """非有限値（NaN 等）の実測は握りつぶさず送出する。"""
        trials = [
            _make_trial(1, 3.1, 0.30, True),
            _make_trial(2, 3.4, 0.40, True),
            _make_trial(3, 3.2, 0.35, True),
            _make_trial(4, 3.6, 0.55, True),
            _make_trial(5, math.nan, 0.38, True),
        ]
        with self.assertRaises(ValueError):
            self.protocol.evaluate_phase(MeasurementPhase.BASELINE, trials)


if __name__ == "__main__":
    # スクリプト直接実行時のエントリーポイント（`python -m unittest` でも実行可能）。
    unittest.main()
