"""コールドスタート実測プロトコル（cost-performance-optimization / Task 8.3）。

本モジュールは要件 R11（コールドスタート目標の定義と実測）を満たすための
「測定条件の明示」「サンプル分類」「p95 算出」「目標／Baseline との対比」「未実測の
明示（undetermined）」を担う成果物である。出典は次のとおり。

- 要件: `.kiro/specs/cost-performance-optimization/requirements.md` Requirement 11
  （11.1 Baseline=現行 Lambda 経由 `/portfolio/top/` GET の Cold Start p95、
   11.2 Contact_Function の許容目標値の定義枠、11.3 Post_Change 実測、
   11.4 測定条件・単位（秒）・p95 の明記と目標／Baseline 対比、
   11.5 未実測は `undetermined`（「許容」と決めつけない）、
   11.6 未達時は実測値と目標値の差分を出典付きで記録・推測補完しない）。
- 設計: `.kiro/specs/cost-performance-optimization/design.md` C3（コールドスタート傾向）、
  「実測駆動」、Error Handling（フォールバック禁止）。
- 品質原則: `.kiro/steering/principles.md` 第一原則（事実のみ・出典必須・未確認は明示）、
  第三原則3（フォールバック禁止）、既往インシデント E-7。
- サンプル分類方針: `.agents/skills/performance-verification/SKILL.md`
  （warm／recovery_after_failure_first_success を cold-start として報告しない）。

本モジュールは AWS API 呼び出し・デプロイ・ネットワークアクセスを行わない。
外部で実測した生サンプル（応答時間・分類・HTTP ステータス・出典）を受け取り、
測定条件付きで p95 を算出し、目標／Baseline と対比した記録を生成する責務のみを持つ。
未実測・不足は `undetermined`、Baseline/Post_Change ペアの片側欠落は `missing` と明記し、
値を推測補完しない（フォールバック禁止）。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Final

# --- 定数（単位・パーセンタイル・最小試行回数・未確定マーカー） ---------------

# 未実測（一次測定ログが存在しない）ことを表す明示マーカー（R11.5 / R12-3）。
UNDETERMINED: Final[str] = "undetermined"
# Baseline/Post_Change ペアの片側が欠落していることを表す明示マーカー（R12-4）。
MISSING: Final[str] = "missing"
# すべての時間値の単位（秒）。R11.4 で単位（秒）の明記が必須。
UNIT_SECONDS: Final[str] = "seconds"
# 算出パーセンタイルのラベル（R11.4 で p95 の明記が必須）。
PERCENTILE_LABEL: Final[str] = "p95"
# 算出パーセンタイル値（%）。
PERCENTILE_VALUE: Final[float] = 95.0
# コールドスタート誘発条件下での最小試行回数（R11.1 / R11.3: 5 回以上）。
MINIMUM_TRIALS: Final[int] = 5


class SampleClassification(Enum):
    """コールドスタート実測サンプルの分類。

    performance-verification スキルの方針に従い、cold-start として集計してよいのは
    `COLD_LIKE_FIRST_REQUEST` のみとする。warm 済み・障害復帰直後の初回成功・無効を
    cold-start として報告しない（既往インシデント E-7 の再発防止）。
    """

    # ウォーム済み実行環境が存在しない状態での初回リクエストに対する応答（cold-start 相当）。
    COLD_LIKE_FIRST_REQUEST = "cold_like_first_request"
    # ウォーム済み（安定後）サンプル。cold-start として集計しない。
    WARM = "warm"
    # HTTP 500 等の失敗後の最初の成功。cold-start ではなく障害復帰の初回成功として区別する。
    RECOVERY_AFTER_FAILURE_FIRST_SUCCESS = "recovery_after_failure_first_success"
    # 無効サンプル（測定条件を満たさない・500 等）。集計対象外。
    INVALID = "invalid"


class MeasurementPhase(Enum):
    """測定フェーズ。変更前後の実測でのみ効果を主張する（R11.1 / R11.3、E-7）。"""

    # 変更前の実測。本タスクでは現行表示経路（Lambda 経由 `/portfolio/top/` GET）が対象。
    BASELINE = "Baseline"
    # 変更後の実測。本タスクでは Contact_Function のコールドスタートが対象。
    POST_CHANGE = "Post_Change"


def percentile_nearest_rank(values: list[float], percentile: float) -> float:
    """最近接順位法（nearest-rank method）でパーセンタイル値を算出する。

    算出手順を明示することで、記録の再現性を担保する（R11.4）。
    昇順ソート後、順位 rank = ceil(percentile/100 * N) の値を返す（1 始まり、範囲内へ丸め）。

    Args:
        values: 応答時間（秒）のサンプル列。空であってはならない。
        percentile: 算出するパーセンタイル（0 < percentile <= 100）。

    Returns:
        指定パーセンタイルに対応するサンプル値（秒）。

    Raises:
        ValueError: values が空、または percentile が範囲外の場合（フォールバックしない）。
    """
    # 空サンプルは推測補完せず明示的に失敗させる（フォールバック禁止）。
    if not values:
        raise ValueError("パーセンタイル算出には 1 件以上のサンプルが必要です。")
    # パーセンタイルの定義域を検証する。
    if not 0.0 < percentile <= 100.0:
        raise ValueError("percentile は 0 より大きく 100 以下である必要があります。")
    # 昇順に整列する。
    ordered = sorted(values)
    # 最近接順位を算出し、1..N の範囲へ丸める。
    rank = math.ceil(percentile / 100.0 * len(ordered))
    rank = min(max(rank, 1), len(ordered))
    # 1 始まりの順位を 0 始まり添字へ変換して返す。
    return ordered[rank - 1]


@dataclass(frozen=True)
class ColdStartSample:
    """コールドスタート実測の 1 試行分のサンプル（不変値オブジェクト）。

    Attributes:
        response_time_seconds: 応答時間（単位: 秒）。有限かつ 0 以上。
        classification: サンプル分類（SampleClassification）。
        http_status: HTTP ステータスコード（cold-start 集計は 2xx のみ有効）。
        source: 出典（実測ログのファイルパス・コマンド出力等、単位付き根拠）。
    """

    response_time_seconds: float
    classification: SampleClassification
    http_status: int
    source: str

    def __post_init__(self) -> None:
        """入力を検証する。不正値は推測補完せず例外送出する（フォールバック禁止）。"""
        # 応答時間は有限の非負数でなければならない（NaN/inf/負値を排除）。
        if not math.isfinite(self.response_time_seconds) or self.response_time_seconds < 0.0:
            raise ValueError("response_time_seconds は有限かつ 0 以上の秒数である必要があります。")
        # HTTP ステータスは整数コードでなければならない。
        if not isinstance(self.http_status, int):
            raise TypeError("http_status は整数のステータスコードである必要があります。")
        # 出典（エビデンス）は必須。空出典を許容しない（第一原則: 出典必須）。
        if not self.source.strip():
            raise ValueError("source（出典）は必須です。空文字を許容しません。")

    def is_valid_cold_start(self) -> bool:
        """このサンプルを cold-start p95 集計に採用できるか判定する。

        採用条件は「cold-like 初回リクエストであり、かつ HTTP 2xx」であること。
        warm・障害復帰初回成功・非 2xx は集計対象外（performance-verification スキル）。
        """
        is_cold_like = self.classification is SampleClassification.COLD_LIKE_FIRST_REQUEST
        is_success = 200 <= self.http_status < 300
        return is_cold_like and is_success


@dataclass(frozen=True)
class MeasurementCondition:
    """測定条件（R11.4 で明記が必須の測定条件・単位・パーセンタイル）。

    Attributes:
        target: 測定対象（対象 URL / ルート / 実行単位）。
        induction_method: コールドスタートを誘発する条件の説明。
        source: 測定条件の出典（要件・設計・構成コードのファイルパス等）。
        minimum_trials: 最小試行回数（既定 5、R11.1 / R11.3）。
        percentile: 算出パーセンタイル（既定 95.0）。
        unit: 時間値の単位（既定 "seconds"）。
    """

    target: str
    induction_method: str
    source: str
    minimum_trials: int = MINIMUM_TRIALS
    percentile: float = PERCENTILE_VALUE
    unit: str = UNIT_SECONDS

    def __post_init__(self) -> None:
        """測定条件を検証する。5 回未満の最小試行回数を許容しない（R11.1 / R11.3）。"""
        # 要件が定める 5 回以上を下回る条件を設定できないようにする。
        if self.minimum_trials < MINIMUM_TRIALS:
            raise ValueError(
                f"minimum_trials は {MINIMUM_TRIALS} 以上である必要があります（R11.1 / R11.3）。"
            )
        # パーセンタイルの定義域を検証する。
        if not 0.0 < self.percentile <= 100.0:
            raise ValueError("percentile は 0 より大きく 100 以下である必要があります。")

    def to_record(self) -> dict[str, object]:
        """測定条件を記録用の辞書へ変換する。"""
        return {
            "target": self.target,
            "induction_method": self.induction_method,
            "minimum_trials": self.minimum_trials,
            "percentile": PERCENTILE_LABEL,
            "unit": self.unit,
            "source": self.source,
        }


@dataclass(frozen=True)
class ColdStartTarget:
    """Contact_Function のコールドスタート許容目標値の定義枠（R11.2）。

    値が未確定の場合は `threshold_seconds=UNDETERMINED` とし、「許容」と決めつけない
    （R11.5）。目標を確定する場合は秒数（float）とパーセンタイルを設定する。

    Attributes:
        component: 目標の対象コンポーネント（例: "Contact_Function"）。
        threshold_seconds: 許容目標の閾値（秒）。未確定は UNDETERMINED。
        percentile: 目標のパーセンタイル（例: 95.0）。未確定は None。
        unit: 単位（既定 "seconds"）。
        source: 目標値の出典（design での定義箇所等）。未確定時はその旨を記す。
    """

    component: str
    threshold_seconds: float | str = UNDETERMINED
    percentile: float | None = None
    unit: str = UNIT_SECONDS
    source: str = "design フェーズで定義予定（未確定のため undetermined）"

    def __post_init__(self) -> None:
        """目標値が数値の場合のみ範囲を検証する。数値でなければ UNDETERMINED を要求する。"""
        # 数値目標が設定された場合は有限の正値であることを検証する。
        if isinstance(self.threshold_seconds, (int, float)):
            if not math.isfinite(float(self.threshold_seconds)) or self.threshold_seconds <= 0.0:
                raise ValueError("threshold_seconds は有限かつ正の秒数である必要があります。")
            # 数値目標にはパーセンタイル指定が必須（R11.2: 秒・パーセンタイル指定）。
            if self.percentile is None:
                raise ValueError("数値目標にはパーセンタイル指定が必須です（R11.2）。")
        elif self.threshold_seconds != UNDETERMINED:
            # 数値でも UNDETERMINED でもない値は許容しない（推測補完・曖昧値の禁止）。
            raise ValueError("threshold_seconds は正の秒数または UNDETERMINED のいずれかです。")

    def is_defined(self) -> bool:
        """目標値が数値として確定しているかを返す。"""
        return isinstance(self.threshold_seconds, (int, float))

    def to_record(self) -> dict[str, object]:
        """目標値を記録用の辞書へ変換する。"""
        return {
            "component": self.component,
            "threshold_seconds": self.threshold_seconds,
            "percentile": PERCENTILE_LABEL if self.percentile is not None else UNDETERMINED,
            "unit": self.unit,
            "source": self.source,
        }


@dataclass
class ColdStartMeasurement:
    """あるフェーズのコールドスタート実測（サンプル集合と p95 算出）。

    Attributes:
        phase: 測定フェーズ（Baseline / Post_Change）。
        condition: 測定条件。
        samples: 実測サンプル列（外部の実測から与えられる）。
    """

    phase: MeasurementPhase
    condition: MeasurementCondition
    samples: list[ColdStartSample] = field(default_factory=list)

    def valid_cold_start_samples(self) -> list[ColdStartSample]:
        """cold-start p95 集計に採用可能なサンプルのみを抽出する。"""
        return [s for s in self.samples if s.is_valid_cold_start()]

    def p95_seconds(self) -> float | str:
        """cold-start の p95（秒）を算出する。要件を満たさない場合は UNDETERMINED。

        採用可能サンプルが最小試行回数（5 回）未満の場合は、達成／未達を決めつけず
        UNDETERMINED を返す（R11.5）。5 回以上ある場合のみ最近接順位法で p95 を算出する。
        """
        valid = self.valid_cold_start_samples()
        # 誘発条件下の有効サンプルが規定回数未満なら未実測扱い（決めつけない）。
        if len(valid) < self.condition.minimum_trials:
            return UNDETERMINED
        # 有効サンプルの応答時間（秒）で p95 を算出する。
        values = [s.response_time_seconds for s in valid]
        return percentile_nearest_rank(values, self.condition.percentile)

    def to_record(self) -> dict[str, object]:
        """フェーズ実測を記録用の辞書へ変換する（単位・出典・試行内訳を含む）。"""
        valid = self.valid_cold_start_samples()
        return {
            "phase": self.phase.value,
            "condition": self.condition.to_record(),
            "trials_total": len(self.samples),
            "trials_valid_cold_start": len(valid),
            "p95_seconds": self.p95_seconds(),
            "unit": self.condition.unit,
            # 各サンプルの出典を列挙し、集計値の根拠を追跡可能にする（第一原則: 出典必須）。
            "sample_sources": [s.source for s in self.samples],
        }


def _diff_or_marker(measured: float | str, target: ColdStartTarget) -> dict[str, object]:
    """実測 p95 と目標値の差分、および達成可否を判定して記録用辞書を返す。

    - 実測が UNDETERMINED、または目標が未定義の場合は判定を保留し UNDETERMINED を返す
      （「許容」と決めつけない、R11.5）。
    - 双方が数値の場合のみ差分（実測 - 目標、単位: 秒）と達成可否を算出する（R11.6）。
    """
    # 目標未定義、または実測が未確定なら達成可否を決めつけない。
    if not target.is_defined() or not isinstance(measured, (int, float)):
        return {
            "achieved": UNDETERMINED,
            "diff_seconds": UNDETERMINED,
            "unit": UNIT_SECONDS,
        }
    # 双方が数値のときのみ差分（実測 - 目標）を算出する（R11.6）。
    threshold = float(target.threshold_seconds)  # type: ignore[arg-type]
    diff = float(measured) - threshold
    return {
        "achieved": measured <= threshold,
        "diff_seconds": diff,
        "unit": UNIT_SECONDS,
    }


@dataclass
class ColdStartRecord:
    """コールドスタート実測記録（Baseline・目標・Post_Change の対比、R11.4）。

    Attributes:
        baseline: 現行表示経路（Lambda 経由 `/portfolio/top/` GET）の Baseline 実測。
        target: Contact_Function の許容目標値の定義枠（未確定は UNDETERMINED）。
        post_change: 変更後の Contact_Function コールドスタート Post_Change 実測。
            未実施の場合は None（ペア欠落として missing 明記）。
    """

    baseline: ColdStartMeasurement
    target: ColdStartTarget
    post_change: ColdStartMeasurement | None = None

    def build_record(self) -> dict[str, object]:
        """測定条件・単位（秒）・p95 を明記し、目標／Baseline と対比した記録を生成する。

        R11.4（測定条件・単位・p95 の明記、目標／Baseline 対比）、R11.5（未実測は
        undetermined）、R12-4（ペア片側欠落は missing）を満たす記録辞書を返す。
        """
        baseline_p95 = self.baseline.p95_seconds()

        # Post_Change が未実施ならペア欠落を明示する（missing、比較を確定扱いしない）。
        if self.post_change is None:
            post_change_record: dict[str, object] = {
                "phase": MeasurementPhase.POST_CHANGE.value,
                "status": MISSING,
                "note": "Contact_Function の Post_Change コールドスタート未実測（ペア欠落）。",
            }
            post_change_p95: float | str = MISSING
        else:
            post_change_record = self.post_change.to_record()
            post_change_p95 = self.post_change.p95_seconds()

        # 目標との対比（Post_Change が数値のときのみ差分・達成可否を算出）。
        target_comparison = _diff_or_marker(
            post_change_p95 if isinstance(post_change_p95, (int, float)) else UNDETERMINED,
            self.target,
        )

        # Baseline との対比（双方が数値のときのみ差分を算出）。
        if isinstance(baseline_p95, (int, float)) and isinstance(post_change_p95, (int, float)):
            baseline_comparison: dict[str, object] = {
                "diff_seconds": float(post_change_p95) - float(baseline_p95),
                "unit": UNIT_SECONDS,
            }
        else:
            baseline_comparison = {"diff_seconds": UNDETERMINED, "unit": UNIT_SECONDS}

        return {
            "metric": "cold_start",
            "percentile": PERCENTILE_LABEL,
            "unit": UNIT_SECONDS,
            "baseline": self.baseline.to_record(),
            "target": self.target.to_record(),
            "post_change": post_change_record,
            "comparison_vs_target": target_comparison,
            "comparison_vs_baseline": baseline_comparison,
        }

    def to_json(self, *, indent: int = 2) -> str:
        """記録を JSON 文字列へ整形して返す。"""
        return json.dumps(self.build_record(), ensure_ascii=False, indent=indent)


def build_baseline_condition() -> MeasurementCondition:
    """現行表示経路（Lambda 経由 `/portfolio/top/` GET）の Baseline 測定条件を生成する。

    出典 E-2: `/portfolio/top/` の GET は Lambda(Django Top ビュー) が毎回動的レンダリング。
    誘発条件は「ウォーム済み実行環境が存在しない状態での初回リクエスト」（R11.1）。
    """
    return MeasurementCondition(
        target="現行表示経路: API Gateway 経由 Lambda(Django Top) の GET /portfolio/top/",
        induction_method=(
            "ウォーム済み実行環境が存在しない状態を誘発し（十分なアイドル経過後の初回、"
            "または新規デプロイ直後の初回リクエスト）、5 回以上試行して cold-like 初回応答を測定する。"
        ),
        source="requirements.md R11.1 / E-2; template.yaml DjangoApi・DjangoFunction",
    )


def build_post_change_condition() -> MeasurementCondition:
    """変更後 Contact_Function の Post_Change 測定条件を生成する（R11.3）。

    誘発条件は Baseline と整合させ「ウォーム済み実行環境が存在しない状態での初回リクエスト」。
    試行回数は 5 回以上（R10 の試行回数と整合、R11.3）。
    """
    return MeasurementCondition(
        target="変更後: Contact_Function（Django 非依存 軽量 Lambda）の問い合わせ POST 初回応答",
        induction_method=(
            "ウォーム済み実行環境が存在しない状態を誘発し、5 回以上試行して cold-like 初回応答を測定する。"
        ),
        source="requirements.md R11.3; design.md C3（Contact_Function）",
    )


def build_undetermined_record() -> ColdStartRecord:
    """未実測時点の記録テンプレートを生成する。

    Baseline・Post_Change いずれもサンプル未投入（p95=undetermined / post_change=missing）、
    Contact_Function 目標値は未確定（undetermined）とする。実測前は「許容」と決めつけない
    （R11.2 / R11.5）。実測サンプルは外部で取得し、`ColdStartMeasurement.samples` へ与える。
    """
    baseline = ColdStartMeasurement(
        phase=MeasurementPhase.BASELINE,
        condition=build_baseline_condition(),
    )
    # R11.2: Contact_Function の許容目標値は design で定義予定。現時点は未確定 = undetermined。
    target = ColdStartTarget(component="Contact_Function")
    # Post_Change は未実施のため None（build_record で missing として明示される）。
    return ColdStartRecord(baseline=baseline, target=target, post_change=None)


if __name__ == "__main__":
    # 実測前の記録テンプレート（未実測は undetermined、ペア欠落は missing）を出力し、
    # 測定条件・単位（秒）・p95・目標定義枠のスキーマを提示する。実測値は含めない。
    print(build_undetermined_record().to_json())
