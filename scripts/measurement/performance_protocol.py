"""表示パフォーマンス実測プロトコル（対象ページ `/portfolio/top/`）。

本スクリプトは要件 R10（`.kiro/specs/cost-performance-optimization/requirements.md`）
および設計 `design.md`「Testing Strategy / 統合・スモーク・実測」に基づき、
表示パフォーマンスの実測値を記録・集計・判定するためのプロトコルを提供する。

責務（Single Responsibility）:
    - 測定条件（対象 URL・Lighthouse モバイル相当スロットリング・試行回数 5 回以上）の明示（R10-1, R10-6）。
    - 与えられた試行データ（Lighthouse 実測結果）から
      LCP の p50、warm 状態の TTFB の p95 を単位付きで算出（R10-4, R10-5）。
    - Baseline（現行 Lambda 経由の `/portfolio/top/` GET）と
      Post_Change（静的配信）の実測を同一条件で比較し、差分を値・単位付きで出力（R10-2, R10-3）。
    - 目標（LCP p50 ≤ 2.5 秒、warm TTFB p95 ≤ 0.8 秒）との差分を出典付きで記録（R10-4, R10-5, R10-7）。
    - 未実測指標は `undetermined` と明記し、達成／未達を決めつけない（R10-8, E-7）。

厳守事項:
    - 本スクリプトは実測値を捏造・推測補完しない（フォールバック禁止、第一原則・E-7）。
      入力が存在しない指標は `undetermined` として扱う。
    - 不正な入力（負値・非数値・試行不足など）はエラーを握りつぶさず明示的に送出する
      （ゼロトラスト入力検証、第三原則3）。

出典:
    - 対象 URL・指標・スロットリング・試行回数: requirements.md R10-1。
    - 目標値: R10-4（LCP p50 ≤ 2.5 秒）、R10-5（warm TTFB p95 ≤ 0.8 秒）。
    - 記録スキーマ: 本パッケージ `__init__.py` の共通記録スキーマ。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

# --- 測定条件・目標値の定数（出典を伴う事実。requirements.md R10） ---

# 対象ページ（出典: R10-1、design C2 静的化対象ページ URL 一覧）
TARGET_URL: str = "/portfolio/top/"

# スロットリング条件（出典: R10-1）
THROTTLING_CONDITION: str = "Lighthouse モバイル相当スロットリング"

# 最小試行回数（出典: R10-1「5 回以上」）
MIN_TRIALS: int = 5

# 指標の単位（出典: R10-6「各指標の単位（秒）を明記する」）
UNIT_SECONDS: str = "秒"

# 目標値（単位: 秒）（出典: R10-4 / R10-5）
LCP_P50_TARGET_SECONDS: float = 2.5
WARM_TTFB_P95_TARGET_SECONDS: float = 0.8

# 指標名（記録スキーマの ``metric`` 値。パッケージ __init__ の共通スキーマに準拠）
METRIC_LCP_P50: str = "LCP_p50"
METRIC_WARM_TTFB_P95: str = "warm_TTFB_p95"

# 出典文字列（要件条項への参照。全数値に出典を付す第一原則3 の履行）
SOURCE_LCP_TARGET: str = "requirements.md R10-4（LCP p50 ≤ 2.5 秒）"
SOURCE_WARM_TTFB_TARGET: str = "requirements.md R10-5（warm TTFB p95 ≤ 0.8 秒）"


class RecordStatus(str, Enum):
    """記録の状態区分（フォールバック禁止・推測補完禁止の明示のため）。

    値の意味（出典: パッケージ共通記録スキーマ、R12-3/R12-4、E-7）:
        MEASURED     : 実測値が存在する。
        UNDETERMINED : 未実測。達成／未達を決めつけない（R10-8, R12-3）。
        MISSING      : 比較対象ペアの一方が欠落している（R12-4）。
    """

    MEASURED = "measured"
    UNDETERMINED = "undetermined"
    MISSING = "missing"


class MeasurementPhase(str, Enum):
    """実測フェーズの区分（変更前後の比較のため）。

    値の意味（出典: R10-2, R10-3、Glossary Baseline_Measurement / Post_Change_Measurement）:
        BASELINE    : 変更前の実測（現行 Lambda 経由の `/portfolio/top/` GET）。
        POST_CHANGE : 変更後の実測（静的配信）。
    """

    BASELINE = "Baseline"
    POST_CHANGE = "Post_Change"


@dataclass(frozen=True)
class MeasurementCondition:
    """測定条件を表す不変の値オブジェクト（R10-1, R10-6）。

    属性:
        target_url          : 測定対象 URL。
        throttling          : スロットリング条件。
        min_trials          : 要求される最小試行回数。
        delivery_description : 当該フェーズの配信経路の説明（Lambda 経由／静的配信）。
    """

    target_url: str
    throttling: str
    min_trials: int
    delivery_description: str


@dataclass(frozen=True)
class Trial:
    """Lighthouse による 1 回分の試行結果（実測値）。

    属性:
        index        : 試行番号（1 始まり）。
        lcp_seconds  : LCP（Largest Contentful Paint）実測値（単位: 秒）。
        ttfb_seconds : TTFB（Time To First Byte）実測値（単位: 秒）。
        is_warm      : ウォーム状態（コールドスタートを含まない）での試行なら True（R10-5）。
        source       : 当該試行の出典（Lighthouse レポートのパス等）。

    注意:
        本クラスは実測値のみを保持する。値の検証は生成時に
        :func:`_validate_trial` で行い、不正値は握りつぶさず送出する。
    """

    index: int
    lcp_seconds: float
    ttfb_seconds: float
    is_warm: bool
    source: str


@dataclass(frozen=True)
class MetricRecord:
    """単一指標の記録（パッケージ共通記録スキーマに準拠）。

    属性:
        metric    : 指標名（例: ``LCP_p50``）。
        value     : 実測値（数値）。未実測時は None。
        unit      : 単位（秒）。
        source    : 出典。
        condition : 測定条件の要約文字列。
        status    : :class:`RecordStatus`。
    """

    metric: str
    value: Optional[float]
    unit: str
    source: str
    condition: str
    status: RecordStatus


@dataclass(frozen=True)
class GoalComparison:
    """指標と目標値の比較結果（R10-4, R10-5, R10-7, R10-8）。

    属性:
        metric        : 指標名。
        measured      : 実測値（未実測時は None）。
        target        : 目標値（単位: 秒）。
        unit          : 単位（秒）。
        diff          : 実測値 − 目標値（単位: 秒）。未実測時は None。
        meets_goal    : 達成なら True、未達なら False、未実測なら None（決めつけない、R10-8）。
        target_source : 目標値の出典。
        status        : :class:`RecordStatus`。
    """

    metric: str
    measured: Optional[float]
    target: float
    unit: str
    diff: Optional[float]
    meets_goal: Optional[bool]
    target_source: str
    status: RecordStatus


@dataclass(frozen=True)
class PhaseResult:
    """1 フェーズ分の集計結果（LCP p50・warm TTFB p95 とその目標比較）。

    属性:
        phase             : :class:`MeasurementPhase`。
        condition         : 当該フェーズの測定条件。
        trial_count       : 有効試行数。
        warm_trial_count  : ウォーム状態の試行数。
        lcp_p50           : LCP p50 の :class:`MetricRecord`。
        warm_ttfb_p95     : warm TTFB p95 の :class:`MetricRecord`。
        lcp_goal          : LCP p50 の :class:`GoalComparison`。
        warm_ttfb_goal    : warm TTFB p95 の :class:`GoalComparison`。
    """

    phase: MeasurementPhase
    condition: MeasurementCondition
    trial_count: int
    warm_trial_count: int
    lcp_p50: MetricRecord
    warm_ttfb_p95: MetricRecord
    lcp_goal: GoalComparison
    warm_ttfb_goal: GoalComparison


@dataclass(frozen=True)
class PhaseDelta:
    """Baseline と Post_Change の差分（R10-3）。

    属性:
        metric   : 指標名。
        unit     : 単位（秒）。
        baseline : Baseline の実測値（未実測／欠落時は None）。
        post     : Post_Change の実測値（未実測／欠落時は None）。
        delta    : Post_Change − Baseline（単位: 秒）。いずれか欠落時は None。
        status   : :class:`RecordStatus`（双方 MEASURED のときのみ MEASURED）。
        note     : 欠落理由等の注記。
    """

    metric: str
    unit: str
    baseline: Optional[float]
    post: Optional[float]
    delta: Optional[float]
    status: RecordStatus
    note: str


# --- 純粋関数（副作用なし。値の算出と検証） ---


def percentile_nearest_rank(values: list[float], percentile: float) -> float:
    """nearest-rank 法でパーセンタイルを算出する（実測サンプルの値を返す）。

    nearest-rank 法を採用する理由: 補間を行わず、実際に観測された試行値のみを
    返すため、事実のみを扱う第一原則および「推測補完しない」方針（R10-7, E-7）に
    最も忠実である。

    定義: 昇順ソートした値列に対し、順位 ``ceil(percentile / 100 * n)``（1 始まり）
    の値を返す（n は要素数）。

    引数:
        values     : 実測値の列（単位: 秒）。空であってはならない。
        percentile : パーセンタイル（0 < percentile ≤ 100）。

    戻り値:
        指定パーセンタイルに対応する実測値（単位: 秒）。

    例外:
        ValueError: ``values`` が空、または ``percentile`` が範囲外の場合。
                    （フォールバックせず明示的に送出する）
    """
    # ゼロトラスト入力検証: 空列は誤った統計値を生むため明示的に拒否する。
    if not values:
        raise ValueError("パーセンタイル算出には 1 件以上の実測値が必要です（空列は不可）。")
    # パーセンタイルの範囲検証（0 < p ≤ 100）。範囲外は握りつぶさず送出する。
    if not 0 < percentile <= 100:
        raise ValueError(
            f"percentile は 0 < percentile ≤ 100 の範囲でなければなりません: {percentile}"
        )
    ordered = sorted(values)  # 昇順に並べ替え、順位計算の前提を整える。
    # nearest-rank の順位（1 始まり）を計算し、0 始まりのインデックスへ変換する。
    rank = math.ceil(percentile / 100 * len(ordered))
    index = rank - 1
    return ordered[index]


def _validate_trial(trial: Trial) -> None:
    """試行値の妥当性を検証する（ゼロトラスト入力検証、第三原則3）。

    引数:
        trial : 検証対象の :class:`Trial`。

    例外:
        ValueError: LCP/TTFB が非数値・非有限・負値の場合、または試行番号が 1 未満の場合。
                    （不正値を握りつぶして集計に混入させないため明示的に送出する）
    """
    # 試行番号は 1 始まりの正の整数でなければならない。
    if trial.index < 1:
        raise ValueError(f"試行番号は 1 以上でなければなりません: {trial.index}")
    # LCP・TTFB は有限かつ非負の実測秒数でなければならない。
    for metric_name, seconds in (("LCP", trial.lcp_seconds), ("TTFB", trial.ttfb_seconds)):
        if not math.isfinite(seconds):
            raise ValueError(
                f"試行 {trial.index} の {metric_name} が有限値ではありません: {seconds}"
            )
        if seconds < 0:
            raise ValueError(
                f"試行 {trial.index} の {metric_name} が負値です（不正な実測値）: {seconds}"
            )


def _condition_summary(condition: MeasurementCondition) -> str:
    """測定条件を人間可読な 1 行要約へ整形する（R10-6 の条件明記のため）。

    引数:
        condition : :class:`MeasurementCondition`。

    戻り値:
        対象 URL・スロットリング・最小試行回数・配信経路を含む要約文字列。
    """
    return (
        f"対象URL={condition.target_url}, スロットリング={condition.throttling}, "
        f"最小試行回数={condition.min_trials}回以上, 配信経路={condition.delivery_description}"
    )


# --- フェーズ既定の測定条件（R10-2 の同一条件比較を担保するための正本） ---

# Baseline（変更前）: 現行 Lambda 経由の `/portfolio/top/` GET（出典: R10-2, E-2）。
BASELINE_CONDITION: MeasurementCondition = MeasurementCondition(
    target_url=TARGET_URL,
    throttling=THROTTLING_CONDITION,
    min_trials=MIN_TRIALS,
    delivery_description="現行 Lambda 経由（Django on Lambda が動的レンダリング）",
)

# Post_Change（変更後）: 静的配信（S3 + CloudFront OAC）（出典: R10-3, design 目標アーキテクチャ）。
POST_CHANGE_CONDITION: MeasurementCondition = MeasurementCondition(
    target_url=TARGET_URL,
    throttling=THROTTLING_CONDITION,
    min_trials=MIN_TRIALS,
    delivery_description="静的配信（S3 + CloudFront OAC、Lambda 非経由）",
)


class PerformanceMeasurementProtocol:
    """表示パフォーマンス実測プロトコル本体（フェーズ集計・目標比較・前後差分）。

    単一責務: 実測試行データを受け取り、LCP p50 と warm TTFB p95 を算出し、
    目標値および Baseline/Post_Change 間の差分を出典・単位付きで導出する。
    副作用（入出力）は持たず、記録の入出力は本クラス外（main 等）が担う。
    """

    def _select_condition(self, phase: MeasurementPhase) -> MeasurementCondition:
        """フェーズに対応する既定測定条件を返す（同一条件比較の担保、R10-2）。

        引数:
            phase : :class:`MeasurementPhase`。

        戻り値:
            当該フェーズの :class:`MeasurementCondition`。
        """
        # フェーズと条件の対応は正本定数で固定し、条件の取り違えを防ぐ。
        if phase is MeasurementPhase.BASELINE:
            return BASELINE_CONDITION
        return POST_CHANGE_CONDITION

    def evaluate_phase(self, phase: MeasurementPhase, trials: list[Trial]) -> PhaseResult:
        """1 フェーズ分の試行から LCP p50 と warm TTFB p95 を集計する。

        引数:
            phase  : :class:`MeasurementPhase`。
            trials : 当該フェーズの試行列（実測値）。空リストは未実測を意味する。

        戻り値:
            :class:`PhaseResult`。未実測（空リスト等）の指標は
            ``RecordStatus.UNDETERMINED`` として記録し、達成／未達を決めつけない（R10-8）。

        例外:
            ValueError: 試行値が不正、または試行数が要求（5 回以上）に満たないのに
                        0 件でない場合（推測を招く不完全データを握りつぶさない、R10-1）。
        """
        condition = self._select_condition(phase)
        condition_text = _condition_summary(condition)

        # 各試行をゼロトラストで検証する（不正値を集計へ混入させない）。
        for trial in trials:
            _validate_trial(trial)

        # LCP p50 の算出。試行が 0 件なら未実測（undetermined）とする（R10-8）。
        lcp_record = self._build_lcp_p50_record(trials, condition_text, condition.min_trials)

        # warm TTFB p95 の算出。ウォーム状態の試行のみを対象とする（R10-5）。
        warm_trials = [t for t in trials if t.is_warm]
        warm_ttfb_record = self._build_warm_ttfb_p95_record(
            warm_trials, condition_text, condition.min_trials
        )

        # 目標比較（LCP p50 ≤ 2.5 秒、warm TTFB p95 ≤ 0.8 秒）。
        lcp_goal = self.compare_to_goal(
            lcp_record, LCP_P50_TARGET_SECONDS, SOURCE_LCP_TARGET
        )
        warm_ttfb_goal = self.compare_to_goal(
            warm_ttfb_record, WARM_TTFB_P95_TARGET_SECONDS, SOURCE_WARM_TTFB_TARGET
        )

        return PhaseResult(
            phase=phase,
            condition=condition,
            trial_count=len(trials),
            warm_trial_count=len(warm_trials),
            lcp_p50=lcp_record,
            warm_ttfb_p95=warm_ttfb_record,
            lcp_goal=lcp_goal,
            warm_ttfb_goal=warm_ttfb_goal,
        )

    def _build_lcp_p50_record(
        self, trials: list[Trial], condition_text: str, min_trials: int
    ) -> MetricRecord:
        """LCP p50 の :class:`MetricRecord` を構築する（R10-4, R10-6）。

        引数:
            trials         : 当該フェーズの全試行。
            condition_text : 測定条件の要約。
            min_trials     : 要求される最小試行回数。

        戻り値:
            LCP p50 の記録。0 件なら undetermined。

        例外:
            ValueError: 試行が 0 件でないのに ``min_trials`` 未満の場合。
        """
        # 0 件は未実測。達成／未達を決めつけず undetermined とする（R10-8）。
        if not trials:
            return MetricRecord(
                metric=METRIC_LCP_P50,
                value=None,
                unit=UNIT_SECONDS,
                source="実測ログ未提供",
                condition=condition_text,
                status=RecordStatus.UNDETERMINED,
            )
        # 5 回以上の要求を満たさない不完全データは推測を招くため明示的に拒否する（R10-1）。
        if len(trials) < min_trials:
            raise ValueError(
                f"LCP p50 の算出には {min_trials} 回以上の試行が必要です"
                f"（受領: {len(trials)} 回、R10-1）。"
            )
        lcp_values = [t.lcp_seconds for t in trials]
        p50 = percentile_nearest_rank(lcp_values, 50)
        # 出典に各試行の出典を連結し、事実の追跡性を確保する（第一原則3）。
        sources = "; ".join(t.source for t in trials)
        return MetricRecord(
            metric=METRIC_LCP_P50,
            value=p50,
            unit=UNIT_SECONDS,
            source=f"全 {len(trials)} 試行の LCP（nearest-rank p50）。試行出典: {sources}",
            condition=condition_text,
            status=RecordStatus.MEASURED,
        )

    def _build_warm_ttfb_p95_record(
        self, warm_trials: list[Trial], condition_text: str, min_trials: int
    ) -> MetricRecord:
        """warm TTFB p95 の :class:`MetricRecord` を構築する（R10-5, R10-6）。

        引数:
            warm_trials    : ウォーム状態の試行のみ。
            condition_text : 測定条件の要約。
            min_trials     : 要求される最小試行回数。

        戻り値:
            warm TTFB p95 の記録。warm 試行が 0 件なら undetermined。

        例外:
            ValueError: warm 試行が 0 件でないのに ``min_trials`` 未満の場合。
        """
        # warm 試行が 0 件なら未実測。undetermined とする（R10-8）。
        if not warm_trials:
            return MetricRecord(
                metric=METRIC_WARM_TTFB_P95,
                value=None,
                unit=UNIT_SECONDS,
                source="warm 状態の実測ログ未提供",
                condition=condition_text,
                status=RecordStatus.UNDETERMINED,
            )
        # warm 状態で 5 回以上の要求を満たさない場合は不完全データとして拒否する（R10-1, R10-5）。
        if len(warm_trials) < min_trials:
            raise ValueError(
                f"warm TTFB p95 の算出には warm 状態で {min_trials} 回以上の試行が必要です"
                f"（受領: {len(warm_trials)} 回、R10-1/R10-5）。"
            )
        ttfb_values = [t.ttfb_seconds for t in warm_trials]
        p95 = percentile_nearest_rank(ttfb_values, 95)
        sources = "; ".join(t.source for t in warm_trials)
        return MetricRecord(
            metric=METRIC_WARM_TTFB_P95,
            value=p95,
            unit=UNIT_SECONDS,
            source=(
                f"warm 状態 全 {len(warm_trials)} 試行の TTFB（nearest-rank p95）。"
                f"試行出典: {sources}"
            ),
            condition=condition_text,
            status=RecordStatus.MEASURED,
        )

    def compare_to_goal(
        self, record: MetricRecord, target: float, target_source: str
    ) -> GoalComparison:
        """指標記録を目標値と比較する（R10-4, R10-5, R10-7, R10-8）。

        引数:
            record        : 対象指標の :class:`MetricRecord`。
            target        : 目標値（単位: 秒）。
            target_source : 目標値の出典。

        戻り値:
            :class:`GoalComparison`。未実測（value が None）の場合は達成／未達を
            決めつけず ``meets_goal=None``・``status=UNDETERMINED`` とする（R10-8）。
        """
        # 未実測の指標は達成／未達を判定しない（決めつけ禁止、R10-8）。
        if record.status is not RecordStatus.MEASURED or record.value is None:
            return GoalComparison(
                metric=record.metric,
                measured=None,
                target=target,
                unit=UNIT_SECONDS,
                diff=None,
                meets_goal=None,
                target_source=target_source,
                status=RecordStatus.UNDETERMINED,
            )
        # 実測値と目標値の差分（実測 − 目標、単位: 秒）を算出する（R10-7）。
        diff = record.value - target
        # 目標は上限（≤）であるため、実測値が目標以下なら達成とする。
        meets_goal = record.value <= target
        return GoalComparison(
            metric=record.metric,
            measured=record.value,
            target=target,
            unit=UNIT_SECONDS,
            diff=diff,
            meets_goal=meets_goal,
            target_source=target_source,
            status=RecordStatus.MEASURED,
        )

    def compare_phases(
        self,
        baseline: Optional[PhaseResult],
        post_change: Optional[PhaseResult],
    ) -> list[PhaseDelta]:
        """Baseline と Post_Change の同一指標を比較し差分を導出する（R10-3, R12-4）。

        引数:
            baseline    : Baseline の :class:`PhaseResult`。未実施なら None。
            post_change : Post_Change の :class:`PhaseResult`。未実施なら None。

        戻り値:
            指標ごとの :class:`PhaseDelta` の一覧。フェーズ欠落側は ``missing``、
            指標未実測は ``undetermined`` と明記し、比較を確定扱いしない（R12-4）。
        """
        deltas: list[PhaseDelta] = []
        # LCP p50 と warm TTFB p95 の 2 指標について、それぞれ差分を導出する。
        for metric_name, base_record, post_record in (
            (
                METRIC_LCP_P50,
                baseline.lcp_p50 if baseline is not None else None,
                post_change.lcp_p50 if post_change is not None else None,
            ),
            (
                METRIC_WARM_TTFB_P95,
                baseline.warm_ttfb_p95 if baseline is not None else None,
                post_change.warm_ttfb_p95 if post_change is not None else None,
            ),
        ):
            deltas.append(
                self._build_delta(metric_name, base_record, post_record)
            )
        return deltas

    def _build_delta(
        self,
        metric_name: str,
        base_record: Optional[MetricRecord],
        post_record: Optional[MetricRecord],
    ) -> PhaseDelta:
        """1 指標の Baseline/Post_Change 差分を構築する（R10-3, R12-4）。

        引数:
            metric_name : 指標名。
            base_record : Baseline の記録。フェーズ未実施なら None。
            post_record : Post_Change の記録。フェーズ未実施なら None。

        戻り値:
            :class:`PhaseDelta`。双方が実測値を持つ場合のみ差分を確定し MEASURED とする。
        """
        # フェーズ自体が欠落している場合は missing（比較不能。ペア欠落、R12-4）。
        if base_record is None or post_record is None:
            missing_sides = []
            if base_record is None:
                missing_sides.append("Baseline")
            if post_record is None:
                missing_sides.append("Post_Change")
            return PhaseDelta(
                metric=metric_name,
                unit=UNIT_SECONDS,
                baseline=base_record.value if base_record is not None else None,
                post=post_record.value if post_record is not None else None,
                delta=None,
                status=RecordStatus.MISSING,
                note=f"{'/'.join(missing_sides)} の実測が欠落（missing）。比較は未確定。",
            )
        # 双方のフェーズは存在するが、いずれかの指標が未実測なら undetermined。
        if base_record.value is None or post_record.value is None:
            return PhaseDelta(
                metric=metric_name,
                unit=UNIT_SECONDS,
                baseline=base_record.value,
                post=post_record.value,
                delta=None,
                status=RecordStatus.UNDETERMINED,
                note="いずれかのフェーズで当該指標が未実測（undetermined）。比較は未確定。",
            )
        # 双方実測済み。差分（Post_Change − Baseline、単位: 秒）を確定する（R10-3）。
        delta = post_record.value - base_record.value
        return PhaseDelta(
            metric=metric_name,
            unit=UNIT_SECONDS,
            baseline=base_record.value,
            post=post_record.value,
            delta=delta,
            status=RecordStatus.MEASURED,
            note="Baseline と Post_Change の同一条件実測に基づく差分。",
        )


# --- 入力の読み込み（ゼロトラスト検証。実測データは外部 JSON から供給する） ---

# 入力 JSON のフェーズキー（Baseline / Post_Change）。
_INPUT_KEY_BASELINE: str = "baseline"
_INPUT_KEY_POST_CHANGE: str = "post_change"
# 試行 1 件に必須のフィールド集合。
_TRIAL_REQUIRED_FIELDS: tuple[str, ...] = (
    "index",
    "lcp_seconds",
    "ttfb_seconds",
    "is_warm",
    "source",
)


def _parse_trial(raw: object, position: int) -> Trial:
    """入力 JSON の 1 試行分（辞書）を :class:`Trial` へ変換する。

    引数:
        raw      : 試行 1 件を表す入力（辞書であることを要求）。
        position : 入力配列内の位置（0 始まり。エラーメッセージ用）。

    戻り値:
        変換された :class:`Trial`。

    例外:
        ValueError: 辞書でない、必須フィールドが欠落、または型が不正な場合。
                    （不正入力を握りつぶさず明示送出する。ゼロトラスト）
    """
    # 試行はオブジェクト（辞書）でなければならない。
    if not isinstance(raw, dict):
        raise ValueError(f"{position} 番目の試行がオブジェクトではありません: {type(raw).__name__}")
    # 必須フィールドの欠落を検出する（フォールバックせず明示送出）。
    missing = [key for key in _TRIAL_REQUIRED_FIELDS if key not in raw]
    if missing:
        raise ValueError(
            f"{position} 番目の試行に必須フィールドが不足しています: {', '.join(missing)}"
        )
    # 型検証: 数値・真偽・文字列を厳格に確認する（bool は int のサブクラスのため除外）。
    index = raw["index"]
    if isinstance(index, bool) or not isinstance(index, int):
        raise ValueError(f"{position} 番目の試行の index は整数でなければなりません: {index!r}")
    lcp = raw["lcp_seconds"]
    ttfb = raw["ttfb_seconds"]
    for name, value in (("lcp_seconds", lcp), ("ttfb_seconds", ttfb)):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                f"{position} 番目の試行の {name} は数値でなければなりません: {value!r}"
            )
    is_warm = raw["is_warm"]
    if not isinstance(is_warm, bool):
        raise ValueError(
            f"{position} 番目の試行の is_warm は真偽値でなければなりません: {is_warm!r}"
        )
    source = raw["source"]
    if not isinstance(source, str) or not source.strip():
        raise ValueError(
            f"{position} 番目の試行の source は非空の文字列でなければなりません: {source!r}"
        )
    # 数値・境界の検証は _validate_trial に委譲し、Trial 生成後に呼び出す。
    trial = Trial(
        index=index,
        lcp_seconds=float(lcp),
        ttfb_seconds=float(ttfb),
        is_warm=is_warm,
        source=source,
    )
    _validate_trial(trial)
    return trial


def _parse_phase_trials(raw_phase: object, phase_key: str) -> list[Trial]:
    """入力 JSON の 1 フェーズ分から試行リストを構築する。

    引数:
        raw_phase : フェーズを表す入力（``{"trials": [...]}`` を要求）。
        phase_key : フェーズキー（エラーメッセージ用）。

    戻り値:
        :class:`Trial` の一覧。

    例外:
        ValueError: 構造が不正（辞書でない・trials が配列でない等）の場合。
    """
    # フェーズはオブジェクトでなければならない。
    if not isinstance(raw_phase, dict):
        raise ValueError(f"フェーズ '{phase_key}' はオブジェクトではありません。")
    # trials キーは配列でなければならない。
    trials_raw = raw_phase.get("trials")
    if not isinstance(trials_raw, list):
        raise ValueError(f"フェーズ '{phase_key}' の trials は配列でなければなりません。")
    # 各試行を順に変換する。
    return [_parse_trial(item, position) for position, item in enumerate(trials_raw)]


def load_measurements(path: Path) -> dict[str, Optional[list[Trial]]]:
    """実測入力 JSON を読み込み、フェーズ別の試行リストへ変換する。

    引数:
        path : 入力 JSON ファイルのパス。

    戻り値:
        ``{"baseline": [...]|None, "post_change": [...]|None}``。
        当該フェーズのキーが存在しない場合は None（＝未実施）。

    例外:
        FileNotFoundError: ファイルが存在しない場合。
        ValueError: JSON 構造が不正な場合（フォールバックせず明示送出）。
    """
    # ファイルの存在を明示的に確認する（存在しなければ握りつぶさず送出）。
    if not path.is_file():
        raise FileNotFoundError(f"入力ファイルが存在しません: {path}")
    # UTF-8 で読み込み、JSON として解釈する。
    raw_text = path.read_text(encoding="utf-8")
    document = json.loads(raw_text)
    # ルートはオブジェクトでなければならない。
    if not isinstance(document, dict):
        raise ValueError("入力 JSON のルートはオブジェクトでなければなりません。")
    result: dict[str, Optional[list[Trial]]] = {
        _INPUT_KEY_BASELINE: None,
        _INPUT_KEY_POST_CHANGE: None,
    }
    # フェーズキーが存在する場合のみ試行を解釈する（未提供フェーズは None のまま）。
    for phase_key in (_INPUT_KEY_BASELINE, _INPUT_KEY_POST_CHANGE):
        if phase_key in document:
            result[phase_key] = _parse_phase_trials(document[phase_key], phase_key)
    return result


# --- 記録の直列化（共通記録スキーマに沿った辞書化） ---


def _metric_record_to_dict(record: MetricRecord) -> dict[str, object]:
    """:class:`MetricRecord` を共通記録スキーマの辞書へ変換する。"""
    return {
        "metric": record.metric,
        "value": record.value,
        "unit": record.unit,
        "source": record.source,
        "condition": record.condition,
        "status": record.status.value,
    }


def _goal_to_dict(goal: GoalComparison) -> dict[str, object]:
    """:class:`GoalComparison` を辞書へ変換する（目標・差分・達成判定を含む）。"""
    return {
        "metric": goal.metric,
        "measured": goal.measured,
        "target": goal.target,
        "unit": goal.unit,
        "diff": goal.diff,
        "meets_goal": goal.meets_goal,
        "target_source": goal.target_source,
        "status": goal.status.value,
    }


def _phase_result_to_dict(result: PhaseResult) -> dict[str, object]:
    """:class:`PhaseResult` を辞書へ変換する（フェーズ集計の全体）。"""
    return {
        "phase": result.phase.value,
        "condition": {
            "target_url": result.condition.target_url,
            "throttling": result.condition.throttling,
            "min_trials": result.condition.min_trials,
            "delivery_description": result.condition.delivery_description,
        },
        "trial_count": result.trial_count,
        "warm_trial_count": result.warm_trial_count,
        "metrics": {
            "lcp_p50": _metric_record_to_dict(result.lcp_p50),
            "warm_ttfb_p95": _metric_record_to_dict(result.warm_ttfb_p95),
        },
        "goals": {
            "lcp_p50": _goal_to_dict(result.lcp_goal),
            "warm_ttfb_p95": _goal_to_dict(result.warm_ttfb_goal),
        },
    }


def _delta_to_dict(delta: PhaseDelta) -> dict[str, object]:
    """:class:`PhaseDelta` を辞書へ変換する（前後差分）。"""
    return {
        "metric": delta.metric,
        "unit": delta.unit,
        "baseline": delta.baseline,
        "post_change": delta.post,
        "delta": delta.delta,
        "status": delta.status.value,
        "note": delta.note,
    }


def build_report(
    protocol: PerformanceMeasurementProtocol,
    baseline: Optional[PhaseResult],
    post_change: Optional[PhaseResult],
) -> dict[str, object]:
    """フェーズ結果と前後差分をまとめた直列化可能なレポート辞書を構築する。

    引数:
        protocol    : 差分算出に用いる :class:`PerformanceMeasurementProtocol`。
        baseline    : Baseline の :class:`PhaseResult`（未実施なら None）。
        post_change : Post_Change の :class:`PhaseResult`（未実施なら None）。

    戻り値:
        測定条件・目標・各フェーズ結果・前後差分を含むレポート辞書。
    """
    deltas = protocol.compare_phases(baseline, post_change)
    return {
        "feature": "cost-performance-optimization",
        "target_url": TARGET_URL,
        "throttling": THROTTLING_CONDITION,
        "min_trials": MIN_TRIALS,
        "unit": UNIT_SECONDS,
        "goals": {
            "lcp_p50_max": {"value": LCP_P50_TARGET_SECONDS, "source": SOURCE_LCP_TARGET},
            "warm_ttfb_p95_max": {
                "value": WARM_TTFB_P95_TARGET_SECONDS,
                "source": SOURCE_WARM_TTFB_TARGET,
            },
        },
        "phases": {
            _INPUT_KEY_BASELINE: (
                _phase_result_to_dict(baseline) if baseline is not None else None
            ),
            _INPUT_KEY_POST_CHANGE: (
                _phase_result_to_dict(post_change) if post_change is not None else None
            ),
        },
        "deltas": [_delta_to_dict(delta) for delta in deltas],
    }


def _format_value(value: Optional[float], unit: str, status: RecordStatus) -> str:
    """数値と状態を人間可読な文字列へ整形する（未実測は undetermined と明記）。

    引数:
        value  : 数値（未実測時は None）。
        unit   : 単位。
        status : :class:`RecordStatus`。

    戻り値:
        実測済みなら ``"<値> <単位>"``、未実測なら ``"undetermined"``、
        欠落なら ``"missing"``。決めつけを避けるための明示表記（R10-8, R12-4）。
    """
    # 状態に応じて明示表記を返す（推測補完しない）。
    if status is RecordStatus.MEASURED and value is not None:
        return f"{value:.3f} {unit}"
    if status is RecordStatus.MISSING:
        return "missing"
    return "undetermined"


def render_report_text(report: dict[str, object]) -> str:
    """レポート辞書を人間可読なテキストへ整形する（コンソール確認・記録用）。

    引数:
        report : :func:`build_report` が返すレポート辞書。

    戻り値:
        測定条件・各フェーズの指標・目標判定・前後差分を含む複数行文字列。
    """
    # レポートは検証済みの構造を前提とするが、可読化のみを担い数値は改変しない。
    lines: list[str] = []
    lines.append("表示パフォーマンス実測レポート（cost-performance-optimization）")
    lines.append(
        f"測定条件: 対象URL={report['target_url']}, スロットリング={report['throttling']}, "
        f"最小試行回数={report['min_trials']}回以上, 単位={report['unit']}"
    )
    goals = report["goals"]
    assert isinstance(goals, dict)  # 構造前提の明示（build_report が保証）。
    lines.append(
        f"目標: LCP p50 ≤ {goals['lcp_p50_max']['value']} 秒 / "
        f"warm TTFB p95 ≤ {goals['warm_ttfb_p95_max']['value']} 秒"
    )
    phases = report["phases"]
    assert isinstance(phases, dict)
    # 各フェーズの指標と目標判定を出力する。
    for phase_key in (_INPUT_KEY_BASELINE, _INPUT_KEY_POST_CHANGE):
        phase = phases[phase_key]
        lines.append("")
        if phase is None:
            lines.append(f"[{phase_key}] 未実施（missing）: 実測が提供されていません。")
            continue
        assert isinstance(phase, dict)
        lines.append(
            f"[{phase['phase']}] 試行数={phase['trial_count']}"
            f"（warm={phase['warm_trial_count']}）, 配信経路={phase['condition']['delivery_description']}"
        )
        for metric_key in ("lcp_p50", "warm_ttfb_p95"):
            metric = phase["metrics"][metric_key]
            goal = phase["goals"][metric_key]
            metric_status = RecordStatus(metric["status"])
            goal_status = RecordStatus(goal["status"])
            measured_text = _format_value(metric["value"], metric["unit"], metric_status)
            # 達成判定は未実測時に None のまま（決めつけない、R10-8）。
            if goal_status is RecordStatus.MEASURED:
                judged = "達成" if goal["meets_goal"] else "未達"
                diff_text = f"{goal['diff']:+.3f} {goal['unit']}"
            else:
                judged = "undetermined（達成/未達を決めつけない）"
                diff_text = "undetermined"
            lines.append(
                f"  - {metric['metric']}: 実測={measured_text}, "
                f"目標={goal['target']} {goal['unit']}, 差分(実測-目標)={diff_text}, 判定={judged}"
            )
            lines.append(f"      出典: {metric['source']}")
    # 前後差分（Post_Change − Baseline）を出力する。
    lines.append("")
    lines.append("前後差分（Post_Change − Baseline）:")
    deltas = report["deltas"]
    assert isinstance(deltas, list)
    for delta in deltas:
        assert isinstance(delta, dict)
        delta_status = RecordStatus(delta["status"])
        if delta_status is RecordStatus.MEASURED:
            delta_text = f"{delta['delta']:+.3f} {delta['unit']}"
        elif delta_status is RecordStatus.MISSING:
            delta_text = "missing"
        else:
            delta_text = "undetermined"
        lines.append(f"  - {delta['metric']}: {delta_text} … {delta['note']}")
    return "\n".join(lines)


# --- CLI エントリーポイント（実測入力の読み込みとレポート出力） ---


def _build_argument_parser() -> argparse.ArgumentParser:
    """コマンドライン引数パーサを構築する。

    戻り値:
        構成済みの :class:`argparse.ArgumentParser`。
    """
    parser = argparse.ArgumentParser(
        description=(
            "表示パフォーマンス実測プロトコル（対象 /portfolio/top/）。"
            "Lighthouse モバイル相当スロットリング・5 回以上の試行から "
            "LCP p50・warm TTFB p95 を算出し、Baseline/Post_Change を比較する。"
        )
    )
    # 実測入力 JSON（未指定時は実測未提供として全指標 undetermined を出力する）。
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="実測入力 JSON のパス（baseline/post_change の trials を含む）。未指定時は全指標 undetermined。",
    )
    # 出力形式（既定は人間可読テキスト。--json で機械可読 JSON を出力）。
    parser.add_argument(
        "--json",
        action="store_true",
        help="レポートを JSON 形式で出力する（既定はテキスト）。",
    )
    # レポートの書き出し先（未指定時は標準出力）。
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="レポートの書き出し先パス（未指定時は標準出力）。",
    )
    return parser


def _evaluate_optional_phase(
    protocol: PerformanceMeasurementProtocol,
    phase: MeasurementPhase,
    trials: Optional[list[Trial]],
) -> Optional[PhaseResult]:
    """試行が提供されたフェーズのみ集計する（未提供フェーズは None を返す）。

    引数:
        protocol : :class:`PerformanceMeasurementProtocol`。
        phase    : 対象フェーズ。
        trials   : 試行列。未提供なら None。

    戻り値:
        集計結果、または未提供時は None。
    """
    # 未提供フェーズは None のまま返す（比較時に missing として扱う、R12-4）。
    if trials is None:
        return None
    return protocol.evaluate_phase(phase, trials)


def run(input_path: Optional[Path]) -> dict[str, object]:
    """入力パスから実測を読み込みレポート辞書を生成する（副作用は読み込みのみ）。

    引数:
        input_path : 実測入力 JSON のパス。None のとき実測未提供として扱う。

    戻り値:
        :func:`build_report` のレポート辞書。

    例外:
        FileNotFoundError / ValueError: 入力が不正な場合（握りつぶさず送出）。
    """
    protocol = PerformanceMeasurementProtocol()
    # 入力未指定なら両フェーズ未提供（全指標 undetermined）とする。
    if input_path is None:
        measurements: dict[str, Optional[list[Trial]]] = {
            _INPUT_KEY_BASELINE: None,
            _INPUT_KEY_POST_CHANGE: None,
        }
    else:
        measurements = load_measurements(input_path)
    baseline_result = _evaluate_optional_phase(
        protocol, MeasurementPhase.BASELINE, measurements[_INPUT_KEY_BASELINE]
    )
    post_change_result = _evaluate_optional_phase(
        protocol, MeasurementPhase.POST_CHANGE, measurements[_INPUT_KEY_POST_CHANGE]
    )
    return build_report(protocol, baseline_result, post_change_result)


def main(argv: Optional[list[str]] = None) -> int:
    """CLI エントリーポイント。実測を読み込みレポートを出力する。

    引数:
        argv : コマンドライン引数（テスト用に注入可能）。None のとき ``sys.argv`` を使用。

    戻り値:
        終了コード（0=正常、1=入力エラー）。

    注意:
        入力エラーは握りつぶさず標準エラーへ明示出力し、非ゼロ終了で呼び出し元へ通知する
        （フォールバック禁止、第三原則3）。
    """
    parser = _build_argument_parser()
    args = parser.parse_args(argv)

    # 入力読み込み・集計。不正入力は明示的に報告し非ゼロ終了する（握りつぶさない）。
    try:
        report = run(args.input)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as error:
        print(f"実測入力の処理に失敗しました: {error}", file=sys.stderr)
        return 1

    # 出力の整形（JSON かテキストか）。
    if args.json:
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
    else:
        rendered = render_report_text(report)

    # 出力先へ書き出す（未指定時は標準出力）。
    if args.output is None:
        print(rendered)
    else:
        args.output.write_text(rendered + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    # スクリプト直接実行時のエントリーポイント。終了コードを OS へ伝播する。
    sys.exit(main())
