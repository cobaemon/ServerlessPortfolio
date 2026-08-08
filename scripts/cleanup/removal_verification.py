"""旧資産除去（legacy-asset-cleanup）判定層の Removal_Verification.

目的:
    検証・記録層が収集した非退行確認の実測記録（`NonRegressionRecord`）が
    requirements.md Requirement 2 の基準 1〜6 および基準 10 を同時に満たすかを
    判定し、不適合な条項の識別子を列挙する。コマンド実行は一切行わない（実行は
    design.md C13 の `scripts/cleanup/cli.py` が担う。出典:
    `.kiro/specs/legacy-asset-cleanup/design.md` C4「Removal_Verification」）。

出典:
    - `.kiro/specs/legacy-asset-cleanup/design.md` C4（関数シグネチャ・判定条件・
      「コマンド実行そのものは行わない」）、同 DM3（`NonRegressionRecord` /
      `VerificationResult`）、同 Property 4「非退行判定の全条件同時成立」、
      同「Error Handling」表の「非退行確認のいずれかが不適合」行（R2-9）。
    - `.kiro/specs/legacy-asset-cleanup/requirements.md` Requirement 2 基準
      1〜6、基準 10、Requirement 10 基準 6。
    - `scripts/cleanup/models.py`（DM3 の不変値型。本モジュールは型を再定義せず
      再利用する）。
    - `.kiro/specs/legacy-asset-cleanup/tasks.md` 3.3。

設計上の制約（出典: design.md「Architecture > 依存方向」、
`.kiro/steering/principles.md` 第二原則5、第三原則3）:
    - 標準ライブラリのみに依存し、Django・boto3・ファイル I/O・`subprocess` を
      import しない。判定に用いるのは引数として渡された値だけである。
    - フォールバックを実装しない。欠落値・`None`・型不一致を既定値で補完せず、
      比較演算および `len()` の評価時に例外として表面化させる（本モジュールは
      `try` / `except` および既定値付きの属性取得を用いない）。
    - 単一責務。除去計画は `removal_plan.py`、除去済み計上および系統 B の完了
      判定は `completion.py`、既存の構成検証は
      `scripts/measurement/non_regression_check.py` が担う。本モジュールは後者の
      終了コードを入力の 1 つとして受け取るだけであり、責務を重複させない
      （出典: design.md C4「既存資産との関係」）。

条項識別子と判定条件の対応（`VerificationResult.violations` へ列挙する値）:
    | 条項 | 判定条件 | 出典 |
    | --- | --- | --- |
    | `R2-1` | `tests_passed >= 133` かつ `tests_failed == 0` かつ `tests_errored == 0` | requirements.md Requirement 2 基準 1 |
    | `R2-2` | `django_check_exit_code == 0` | 同 基準 2 |
    | `R2-3` | `control_platform_exit_code == 0` かつ `self_test_exit_code == 0` | 同 基準 3 |
    | `R2-4` | `non_regression_exit_code == 0` | 同 基準 4 |
    | `R2-5` | `prerendered_pages == 7` かつ `manifest_files == 1` | 同 基準 5 |
    | `R2-6` | `len(content_security_policy) >= 1` | 同 基準 6 |
    | `R2-10` | `commands` が非空 | 同 基準 10 |

    Requirement 10 基準 6（開発記録は Requirement 2 で取得した非退行確認結果を
    含む）は、記録内容の充足を基準 10 が定める `commands` / 終了コード /
    pass・failure・error 件数に依拠する。したがって本モジュールでは基準 10 の
    条項識別子 `R2-10` による判定に集約し、独立した識別子を設けない（出典:
    requirements.md Requirement 2 基準 10、Requirement 10 基準 6）。

本モジュールが判定しない事項（design.md C4「判定条件」に列挙がないため、判定を
追加せず設計の範囲に留める）:
    - `stream` の値（`"A"` / `"B"` / `"D"`）の妥当性。
    - `commands` の各要素が実際に実行されたコマンドと一致するか。
    - R2-7（`template.yaml` の `ContactApi` / `ContactFunction` 保持）および
      R2-8（`contact_function/` の 18 件）。いずれも実体の確認を伴うため
      design.md「Testing Strategy」の `tests/cleanup/test_preserved_assets.py`
      が担う。
    - R2-9（不適合時の適用前状態への復帰）。復帰は git 操作であり C13 と運用手順
      が担う。本モジュールは不適合条項の列挙までを担う。
"""

