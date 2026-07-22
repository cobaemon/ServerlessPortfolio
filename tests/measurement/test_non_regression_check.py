"""デプロイ後非退行検証スクリプトの単体テスト（`scripts/measurement/non_regression_check.py`）.

本モジュールは tasks.md 8.5 に対応し、`scripts.measurement.non_regression_check` が
Requirement 9（セキュリティ・多言語の維持＝非退行）および R7（CSP のエッジ付与）の
受け入れ基準を、AWS 認証情報・ネットワーク・Docker に依存せず決定的に検証できる
ことを確かめる（出典: tasks.md 8.5、requirements.md R9-1/R9-2/R9-4/R9-5/R9-7/R7、
design.md「Testing Strategy > スナップショット/ポリシー・統合/スモーク・例ベース」＝
IaC/配信/実測系は PBT 不適合・例ベースで担保）。

検証項目:
    1. CloudFormation 短縮タグローダ（`_load_cfn_yaml`/`_construct_cfn_tag`）が
       `!Ref`/`!Sub`/`!GetAtt`/`!If` を完全表記の辞書へ変換する。
    2. 構成検証（HTTPS 強制 R9-1・S3 OAC 経由のみ R9-2/R9-6・7 言語 R9-4・
       Contact_Payload 4 項目 R9-5・CSP 付与 R7）が現行リポジトリで COMPLIANT を返す。
    3. 実配信実測（`run_live_checks`/live チェック）が、`--base-url` 未指定時は
       UNDETERMINED、注入した実測ポート（DIP）に応じて COMPLIANT/NON_COMPLIANT/
       UNDETERMINED を出典付きで返す（フォールバックせず取得失敗を明示）。
    4. エントリーポイント `main` の終了コード（全適合=0、--fail-on-undetermined 時に
       未確認あり=2）。

外部依存とライセンス（第二原則6）:
    - 標準ライブラリ `unittest` / `io` / `contextlib` / `sys` / `urllib.error` のみを
      用いる（既存テスト `tests/measurement/`・`tests/iac/` の方針と一貫）。追加の
      外部パッケージは使用しない（PyYAML は被テスト側が使用）。

実行コマンド（プロジェクトルートから）:
    python -m unittest tests.measurement.test_non_regression_check -v
"""

from __future__ import annotations

import contextlib
import io
import sys
import unittest
import urllib.error
from pathlib import Path

import yaml

from scripts.measurement.non_regression_check import (
    CheckResult,
    ProbeResponse,
    Verdict,
    _CloudFormationLoader,
    _construct_cfn_tag,
    _load_cfn_yaml,
    build_report,
    check_contact_payload_fields,
    check_csp_configuration,
    check_https_enforcement,
    check_s3_oac_only,
    check_seven_languages,
    collect_check_results,
    main,
    run_live_checks,
)

# リポジトリルート（tests/measurement/ から 2 階層上）。構成検証の起点として用いる。
_REPO_ROOT = Path(__file__).resolve().parents[2]


