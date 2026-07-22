"""
変更前後エビデンス記録様式。

本モジュールは spec `cost-performance-optimization` のタスク 8.4 に対応し、
Requirement 12（変更前後のエビデンス記録）を満たす記録・集約の「様式（スキーマ）」を
提供する。対象指標は以下の 4 つで、いずれも Baseline（変更前）と Post_Change（変更後）の
双方を単位・出典付きで記録する（出典: R12-1, R12-2、design.md DM6 / Testing Strategy）。

- コスト: Portfolio_Operational_Cost（単位 USD、出典 AWS 請求の概要の該当月）
- 表示パフォーマンス: LCP p50、warm 状態の TTFB p95（単位 秒、出典 パフォーマンス測定ログ）
- コールドスタート: Cold Start p95（単位 秒、出典 コールドスタート実測ログ）

本モジュールは実測ロジック（コスト算出・Lighthouse 計測・コールドスタート計測）を
再実装しない。それらは兄弟スクリプト（8.1 cost_attribution.py、8.2 performance_protocol.py、
8.3 cold_start_protocol.py）が担い、本モジュールはその結果値を受領して記録・集約し、
比較可否を判定する責務のみを持つ（単一責務、出典: 第二原則3 SOLID）。

品質制約（出典: 第一原則、第三原則3、R12-3/R12-4/R12-5）:
- 一次測定ログが存在しない指標は `undetermined` と明記し、推測補完しない。
- Baseline / Post_Change のペアの一方が欠落する場合、欠落側を `missing` と明記し、
  変更前後の比較を確定として扱わない。
- Email_Sender の送信失敗を含むエラーは握りつぶさず、明示的に記録し呼び出し元へ通知する
  （フォールバック禁止、R6-4/R12-5 と整合）。
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from enum import Enum


class ValueStatus(str, Enum):
    """
    測定値の確定状態を表す列挙。

    - DETERMINED: 一次測定ログに基づく確定値。value と source を必須とする。
    - UNDETERMINED: 一次測定ログが未取得のため値を確定できない状態（R12-3）。
    - MISSING: Baseline / Post_Change ペアの片側が欠落している状態（R12-4）。
    """

    DETERMINED = "determined"
    UNDETERMINED = "undetermined"
    MISSING = "missing"


class MetricKind(Enum):
    """
    記録対象指標の種別。各要素は表示ラベル・単位・出典分類を保持する
    （出典: R12-1/R12-2、design.md DM6 / Testing Strategy）。
    """

    # 値は (表示ラベル, 単位, 出典分類) のタプル。
    COST = ("Portfolio_Operational_Cost", "USD", "AWS 請求の概要の該当月")
    LCP_P50 = ("LCP p50", "秒", "パフォーマンス測定ログ")
    WARM_TTFB_P95 = ("warm TTFB p95", "秒", "パフォーマンス測定ログ")
    COLD_START_P95 = ("Cold Start p95", "秒", "コールドスタート実測ログ")

    def __init__(self, label: str, unit: str, source_category: str) -> None:
        """
        列挙要素の付随属性を初期化する。

        引数:
            label: 記録上の指標表示名。
            unit: 数値に必ず付与する単位（R12-2）。
            source_category: 一次測定ログの出典分類（R12-2）。
        """

        self.label = label
        self.unit = unit
        self.source_category = source_category


@dataclass(frozen=True)
class MeasurementValue:
    """
    単一の測定値を表す不変値オブジェクト。

    数値には必ず単位を付し、確定値には出典（一次測定ログの分類と該当ファイルパス等）を
    付す（出典: R12-2）。未確定・欠落は status で明示し、推測補完しない（R12-3/R12-4）。

    属性:
        status: 確定状態（DETERMINED / UNDETERMINED / MISSING）。
        unit: 単位（USD または 秒）。
        value: 確定値。未確定・欠落時は None。
        source: 出典。確定値では必須（一次測定ログ分類＋該当ファイルパス等）。
        note: 未確定・欠落理由などの補足（推測ではなく事実の記述に限る）。
    """

    status: ValueStatus
    unit: str
    value: float | None = None
    source: str | None = None
    note: str = ""

    def __post_init__(self) -> None:
        """
        値オブジェクトの整合性を検証する（ゼロトラスト: 入力検証）。

        確定値は value と source を必須とし、欠くと矛盾記録になるため例外送出する
        （フォールバック禁止、出典: R12-2/R12-3、第三原則3）。未確定・欠落は
        value を持たないこと（推測補完しないこと）を保証する。

        例外:
            ValueError: 状態と値・出典の組み合わせが不整合な場合。
        """

        # 単位は必須（全数値に単位を付す、R12-2）。
        if not self.unit:
            raise ValueError("単位（unit）は必須である（R12-2）")

        if self.status is ValueStatus.DETERMINED:
            # 確定値は数値と出典の双方が揃っていなければならない（R12-2）。
            if self.value is None:
                raise ValueError("確定値には value が必須である（R12-2）")
            if not self.source:
                raise ValueError("確定値には source（出典）が必須である（R12-2）")
        else:
            # 未確定・欠落で値を持つことは推測補完に当たるため禁止する（R12-3/R12-4）。
            if self.value is not None:
                raise ValueError(
                    "undetermined / missing の測定値は value を持ってはならない（推測補完禁止、R12-3）"
                )

    @classmethod
    def determined(cls, value: float, unit: str, source: str) -> "MeasurementValue":
        """
        一次測定ログに基づく確定値を生成する。

        引数:
            value: 一次測定ログ由来の確定数値。
            unit: 単位（USD または 秒）。
            source: 出典（一次測定ログの分類＋該当ファイルパス等、R12-2）。

        戻り値:
            確定状態の MeasurementValue。
        """

        return cls(status=ValueStatus.DETERMINED, unit=unit, value=value, source=source)

    @classmethod
    def undetermined(cls, unit: str, note: str) -> "MeasurementValue":
        """
        一次測定ログ未取得の未確定値を生成する（R12-3）。

        引数:
            unit: 単位（USD または 秒）。
            note: 未確定である事実の記述（例: 一次測定ログが未取得）。

        戻り値:
            未確定状態の MeasurementValue。
        """

        return cls(status=ValueStatus.UNDETERMINED, unit=unit, note=note)

    @classmethod
    def missing(cls, unit: str, note: str) -> "MeasurementValue":
        """
        ペアの片側欠落を表す欠落値を生成する（R12-4）。

        引数:
            unit: 単位（USD または 秒）。
            note: 欠落である事実の記述（例: 対となる測定が未実施）。

        戻り値:
            欠落状態の MeasurementValue。
        """

        return cls(status=ValueStatus.MISSING, unit=unit, note=note)

    def to_dict(self) -> dict[str, object]:
        """
        シリアライズ用の辞書表現へ変換する。

        戻り値:
            status・unit・value・source・note を含む辞書。
        """

        return {
            "status": self.status.value,
            "unit": self.unit,
            "value": self.value,
            "source": self.source,
            "note": self.note,
        }


@dataclass(frozen=True)
class ComparisonResult:
    """
    Baseline と Post_Change の比較結果。

    双方が確定値の場合のみ比較を確定（confirmed=True）とし、差分を数値で示す。
    いずれかが未確定・欠落の場合は confirmed=False とし、比較を確定として扱わない
    （出典: R12-4）。

    属性:
        confirmed: 比較が確定できるか（両側 DETERMINED のときのみ True）。
        unit: 差分の単位。
        difference: Post_Change - Baseline の差分。確定できない場合は None。
        reason: 確定できない場合の事実に基づく理由。
    """

    confirmed: bool
    unit: str
    difference: float | None
    reason: str

    def to_dict(self) -> dict[str, object]:
        """比較結果の辞書表現を返す。"""

        return {
            "confirmed": self.confirmed,
            "unit": self.unit,
            "difference": self.difference,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class MetricEvidence:
    """
    1 指標分の Baseline / Post_Change エビデンス。

    属性:
        kind: 指標種別（単位・出典分類を内包）。
        baseline: 変更前の測定値。
        post_change: 変更後の測定値。
    """

    kind: MetricKind
    baseline: MeasurementValue
    post_change: MeasurementValue

    def __post_init__(self) -> None:
        """
        指標種別の単位と各測定値の単位の一致を検証する（ゼロトラスト: 入力検証）。

        単位不一致は記録の矛盾であり握りつぶさず例外送出する（フォールバック禁止）。

        例外:
            ValueError: 単位が指標種別と一致しない場合。
        """

        if self.baseline.unit != self.kind.unit:
            raise ValueError(
                f"{self.kind.label} の baseline 単位が不一致である"
                f"（期待 {self.kind.unit} / 実際 {self.baseline.unit}）"
            )
        if self.post_change.unit != self.kind.unit:
            raise ValueError(
                f"{self.kind.label} の post_change 単位が不一致である"
                f"（期待 {self.kind.unit} / 実際 {self.post_change.unit}）"
            )

    def compare(self) -> ComparisonResult:
        """
        Baseline と Post_Change を比較する。

        両側が確定値の場合のみ差分（Post_Change - Baseline）を算出し確定比較とする。
        いずれかが未確定・欠落の場合は確定比較としない（R12-4）。差分の良否判定
        （達成/未達）は本モジュールの責務ではなく、各実測スクリプトが担う。

        戻り値:
            比較可否・差分・理由を保持する ComparisonResult。
        """

        both_determined = (
            self.baseline.status is ValueStatus.DETERMINED
            and self.post_change.status is ValueStatus.DETERMINED
        )
        if both_determined and self.baseline.value is not None and self.post_change.value is not None:
            # DETERMINED は __post_init__ で value 非 None を保証済み。ここで確定差分を算出する。
            difference = self.post_change.value - self.baseline.value
            return ComparisonResult(
                confirmed=True,
                unit=self.kind.unit,
                difference=difference,
                reason="Baseline / Post_Change の双方が確定値のため比較を確定した。",
            )

        # 片側でも未確定・欠落なら比較を確定として扱わない（R12-4）。
        return ComparisonResult(
            confirmed=False,
            unit=self.kind.unit,
            difference=None,
            reason=(
                f"比較未確定: baseline={self.baseline.status.value}, "
                f"post_change={self.post_change.status.value}（R12-4 により確定扱いしない）"
            ),
        )

    def to_dict(self) -> dict[str, object]:
        """指標エビデンスの辞書表現を返す。"""

        return {
            "metric": self.kind.name,
            "label": self.kind.label,
            "unit": self.kind.unit,
            "source_category": self.kind.source_category,
            "baseline": self.baseline.to_dict(),
            "post_change": self.post_change.to_dict(),
            "comparison": self.compare().to_dict(),
        }


@dataclass(frozen=True)
class ErrorEntry:
    """
    明示記録するエラー 1 件。

    Email_Sender の送信失敗を含むあらゆるエラーを握りつぶさず記録するための構造
    （出典: R6-4/R12-5、第三原則3）。

    属性:
        context: エラー発生箇所・文脈（例: "Email_Sender", "cost_attribution"）。
        message: エラー内容の要約。
        detail: 例外詳細やスタック等の補足（任意）。
    """

    context: str
    message: str
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        """エラー記録の辞書表現を返す。"""

        return {"context": self.context, "message": self.message, "detail": self.detail}


class EvidenceError(Exception):
    """
    記録されたエラーを呼び出し元へ通知するための例外。

    エラーを握りつぶさず、集約結果の確定前に呼び出し元へ明示的に伝播させる
    （フォールバック禁止、出典: R6-4/R12-5、第三原則3）。

    属性:
        errors: 通知対象のエラー記録一覧。
    """

    def __init__(self, errors: list[ErrorEntry]) -> None:
        """
        例外を初期化する。

        引数:
            errors: 記録済みエラーの一覧（1 件以上）。
        """

        self.errors = errors
        summary = "; ".join(f"[{e.context}] {e.message}" for e in errors)
        super().__init__(f"エビデンス記録中に握りつぶさず記録したエラーが存在する: {summary}")


# 記録対象として必須の指標集合（R12-1）。全指標について Baseline / Post_Change を記録する。
REQUIRED_METRICS: tuple[MetricKind, ...] = (
    MetricKind.COST,
    MetricKind.LCP_P50,
    MetricKind.WARM_TTFB_P95,
    MetricKind.COLD_START_P95,
)


@dataclass
class EvidenceRecord:
    """
    変更前後エビデンスの集約記録。

    4 指標（コスト・LCP p50・warm TTFB p95・Cold Start p95）の Baseline / Post_Change を
    集約し、エラーを明示記録する。実測ロジックは持たず、兄弟スクリプトの結果値を
    受領して記録・集約する（単一責務、出典: R12-1、design.md Testing Strategy）。

    属性:
        metrics: 指標種別ごとのエビデンス。
        errors: 明示記録したエラー一覧。
    """

    metrics: dict[MetricKind, MetricEvidence] = field(default_factory=dict)
    errors: list[ErrorEntry] = field(default_factory=list)

    def set_metric(self, evidence: MetricEvidence) -> None:
        """
        指標エビデンスを登録する（同一指標は上書き）。

        引数:
            evidence: 登録する指標エビデンス。
        """

        self.metrics[evidence.kind] = evidence

    def record_error(self, context: str, message: str, detail: str = "") -> None:
        """
        エラーを握りつぶさず明示記録する（R6-4/R12-5）。

        引数:
            context: エラー発生箇所・文脈。
            message: エラー内容の要約。
            detail: 例外詳細等の補足（任意）。

        例外:
            ValueError: context または message が空の場合。
        """

        # 入力検証（ゼロトラスト）: 文脈と要約は必須。空記録は事実性を損なうため拒否する。
        if not context or not message:
            raise ValueError("エラー記録には context と message が必須である")
        self.errors.append(ErrorEntry(context=context, message=message, detail=detail))

    def missing_metrics(self) -> list[MetricKind]:
        """
        未登録の必須指標を返す（R12-1 の記録漏れ検出用）。

        戻り値:
            登録されていない必須指標の一覧。
        """

        return [kind for kind in REQUIRED_METRICS if kind not in self.metrics]

    def raise_if_errors(self) -> None:
        """
        記録済みエラーが存在する場合、呼び出し元へ通知するため例外送出する。

        エラーを握りつぶして正常終了扱いにしない（フォールバック禁止、R6-4/R12-5）。

        例外:
            EvidenceError: 1 件以上のエラーが記録されている場合。
        """

        if self.errors:
            raise EvidenceError(self.errors)

    def to_dict(self) -> dict[str, object]:
        """
        集約記録全体の辞書表現へ変換する。

        戻り値:
            指標エビデンス・未登録指標・エラー記録を含む辞書。
        """

        return {
            "metrics": [
                self.metrics[kind].to_dict() for kind in REQUIRED_METRICS if kind in self.metrics
            ],
            "missing_metrics": [kind.name for kind in self.missing_metrics()],
            "errors": [error.to_dict() for error in self.errors],
        }

    def to_json(self) -> str:
        """
        集約記録を UTF-8・整形済み JSON 文字列へ変換する。

        戻り値:
            日本語をエスケープしない整形済み JSON 文字列。
        """

        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def build_template_record() -> EvidenceRecord:
    """
    未実測状態のエビデンス記録テンプレートを生成する。

    実測前は一次測定ログが存在しないため、全指標の Baseline / Post_Change を
    `undetermined` として初期化する（推測補完しない、R12-3）。各実測スクリプトが
    確定値を得た時点で `MeasurementValue.determined(...)` により置換し、対の片側のみ
    欠落する場合は `MeasurementValue.missing(...)` に置換する運用とする（R12-4）。

    戻り値:
        4 指標すべてを undetermined で初期化した EvidenceRecord。
    """

    record = EvidenceRecord()
    for kind in REQUIRED_METRICS:
        # 実測前の初期状態は一次測定ログ未取得の undetermined（R12-3）。
        record.set_metric(
            MetricEvidence(
                kind=kind,
                baseline=MeasurementValue.undetermined(
                    unit=kind.unit,
                    note=f"一次測定ログ未取得（出典分類: {kind.source_category}）",
                ),
                post_change=MeasurementValue.undetermined(
                    unit=kind.unit,
                    note=f"一次測定ログ未取得（出典分類: {kind.source_category}）",
                ),
            )
        )
    return record


def main() -> int:
    """
    エビデンス記録テンプレートを JSON として標準出力へ出力する。

    実測スクリプトが記録を埋める前の「記録様式」を可視化・受け渡すための起動口。
    実測値を持たない初期テンプレートのため、全指標は `undetermined` で出力される。

    戻り値:
        正常終了時 0。
    """

    record = build_template_record()
    sys.stdout.write(record.to_json() + "\n")
    return 0


if __name__ == "__main__":
    # スクリプト直接起動時はテンプレート JSON を出力する。
    raise SystemExit(main())
