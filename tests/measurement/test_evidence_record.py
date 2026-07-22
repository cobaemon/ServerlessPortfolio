"""変更前後エビデンス記録様式の単体テスト（`scripts/measurement/evidence_record.py`）.

本モジュールは tasks.md 8.4 に対応し、`scripts.measurement.evidence_record` が
Requirement 12（変更前後のエビデンス記録）の受け入れ基準を満たすことを、
外部依存・モックなしの純粋ロジックとして決定的に検証する（出典: tasks.md 8.4、
requirements.md R12-1〜R12-5、design.md「DM6 コスト記録様式」/「Testing Strategy >
単体/例ベーステスト」＝実測系は PBT 不適合・例ベースで担保）。

検証項目（受け入れ基準との対応）:
    1. R12-1: テンプレートがコスト・LCP p50・warm TTFB p95・Cold Start p95 の 4 指標を
       Baseline / Post_Change の双方について保持する。
    2. R12-2: 確定値は数値に単位と出典を必須とし、欠くと矛盾記録として拒否する。
    3. R12-3: 一次測定ログ未取得は `undetermined` として値を持たず、推測補完を拒否する。
    4. R12-4: ペアの片側欠落は `missing` と明記し、比較を確定として扱わない。
    5. R12-5: Email_Sender 送信失敗を含むエラーを握りつぶさず記録し、呼び出し元へ通知する。

外部依存とライセンス（第二原則6）:
    - 標準ライブラリ `unittest` のみを用いる（既存テスト `tests/iac/`・
      `tests/measurement/__init__.py` の方針と一貫）。追加の外部パッケージは使用しない。

実行コマンド（プロジェクトルートから）:
    python -m unittest tests.measurement.test_evidence_record -v
"""

from __future__ import annotations

import unittest

from scripts.measurement.evidence_record import (
    REQUIRED_METRICS,
    ComparisonResult,
    EvidenceError,
    EvidenceRecord,
    MeasurementValue,
    MetricEvidence,
    MetricKind,
    ValueStatus,
    build_template_record,
)


class BuildTemplateRecordTest(unittest.TestCase):
    """テンプレート生成が R12-1 / R12-3 を満たすことを検証する。"""

    def test_template_contains_all_four_required_metrics(self) -> None:
        """R12-1: 4 指標すべてが Baseline / Post_Change 付きで登録される。"""

        record = build_template_record()
        # 必須指標がコスト・LCP p50・warm TTFB p95・Cold Start p95 の 4 種であること。
        self.assertEqual(
            set(record.metrics.keys()),
            {
                MetricKind.COST,
                MetricKind.LCP_P50,
                MetricKind.WARM_TTFB_P95,
                MetricKind.COLD_START_P95,
            },
        )
        # 未登録の必須指標が存在しないこと（記録漏れ検出）。
        self.assertEqual(record.missing_metrics(), [])
        # 各指標が Baseline / Post_Change の双方を保持すること。
        for kind in REQUIRED_METRICS:
            evidence = record.metrics[kind]
            self.assertIsInstance(evidence.baseline, MeasurementValue)
            self.assertIsInstance(evidence.post_change, MeasurementValue)

    def test_template_values_are_undetermined_without_measurement(self) -> None:
        """R12-3: 実測前は全指標が undetermined で、推測値（value）を持たない。"""

        record = build_template_record()
        for kind in REQUIRED_METRICS:
            evidence = record.metrics[kind]
            self.assertIs(evidence.baseline.status, ValueStatus.UNDETERMINED)
            self.assertIs(evidence.post_change.status, ValueStatus.UNDETERMINED)
            self.assertIsNone(evidence.baseline.value)
            self.assertIsNone(evidence.post_change.value)

    def test_template_comparison_is_not_confirmed(self) -> None:
        """R12-4: 未確定ペアの比較は確定扱いしない。"""

        record = build_template_record()
        for kind in REQUIRED_METRICS:
            comparison = record.metrics[kind].compare()
            self.assertFalse(comparison.confirmed)
            self.assertIsNone(comparison.difference)