class _StubProber:
    """実測ポート（EndpointProber）のスタブ実装（DIP でネットワークを排除する）.

    事前に与えた応答またはエラーを返し、実ネットワークに依存せず live チェックの
    分岐（COMPLIANT/NON_COMPLIANT/UNDETERMINED）を決定的に検証する。
    """

    def __init__(
        self,
        response: ProbeResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        """返却する応答または送出する例外を受け取る.

        Args:
            response: probe が返す応答（error 未指定時に使用）。
            error: probe が送出する例外（指定時は response より優先）。
        """
        # 応答と例外を保持する（どちらを使うかは probe で決定する）。
        self._response = response
        self._error = error

    def probe(self, url: str, follow_redirects: bool) -> ProbeResponse:
        """設定に応じて応答を返すか例外を送出する（EndpointProber 準拠）.

        Args:
            url: 実測対象 URL（本スタブでは未使用だがインターフェース整合のため受領）。
            follow_redirects: リダイレクト追従可否（本スタブでは未使用）。

        Returns:
            ProbeResponse: 事前設定した応答。

        Raises:
            Exception: 事前設定した例外（取得失敗の模擬）。
        """
        # 例外が設定されていれば取得失敗として送出する（握りつぶさない挙動の検証用）。
        if self._error is not None:
            raise self._error
        # 応答未設定は想定外のため明示的に失敗させる（テストの誤設定を握りつぶさない）。
        if self._response is None:
            raise AssertionError("スタブに応答も例外も設定されていない")
        return self._response


class CfnLoaderTests(unittest.TestCase):
    """CloudFormation 短縮タグローダの変換を検証する。"""

    def test_construct_ref_sub_getatt_if(self) -> None:
        """`!Ref`/`!Sub`/`!GetAtt`/`!If` が完全表記の辞書へ変換される。"""
        # ローダを直接用いて短縮タグ文字列を解析する（一時ファイルを作らない）。
        document = yaml.load(
            "a: !Ref Foo\n"
            "b: !Sub 'x-${Env}'\n"
            "c: !GetAtt Res.Attr\n"
            "d: !If [Cond, 1, 2]\n",
            Loader=_CloudFormationLoader,
        )
        # Ref は Fn:: 接頭辞を持たない。
        self.assertEqual(document["a"], {"Ref": "Foo"})
        # Sub は Fn::Sub へ。
        self.assertEqual(document["b"], {"Fn::Sub": "x-${Env}"})
        # GetAtt のスカラ "Res.Attr" は ["Res", "Attr"] へ分割される。
        self.assertEqual(document["c"], {"Fn::GetAtt": ["Res", "Attr"]})
        # If はシーケンスを保持して Fn::If へ。
        self.assertEqual(document["d"], {"Fn::If": ["Cond", 1, 2]})

    def test_load_missing_template_raises(self) -> None:
        """存在しないテンプレートは握りつぶさず FileNotFoundError で失敗する。"""
        with self.assertRaises(FileNotFoundError):
            _load_cfn_yaml(_REPO_ROOT / "does_not_exist_template.yaml")

    def test_construct_cfn_tag_is_callable(self) -> None:
        """短縮タグコンストラクタが呼び出し可能な関数として存在する（回帰防止）。"""
        # 関数参照が import 可能であること（マルチコンストラクタ登録の存在確認）。
        self.assertTrue(callable(_construct_cfn_tag))


class ConfigCheckComplianceTests(unittest.TestCase):
    """現行リポジトリ構成が各非退行不変条件を満たす（COMPLIANT）ことを検証する。"""

    def _assert_all_compliant(self, results: list[CheckResult]) -> None:
        """与えられた検証結果がすべて COMPLIANT かつ出典付きであることを表明する.

        Args:
            results: 検証結果の一覧。
        """
        # 各結果に出典（evidence）が付与されていること（第一原則: 全報告に出典）。
        for result in results:
            with self.subTest(check_id=result.check_id):
                self.assertTrue(result.evidence, msg="出典（evidence）が空である")
                self.assertIs(
                    result.verdict,
                    Verdict.COMPLIANT,
                    msg=f"{result.check_id} が COMPLIANT でない: {result.detail}",
                )

    def test_https_enforcement_compliant(self) -> None:
        """HTTPS 強制（prod.py + CloudFront 全 Behavior）が COMPLIANT（R9-1）."""
        self._assert_all_compliant(check_https_enforcement(_REPO_ROOT))

    def test_s3_oac_only_compliant(self) -> None:
        """S3 OAC 経由のみ・公開遮断が COMPLIANT（R9-2/R9-6）."""
        self._assert_all_compliant(check_s3_oac_only(_REPO_ROOT))

    def test_seven_languages_compliant(self) -> None:
        """7 言語設定・locale カタログが COMPLIANT（R9-4）."""
        self._assert_all_compliant(check_seven_languages(_REPO_ROOT))

    def test_contact_payload_fields_compliant(self) -> None:
        """Contact_Payload 4 項目限定が COMPLIANT（R9-5）."""
        # contact_function を import できるよう sys.path を整える（main と同等の前提）。
        root_str = str(_REPO_ROOT)
        if root_str not in sys.path:
            sys.path.insert(0, root_str)
        self._assert_all_compliant(check_contact_payload_fields())

    def test_csp_configuration_compliant(self) -> None:
        """CSP 付与（ResponseHeadersPolicy）・nonce 不在が COMPLIANT（R7）."""
        self._assert_all_compliant(check_csp_configuration(_REPO_ROOT))


class LiveCheckTests(unittest.TestCase):
    """実配信実測の分岐（未実施/成功/失敗/取得エラー）を DIP スタブで検証する。"""

    def test_without_base_url_yields_two_undetermined(self) -> None:
        """`--base-url` 未指定時は 2 項目が UNDETERMINED（決めつけない）。"""
        # base_url=None のため実測は行わず、実配信次元を未確認として記録する。
        results = run_live_checks(None, _StubProber())
        self.assertEqual(len(results), 2)
        for result in results:
            self.assertIs(result.verdict, Verdict.UNDETERMINED)
            self.assertTrue(result.evidence)

    def test_https_redirect_compliant_with_stub(self) -> None:
        """301 かつ Location が https のとき HTTPS リダイレクトは COMPLIANT（R9-1）."""
        prober = _StubProber(
            ProbeResponse(
                status=301,
                headers={"location": "https://example.test/"},
                final_url="http://example.test/",
            )
        )
        results = run_live_checks("https://example.test/", prober)
        # 先頭が HTTPS リダイレクト実測結果である。
        self.assertIs(results[0].verdict, Verdict.COMPLIANT)

    def test_https_redirect_non_compliant_when_not_redirected(self) -> None:
        """200 かつリダイレクト無しのとき HTTPS リダイレクトは NON_COMPLIANT（R9-1）."""
        prober = _StubProber(
            ProbeResponse(status=200, headers={}, final_url="http://example.test/")
        )
        results = run_live_checks("https://example.test/", prober)
        self.assertIs(results[0].verdict, Verdict.NON_COMPLIANT)

    def test_csp_header_compliant_without_nonce(self) -> None:
        """CSP ヘッダがあり nonce を含まないとき CSP 実測は COMPLIANT（R7-1/R7-2）."""
        prober = _StubProber(
            ProbeResponse(
                status=200,
                headers={"content-security-policy": "default-src 'self'"},
                final_url="https://example.test/",
            )
        )
        results = run_live_checks("https://example.test/", prober)
        # 2 番目が CSP ヘッダ実測結果である。
        self.assertIs(results[1].verdict, Verdict.COMPLIANT)

    def test_csp_header_non_compliant_with_nonce(self) -> None:
        """CSP に per-request nonce を含むとき CSP 実測は NON_COMPLIANT（R7-2）."""
        prober = _StubProber(
            ProbeResponse(
                status=200,
                headers={"content-security-policy": "script-src 'nonce-abc'"},
                final_url="https://example.test/",
            )
        )
        results = run_live_checks("https://example.test/", prober)
        self.assertIs(results[1].verdict, Verdict.NON_COMPLIANT)

    def test_probe_failure_is_recorded_as_undetermined(self) -> None:
        """取得失敗（URLError）は握りつぶさず UNDETERMINED として明示記録する。"""
        prober = _StubProber(error=urllib.error.URLError("接続不可"))
        results = run_live_checks("https://example.test/", prober)
        # 取得失敗は達成/未達を決めつけず未確認として記録する（推測補完しない）。
        for result in results:
            self.assertIs(result.verdict, Verdict.UNDETERMINED)


class ReportAndMainTests(unittest.TestCase):
    """レポート集計と `main` 終了コードを検証する。"""

    def test_build_report_summary_counts_match(self) -> None:
        """レポートの判定内訳合計が結果件数と一致する（集計の整合）。"""
        results = collect_check_results(_REPO_ROOT, None, _StubProber())
        report = build_report(results)
        # 三値の合計が結果件数に等しいこと。
        self.assertEqual(sum(report["summary"].values()), len(results))
        # 各結果が辞書化され verdict が文字列へ落ちていること。
        for entry in report["results"]:
            self.assertIn(entry["verdict"], {v.value for v in Verdict})

    def test_main_returns_zero_on_current_repo(self) -> None:
        """現行リポジトリでは不適合が無く main は 0 を返す（構成検証のみ）。"""
        # 標準出力の JSON は本テストの対象外のため捨てる。
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = main([])
        self.assertEqual(exit_code, 0)

    def test_main_fails_on_undetermined_flag(self) -> None:
        """--fail-on-undetermined 指定時、実配信未実測（undetermined）で 2 を返す。"""
        # 標準出力/標準エラーは対象外のため捨てる。
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
            io.StringIO()
        ):
            exit_code = main(["--fail-on-undetermined"])
        self.assertEqual(exit_code, 2)


if __name__ == "__main__":
    # プロジェクトルートから `python -m unittest tests.measurement.test_non_regression_check -v` で実行。
    unittest.main()