from __future__ import annotations

from .models import NonRegressionRecord, VerificationResult

# ---------------------------------------------------------------------------
# 判定基準の定数（design.md C4「判定条件」）
# ---------------------------------------------------------------------------

# Test_Suite の Baseline pass 件数。requirements.md Requirement 2 基準 1 は
# 「pass 件数が Baseline の 133 件以上」を求める（出典: requirements.md
# Requirement 2 基準 1、同 E-10 の実測 `Ran 133 tests` / `OK`
# （`$env:DJANGO_SETTINGS_MODULE="config.settings.dev"; python manage.py test`）、
# design.md「計測基準」の Test_Suite Baseline 行）。新規テストの追加により実測値
# が本値を上回ることは基準に整合する（出典: tasks.md「Notes」の最終項）。
BASELINE_TESTS_PASSED: int = 133

# failure / error は 0 件でなければならない（R2-1）。
EXPECTED_TESTS_FAILED: int = 0
EXPECTED_TESTS_ERRORED: int = 0

# 非退行ゲートの各コマンドに期待する終了コード（R2-2、R2-3、R2-4）。
EXPECTED_EXIT_CODE: int = 0

# Supported_Languages 7 言語分の Prerendered_Page 件数（R2-5。出典:
# requirements.md Requirement 2 基準 5、`config/settings/base.py:151-159` の
# `LANGUAGES`）。
EXPECTED_PRERENDERED_PAGES: int = 7

# `staticfiles/prerender_manifest.json` の生成件数（R2-5）。
EXPECTED_MANIFEST_FILES: int = 1

# `content_security_policy` に要求する最小長（R2-6。1 文字以上）。
MIN_CONTENT_SECURITY_POLICY_LENGTH: int = 1

# `commands` に要求する最小件数（R2-10。実行したコマンドを記録する）。
MIN_COMMANDS: int = 1

# ---------------------------------------------------------------------------
# 条項識別子（`VerificationResult.violations` の要素）
# ---------------------------------------------------------------------------

CLAUSE_TEST_SUITE = "R2-1"
CLAUSE_DJANGO_CHECK = "R2-2"
CLAUSE_CONTROL_PLATFORM_SELF_TEST = "R2-3"
CLAUSE_NON_REGRESSION_CHECK = "R2-4"
CLAUSE_PRERENDER = "R2-5"
CLAUSE_CONTENT_SECURITY_POLICY = "R2-6"
CLAUSE_RECORD_CONTENT = "R2-10"