class MeasurementValueTest(unittest.TestCase):
    """測定値オブジェクトが R12-2 / R12-3 の整合性制約を満たすことを検証する。"""

    def test_determined_requires_value_and_source(self) -> None:
        """R12-2: 確定値は数値と出典を必須とする。"""

        value = MeasurementValue.determined(
            value=1.23, unit="USD", source="AWS 請求の概要 2026-07 / billing.csv"
        )
        self.assertIs(value.status, ValueStatus.DETERMINED)
        self.assertEqual(value.value, 1.23)
        self.assertEqual(value.unit, "USD")
        self.assertTrue(value.source)

    def test_determined_without_source_is_rejected(self) -> None:
        """R12-2: 出典を欠く確定値は矛盾記録として拒否する（フォールバック禁止）。"""

        with self.assertRaises(ValueError):
            MeasurementValue(status=ValueStatus.DETERMINED, unit="USD", value=1.0, source=None)

    def test_missing_unit_is_rejected(self) -> None:
        """R12-2: 単位を欠く測定値は拒否する（全数値に単位を付す）。"""

        with self.assertRaises(ValueError):
            MeasurementValue.determined(value=1.0, unit="", source="src")

    def test_undetermined_must_not_hold_value(self) -> None:
        """R12-3: 未確定値が数値を持つこと（推測補完）を拒否する。"""

        with self.assertRaises(ValueError):
            MeasurementValue(status=ValueStatus.UNDETERMINED, unit="秒", value=0.5)

    def test_missing_must_not_hold_value(self) -> None:
        """R12-4: 欠落値が数値を持つこと（推測補完）を拒否する。"""

        with self.assertRaises(ValueError):
            MeasurementValue(status=ValueStatus.MISSING, unit="秒", value=0.5)


class MetricEvidenceComparisonTest(unittest.TestCase):
    """比較ロジックが R12-4 を満たすことを検証する。"""

    def test_unit_mismatch_is_rejected(self) -> None:
        """指標種別と測定値の単位不一致は握りつぶさず拒否する（フォールバック禁止）。"""

        with self.assertRaises(ValueError):
            MetricEvidence(
                kind=MetricKind.COST,  # 単位 USD を期待
                baseline=MeasurementValue.undetermined(unit="秒", note="単位誤り"),
                post_change=MeasurementValue.undetermined(unit="USD", note="未取得"),
            )

    def test_both_determined_yields_confirmed_difference(self) -> None:
        """R12-4: 両側確定時のみ比較を確定し、差分（Post - Baseline）を返す。"""

        evidence = MetricEvidence(
            kind=MetricKind.LCP_P50,
            baseline=MeasurementValue.determined(value=2.0, unit="秒", source="perf/base.json"),
            post_change=MeasurementValue.determined(value=1.5, unit="秒", source="perf/post.json"),
        )
        result: ComparisonResult = evidence.compare()
        self.assertTrue(result.confirmed)
        self.assertAlmostEqual(result.difference, -0.5)
        self.assertEqual(result.unit, "秒")

    def test_missing_pair_side_is_not_confirmed(self) -> None:
        """R12-4: ペア片側が missing の場合、比較を確定として扱わない。"""

        evidence = MetricEvidence(
            kind=MetricKind.COLD_START_P95,
            baseline=MeasurementValue.determined(value=10.0, unit="秒", source="cold/base.json"),
            post_change=MeasurementValue.missing(unit="秒", note="対となる変更後測定が未実施"),
        )
        result = evidence.compare()
        self.assertFalse(result.confirmed)
        self.assertIsNone(result.difference)
        # 欠落側が missing と明記されていること。
        self.assertIs(evidence.post_change.status, ValueStatus.MISSING)


class ErrorRecordingTest(unittest.TestCase):
    """エラー記録・通知が R12-5 を満たすことを検証する。"""

    def test_email_sender_error_is_recorded_and_raised(self) -> None:
        """R12-5: Email_Sender 送信失敗を記録し、呼び出し元へ例外通知する。"""

        record = build_template_record()
        record.record_error(
            context="Email_Sender",
            message="SES 送信失敗",
            detail="ClientError: MessageRejected",
        )
        # 記録が保持されていること（握りつぶさない）。
        self.assertEqual(len(record.errors), 1)
        self.assertEqual(record.errors[0].context, "Email_Sender")
        # 呼び出し元へ例外として通知されること。
        with self.assertRaises(EvidenceError) as ctx:
            record.raise_if_errors()
        self.assertEqual(len(ctx.exception.errors), 1)

    def test_empty_error_fields_are_rejected(self) -> None:
        """R12-5: 文脈・要約を欠く空エラー記録は事実性を損なうため拒否する。"""

        record = EvidenceRecord()
        with self.assertRaises(ValueError):
            record.record_error(context="", message="内容あり")
        with self.assertRaises(ValueError):
            record.record_error(context="Email_Sender", message="")

    def test_no_errors_does_not_raise(self) -> None:
        """エラー未記録時は通知例外を送出しない。"""

        record = build_template_record()
        # 例外を送出しないこと（記録が無い状態では正常）。
        record.raise_if_errors()
        self.assertEqual(record.errors, [])


if __name__ == "__main__":
    # プロジェクトルートから `python -m unittest tests.measurement.test_evidence_record` で実行。
    unittest.main()