def evaluate(record: NonRegressionRecord) -> VerificationResult:
    """R2-1〜R2-6 および R2-10 の全条件の同時成立を判定し、不適合条項を列挙する.

    判定条件（出典: design.md C4「判定条件」、同 Property 4、requirements.md
    Requirement 2 基準 1〜6・基準 10）:
        - `R2-1`: `tests_passed >= 133`（`BASELINE_TESTS_PASSED`）かつ
          `tests_failed == 0` かつ `tests_errored == 0`。
        - `R2-2`: `django_check_exit_code == 0`。
        - `R2-3`: `control_platform_exit_code == 0` かつ
          `self_test_exit_code == 0`（Control_Platform_Self_Test は 2 コマンドで
          構成されるため双方を同一条項で判定する）。
        - `R2-4`: `non_regression_exit_code == 0`。
        - `R2-5`: `prerendered_pages == 7` かつ `manifest_files == 1`。
        - `R2-6`: `len(content_security_policy) >= 1`。
        - `R2-10`: `commands` が非空。

    引数:
        record: 判定対象の `NonRegressionRecord`（1 回の非退行確認の実測記録）。
            外部入力として扱い、既定値による補完は行わない。

    戻り値:
        `VerificationResult`。`conformant` は上記全条件が同時成立した場合、かつ
        その場合に限り `True` となり、これは `violations` が空タプルであることと
        同値である。`violations` は不適合条項の識別子を上記の順（`R2-1` →
        `R2-2` → `R2-3` → `R2-4` → `R2-5` → `R2-6` → `R2-10`）で保持し、各識別子
        は最大 1 回出現する。

    例外:
        TypeError: `record` の各フィールドが比較演算（`int` の比較）または
            `len()` の適用に適さない場合。値の欠落や `None` を既定値で補完せず、
            評価時点で表面化させる（第三原則3 フォールバック禁止）。本関数は
            例外を捕捉しない。

    副作用:
        なし。コマンド実行・ファイル I/O・入力オブジェクトの変更を行わない
        （出典: design.md C4「コマンド実行そのものは行わない」）。
    """
    violations: list[str] = []

    # R2-1: Test_Suite。pass は Baseline 以上、failure と error は 0 件。
    # 3 つの下位条件はいずれも基準 1 に属するため、単一の条項識別子へ集約する。
    if (
        record.tests_passed < BASELINE_TESTS_PASSED
        or record.tests_failed != EXPECTED_TESTS_FAILED
        or record.tests_errored != EXPECTED_TESTS_ERRORED
    ):
        violations.append(CLAUSE_TEST_SUITE)

    # R2-2: `python manage.py check --fail-level WARNING` の終了コード。
    if record.django_check_exit_code != EXPECTED_EXIT_CODE:
        violations.append(CLAUSE_DJANGO_CHECK)

    # R2-3: Control_Platform_Self_Test は
    # `python -m scripts.control_platform.cli --self-test` と
    # `python tests/self_test.py` の 2 コマンドで構成される（出典:
    # requirements.md Glossary「Control_Platform_Self_Test」）。双方の終了コードが
    # 0 でなければ基準 3 は不成立である。
    if (
        record.control_platform_exit_code != EXPECTED_EXIT_CODE
        or record.self_test_exit_code != EXPECTED_EXIT_CODE
    ):
        violations.append(CLAUSE_CONTROL_PLATFORM_SELF_TEST)

    # R2-4: `python -m scripts.measurement.non_regression_check` の終了コード。
    if record.non_regression_exit_code != EXPECTED_EXIT_CODE:
        violations.append(CLAUSE_NON_REGRESSION_CHECK)

    # R2-5: Prerender_Command の生成件数（7 言語 + manifest 1 件）。
    if (
        record.prerendered_pages != EXPECTED_PRERENDERED_PAGES
        or record.manifest_files != EXPECTED_MANIFEST_FILES
    ):
        violations.append(CLAUSE_PRERENDER)

    # R2-6: manifest の `content_security_policy` は 1 文字以上。`len()` を用いる
    # ことで、値が `None` の場合は真偽値へ縮退させず TypeError として表面化する。
    if len(record.content_security_policy) < MIN_CONTENT_SECURITY_POLICY_LENGTH:
        violations.append(CLAUSE_CONTENT_SECURITY_POLICY)

    # R2-10: 非退行確認記録は実行したコマンドを含む。R2-6 と同じ理由で `len()` を
    # 用い、`None` を空と同一視しない。
    if len(record.commands) < MIN_COMMANDS:
        violations.append(CLAUSE_RECORD_CONTENT)

    # 適合は violations が空であることと同値（全条件同時成立。Property 4）。
    return VerificationResult(conformant=not violations, violations=tuple(violations))
