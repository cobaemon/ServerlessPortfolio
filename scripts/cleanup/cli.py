"""旧資産除去（legacy-asset-cleanup）の I/O 層 Cleanup CLI（design.md C13）.

目的:
    判定層（`inventory.py` / `removal_verification.py` / `completion.py` /
    `dependency_audit.py`）は外部 I/O を持たない純関数群である。本モジュールは
    その唯一の外側として、次の 3 点のみを担う。

    1. 外部入力の読み込みと**厳格な**デシリアライズ（Legacy_Asset_Inventory、
       非退行レコード、Dependency_Manifest、License_Ledger）。
    2. `git` コマンドの実行と終了コードの検査（残存走査の一致件数の取得）。
    3. 判定層の呼び出し結果を日本語の報告として出力し、不適合を非ゼロ終了で
       表面化させること。

    判定ロジックそのものは実装しない（単一責務。出典: design.md
    「Architecture > 依存方向」の「外側（`cli.py`）のみがファイル読み書きと
    `git` / `pip` / AWS CLI 実行結果の取り込みを担う」、同 C13）。

出典:
    - `.kiro/specs/legacy-asset-cleanup/design.md` C13「Cleanup CLI」（サブコマンド
      表・「`--verify-lines` の照合基準（R1-5）」・「Repository 外の `source_path` の
      扱い（R1-5 の適用範囲）」・フォールバック禁止・外部依存・ゼロトラスト）、同
      「Architecture > 依存方向」、同「Error Handling」表（スキーマ違反 → 違反一覧を
      出力して非ゼロ終了・判定を継続しない／行番号が記録 `revision` 時点の実体と
      不一致 → 不一致項目を出力して非ゼロ終了／台帳不整合 → 差分を出力して非ゼロ
      終了）、同 C1・DM1〜DM6。
    - `.kiro/specs/legacy-asset-cleanup/requirements.md` Glossary「Repository」
      （git 追跡下のファイル集合。`.kiro` は `.gitignore:176` により含まれない）。
    - `.kiro/specs/legacy-asset-cleanup/requirements.md` R1-5、R2-9、R2-10、
      R3-1、R3-2、R3-3、R3-4、R3-5、R4-1、R4-4、R4-5、R4-7、R4-8、R4-17、R6-1、
      R6-2、R6-3、R6-7、R7-5、R7-7、R9-1、R9-4、R9-5、R10-1。
    - `.kiro/specs/legacy-asset-cleanup/tasks.md` 5.1。
    - 既存前例: `scripts/measurement/non_regression_check.py`（`main(argv) -> int`
      と `raise SystemExit(main())` による終了コード規律、日本語ドキュメント、
      不適合の標準エラー出力）。
    - 同一の照合規則を実装する独立した検査:
      `tests/cleanup/test_inventory_line_numbers.py`（`source_lines` の表記解釈、
      UTF-8 固定・CRLF 安全な行数計上、記録 `revision` の追跡パス集合による適用範囲の
      導出）。本モジュールは同テストへ依存しない（`scripts/` から `tests/` を import
      しない。テストは独立した検査として残す）。

サブコマンド（design.md C13 の表と 1 対 1）:
    | サブコマンド | 処理 | 対応要件 |
    | --- | --- | --- |
    | `--validate-inventory` | Inventory を厳格に読み込み `validate_inventory` を適用 | R1 |
    | `--verify-lines` | 各項目の `source_path:source_lines` を Inventory が記録する `revision` 時点の実体（`git show <revision>:<source_path>`）へ照合する。対象は `source_path` が当該 revision の追跡集合に含まれる項目に限る | R1-5、Glossary（Repository） |
    | `--check-residual` | 除去確認コマンド（`git ls-files` / `git grep` / `git check-ignore`）を実行し一致件数を取得 | R3-1、R3-2、R3-3、R3-4、R3-5、R4-1、R4-4、R4-5、R4-7、R4-8、R4-17、R6-1〜R6-3、R6-7、R7-5、R10-1 |
    | `--evaluate` | 非退行レコードを読み込み `evaluate` / `is_removed` / `is_stream_b_complete` を適用する。不適合として扱うのは R2-9（非退行不適合）と R4-14（系統 B 未完了）のみであり、R9-5 の計上不能は「計上対象外」として理由付きで報告する（下記「`--evaluate` が不適合として扱う条件」） | R2、R9-5 |
    | `--audit-dependencies` | Dependency_Manifest と License_Ledger の記載集合を `check_ledger_coherence` へ渡す | R7-7 |

終了コード規律（`.kiro/steering/principles.md` 第三原則3 フォールバック禁止）:
    - `0`: 要求された検査がすべて適合した場合に限る。
    - `1`: 検査結果が不適合（違反一覧を標準エラーへ日本語で出力する）。
    - `2`: 入力またはコマンド実行の失敗、および判定不能（入力ファイルの不在、
      スキーマ違反による判定継続の中止、`git` の異常終了、判定層が矛盾入力に対して
      送出した `ValueError`）。既定値による補完を行わないため、これらは適合／不適合
      の判定へ吸収せず区別して終了する。

ゼロトラスト（第二原則2）:
    - Inventory とレコードは外部入力として扱う。`--verify-lines` /
      `--check-residual` / `--evaluate` は判定の前に必ず `validate_inventory` を
      適用し、違反が 1 件でもあれば判定を実行せず終了コード 2 で終了する
      （出典: design.md C13「ゼロトラスト」、同 Error Handling の「Inventory の
      スキーマ違反」行）。
    - デシリアライズは厳格に行う。キーの欠落・余剰キー・型不一致はいずれも失敗と
      し、既定値で補完しない（design.md C13「フォールバック禁止」）。
    - Inventory が保持する確認コマンド文字列は外部入力であるため、そのまま実行
      しない。`shell=True` を用いず引数配列で実行し、実行を許すのは `git` の
      `ls-files` / `grep` / `check-ignore` に限定する（`_ALLOWED_GIT_SUBCOMMANDS`）。
      これ以外のプログラム・サブコマンドは実行せず失敗させる。
    - `--verify-lines` が用いる `git ls-tree` / `git show` は、コマンド文字列では
      なく本モジュールが組み立てる固定の引数配列で実行する（`_run_git`）。引数へ
      渡す Inventory の `revision` は外部入力であるため、SHA-1 の 16 進表記である
      ことを `_validated_revision` で検証してから渡す（`-` で始まる値がオプションと
      して解釈される余地を残さない）。`source_path` は `git show <revision>:<path>`
      の形で revision 接頭辞の後に置くため、単独の引数としてオプション位置に現れない。

`--verify-lines` の照合基準（R1-5。出典: design.md C13 の同名の節）:
    - 照合先は作業ツリーの現在の内容ではなく、Inventory が `revision`（DM2）として
      記録した時点の内容とし、`git show <revision>:<source_path>` で取得する。
      R1-5 が求めるのは「作成時点のリポジトリ実体」との一致であり、作業ツリーを
      照合先にすると除去の適用後に R1-5 が求めていない理由（当該行が既に除去済みで
      あること）で不一致となるためである。
    - 照合対象は `source_path` が Repository（Glossary。git 追跡下のファイル集合）に
      含まれる項目に限る。当該 revision 時点の追跡集合は
      `git ls-tree -r -z --name-only <revision>` で取得する（`git ls-files` は現在の
      インデックスを対象とし、過去 revision の集合を返さないため用いない）。
    - Repository 外の `source_path`（`.kiro` は `.gitignore:176` により Repository に
      含まれない）を持つ項目は「R1-5 の照合対象外」である事実として出典付きで報告し、
      不一致（非ゼロ終了）として扱わない。照合結果を既定値や推測で補わない。
    - 照合するのは出典 3 要素のうちファイルパスと行番号である（R1-1）。`description`
      は DM1 が「対象の説明」と定める非出典要素であるため、その文面と実体の一致は
      照合しない（R1-5 の要求範囲外）。

`--evaluate` が不適合として扱う条件（R9-5 の文面解釈。実装は `run_evaluate`）:
    - 不適合（終了コード 1）とするのは、要件本文が不適合を定める次の 2 つに限る。
      R2-9（requirements.md:189。基準 1 から基準 6 のいずれかの確認が不適合となった
      場合に当該除去を未完了として扱う）と、R4-14（requirements.md:225。系統 B の
      完了判定）および R4-15（requirements.md:226。AWS 側不在確認が未成立の間は
      未完了として記録する）である。いずれも design.md「Error Handling」表に検知
      箇所と扱いが定められている（design.md:727、design.md:729）。
    - R9-5（requirements.md:313）は「…項目**のみ**を『除去済み』として計上する」で
      あり、計上してよい条件の**限定**を定める。「すべての `除去対象` 項目が計上
      可能でなければならない」とは定めていないため、「計上できないこと」自体を
      不適合とする条件は要件本文から導出できない。design.md C13 の `--evaluate`
      行（design.md:385）も「除去済み計上を**判定**」と記述するにとどまり、計上不能を
      違反として列挙することを規定していない。したがって計上できなかった項目は
      違反ではなく「計上対象外」として件数と理由を報告する（握りつぶさない。
      第三原則3）。
    - 条項の期待が「一致 1 件以上」である 2 項目（`gitignore_aws_sam` → R3-3、
      `prod_email_backend_policy` → R4-17。`_RESIDUAL_EXPECTATIONS` の
      `expect_zero_matches=False`）は、条項が適合しているときに一致件数が 1 件以上と
      なるため、R9-5 の計上条件「一致 0 件」とは向きが逆であり構造的に計上対象外で
      ある。これらの条項の適合判定は `--check-residual` が担う（同サブコマンドは
      条項別の期待に基づいて適合を判定する）。
    - 期待「一致 0 件」の項目に一致が残っている場合（除去が実際に成立していない
      場合）は、当該項目の条項（R3-1、R3-2、R4-1、R4-4、R4-5、R4-7、R4-8、R6-1〜
      R6-3、R7-5、R10-1）の不適合であり、design.md C13 はこれらの適合判定を
      `--check-residual` 行（design.md:384）へ割り当てている。`--evaluate` と
      `--check-residual` はいずれも `collect_residual_results(inventory)` を用いるため
      走査対象が完全に一致しており、`--check-residual` が終了コード 1 で表面化させる。
      条項識別子の帰属を二重化せず、かつ見逃しも生じない（第三原則2 整合性）。

`git` の終了コードの扱い（重要な非自明点。実装は `run_check_command`）:
    - `git grep`: 一致あり → `0`、**一致なし → `1`**、異常 → `2` 以上。残存走査に
      おいて「一致なし」は成功側の結果であるため `1` を失敗として扱わない。同時に
      `2` 以上を「一致なし」へ丸めない（異常を成功と誤認しない）。
    - `git check-ignore -v`: 指定パスが除外規則に一致 → `0`（規則を出力）、
      一致なし → `1`、異常 → `128`（`2` 以上）。R3-3 は `.aws-sam/build.toml` が
      当該規則により除外されることを求めるため、本コマンドの期待は「一致 1 件
      以上」である（他の除去確認コマンドと期待が逆であることに注意）。
    - `git ls-files`: 対象が存在しなくても `0` で終了し標準出力が空になる。したがって
      非ゼロ終了は異常として扱い、「一致なし」と解釈しない。
    - `--verify-lines` が用いる `git ls-tree` / `git show`（実装は
      `list_tracked_paths_at_revision` / `read_revision_lines`）は `0` のみを正常と
      する。`git show <revision>:<path>` は当該 revision に当該パスが存在しない場合に
      非ゼロで終了するため、これは「記録 revision に存在しない出典を主張している」
      ことを意味する失敗として扱い、空内容へ丸めない（第三原則3）。

除去確認コマンドの出所（重複記述の回避。第三原則2）:
    - 実行するコマンド文字列は Legacy_Asset_Inventory の各項目の
      `removal_check_command` から取得する。Inventory が正本として保持している
      ため、CLI 側でコマンド一覧を再記述しない。
    - 一方、各コマンドに対する**期待値**（一致 0 件か、1 件以上か）は Inventory の
      スキーマ（DM1）に存在しない。期待値は受入基準が定めるものであるため、
      `_RESIDUAL_EXPECTATIONS` に「Inventory 項目キー → 条項識別子と期待」の対応と
      してのみ保持する（コマンド文字列は保持しない）。表に存在しないキーの除去確認は
      判定不能として終了コード 2 で表面化させ、既定の期待値（例「常に 0 件」）を
      与えない。
    - R3-5（`git grep -n -E "asgi_lambda|mangum|Mangum"` の一致箇所が
      Repository_Documents、`.kiro/specs` 配下の記録、
      `docs/legacy-asset-inventory.json`、`scripts/cleanup/` 配下、`tests/cleanup/`
      配下に限定されること）は、単一の
      Inventory 項目に紐づく確認ではなく系統 A 全体に対する条項であり、いずれの項目の
      `removal_check_command` にも記録されていない（出典:
      `docs/legacy-asset-inventory.json` の `removal_check_command` 全件）。この 1 件
      に限り条項本文の実行コマンドを `_R3_5_*` 定数として保持する。

外部依存:
    標準ライブラリのみを用いる（`argparse`, `dataclasses`, `json`, `pathlib`,
    `re`, `shlex`, `subprocess`, `sys`）。新規の外部パッケージを導入しないため、
    第二原則6 のライセンス確認対象を増やさない（出典: design.md C13「外部依存」）。

実行コマンド（プロジェクトルートから）:
    python -m scripts.cleanup.cli --validate-inventory
    python -m scripts.cleanup.cli --verify-lines
    python -m scripts.cleanup.cli --check-residual
    python -m scripts.cleanup.cli --evaluate [--records-path <path>]
    python -m scripts.cleanup.cli --audit-dependencies
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .completion import is_removed, is_stream_b_complete
from .dependency_audit import (
    JUDGEMENT_TARGET_DEPENDENCIES,
    check_ledger_coherence,
    normalize_package_name,
)
from .inventory import (
    DISPOSITION_REMOVAL_TARGET,
    DISPOSITION_UNDETERMINED,
    validate_inventory,
)
from .models import (
    STREAM_B_AWS_TARGETS,
    AwsSmtpState,
    Confirmation,
    Inventory,
    LegacyAssetItem,
    NonRegressionRecord,
    PreservedAssetItem,
    UndeterminedNote,
    VerificationResult,
)
from .removal_verification import evaluate

# ---------------------------------------------------------------------------
# パス定数（本ファイルは <repo>/scripts/cleanup/cli.py。2 階層上がリポジトリルート）
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Inventory 正本（design.md C1「正本は 1 つに限定する」）。引数で差し替えない。
_INVENTORY_PATH = _REPO_ROOT / "docs" / "legacy-asset-inventory.json"

# 非退行レコードの既定パス（tasks.md 13.1 が作成する。本タスクでは作成しない）。
_DEFAULT_RECORDS_PATH = (
    _REPO_ROOT / "docs" / "development-records" / "legacy-asset-cleanup-records.json"
)

# Dependency_Manifest と License_Ledger（requirements.md Glossary）。
_MANIFEST_PATH = _REPO_ROOT / "requirements.txt"
_LEDGER_PATH = _REPO_ROOT / "docs" / "external-assets.md"

# ---------------------------------------------------------------------------
# 終了コード（モジュール docstring「終了コード規律」）
# ---------------------------------------------------------------------------

EXIT_CONFORMANT = 0
EXIT_NON_CONFORMANT = 1
EXIT_INPUT_FAILURE = 2

# ---------------------------------------------------------------------------
# 実行を許可するコマンド（ゼロトラスト）
# ---------------------------------------------------------------------------

# Inventory の `removal_check_command` は外部入力である。実行を許すのは `git` の
# 読み取り専用サブコマンド 3 種に限定し、これ以外は実行しない。
_ALLOWED_GIT_SUBCOMMANDS: frozenset[str] = frozenset(
    {"ls-files", "grep", "check-ignore"}
)

# 「一致なし」を終了コード 1 で表すサブコマンド（モジュール docstring 参照）。
_NO_MATCH_EXIT_SUBCOMMANDS: frozenset[str] = frozenset({"grep", "check-ignore"})


@dataclass(frozen=True)
class ResidualExpectation:
    """除去確認コマンド 1 件に対する期待（受入基準由来）.

    属性:
        clause: 期待の根拠となる条項識別子（例 `"R3-1"`）。
        expect_zero_matches: `True` は「一致 0 件」を期待する条項、`False` は
            「一致 1 件以上」を期待する条項であることを表す。
        note: 期待の内容を日本語で述べた説明（報告へ出力する）。
    """

    clause: str
    expect_zero_matches: bool
    note: str


# Inventory 項目キー → 期待。コマンド文字列は Inventory 側が正本であるため保持しない。
# 各条項の出典は requirements.md の対応基準（`R<要件番号>-<基準番号>`）。
_RESIDUAL_EXPECTATIONS: dict[str, ResidualExpectation] = {
    "asgi_lambda": ResidualExpectation(
        "R3-1", True, "`git ls-files -- asgi_lambda.py` の一致 0 件"
    ),
    "aws_sam_build_toml": ResidualExpectation(
        "R3-2", True, "`git ls-files -- .aws-sam/` の一致 0 件"
    ),
    # R3-3 のみ期待が逆。`.gitignore` の `.aws-sam/` 規則が報告されることを求める。
    "gitignore_aws_sam": ResidualExpectation(
        "R3-3",
        False,
        "`git check-ignore -v .aws-sam/build.toml` が除外規則を 1 件以上報告",
    ),
    "prod_smtp_required": ResidualExpectation(
        "R4-1",
        True,
        "`config/` の EMAIL_HOST|EMAIL_PORT|EMAIL_USE_TLS|EMAIL_USE_SSL 一致 0 件",
    ),
    "prod_smtp_comment": ResidualExpectation(
        "R4-1", True, "同上（コメント記述の整合も同一走査で確認する）"
    ),
    "dev_smtp_block": ResidualExpectation("R4-1", True, "同上（dev の SMTP 読み込み）"),
    "forms_smtp_log": ResidualExpectation(
        "R4-5", True, "`portfolio/` の EMAIL_* 一致 0 件"
    ),
    # R4-7 は `except Exception` による握りつぶしの除去を求める（design.md 区分 B-5）。
    "forms_send_email_fallback": ResidualExpectation(
        "R4-7", True, "`portfolio/forms.py` の `except Exception` 一致 0 件"
    ),
    "buildspec_smtp_export": ResidualExpectation(
        "R4-4", True, "`buildspec.yml` の email_* 一致 0 件"
    ),
    "buildspec_smtp_comment": ResidualExpectation(
        "R4-4", True, "同上（コメント記述の整合も同一走査で確認する）"
    ),
    "docs_configuration_smtp": ResidualExpectation(
        "R4-8", True, "Configuration_Documents の SMTP 関連キー一致 0 件"
    ),
    "docs_staging_policy_smtp": ResidualExpectation("R4-8", True, "同上"),
    "test_regression_smtp_env": ResidualExpectation(
        "R4-5", True, "`portfolio/` の EMAIL_* 一致 0 件（required_env を含む）"
    ),
    "base_unused_imports": ResidualExpectation(
        "R6-3", True, "`config/settings/base.py` の未使用 import 一致 0 件"
    ),
    "base_installed_apps_comments": ResidualExpectation(
        "R6-1", True, "`config/` の allauth|django_otp 一致 0 件"
    ),
    "base_middleware_comments": ResidualExpectation("R6-1", True, "同上"),
    "base_auth_comment_block": ResidualExpectation("R6-1", True, "同上"),
    "base_templates_comment": ResidualExpectation(
        "R6-2", True, "`config/` の accounts 一致 0 件"
    ),
    "urls_comments": ResidualExpectation("R6-2", True, "同上"),
    "docs_deployment_time_record": ResidualExpectation(
        "R10-1",
        True,
        "`docs/development-records/deployment-time-optimization.md` の "
        "asgi_lambda 一致 0 件",
    ),
    # R4-17 も期待が逆。prod へ console バックエンドが明示設定されることを求める。
    "prod_email_backend_policy": ResidualExpectation(
        "R4-17",
        False,
        "`config/settings/prod.py` の EMAIL_BACKEND 明示設定が 1 件以上",
    ),
    # 系統 D（未使用 dependency）の 12 件。Inventory の `removal_check_command` は
    # いずれも `git grep -n -E "^<pkg>==" -- requirements.txt` であり、除去後の期待は
    # 「一致 0 件」である。根拠条項の選定は次のとおり。
    #   - 既定は R7-5（「WHEN Direct_Dependency としても Transitive_Dependency
    #     としても要求されないことが確認された時、THE Executor SHALL 当該 dependency
    #     の行を Dependency_Manifest から除去する」）。Dependency_Manifest（=
    #     `requirements.txt`）からの行除去を求める条項はこれである。
    #   - `dep_mangum` のみ R3-4 を用いる。R3-4 は「WHEN `asgi_lambda.py` を除去する
    #     時、THE Executor SHALL Dependency_Manifest から `mangum==0.21.0`（出典:
    #     `requirements.txt:20`）を除去し、Requirement 7 の各基準を適用する」と対象
    #     パッケージ・バージョン・出典行を名指しで定めており、当該 1 行の除去に対する
    #     最も特定的な条項である（R7-5 は R3-4 が委任する一般条項として併せて成立する）。
    #     `asgi_lambda.py` の除去はタスク 7.1 で適用済みであり R3-4 の WHEN 条件は成立
    #     している（出典: `git ls-files -- asgi_lambda.py` の一致 0 件）。
    #   - `dep_django_allauth` / `dep_django_otp` の除去契機は R6-7（「WHEN
    #     `django-allauth` または `django-otp` を参照するコメントアウト行を除去した時、
    #     THE Executor SHALL Requirement 7 の各基準を当該 dependency へ適用する」）で
    #     あるが、R6-7 自体は行除去を定めず Requirement 7 へ委任するため、期待の根拠
    #     条項は R7-5 とする。
    "dep_awsgi": ResidualExpectation(
        "R7-5", True, "`requirements.txt` の `^awsgi==` 一致 0 件"
    ),
    "dep_django_allauth": ResidualExpectation(
        "R7-5",
        True,
        "`requirements.txt` の `^django-allauth==` 一致 0 件（契機は R6-7）",
    ),
    "dep_django_otp": ResidualExpectation(
        "R7-5",
        True,
        "`requirements.txt` の `^django-otp==` 一致 0 件（契機は R6-7）",
    ),
    "dep_gunicorn": ResidualExpectation(
        "R7-5", True, "`requirements.txt` の `^gunicorn==` 一致 0 件"
    ),
    "dep_httptools": ResidualExpectation(
        "R7-5", True, "`requirements.txt` の `^httptools==` 一致 0 件"
    ),
    # R3-4 が `mangum==0.21.0` の除去を名指しで求める（R7-5 も委任により成立）。
    "dep_mangum": ResidualExpectation(
        "R3-4", True, "`requirements.txt` の `^mangum==` 一致 0 件"
    ),
    "dep_psycopg2_binary": ResidualExpectation(
        "R7-5", True, "`requirements.txt` の `^psycopg2-binary==` 一致 0 件"
    ),
    "dep_pyjwt": ResidualExpectation(
        "R7-5", True, "`requirements.txt` の `^pyjwt==` 一致 0 件"
    ),
    "dep_qrcode": ResidualExpectation(
        "R7-5", True, "`requirements.txt` の `^qrcode==` 一致 0 件"
    ),
    "dep_uvloop": ResidualExpectation(
        "R7-5", True, "`requirements.txt` の `^uvloop==` 一致 0 件"
    ),
    "dep_websockets": ResidualExpectation(
        "R7-5", True, "`requirements.txt` の `^websockets==` 一致 0 件"
    ),
    "dep_werkzeug": ResidualExpectation(
        "R7-5", True, "`requirements.txt` の `^werkzeug==` 一致 0 件"
    ),
}

# R3-5 の走査（Inventory の項目に紐づかない系統 A 全体の条項）。コマンドは
# requirements.md R3-5 の本文から引用する。
_R3_5_COMMAND = 'git grep -n -E "asgi_lambda|mangum|Mangum"'

# R3-5 が一致を許す範囲（出典: requirements.md Requirement 3 基準 5 および同
# 「Evidence（基準 5 の許容範囲の根拠）」、design.md C6 の A1-6）。内訳は次の 5 区分。
#   1. Repository_Documents = 「git 追跡下の `docs/` 配下 Markdown および
#      `README.md`」（requirements.md Glossary。本改訂で当該定義は変更されていない
#      ため、`docs/` 配下は Markdown に限る）。
#   2. `.kiro/specs` 配下の記録。`.kiro` は `.gitignore:176` により git 追跡外であり
#      `git grep` の走査対象に入らないが、条項本文が挙げる範囲であるため判定条件と
#      しても明示する。
#   3. Legacy_Asset_Inventory の正本 `docs/legacy-asset-inventory.json`。Markdown で
#      はないため prefix 判定ではなく完全一致で許容する。
#   4. 判定層および Cleanup CLI（`scripts/cleanup/` 配下）。
#   5. 判定層のテスト（`tests/cleanup/` 配下）。
# 3〜5 は本 spec 自身が生成を義務付ける記録および判定コードであり、実行経路から
# `asgi_lambda` / `mangum` を参照するものではない（同 Evidence 節）。条項本文が挙げる
# 範囲を超えて許容しないため、`scripts/` 全体や `tests/` 全体は許容範囲に含めない。
_R3_5_ALLOWED_DIRECTORY_PREFIXES: tuple[str, ...] = (
    "docs/",
    ".kiro/specs/",
    "scripts/cleanup/",
    "tests/cleanup/",
)
_R3_5_ALLOWED_EXACT_PATHS: frozenset[str] = frozenset(
    {"README.md", "docs/legacy-asset-inventory.json"}
)
_R3_5_ALLOWED_DOC_SUFFIX = ".md"

# ---------------------------------------------------------------------------
# 外部入力のスキーマ（design.md DM1〜DM3、DM6 の写像）
# ---------------------------------------------------------------------------

_INVENTORY_KEYS: frozenset[str] = frozenset(
    {"revision", "items", "preserved", "undetermined_notes"}
)
_ITEM_KEYS: frozenset[str] = frozenset(
    {
        "key",
        "description",
        "stream",
        "disposition",
        "source_path",
        "source_lines",
        "detection_command",
        "confirmation",
        "removal_check_command",
        "approver_decision_required",
    }
)
_CONFIRMATION_KEYS: frozenset[str] = frozenset({"result", "evidence_command"})
_PRESERVED_KEYS: frozenset[str] = frozenset(
    {
        "key",
        "description",
        "disposition",
        "source_path",
        "source_lines",
        "detection_command",
        "build_time_dependency",
    }
)
_NOTE_KEYS: frozenset[str] = frozenset({"key", "reason", "pending_check"})

_RECORDS_DOCUMENT_KEYS: frozenset[str] = frozenset(
    {"applied_stream_b_segments", "non_regression_records", "aws_smtp_state"}
)
_NON_REGRESSION_RECORD_KEYS: frozenset[str] = frozenset(
    {
        "stream",
        "commands",
        "tests_passed",
        "tests_failed",
        "tests_errored",
        "django_check_exit_code",
        "control_platform_exit_code",
        "self_test_exit_code",
        "non_regression_exit_code",
        "prerendered_pages",
        "manifest_files",
        "content_security_policy",
    }
)
_AWS_SMTP_STATE_KEYS: frozenset[str] = frozenset(
    {"queried", "absent_targets", "deleted_targets", "expected_targets"}
)

# ---------------------------------------------------------------------------
# 行番号照合の表記解釈（`tests/cleanup/test_inventory_line_numbers.py` と同一規則）
# ---------------------------------------------------------------------------

# `source_lines` の 1 トークン。単一行番号（`170`）または閉区間（`72-86`）のみを許す。
_SOURCE_LINES_TOKEN = re.compile(r"\A(?:(?P<single>\d+)|(?P<start>\d+)-(?P<end>\d+))\Z")

# 記録 `revision` として受理する表記（短縮または完全な SHA-1 の 16 進表記）。外部入力を
# `git` の引数へ渡す前に表記を限定する（ゼロトラスト。モジュール docstring 参照）。
_REVISION_PATTERN = re.compile(r"\A[0-9a-f]{7,40}\Z")


class CleanupCliError(Exception):
    """外部入力の不備・コマンド実行の失敗・判定不能を表す例外.

    `main` が捕捉し、内容を標準エラーへ出力して終了コード
    `EXIT_INPUT_FAILURE`（2）で終了する。既定値による補完を行わないため、
    適合／不適合の判定へ吸収せず区別して扱う（第三原則3）。
    """


# ---------------------------------------------------------------------------
# 厳格なデシリアライズ（design.md C13「ゼロトラスト」「フォールバック禁止」）
# ---------------------------------------------------------------------------


def _read_json_document(path: Path, description: str) -> object:
    """JSON ファイルを UTF-8 固定で読み込み、デコード結果を返す（内部関数）.

    引数:
        path: 読み込み対象の絶対パス。
        description: エラーメッセージへ含める入力の説明（例 `"Inventory 正本"`）。

    戻り値:
        `json.loads` の結果（型は呼び出し側が検証する）。

    例外:
        CleanupCliError: ファイルが存在しない、UTF-8 として解釈できない、または
            JSON として解釈できない場合。いずれも欠落を既定値で補完せず、終了
            コード 2 の失敗として表面化させる。

    UTF-8 以外のエンコーディングへ再試行しない（代替エンコーディングでの読み替えは
    フォールバックに相当する。第三原則3）。
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CleanupCliError(f"{description} を読み込めない: {path}（{exc}）") from exc

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CleanupCliError(
            f"{description} を UTF-8 として解釈できない: {path}（{exc}）"
        ) from exc

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise CleanupCliError(
            f"{description} を JSON として解釈できない: {path}（{exc}）"
        ) from exc


def _require_mapping(value: object, context: str) -> dict[str, object]:
    """値が JSON オブジェクト（辞書）であることを確認して返す（内部関数）.

    引数:
        value: 検査対象の値。
        context: エラーメッセージへ含める位置情報（例 `"items[3]"`）。

    戻り値:
        辞書としての `value`。

    例外:
        CleanupCliError: 辞書でない場合。
    """
    if not isinstance(value, dict):
        raise CleanupCliError(
            f"{context}: JSON オブジェクトである必要がある"
            f"（実際: {type(value).__name__}）"
        )
    return value


def _require_list(value: object, context: str) -> list[object]:
    """値が JSON 配列（リスト）であることを確認して返す（内部関数）.

    引数:
        value: 検査対象の値。
        context: エラーメッセージへ含める位置情報。

    戻り値:
        リストとしての `value`。

    例外:
        CleanupCliError: リストでない場合。
    """
    if not isinstance(value, list):
        raise CleanupCliError(
            f"{context}: JSON 配列である必要がある（実際: {type(value).__name__}）"
        )
    return value


def _require_exact_keys(
    mapping: dict[str, object], expected: frozenset[str], context: str
) -> None:
    """辞書のキー集合が期待と完全一致することを確認する（内部関数）.

    欠落キーを既定値で補完せず、未知キーも黙って無視しない。スキーマの想定外は
    入力側の誤りとして表面化させる（design.md C13「フォールバック禁止」、
    第二原則2 ゼロトラスト）。

    引数:
        mapping: 検査対象の辞書。
        expected: 期待するキー集合。
        context: エラーメッセージへ含める位置情報。

    戻り値:
        なし。

    例外:
        CleanupCliError: 欠落キーまたは未知キーが存在する場合。
    """
    actual = frozenset(mapping)
    missing = tuple(sorted(expected - actual))
    unknown = tuple(sorted(actual - expected))
    if missing:
        raise CleanupCliError(f"{context}: 必須キーが欠落している（{missing}）")
    if unknown:
        raise CleanupCliError(f"{context}: 未知のキーが存在する（{unknown}）")


def _require_str(mapping: dict[str, object], key: str, context: str) -> str:
    """辞書から文字列値を取得する（内部関数）.

    引数:
        mapping: 取得元の辞書。
        key: 取得するキー。
        context: エラーメッセージへ含める位置情報。

    戻り値:
        文字列値。

    例外:
        CleanupCliError: 値が文字列でない場合（`None` を含む）。
    """
    value = mapping[key]
    if not isinstance(value, str):
        raise CleanupCliError(
            f"{context}.{key}: 文字列である必要がある（実際: {type(value).__name__}）"
        )
    return value


def _require_optional_str(
    mapping: dict[str, object], key: str, context: str
) -> str | None:
    """辞書から文字列または `None` の値を取得する（内部関数）.

    引数:
        mapping: 取得元の辞書。
        key: 取得するキー。
        context: エラーメッセージへ含める位置情報。

    戻り値:
        文字列値、または `None`（未設定であることを明示する値）。

    例外:
        CleanupCliError: 値が文字列でも `None` でもない場合。
    """
    value = mapping[key]
    if value is None:
        return None
    if not isinstance(value, str):
        raise CleanupCliError(
            f"{context}.{key}: 文字列または null である必要がある"
            f"（実際: {type(value).__name__}）"
        )
    return value


def _require_bool(mapping: dict[str, object], key: str, context: str) -> bool:
    """辞書から真偽値を取得する（内部関数）.

    引数:
        mapping: 取得元の辞書。
        key: 取得するキー。
        context: エラーメッセージへ含める位置情報。

    戻り値:
        真偽値。

    例外:
        CleanupCliError: 値が真偽値でない場合。整数 `0` / `1` や文字列
            `"true"` を真偽値へ読み替えない（型の推測補完を行わない）。
    """
    value = mapping[key]
    if not isinstance(value, bool):
        raise CleanupCliError(
            f"{context}.{key}: 真偽値である必要がある（実際: {type(value).__name__}）"
        )
    return value


def _require_int(mapping: dict[str, object], key: str, context: str) -> int:
    """辞書から整数値を取得する（内部関数）.

    引数:
        mapping: 取得元の辞書。
        key: 取得するキー。
        context: エラーメッセージへ含める位置情報。

    戻り値:
        整数値。

    例外:
        CleanupCliError: 値が整数でない場合。`bool` は `int` の派生型であるが
            件数・終了コードとして受理しない（真偽値の混入を黙認しない）。
    """
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise CleanupCliError(
            f"{context}.{key}: 整数である必要がある（実際: {type(value).__name__}）"
        )
    return value


def _require_str_tuple(
    mapping: dict[str, object], key: str, context: str
) -> tuple[str, ...]:
    """辞書から文字列配列を取得しタプルへ変換する（内部関数）.

    引数:
        mapping: 取得元の辞書。
        key: 取得するキー。
        context: エラーメッセージへ含める位置情報。

    戻り値:
        文字列のタプル（判定層は不変値を前提とするためタプルへ変換する）。

    例外:
        CleanupCliError: 値が配列でない、または要素に文字列以外を含む場合。
    """
    values = _require_list(mapping[key], f"{context}.{key}")
    result: list[str] = []
    for index, element in enumerate(values):
        if not isinstance(element, str):
            raise CleanupCliError(
                f"{context}.{key}[{index}]: 文字列である必要がある"
                f"（実際: {type(element).__name__}）"
            )
        result.append(element)
    return tuple(result)


# ---------------------------------------------------------------------------
# Inventory の読み込み（DM1 / DM2 への写像）
# ---------------------------------------------------------------------------


def _build_confirmation(value: object, context: str) -> Confirmation | None:
    """`confirmation` を `Confirmation` または `None` へ変換する（内部関数）.

    引数:
        value: JSON 上の `confirmation` の値（オブジェクトまたは null）。
        context: エラーメッセージへ含める位置情報。

    戻り値:
        `Confirmation`、または未確認を表す `None`（R1-6）。

    例外:
        CleanupCliError: オブジェクトでも null でない場合、キー集合が不一致の
            場合、または値の型が不正な場合。
    """
    if value is None:
        # 未確認は `None` として保持する。空の `Confirmation` を捏造しない（R1-6）。
        return None
    mapping = _require_mapping(value, f"{context}.confirmation")
    _require_exact_keys(mapping, _CONFIRMATION_KEYS, f"{context}.confirmation")
    return Confirmation(
        result=_require_str(mapping, "result", f"{context}.confirmation"),
        evidence_command=_require_str(
            mapping, "evidence_command", f"{context}.confirmation"
        ),
    )


def _build_item(value: object, context: str) -> LegacyAssetItem:
    """JSON オブジェクト 1 件を `LegacyAssetItem`（DM1）へ変換する（内部関数）.

    引数:
        value: JSON 上の 1 項目。
        context: エラーメッセージへ含める位置情報（例 `"items[0]"`）。

    戻り値:
        `LegacyAssetItem`。

    例外:
        CleanupCliError: キー集合が不一致、または値の型が不正な場合。値域
            （`stream` / `disposition` の排他値）の検証は判定層
            `inventory.validate_inventory` が担うため、本関数は型のみを検証する。
    """
    mapping = _require_mapping(value, context)
    _require_exact_keys(mapping, _ITEM_KEYS, context)
    return LegacyAssetItem(
        key=_require_str(mapping, "key", context),
        description=_require_str(mapping, "description", context),
        stream=_require_str(mapping, "stream", context),
        disposition=_require_str(mapping, "disposition", context),
        source_path=_require_str(mapping, "source_path", context),
        source_lines=_require_str(mapping, "source_lines", context),
        detection_command=_require_str(mapping, "detection_command", context),
        confirmation=_build_confirmation(mapping["confirmation"], context),
        removal_check_command=_require_optional_str(
            mapping, "removal_check_command", context
        ),
        approver_decision_required=_require_bool(
            mapping, "approver_decision_required", context
        ),
    )


def _build_preserved_item(value: object, context: str) -> PreservedAssetItem:
    """JSON オブジェクト 1 件を `PreservedAssetItem`（DM1）へ変換する（内部関数）.

    引数:
        value: JSON 上の 1 項目。
        context: エラーメッセージへ含める位置情報（例 `"preserved[0]"`）。

    戻り値:
        `PreservedAssetItem`。

    例外:
        CleanupCliError: キー集合が不一致、または値の型が不正な場合。
    """
    mapping = _require_mapping(value, context)
    _require_exact_keys(mapping, _PRESERVED_KEYS, context)
    return PreservedAssetItem(
        key=_require_str(mapping, "key", context),
        description=_require_str(mapping, "description", context),
        disposition=_require_str(mapping, "disposition", context),
        source_path=_require_str(mapping, "source_path", context),
        source_lines=_require_str(mapping, "source_lines", context),
        detection_command=_require_str(mapping, "detection_command", context),
        build_time_dependency=_require_str(mapping, "build_time_dependency", context),
    )


def _build_note(value: object, context: str) -> UndeterminedNote:
    """JSON オブジェクト 1 件を `UndeterminedNote`（DM1）へ変換する（内部関数）.

    引数:
        value: JSON 上の 1 項目。
        context: エラーメッセージへ含める位置情報（例 `"undetermined_notes[0]"`）。

    戻り値:
        `UndeterminedNote`。

    例外:
        CleanupCliError: キー集合が不一致、または値の型が不正な場合。
    """
    mapping = _require_mapping(value, context)
    _require_exact_keys(mapping, _NOTE_KEYS, context)
    return UndeterminedNote(
        key=_require_str(mapping, "key", context),
        reason=_require_str(mapping, "reason", context),
        pending_check=_require_str(mapping, "pending_check", context),
    )


def load_inventory(path: Path) -> Inventory:
    """Legacy_Asset_Inventory を厳格に読み込み `Inventory`（DM2）へ変換する.

    キーの欠落・未知キー・型不一致はすべて `CleanupCliError` とし、既定値による
    補完を行わない（出典: design.md C13「フォールバック禁止」「ゼロトラスト」）。
    値域（`stream` / `disposition` の排他値、必須キー網羅）の検証は判定層
    `inventory.validate_inventory` が担う（責務分離）。

    引数:
        path: `docs/legacy-asset-inventory.json` の絶対パス。

    戻り値:
        `Inventory`。

    例外:
        CleanupCliError: ファイルの読み込み・デコード・スキーマ検証に失敗した場合。
    """
    document = _require_mapping(
        _read_json_document(path, "Inventory 正本"), "legacy-asset-inventory.json"
    )
    _require_exact_keys(document, _INVENTORY_KEYS, "legacy-asset-inventory.json")

    items = tuple(
        _build_item(element, f"items[{index}]")
        for index, element in enumerate(_require_list(document["items"], "items"))
    )
    preserved = tuple(
        _build_preserved_item(element, f"preserved[{index}]")
        for index, element in enumerate(
            _require_list(document["preserved"], "preserved")
        )
    )
    notes = tuple(
        _build_note(element, f"undetermined_notes[{index}]")
        for index, element in enumerate(
            _require_list(document["undetermined_notes"], "undetermined_notes")
        )
    )

    return Inventory(
        revision=_require_str(document, "revision", "legacy-asset-inventory.json"),
        items=items,
        preserved=preserved,
        undetermined_notes=notes,
    )


def load_validated_inventory(path: Path) -> Inventory:
    """Inventory を読み込み、判定前に `validate_inventory` を通した結果を返す.

    ゼロトラスト（design.md C13）: 検証を通らない入力で判定を実行しない。違反が
    1 件でも存在する場合は違反一覧を含む `CleanupCliError` を送出し、呼び出し側の
    判定処理へ進ませない（出典: design.md「Error Handling」の「Inventory の
    スキーマ違反 → 違反一覧を出力して非ゼロ終了。判定を継続しない」）。

    引数:
        path: Inventory 正本の絶対パス。

    戻り値:
        構造的不変条件を満たす `Inventory`。

    例外:
        CleanupCliError: 読み込みに失敗した場合、または `validate_inventory` が
            違反を列挙した場合。
    """
    inventory = load_inventory(path)
    violations = validate_inventory(inventory)
    if violations:
        detail = "\n".join(f"  - {violation}" for violation in violations)
        raise CleanupCliError(
            "Inventory のスキーマ違反により判定を継続しない（R1）:\n" + detail
        )
    return inventory


# ---------------------------------------------------------------------------
# 行番号照合（R1-5。`--verify-lines`）
# ---------------------------------------------------------------------------


def _split_lines(text: str) -> tuple[str, ...]:
    """テキストをエディタおよび `git grep -n` の行番号と一致する行へ分割する（内部関数）.

    行数の数え方（`tests/cleanup/test_inventory_line_numbers.py` と同一）:
        - `"\\n"` で分割し、末尾改行が生む空要素を行として数えない。
        - CRLF のファイルで各行末に残る `"\\r"` を除去する。
        - `str.splitlines()` は `\\x0b` / `\\u2028` 等も行境界として扱い `git grep -n`
          やエディタの行番号と一致しないため用いない。

    引数:
        text: UTF-8 として解釈済みの内容。

    戻り値:
        行末の改行を除いた行内容のタプル。要素数が当該内容の行数である。

    例外:
        送出しない。
    """
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return tuple(line[:-1] if line.endswith("\r") else line for line in lines)


def read_source_lines(path: Path) -> tuple[str, ...]:
    """作業ツリーのファイルを UTF-8 固定で読み取り、行番号と一致する行内容を返す.

    用途は Dependency_Manifest / License_Ledger の記載集合の読み取りである
    （`--audit-dependencies`。R7-7 は現在の記載どおりの整合を求めるため作業ツリーを
    読む）。R1-5 の行番号照合は記録 `revision` 時点の内容を対象とするため
    `read_revision_lines` を用いる。

    引数:
        path: 読み取り対象の絶対パス。

    戻り値:
        行末の改行を除いた行内容のタプル。要素数が当該ファイルの行数である。

    例外:
        CleanupCliError: ファイルが存在しない、または UTF-8 として解釈できない
            場合（代替エンコーディングへ再試行しない）。
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CleanupCliError(f"出典ファイルを読み込めない: {path}（{exc}）") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CleanupCliError(
            f"出典ファイルを UTF-8 として解釈できない: {path}（{exc}）"
        ) from exc

    return _split_lines(text)


def _validated_revision(revision: str) -> str:
    """Inventory の `revision` を `git` の引数へ渡せる値として検証して返す（内部関数）.

    引数:
        revision: Inventory の `revision`（DM2）。

    戻り値:
        SHA-1 の 16 進表記（短縮を含む）である `revision`。

    例外:
        CleanupCliError: SHA-1 の 16 進表記でない場合。表記外の値を `git` の引数へ
            渡さない（`-` で始まる値がオプションとして解釈される余地を残さない。
            第二原則2）。既定値での代替を行わず判定不能として表面化させる（第三原則3）。
    """
    if _REVISION_PATTERN.match(revision) is None:
        raise CleanupCliError(
            f"Inventory の revision が SHA-1 の 16 進表記でない: {revision!r}"
        )
    return revision


def _run_git(argv: tuple[str, ...], description: str) -> bytes:
    """`git` を固定の引数配列で実行し、終了コード 0 の標準出力を返す（内部関数）.

    引数配列は本モジュールが組み立てる（外部入力のコマンド文字列を解釈する
    `run_check_command` とは別経路である）。`shell=True` を用いないため、引数中の
    シェルメタ文字は解釈されない（第二原則2）。

    引数:
        argv: `git` に続く引数の並び。
        description: エラーメッセージへ含める処理の説明。

    戻り値:
        標準出力のバイト列。

    例外:
        CleanupCliError: `git` を起動できない場合、または終了コードが 0 でない場合。
            非ゼロ終了を空出力へ丸めない（第三原則3）。
    """
    try:
        completed = subprocess.run(
            ["git", *argv],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise CleanupCliError(
            f"{description}: git を実行できない（{argv}、{exc}）"
        ) from exc
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise CleanupCliError(
            f"{description}: git が非ゼロ終了した（{argv}、終了コード "
            f"{completed.returncode}、標準エラー: {stderr!r}）"
        )
    return completed.stdout


def list_tracked_paths_at_revision(revision: str) -> frozenset[str]:
    """記録 `revision` 時点の追跡パス集合を返す（当該時点の Repository の実体）.

    `git ls-files` は現在のインデックスを対象とし過去 revision の集合を返さないため、
    `git ls-tree -r -z --name-only <revision>` を用いる（モジュール docstring
    「`--verify-lines` の照合基準」）。パスは `-z` により NUL 区切りで受け取り、`git`
    によるパスの引用（非 ASCII 文字を含む場合の `"..."` 表記）を介さず比較する。

    引数:
        revision: Inventory の `revision`（DM2）。

    戻り値:
        当該 revision のツリーに含まれるパス（リポジトリルート相対・`/` 区切り）の集合。

    例外:
        CleanupCliError: `revision` の表記が不正、`git ls-tree` が非ゼロ終了した、
            または出力を UTF-8 として解釈できない場合。
    """
    validated = _validated_revision(revision)
    stdout = _run_git(
        ("ls-tree", "-r", "-z", "--name-only", validated),
        f"revision {validated} の追跡パス集合の取得",
    )
    try:
        text = stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CleanupCliError(
            f"revision {validated} の追跡パス集合を UTF-8 として解釈できない（{exc}）"
        ) from exc
    return frozenset(path for path in text.split("\0") if path != "")


def read_revision_lines(revision: str, source_path: str) -> tuple[str, ...]:
    """記録 `revision` 時点のファイル内容を、行番号と一致する行内容の並びで返す.

    R1-5 の照合先は「作成時点のリポジトリ実体」であるため、作業ツリーではなく
    `git show <revision>:<source_path>` の内容を読む（モジュール docstring
    「`--verify-lines` の照合基準」）。

    引数:
        revision: Inventory の `revision`（DM2）。
        source_path: リポジトリルート相対のパス（`/` 区切り）。

    戻り値:
        行末の改行を除いた行内容のタプル。要素数が当該時点の当該ファイルの行数である。

    例外:
        CleanupCliError: `revision` の表記が不正、`git show` が非ゼロ終了した（当該
            revision に当該パスが存在しない場合を含む）、または出力を UTF-8 として
            解釈できない場合。存在しない出典を空内容へ丸めない（第三原則3）。
    """
    validated = _validated_revision(revision)
    stdout = _run_git(
        # `<revision>:<path>` は 1 個のオブジェクト指定であり、パス終端子 `--` を
        # 伴わない。`revision` の表記検証と `<revision>:` 接頭辞により、`source_path`
        # が単独の引数としてオプション位置に現れないことを担保する。
        ("show", f"{validated}:{source_path}"),
        f"出典 {validated}:{source_path} の読み取り",
    )
    try:
        text = stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CleanupCliError(
            f"出典 {validated}:{source_path} を UTF-8 として解釈できない（{exc}）"
        ) from exc
    return _split_lines(text)


def parse_source_lines(value: str) -> tuple[int, ...]:
    """`source_lines` を参照行番号の昇順タプルへ展開する.

    許す表記は「単一行番号」または「開始-終了」のカンマ区切り列のみ（例
    `6,8,12` / `72-86` / `36,38,48-49`）。解釈できない値を既定値で補完しない
    （第三原則3）。

    引数:
        value: Inventory の `source_lines` の値。

    戻り値:
        参照される全行番号（重複排除・昇順）。

    例外:
        ValueError: 空文字、未知の表記、1 未満の行番号、または開始 > 終了の区間を
            含む場合。呼び出し側は本例外を不一致（違反）として報告する。
    """
    if not value.strip():
        raise ValueError("source_lines が空である")

    numbers: set[int] = set()
    for token in value.split(","):
        matched = _SOURCE_LINES_TOKEN.match(token.strip())
        if matched is None:
            raise ValueError(f"source_lines のトークンを解釈できない: {token!r}")
        if matched.group("single") is not None:
            single = int(matched.group("single"))
            if single < 1:
                raise ValueError(f"行番号が 1 未満である: {token!r}")
            numbers.add(single)
            continue
        start = int(matched.group("start"))
        end = int(matched.group("end"))
        if start < 1:
            raise ValueError(f"区間の開始行番号が 1 未満である: {token!r}")
        if start > end:
            raise ValueError(f"区間の開始行番号が終了行番号を超える: {token!r}")
        numbers.update(range(start, end + 1))
    return tuple(sorted(numbers))


def _verify_entry_lines(
    key: str,
    source_path: str,
    source_lines: str,
    revision: str,
    lines_cache: dict[str, tuple[str, ...]],
) -> tuple[str, ...]:
    """1 項目の出典を記録 `revision` 時点の実体へ照合し、不一致を返す（内部関数）.

    照合の強度（`tests/cleanup/test_inventory_line_numbers.py` の L1〜L3 と同一）:
        L1: `source_path` が記録 `revision` 時点に実体として存在すること
            （`git show <revision>:<source_path>` が成功すること）。
        L2: `source_lines` が定義した表記として厳密に解釈できること。
        L3: 参照する全行番号が記録 `revision` 時点の当該ファイルの行数以内であること。

    本関数は Repository 内（記録 `revision` の追跡集合に含まれる）`source_path` のみを
    対象とする。範囲の判定は呼び出し側（`run_verify_lines`）が
    `list_tracked_paths_at_revision` の結果に基づいて行う。

    引数:
        key: Inventory 項目キー（報告に用いる）。
        source_path: リポジトリルート相対の出典パス。
        source_lines: 出典の行番号表記。
        revision: 照合先の時点（Inventory の `revision`。DM2）。
        lines_cache: `source_path` ごとの行内容キャッシュ（同一ファイルを複数項目が
            参照するため呼び出し側で共有する）。

    戻り値:
        不一致メッセージのタプル。不一致がなければ空タプル。

    例外:
        CleanupCliError: `git show` の実行または出力の解釈に失敗した場合。読み飛ばさず
            終了コード 2 で表面化させる（第三原則3）。
    """
    violations: list[str] = []

    # L2: 表記の妥当性。解釈不能は握りつぶさず不一致として報告する。
    try:
        line_numbers = parse_source_lines(source_lines)
    except ValueError as exc:
        return (f"R1-5: {key}: {source_path}:{source_lines} を解釈できない（{exc}）",)

    # L1: 記録 revision 時点の実在性。`git show` の非ゼロ終了は CleanupCliError となり、
    # 当該項目が存在しない出典を主張していることが終了コード 2 で表面化する。
    cached = lines_cache.get(source_path)
    if cached is None:
        cached = read_revision_lines(revision, source_path)
        lines_cache[source_path] = cached

    # L3: 行番号の実在性（照合先は記録 revision 時点の内容であり作業ツリーではない）。
    for line_number in line_numbers:
        if line_number > len(cached):
            violations.append(
                f"R1-5: {key}: {source_path}:{source_lines} の行 {line_number} は"
                f"revision {revision} 時点の行数 {len(cached)} を超える"
            )

    return tuple(violations)


# ---------------------------------------------------------------------------
# `git` コマンドの実行（残存走査。`--check-residual` / `--evaluate`）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CommandOutcome:
    """除去確認コマンド 1 件の実行結果.

    属性:
        command: 実行したコマンド文字列（Inventory または条項本文の記載）。
        argv: 実際に実行した引数配列（`shell=True` を用いないことの記録）。
        exit_code: `git` の終了コード。
        lines: 標準出力の行（空行を除く）。
        match_count: 一致件数（`lines` の件数。一致なしは 0）。
    """

    command: str
    argv: tuple[str, ...]
    exit_code: int
    lines: tuple[str, ...]
    match_count: int


def run_check_command(command: str) -> CommandOutcome:
    """除去確認コマンドを実行し、終了コードを検査して一致件数を返す.

    ゼロトラスト（第二原則2）:
        - コマンド文字列は外部入力（Inventory）由来であるため、`shlex.split` で
          引数配列へ分解して実行する。`shell=True` を用いないためシェルの
          メタ文字は解釈されない。
        - 実行を許すのは `git` の `ls-files` / `grep` / `check-ignore` に限る
          （`_ALLOWED_GIT_SUBCOMMANDS`）。これ以外は実行せず失敗させる（最小権限）。
        - 作業ディレクトリはリポジトリルート固定とし、呼び出し時のカレント
          ディレクトリに依存しない。

    終了コードの扱い（モジュール docstring「`git` の終了コードの扱い」）:
        - `grep` / `check-ignore`: `0` は一致あり、`1` は一致なし（成功側の結果で
          あり失敗として扱わない）、`2` 以上は異常として `CleanupCliError`。
          `1` で標準出力が非空である場合は想定外の状態であるため失敗させる。
        - `ls-files`: `0` のみを正常とし（一致なしでも `0` で標準出力が空）、
          非ゼロは異常として `CleanupCliError`。「一致なし」へ丸めない。

    引数:
        command: 実行するコマンド文字列（例
            `'git grep -n -E "allauth|django_otp" -- config/'`）。

    戻り値:
        `CommandOutcome`。

    例外:
        CleanupCliError: コマンド文字列を分解できない、許可外のプログラム・
            サブコマンドである、`git` 実行ファイルが見つからない、標準出力を
            UTF-8 として解釈できない、または終了コードが異常である場合。
    """
    try:
        argv = tuple(shlex.split(command, posix=True))
    except ValueError as exc:
        raise CleanupCliError(
            f"確認コマンドを引数配列へ分解できない: {command!r}（{exc}）"
        ) from exc

    if len(argv) < 2:
        raise CleanupCliError(
            f"確認コマンドが `git <サブコマンド>` の形式でない: {command!r}"
        )
    if argv[0] != "git":
        raise CleanupCliError(
            f"許可されていないプログラムの実行要求（`git` 以外）: {argv[0]!r}"
            f"（コマンド: {command!r}）"
        )
    if argv[1] not in _ALLOWED_GIT_SUBCOMMANDS:
        raise CleanupCliError(
            f"許可されていない git サブコマンドの実行要求: {argv[1]!r}"
            f"（許可: {tuple(sorted(_ALLOWED_GIT_SUBCOMMANDS))}、"
            f"コマンド: {command!r}）"
        )

    try:
        # shell=False（既定）で引数配列を渡すため、シェルのメタ文字は解釈されない。
        # 標準出力・標準エラーはバイト列で受け取り、下で UTF-8 として厳格に解釈する。
        completed = subprocess.run(
            list(argv),
            cwd=str(_REPO_ROOT),
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise CleanupCliError(
            f"確認コマンドを実行できない: {command!r}（{exc}）"
        ) from exc

    try:
        stdout = completed.stdout.decode("utf-8")
        stderr = completed.stderr.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CleanupCliError(
            f"確認コマンドの出力を UTF-8 として解釈できない: {command!r}（{exc}）"
        ) from exc

    lines = tuple(line for line in stdout.split("\n") if line != "")
    subcommand = argv[1]

    if completed.returncode == 0:
        return CommandOutcome(command, argv, 0, lines, len(lines))

    if subcommand in _NO_MATCH_EXIT_SUBCOMMANDS and completed.returncode == 1:
        # `git grep` / `git check-ignore` の終了コード 1 は「一致なし」であり、
        # 残存走査では成功側の結果である。異常（2 以上）とは区別する。
        if lines:
            raise CleanupCliError(
                f"確認コマンドが一致なし（終了コード 1）を返したが標準出力が"
                f"非空である: {command!r}（出力 {len(lines)} 行）"
            )
        return CommandOutcome(command, argv, 1, (), 0)

    raise CleanupCliError(
        f"確認コマンドが異常終了した: {command!r}（終了コード "
        f"{completed.returncode}、標準エラー: {stderr.strip()!r}）"
    )


# ---------------------------------------------------------------------------
# 残存走査（`--check-residual`。R3-1、R3-2、R3-3、R3-5、R4-*、R6-*、R10-1）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResidualCheckResult:
    """除去対象 1 項目に対する残存走査の結果.

    属性:
        key: Inventory 項目キー。
        expectation: 適用した期待（条項識別子を含む）。
        outcome: コマンド実行結果。
        conformant: 期待を満たしたか。
    """

    key: str
    expectation: ResidualExpectation
    outcome: CommandOutcome
    conformant: bool


def collect_residual_results(inventory: Inventory) -> tuple[ResidualCheckResult, ...]:
    """`除去対象` 全項目の除去確認コマンドを実行し、期待との適合を判定する.

    コマンド文字列は Inventory の `removal_check_command`（正本）から取得し、
    期待は `_RESIDUAL_EXPECTATIONS`（受入基準由来）から取得する（モジュール
    docstring「除去確認コマンドの出所」）。

    引数:
        inventory: `validate_inventory` を通過済みの `Inventory`。

    戻り値:
        `Inventory.items` の並び順に対応する `ResidualCheckResult` のタプル。

    例外:
        CleanupCliError: 次のいずれかの場合。既定値による補完を行わず判定不能を
            表面化させる（第三原則3）。
            - `除去対象` の項目に `removal_check_command` が記録されていない。
            - `_RESIDUAL_EXPECTATIONS` に当該項目キーの期待が存在しない。
            - コマンドの実行または終了コードの検査に失敗した
              （`run_check_command` が送出）。
    """
    results: list[ResidualCheckResult] = []
    for item in inventory.items:
        if item.disposition != DISPOSITION_REMOVAL_TARGET:
            # `undetermined` / `保全対象` は除去を保留する対象であり、残存走査の
            # 判定対象にしない（R9-4、R5-9）。件数は呼び出し側が報告する。
            continue
        if item.removal_check_command is None:
            raise CleanupCliError(
                f"R9-5: {item.key}: disposition が 除去対象 であるのに "
                "removal_check_command が記録されていない（残存一致件数を確認できず"
                "判定不能）"
            )
        expectation = _RESIDUAL_EXPECTATIONS.get(item.key)
        if expectation is None:
            raise CleanupCliError(
                f"R9-5: {item.key}: 除去確認の期待（条項）が未定義であるため判定"
                "不能（`_RESIDUAL_EXPECTATIONS` へ条項識別子と期待を追加すること）"
            )
        outcome = run_check_command(item.removal_check_command)
        # 期待は条項により「一致 0 件」または「一致 1 件以上」のいずれかである。
        conformant = (
            outcome.match_count == 0
            if expectation.expect_zero_matches
            else outcome.match_count >= 1
        )
        results.append(ResidualCheckResult(item.key, expectation, outcome, conformant))
    return tuple(results)


def _is_r3_5_allowed_path(path: str) -> bool:
    """R3-5 が一致を許す範囲のパスかを判定する（内部関数）.

    許す範囲（出典: requirements.md Requirement 3 基準 5 および同「Evidence（基準 5
    の許容範囲の根拠）」、design.md C6 の A1-6）:
        - `docs/` 配下の Markdown、および `README.md`（Repository_Documents。
          定義は requirements.md Glossary であり本改訂でも変更されていない）。
        - `.kiro/specs/` 配下の記録。
        - Legacy_Asset_Inventory の正本 `docs/legacy-asset-inventory.json`。
        - 判定層および Cleanup CLI（`scripts/cleanup/` 配下）。
        - 判定層のテスト（`tests/cleanup/` 配下）。

    後 3 者は本 spec 自身が生成を義務付ける記録および判定コードであり、実行経路から
    `asgi_lambda` / `mangum` を参照するものではない（出典: 同 Evidence 節）。

    引数:
        path: `git grep -n` の出力から取り出したリポジトリ相対パス。

    戻り値:
        許す範囲であれば True。

    例外:
        送出しない。
    """
    # 完全一致の許容パスを prefix 判定より先に評価する。`docs/` 配下は Markdown 限定
    # であるため、`docs/legacy-asset-inventory.json` は完全一致でのみ許容できる。
    if path in _R3_5_ALLOWED_EXACT_PATHS:
        return True
    for prefix in _R3_5_ALLOWED_DIRECTORY_PREFIXES:
        if path.startswith(prefix):
            # `docs/` 配下は Markdown のみが Repository_Documents である。
            # 他の prefix（`.kiro/specs/`、`scripts/cleanup/`、`tests/cleanup/`）は
            # 条項本文が配下全体を挙げるため拡張子で絞らない。
            if prefix == "docs/":
                return path.endswith(_R3_5_ALLOWED_DOC_SUFFIX)
            return True
    return False


def check_r3_5_scope() -> tuple[CommandOutcome, tuple[str, ...]]:
    """R3-5 の走査を実行し、許容範囲外の一致行を列挙する.

    R3-5 は一致の有無ではなく、一致箇所が Repository_Documents、`.kiro/specs` 配下の
    記録、Legacy_Asset_Inventory の正本 `docs/legacy-asset-inventory.json`、
    `scripts/cleanup/` 配下、`tests/cleanup/` 配下に限定されることを求める（出典:
    requirements.md Requirement 3 基準 5。判定は `_is_r3_5_allowed_path`）。
    したがって一致 0 件も適合であり、許容範囲外の一致が 1 件でもあれば不適合と
    する。

    引数:
        なし（走査コマンドは条項本文由来の `_R3_5_COMMAND` 固定）。

    戻り値:
        (コマンド実行結果, 許容範囲外の一致行のタプル)。

    例外:
        CleanupCliError: コマンドの実行または終了コードの検査に失敗した場合。
    """
    outcome = run_check_command(_R3_5_COMMAND)
    disallowed: list[str] = []
    for line in outcome.lines:
        # `git grep -n` の出力は `<path>:<line>:<内容>`。追跡ファイル名に `:` を
        # 含むものは存在しないため、最初の `:` までをパスとして扱う。
        path = line.split(":", 1)[0]
        if not _is_r3_5_allowed_path(path):
            disallowed.append(line)
    return outcome, tuple(disallowed)


def _pending_item_keys(inventory: Inventory) -> tuple[str, ...]:
    """除去を保留している項目（`undetermined`）のキー一覧を返す（内部関数）.

    引数:
        inventory: `validate_inventory` を通過済みの `Inventory`。

    戻り値:
        項目キーの並び（`Inventory.items` の順を保つ）。

    例外:
        送出しない。

    R9-4 に従い `undetermined` の項目に対する除去は保留されるため、これらは残存
    走査の不適合ではない。ただし無記録にすると保留の存在が見えなくなるため、報告
    へ明示する（第一原則3、第三原則3）。
    """
    return tuple(
        item.key
        for item in inventory.items
        if item.disposition == DISPOSITION_UNDETERMINED
    )


# ---------------------------------------------------------------------------
# 非退行レコードの読み込み（`--evaluate`。DM3 / DM6 の写像）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecordsDocument:
    """非退行レコードファイルの内容（DM3 / DM6 の写像）.

    期待する JSON スキーマ（`docs/development-records/legacy-asset-cleanup-records.json`。
    作成は tasks.md 13.1 の範囲であり、本モジュールは読み取りのみを行う）:

    ```json
    {
      "applied_stream_b_segments": ["B-1_prod_settings", "..."],
      "non_regression_records": [
        {
          "stream": "A",
          "commands": ["python manage.py test", "..."],
          "tests_passed": 196,
          "tests_failed": 0,
          "tests_errored": 0,
          "django_check_exit_code": 0,
          "control_platform_exit_code": 0,
          "self_test_exit_code": 0,
          "non_regression_exit_code": 0,
          "prerendered_pages": 7,
          "manifest_files": 1,
          "content_security_policy": "default-src 'self'; ..."
        }
      ],
      "aws_smtp_state": {
        "queried": false,
        "absent_targets": [],
        "deleted_targets": [],
        "expected_targets": [
          "parameter:email_host", "parameter:email_port",
          "parameter:email_use_tls", "parameter:email_use_ssl",
          "secret:EMAIL_HOST_USER", "secret:EMAIL_HOST_PASSWORD"
        ]
      }
    }
    ```

    `non_regression_records` の各要素は DM3 の `NonRegressionRecord`、
    `aws_smtp_state` は DM6 の `AwsSmtpState` に 1 対 1 で対応する。
    `applied_stream_b_segments` は DM6 の `STREAM_B_SEGMENTS` の部分集合として
    「適用済みの系統 B 区分」を表し、`completion.is_stream_b_complete` の第 1 引数
    となる（出典: design.md DM6「完了条件」）。

    属性:
        applied_stream_b_segments: 適用済みの系統 B 変更区分。
        non_regression_records: 非退行確認の実測記録（1 件以上）。
        aws_smtp_state: AWS 側状態。
    """

    applied_stream_b_segments: frozenset[str]
    non_regression_records: tuple[NonRegressionRecord, ...]
    aws_smtp_state: AwsSmtpState


def _build_non_regression_record(value: object, context: str) -> NonRegressionRecord:
    """JSON オブジェクト 1 件を `NonRegressionRecord`（DM3）へ変換する（内部関数）.

    引数:
        value: JSON 上の 1 レコード。
        context: エラーメッセージへ含める位置情報。

    戻り値:
        `NonRegressionRecord`。

    例外:
        CleanupCliError: キー集合が不一致、または値の型が不正な場合。件数・終了
            コードの妥当性（R2-1〜R2-6）の判定は
            `removal_verification.evaluate` が担う。
    """
    mapping = _require_mapping(value, context)
    _require_exact_keys(mapping, _NON_REGRESSION_RECORD_KEYS, context)
    return NonRegressionRecord(
        stream=_require_str(mapping, "stream", context),
        commands=_require_str_tuple(mapping, "commands", context),
        tests_passed=_require_int(mapping, "tests_passed", context),
        tests_failed=_require_int(mapping, "tests_failed", context),
        tests_errored=_require_int(mapping, "tests_errored", context),
        django_check_exit_code=_require_int(mapping, "django_check_exit_code", context),
        control_platform_exit_code=_require_int(
            mapping, "control_platform_exit_code", context
        ),
        self_test_exit_code=_require_int(mapping, "self_test_exit_code", context),
        non_regression_exit_code=_require_int(
            mapping, "non_regression_exit_code", context
        ),
        prerendered_pages=_require_int(mapping, "prerendered_pages", context),
        manifest_files=_require_int(mapping, "manifest_files", context),
        content_security_policy=_require_str(
            mapping, "content_security_policy", context
        ),
    )


def _build_aws_smtp_state(value: object, context: str) -> AwsSmtpState:
    """JSON オブジェクトを `AwsSmtpState`（DM6）へ変換する（内部関数）.

    引数:
        value: JSON 上の `aws_smtp_state`。
        context: エラーメッセージへ含める位置情報。

    戻り値:
        `AwsSmtpState`。

    例外:
        CleanupCliError: キー集合が不一致、または値の型が不正な場合。
            `expected_targets` が `STREAM_B_AWS_TARGETS` と一致するかの検証は
            `completion.is_stream_b_complete` が担う（判定条件を二重実装しない）。
    """
    mapping = _require_mapping(value, context)
    _require_exact_keys(mapping, _AWS_SMTP_STATE_KEYS, context)
    return AwsSmtpState(
        queried=_require_bool(mapping, "queried", context),
        absent_targets=frozenset(
            _require_str_tuple(mapping, "absent_targets", context)
        ),
        deleted_targets=frozenset(
            _require_str_tuple(mapping, "deleted_targets", context)
        ),
        expected_targets=frozenset(
            _require_str_tuple(mapping, "expected_targets", context)
        ),
    )


def load_records(path: Path) -> RecordsDocument:
    """非退行レコードファイルを厳格に読み込み `RecordsDocument` へ変換する.

    ファイルが存在しない場合は明示的な失敗とする（黙って判定を省略しない。
    出典: design.md C13「フォールバック禁止」）。本タスク（tasks.md 5.1）の時点で
    `docs/development-records/legacy-asset-cleanup-records.json` は未作成であり、
    作成は tasks.md 13.1 の範囲である。したがって既定パスでの実行は終了コード 2
    で失敗するのが正しい状態である。

    引数:
        path: レコードファイルの絶対パス（`--records-path` で指定可能）。

    戻り値:
        `RecordsDocument`。

    例外:
        CleanupCliError: ファイルの読み込み・デコード・スキーマ検証に失敗した場合、
            または `non_regression_records` が 0 件の場合（R2-10）。
    """
    document = _require_mapping(_read_json_document(path, "非退行レコード"), "records")
    _require_exact_keys(document, _RECORDS_DOCUMENT_KEYS, "records")

    records = tuple(
        _build_non_regression_record(element, f"non_regression_records[{index}]")
        for index, element in enumerate(
            _require_list(document["non_regression_records"], "non_regression_records")
        )
    )
    if not records:
        raise CleanupCliError(
            "R2-10: non_regression_records が 0 件である（非退行確認記録がない状態で"
            "完了判定を行わない）"
        )

    return RecordsDocument(
        applied_stream_b_segments=frozenset(
            _require_str_tuple(document, "applied_stream_b_segments", "records")
        ),
        non_regression_records=records,
        aws_smtp_state=_build_aws_smtp_state(
            document["aws_smtp_state"], "records.aws_smtp_state"
        ),
    )


# ---------------------------------------------------------------------------
# Dependency_Manifest / License_Ledger の解析（`--audit-dependencies`。R7-7）
# ---------------------------------------------------------------------------

# `requirements.txt` の 1 行。本リポジトリが用いる「固定版指定（`==`）+ 任意の
# 環境マーカー」の形式のみを受理する（出典: `requirements.txt` の全 41 行が
# `name==version` または `name==version; marker` の形式）。
_MANIFEST_LINE = re.compile(
    r"\A(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)=="
    r"(?P<version>[^;\s]+)"
    r"(?:\s*;\s*(?P<marker>\S.*))?\Z"
)

# License_Ledger（`docs/external-assets.md`）の dependency 一覧セクションの見出し。
_LEDGER_SECTION_HEADING = "## Python dependencies"

# 表のヘッダ行の第 1 セル（ヘッダ行の判別に用いる）。
_LEDGER_TABLE_HEADER_CELL = "パッケージ"

# 表の区切り行のセル（`---` の並び）。
_LEDGER_TABLE_SEPARATOR = re.compile(r"\A-{3,}\Z")


def parse_manifest_names(path: Path) -> frozenset[str]:
    """Dependency_Manifest（`requirements.txt`）の記載パッケージ名集合を返す.

    解析規則（限界も含めて明示する。第一原則7）:
        - UTF-8 固定で読み込み、空行と `#` で始まる行を除外する。
        - 残る各行は `name==version`（末尾に `; <marker>` を許す）の形式のみを
          受理する。本リポジトリの `requirements.txt` は全行がこの形式である。
        - 受理できない行は `CleanupCliError` とする。読み飛ばさない理由は、
          未対応形式（extras `name[extra]`、範囲指定、`-r` による別ファイル取り込み、
          VCS URL、`--hash` 付き行）を黙って無視すると記載集合が欠けたまま R7-7 の
          整合が成立してしまうためである（フォールバック禁止。第三原則3）。
        - 名前は `dependency_audit.normalize_package_name` で正規化して返す
          （`check_ledger_coherence` も内部で正規化するが、本関数の戻り値を報告へ
          出力するため表記を揃える）。
        - 版・マーカーは R7-7 の比較対象ではないため戻り値へ含めない（R7-7 は
          「記載集合の一致」のみを求める）。

    引数:
        path: `requirements.txt` の絶対パス。

    戻り値:
        正規化済みパッケージ名の集合。

    例外:
        CleanupCliError: 読み込みに失敗した場合、受理できない行が存在する場合、
            または記載が 0 件の場合。
    """
    lines = read_source_lines(path)
    names: set[str] = set()
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        matched = _MANIFEST_LINE.match(stripped)
        if matched is None:
            raise CleanupCliError(
                f"R7-7: {path.name}:{index}: 未対応の記載形式であるため解析できない"
                f"（{stripped!r}）"
            )
        names.add(normalize_package_name(matched.group("name")))
    if not names:
        raise CleanupCliError(
            f"R7-7: {path.name}: dependency の記載が 1 件も抽出できなかった"
        )
    return frozenset(names)


def parse_ledger_names(path: Path) -> frozenset[str]:
    """License_Ledger（`docs/external-assets.md`）の記載パッケージ名集合を返す.

    解析規則（限界も含めて明示する。第一原則7）:
        - UTF-8 固定で読み込み、見出し `## Python dependencies` から次の `## ` 見出し
          までを dependency 一覧セクションとして扱う。他セクション（Docker image /
          Build tools / Google Fonts）は Dependency_Manifest の記載対象ではないため
          比較集合に含めない（出典: `docs/external-assets.md` の節構成、
          requirements.md Glossary の Dependency_Manifest / License_Ledger 定義）。
        - セクション内で `|` から始まる行を表の行とし、`|` で分割した 3 セル
          （パッケージ / バージョン / ライセンス確認結果）を要求する。ヘッダ行
          （第 1 セルが `パッケージ`）と区切り行（`---`）は集合へ含めない。
        - セル数が 3 でない表の行は `CleanupCliError` とする（読み飛ばさない）。
        - 名前は `dependency_audit.normalize_package_name` で正規化する
          （`docs/external-assets.md` の `Django` / `PyJWT` と `requirements.txt` の
          `django` / `pyjwt` の表記差に対応する。出典: design.md C10「正規化」）。
        - バージョン・ライセンス列は R7-7 の比較対象ではないため戻り値へ含めない。

    引数:
        path: `docs/external-assets.md` の絶対パス。

    戻り値:
        正規化済みパッケージ名の集合。

    例外:
        CleanupCliError: 読み込みに失敗した場合、対象見出しが存在しない場合、
            表の行のセル数が 3 でない場合、または記載が 0 件の場合。
    """
    lines = read_source_lines(path)
    names: set[str] = set()
    in_section = False
    for index, line in enumerate(lines, start=1):
        if line.startswith("## "):
            # 見出しに到達したらセクションの内外を切り替える（対象は 1 節のみ）。
            in_section = line.strip() == _LEDGER_SECTION_HEADING
            continue
        if not in_section or not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 3:
            raise CleanupCliError(
                f"R7-7: {path.name}:{index}: dependency 表の列数が 3 でない"
                f"（{cells!r}）"
            )
        if cells[0] == _LEDGER_TABLE_HEADER_CELL:
            continue
        if _LEDGER_TABLE_SEPARATOR.match(cells[0]):
            continue
        names.add(normalize_package_name(cells[0]))
    if not names:
        raise CleanupCliError(
            f"R7-7: {path.name}: 見出し {_LEDGER_SECTION_HEADING!r} 配下から"
            "dependency の記載が 1 件も抽出できなかった"
        )
    return frozenset(names)


# ---------------------------------------------------------------------------
# 出力ヘルパ
# ---------------------------------------------------------------------------


def _emit(line: str) -> None:
    """報告 1 行を標準出力へ出力する（内部関数）.

    引数:
        line: 出力する行（改行を含まない）。

    戻り値:
        なし。

    例外:
        送出しない（`sys.stdout` の書き込み失敗は呼び出し側へ伝播する）。
    """
    sys.stdout.write(line + "\n")


def _emit_violations(title: str, violations: tuple[str, ...]) -> None:
    """違反一覧を標準エラーへ日本語で出力する（内部関数）.

    引数:
        title: 見出し行（何の違反かを述べる）。
        violations: 違反の内容（1 件 1 行）。

    戻り値:
        なし。

    例外:
        送出しない。

    不適合を握りつぶさず、全件を出力する（第三原則3、第一原則3）。
    """
    sys.stderr.write(
        title + "\n" + "".join(f"  - {violation}\n" for violation in violations)
    )


# ---------------------------------------------------------------------------
# サブコマンド実装（design.md C13 の表と 1 対 1）
# ---------------------------------------------------------------------------


def run_validate_inventory(inventory_path: Path) -> int:
    """`--validate-inventory`: Inventory を読み込み構造的不変条件を検証する.

    判定は `inventory.validate_inventory`（C2）が行い、本関数は読み込みと結果の
    出力・終了コード化のみを担う（出典: design.md C13 の表「C2 を適用し違反が
    あれば非ゼロ終了」）。

    引数:
        inventory_path: Inventory 正本の絶対パス。

    戻り値:
        `EXIT_CONFORMANT`（違反 0 件）または `EXIT_NON_CONFORMANT`（違反あり）。

    例外:
        CleanupCliError: 読み込み・デシリアライズに失敗した場合。
    """
    inventory = load_inventory(inventory_path)
    violations = validate_inventory(inventory)

    _emit(f"Inventory: {inventory_path}")
    _emit(f"revision: {inventory.revision}")
    _emit(
        f"items: {len(inventory.items)} 件 / preserved: {len(inventory.preserved)} 件"
        f" / undetermined_notes: {len(inventory.undetermined_notes)} 件"
    )

    if violations:
        _emit(f"判定: 不適合（違反 {len(violations)} 件。R1）")
        _emit_violations("Inventory のスキーマ違反（R1）:", violations)
        return EXIT_NON_CONFORMANT

    _emit("判定: 適合（構造的不変条件の違反 0 件。R1-1〜R1-8、R7-11、R9-1〜R9-3）")
    return EXIT_CONFORMANT


def run_verify_lines(inventory_path: Path) -> int:
    """`--verify-lines`: 出典行番号を記録 `revision` 時点の実体へ照合する（R1-5）.

    照合先は作業ツリーではなく Inventory が記録する `revision` 時点の内容
    （`git show <revision>:<source_path>`）であり、照合対象は `source_path` が当該
    revision の追跡集合に含まれる項目に限る（出典: design.md C13
    「`--verify-lines` の照合基準（R1-5）」「Repository 外の `source_path` の扱い
    （R1-5 の適用範囲）」）。Repository 外の項目は「照合対象外」である事実として出典
    付きで報告し、不一致として扱わない。不一致があれば不一致項目を出力して非ゼロ終了
    する（出典: design.md「Error Handling」の「行番号が記録 `revision` 時点の実体と
    不一致」行）。判定前に `validate_inventory` を通す（ゼロトラスト）。

    引数:
        inventory_path: Inventory 正本の絶対パス。

    戻り値:
        `EXIT_CONFORMANT`（照合対象の全項目が一致）または `EXIT_NON_CONFORMANT`。

    例外:
        CleanupCliError: 読み込み・スキーマ検証・`git` 実行に失敗した場合。
    """
    inventory = load_validated_inventory(inventory_path)
    revision = inventory.revision
    tracked_paths = list_tracked_paths_at_revision(revision)

    # `items` と `preserved` のみが出典 3 要素を持つ（`undetermined_notes` は
    # design.md DM1 の `UndeterminedNote` のとおり出典を持たないため対象外）。
    entries: tuple[tuple[str, str, str], ...] = tuple(
        (item.key, item.source_path, item.source_lines) for item in inventory.items
    ) + tuple(
        (
            preserved_item.key,
            preserved_item.source_path,
            preserved_item.source_lines,
        )
        for preserved_item in inventory.preserved
    )

    violations: list[str] = []
    lines_cache: dict[str, tuple[str, ...]] = {}
    out_of_scope: list[tuple[str, str]] = []

    for key, source_path, source_lines in entries:
        if source_path not in tracked_paths:
            # Repository 外（Glossary。`.kiro` は `.gitignore:176` により対象外）は
            # 記録 revision の git 実体として解決できないため照合しない。R1-5 が求めて
            # いない理由による不一致としないが、無記録にもしない。
            out_of_scope.append((key, source_path))
            continue
        violations.extend(
            _verify_entry_lines(key, source_path, source_lines, revision, lines_cache)
        )

    in_scope_count = len(entries) - len(out_of_scope)
    _emit(f"照合先 revision: {revision}（git show <revision>:<source_path>）")
    _emit(f"当該 revision の追跡パス: {len(tracked_paths)} 件（git ls-tree -r）")
    _emit(
        f"照合対象: {in_scope_count} 件 / 対象外: {len(out_of_scope)} 件"
        f"（items + preserved 合計 {len(entries)} 件）"
    )
    _emit(f"参照ファイル: {len(lines_cache)} 件")
    for key, source_path in out_of_scope:
        _emit(
            f"[対象外] {key}: {source_path} は revision {revision} の追跡集合に"
            f"存在せず Repository 外であるため R1-5 の照合対象外"
            f"（出典: requirements.md Glossary「Repository」、`.gitignore:176`、"
            f"`git ls-tree -r --name-only {revision}` に当該パスなし）"
        )

    if violations:
        _emit(f"判定: 不適合（不一致 {len(violations)} 件。R1-5）")
        _emit_violations(
            f"行番号が revision {revision} 時点の実体と不一致（R1-5）:",
            tuple(violations),
        )
        return EXIT_NON_CONFORMANT

    _emit(
        f"判定: 適合（照合対象 {in_scope_count} 件の出典が revision {revision} "
        "時点の実体と一致。R1-5）"
    )
    return EXIT_CONFORMANT


def run_check_residual(inventory_path: Path) -> int:
    """`--check-residual`: 除去確認コマンドを実行し一致件数を期待と照合する.

    実行するコマンドは Inventory の `removal_check_command`、期待は受入基準由来の
    `_RESIDUAL_EXPECTATIONS` から取得する。加えて R3-5（一致箇所の範囲限定）を
    条項本文のコマンドで確認する（モジュール docstring「除去確認コマンドの出所」）。

    引数:
        inventory_path: Inventory 正本の絶対パス。

    戻り値:
        `EXIT_CONFORMANT`（全期待を満たす）または `EXIT_NON_CONFORMANT`。

    例外:
        CleanupCliError: スキーマ検証の失敗、期待の未定義、確認コマンドの欠落、
            `git` の異常終了。
    """
    inventory = load_validated_inventory(inventory_path)
    results = collect_residual_results(inventory)
    r3_5_outcome, r3_5_disallowed = check_r3_5_scope()
    pending = _pending_item_keys(inventory)

    violations: list[str] = []

    for result in results:
        expectation = result.expectation
        status = "適合" if result.conformant else "不適合"
        _emit(
            f"[{expectation.clause}] {result.key}: {status}"
            f"（一致 {result.outcome.match_count} 件 / 終了コード "
            f"{result.outcome.exit_code}）: {result.outcome.command}"
        )
        if not result.conformant:
            violations.append(
                f"{expectation.clause}: {result.key}: 期待「{expectation.note}」に対し"
                f"一致 {result.outcome.match_count} 件"
                f"（コマンド: {result.outcome.command}）"
            )

    # R3-5 は一致 0 件を求めず、一致箇所の範囲を限定する条項である。
    _emit(
        f"[R3-5] 一致 {r3_5_outcome.match_count} 件 / 終了コード "
        f"{r3_5_outcome.exit_code}: {r3_5_outcome.command}"
    )
    _emit(
        f"[R3-5] 許容範囲外の一致: {len(r3_5_disallowed)} 件"
        "（許容範囲: docs/ 配下 Markdown、README.md、.kiro/specs/ 配下、"
        "docs/legacy-asset-inventory.json、scripts/cleanup/ 配下、tests/cleanup/ 配下）"
    )
    for line in r3_5_disallowed:
        violations.append(f"R3-5: 許容範囲外の一致: {line}")

    # R9-4 により除去を保留している項目を明示する（不適合ではない）。
    _emit(
        f"除去保留（undetermined。R9-4）: {len(pending)} 件"
        + (f" — {', '.join(pending)}" if pending else "")
    )

    if violations:
        _emit(f"判定: 不適合（違反 {len(violations)} 件）")
        _emit_violations("残存走査の不適合:", tuple(violations))
        return EXIT_NON_CONFORMANT

    _emit(f"判定: 適合（除去確認 {len(results)} 件と R3-5 の範囲限定がすべて成立）")
    return EXIT_CONFORMANT


def _index_verifications_by_stream(
    records: tuple[NonRegressionRecord, ...],
) -> dict[str, tuple[NonRegressionRecord, VerificationResult]]:
    """系統ごとの非退行レコードと判定結果を対応付ける（内部関数）.

    引数:
        records: 読み込んだ `NonRegressionRecord` の並び。

    戻り値:
        `stream` をキー、(レコード, `evaluate` の判定結果) を値とする辞書。

    例外:
        CleanupCliError: 同一 `stream` のレコードが 2 件以上存在する場合。どの
            レコードを当該系統の除去済み計上（R9-5）に用いるべきかが定まらず判定
            不能であるため、既定（例「最後の 1 件」）を選ばずに失敗させる
            （第三原則3、第四原則3）。

    tasks.md 13.1 は「系統 A / B / D 各回分」の記録を求めるため、`stream` は系統
    ごとに 1 件であることを前提とする。
    """
    indexed: dict[str, tuple[NonRegressionRecord, VerificationResult]] = {}
    for record in records:
        if record.stream in indexed:
            raise CleanupCliError(
                f"R9-5: stream={record.stream!r} の非退行レコードが複数存在するため"
                "除去済み計上に用いるレコードを決定できない（判定不能）"
            )
        indexed[record.stream] = (record, evaluate(record))
    return indexed


def _not_counted_reasons(
    residual: ResidualCheckResult, verification: VerificationResult
) -> tuple[str, ...]:
    """`除去済み` として計上できなかった理由を列挙する（内部関数）.

    R9-5（requirements.md:313）は「扱いが『除去対象』であり、除去確認コマンドで
    一致 0 件となり、かつ Requirement 2 の基準 1 から基準 6 の確認がすべて適合した
    項目**のみ**を『除去済み』として計上する」と定める。すなわち条項本文は計上して
    よい条件の**限定**であり、計上できないこと自体を不適合と定めていない。したがって
    本関数は違反文字列を作らず、報告用の理由（計上対象外の内訳）のみを組み立てる
    （出典: requirements.md:313、design.md C13 の `--evaluate` 行「非退行レコードを
    読み込み C4 / C5 を適用し、除去済み計上を判定」（design.md:385）。同 Error
    Handling 表に「計上不能」に対応する行は存在しない）。

    引数:
        residual: 当該項目の残存走査結果（`collect_residual_results` の要素）。
        verification: 当該項目の系統に対応する `VerificationResult`（C4 の出力）。

    戻り値:
        理由文字列のタプル（1 件以上）。理由は R9-5 の 3 条件のうち不成立となった
        条件に対応する。

    例外:
        CleanupCliError: 理由を 1 件も特定できない場合。`is_removed`（C5）が偽を
            返した以上、残存一致件数または非退行判定のいずれかが条件を満たして
            いないはずであり、理由を特定できない状態は本関数と C5 の判定の不整合を
            意味する。理由なしの空行を報告して差異を握りつぶさず、判定不能として
            表面化させる（第三原則3）。
    """
    reasons: list[str] = []
    expectation = residual.expectation
    match_count = residual.outcome.match_count

    if not expectation.expect_zero_matches:
        # 条項の期待が「一致 1 件以上」である項目（R3-3: requirements.md:200、
        # R4-17: requirements.md:228）は、条項が適合しているときに一致件数が 1 件
        # 以上となる。R9-5 の計上条件「除去確認コマンドで一致 0 件」とは向きが逆で
        # あるため、条項が適合している限り構造的に計上対象外である。
        reasons.append(
            f"条項 {expectation.clause} の期待は「{expectation.note}」であり、"
            "R9-5 の計上条件「除去確認コマンドで一致 0 件」と向きが逆であるため"
            "構造的に計上対象外（残存走査は"
            f"{'適合' if residual.conformant else '不適合'}。一致 {match_count} 件）"
        )
    elif match_count != 0:
        # 期待が「一致 0 件」である項目で一致が残っている場合。これは条項
        # （`expectation.clause`）自体の不適合であり、当該条項の適合判定は
        # design.md C13 が `--check-residual` に割り当てている（design.md:384）。
        # 本サブコマンドは同一の `collect_residual_results` を用いるため走査範囲が
        # 一致しており、`--check-residual` が当該条項の違反として非ゼロ終了で
        # 表面化させる（見逃しは生じない）。
        reasons.append(
            f"条項 {expectation.clause} が求める一致 0 件を満たしていない"
            f"（一致 {match_count} 件）。当該条項の適合判定は `--check-residual` が"
            "担い、同サブコマンドが違反として非ゼロ終了で表面化させる"
        )

    if verification.conformant is not True:
        # 非退行不適合は R2-9（requirements.md:189）が「当該除去を未完了として
        # 扱う」ことを定める条項であり、本サブコマンドが違反として列挙している。
        reasons.append("当該系統の非退行判定が不適合（R2-9 の違反として別途列挙）")

    if not reasons:
        raise CleanupCliError(
            f"R9-5: {residual.key}: 除去済み計上に至らなかった理由を特定できない"
            f"（一致 {match_count} 件、期待 {expectation.clause}、非退行判定 "
            f"{'適合' if verification.conformant else '不適合'}。判定不能）"
        )
    return tuple(reasons)


def run_evaluate(inventory_path: Path, records_path: Path) -> int:
    """`--evaluate`: 非退行レコードを読み込み C4 / C5 を適用する（R2、R9-5）.

    処理内容:
        1. Inventory を読み込み `validate_inventory` を通す（ゼロトラスト）。
        2. 非退行レコードを厳格に読み込む。ファイル不在は明示的な失敗とする。
        3. 各レコードへ `removal_verification.evaluate`（C4）を適用し、不適合条項を
           列挙する（R2-1〜R2-6、R2-10）。
        4. `除去対象` 各項目について除去確認コマンドを実行して一致件数を取得し、
           当該項目の系統に対応する `VerificationResult` とともに
           `completion.is_removed`（C5）へ渡して除去済み計上の可否を判定する
           （R9-5）。計上できなかった項目は**違反ではなく「計上対象外」**として
           理由付きで報告する（下記「計上不能を違反として扱わない理由」）。
        5. `completion.is_stream_b_complete`（C5）で系統 B の完了を判定する
           （R4-9、R4-10、R4-14〜R4-17）。

    本サブコマンドが「不適合」（終了コード 1）として扱う条件は、要件本文が不適合を
    定める次の 2 つに限る:
        - R2-9（requirements.md:189）「IF 基準 1 から基準 6 のいずれかの確認が不適合
          となった場合、THEN THE Executor SHALL 当該除去を適用前の状態へ復帰させ、
          不適合の内容と出典を記録し、当該除去を未完了として扱う。」C4 が列挙した
          不適合条項（R2-1〜R2-6、および記録内容を定める R2-10（requirements.md:190））
          を違反として列挙する（出典: design.md Error Handling「非退行確認のいずれかが
          不適合 | C4 `evaluate`」（design.md:727））。
        - R4-14（requirements.md:225）「THE 系統 B の完了判定 SHALL 基準 1 から基準 8
          および基準 17 の適用完了と、…承認済み Destructive_Operation の完了および
          不在確認の双方が成立した場合にのみ成立する。」および R4-15
          （requirements.md:226）「WHILE 基準 14 の AWS 側不在確認が成立していない
          間、THE Executor SHALL 系統 B を未完了として記録する。」
          `is_stream_b_complete` が偽の場合を違反として列挙する（出典: design.md
          Error Handling「系統 B の部分適用 | C5 `is_stream_b_complete`」
          （design.md:729））。

    計上不能を違反として扱わない理由（R9-5 の文面解釈。第四原則2 曲解禁止）:
        - R9-5（requirements.md:313）は「…項目**のみ**を『除去済み』として計上する」
          であり、計上してよい条件の限定を定める条項である。「すべての `除去対象`
          項目が計上可能でなければならない」とは定めていないため、「計上できない
          こと」を不適合とする条件は要件本文から導出できない。
        - design.md C13 の `--evaluate` 行（design.md:385）は「除去済み計上を**判定**」
          と記述しており、計上不能を違反として列挙することを規定していない。同
          Error Handling 表（design.md:722-733）にも該当行はない。
        - 実測される構造的な計上対象外 2 件は、条項の期待が「一致 1 件以上」である
          項目である（`gitignore_aws_sam` → R3-3（requirements.md:200）は `.gitignore`
          への `.aws-sam/` 追加を求め、`git check-ignore -v .aws-sam/build.toml` は
          適用成功時に一致 1 件となる。`prod_email_backend_policy` → R4-17
          （requirements.md:228）は `EMAIL_BACKEND` の明示設定を求め、
          `git grep -n "EMAIL_BACKEND" -- config/settings/prod.py` は適用成功時に
          一致 2 件となる）。これらを違反として扱うと、条項が適合している状態で
          恒久的に不適合となる。
        - 握りつぶしは行わない（第三原則3）。計上できなかった項目は件数と理由を
          標準出力へ全件報告する（`_not_counted_reasons`）。

    残存走査の不適合を本サブコマンドの違反として扱わない理由（責務分離）:
        期待「一致 0 件」の項目に一致が残っている場合、それは当該項目の条項
        （R3-1、R3-2、R4-1、R4-4、R4-5、R4-7、R4-8、R6-1〜R6-3、R7-5、R10-1）の不適合
        であり、design.md C13 はこれらの条項の適合判定を `--check-residual` 行
        （design.md:384）へ割り当てている。本サブコマンドと `--check-residual` は
        いずれも `collect_residual_results(inventory)` を用いるため走査対象が完全に
        一致しており、`--check-residual` が終了コード 1 で表面化させる。したがって
        条項識別子の帰属を二重化せずに見逃しも生じない（第三原則2 整合性）。
        なお期待が「一致 1 件以上」の 2 項目については、条項が不適合（一致 0 件）に
        なると R9-5 の計上条件（一致 0 件）を満たして計上され得るため、当該 2 条項
        （R3-3、R4-17）の適合判定を本サブコマンドの計上件数で代替してはならない。
        これらの判定は `--check-residual` が担う。

    引数:
        inventory_path: Inventory 正本の絶対パス。
        records_path: 非退行レコードファイルの絶対パス。

    戻り値:
        `EXIT_CONFORMANT`（全レコードが R2 に適合し、系統 B が完了）または
        `EXIT_NON_CONFORMANT`（R2-9 または R4-14 の違反あり）。

    例外:
        CleanupCliError: 入力の読み込み・スキーマ検証の失敗、確認コマンドの異常
            終了、系統に対応するレコードの欠落、同一系統のレコードの重複、または
            計上対象外の理由を特定できない場合。
        ValueError: 判定層（`is_removed` / `is_stream_b_complete`）が矛盾入力に対して
            送出する（`main` が捕捉し終了コード 2 とする）。
    """
    inventory = load_validated_inventory(inventory_path)
    records = load_records(records_path)
    verifications = _index_verifications_by_stream(records.non_regression_records)

    violations: list[str] = []

    _emit(f"非退行レコード: {records_path}")
    for stream in sorted(verifications):
        record, verification = verifications[stream]
        status = "適合" if verification.conformant else "不適合"
        _emit(
            f"[R2] stream={stream}: {status}"
            f"（pass {record.tests_passed} / failure {record.tests_failed} / "
            f"error {record.tests_errored}、コマンド {len(record.commands)} 件）"
        )
        for clause in verification.violations:
            violations.append(
                f"{clause}: stream={stream}: 非退行確認が不適合"
                "（当該除去は未完了として扱う。R2-9）"
            )

    # 除去済み計上（R9-5）。残存一致件数は除去確認コマンドの実行結果から取得する。
    residual_results = collect_residual_results(inventory)
    residual_by_key = {result.key: result for result in residual_results}
    removed_count = 0
    # 計上対象外の内訳（違反ではない。R9-5 は計上してよい条件の限定を定める条項で
    # あり、計上できないことを不適合と定めていない。docstring 参照）。
    not_counted: list[str] = []
    for item in inventory.items:
        if item.disposition != DISPOSITION_REMOVAL_TARGET:
            continue
        indexed = verifications.get(item.stream)
        if indexed is None:
            raise CleanupCliError(
                f"R9-5: {item.key}: stream={item.stream!r} の非退行レコードが存在"
                "しないため除去済み計上を判定できない（判定不能）"
            )
        verification = indexed[1]
        # `collect_residual_results` は `除去対象` 全項目を走査するため必ず存在する。
        residual = residual_by_key[item.key]
        if is_removed(item, residual.outcome.match_count, verification):
            removed_count += 1
            continue
        # 計上できなかった事実と理由を報告する（握りつぶさない。第三原則3）。
        reasons = _not_counted_reasons(residual, verification)
        not_counted.append(f"{item.key}: " + " / ".join(reasons))

    _emit(
        f"[R9-5] 除去済み計上: {removed_count} 件 / 除去対象 "
        f"{len(residual_results)} 件"
    )
    if not_counted:
        _emit(
            f"[R9-5] 計上対象外: {len(not_counted)} 件"
            "（R9-5 は計上条件の限定を定める条項であり、計上不能は不適合ではない）"
        )
        for entry in not_counted:
            _emit(f"  - {entry}")

    # 系統 B の完了判定（R4-14）。期待対象集合の妥当性検証は判定層が行う。
    stream_b_complete = is_stream_b_complete(
        records.applied_stream_b_segments, records.aws_smtp_state
    )
    _emit(
        f"[R4-14] 系統 B 完了: {'成立' if stream_b_complete else '未成立'}"
        f"（適用済み区分 {len(records.applied_stream_b_segments)} 件、"
        f"AWS 照会 {'実施' if records.aws_smtp_state.queried else '未実施'}、"
        f"対象 {len(STREAM_B_AWS_TARGETS)} 件）"
    )
    if not stream_b_complete:
        violations.append(
            "R4-14: 系統 B が未完了（8 区分の適用と AWS 側の削除完了・不在確認の"
            "双方成立が必要。R4-9、R4-10、R4-15、R4-16、R4-17）"
        )

    if violations:
        _emit(f"判定: 不適合（違反 {len(violations)} 件）")
        _emit_violations("完了判定の不適合:", tuple(violations))
        return EXIT_NON_CONFORMANT

    _emit("判定: 適合（R2 の非退行判定と R4-14 の系統 B 完了がすべて成立）")
    return EXIT_CONFORMANT


def run_audit_dependencies(manifest_path: Path, ledger_path: Path) -> int:
    """`--audit-dependencies`: 台帳整合（R7-7）を判定しレポートを出力する.

    判定は `dependency_audit.check_ledger_coherence`（C10）が行う。不整合の場合は
    差分を出力して非ゼロ終了する（出典: design.md「Error Handling」の「台帳不整合
    （集合差分あり）」行）。

    `pip` を実行しない理由（本タスクの範囲判断。第一原則5、第四原則2）:
        R7-2（依存グラフ解決）と R7-8（クリーン環境での `pip install`）の確認は、
        design.md C10「確認手順」により **Windows venv と Docker
        （`python:3.12-slim-bookworm`）の 2 環境**で実施し、その結果を
        `DependencyCandidate` として記録することが求められる。記録と
        `dependency_audit.decide` の適用は tasks.md 12.1 の範囲であり、Docker 環境の
        実行は本 CLI プロセス内で代替できない。したがって本サブコマンドでは `pip`
        を起動せず、`decide` の入力となる `DependencyCandidate` も捏造しない
        （未収集の証拠に基づく判定を行わない。ゼロトラスト）。実行する場合も
        読み取り専用の形式（`pip show` / `pip install --dry-run --report`）に限る
        ことが design.md C10 の手順であり、環境を変更する実行は行わない。

    引数:
        manifest_path: `requirements.txt` の絶対パス。
        ledger_path: `docs/external-assets.md` の絶対パス。

    戻り値:
        `EXIT_CONFORMANT`（記載集合が一致）または `EXIT_NON_CONFORMANT`。

    例外:
        CleanupCliError: いずれかのファイルの読み込み・解析に失敗した場合。
    """
    manifest_names = parse_manifest_names(manifest_path)
    ledger_names = parse_ledger_names(ledger_path)
    report = check_ledger_coherence(manifest_names, ledger_names)

    _emit(f"Dependency_Manifest: {manifest_path}（記載 {len(manifest_names)} 件）")
    _emit(f"License_Ledger: {ledger_path}（記載 {len(ledger_names)} 件）")

    # R7-11 の判定対象 12 件のうち Dependency_Manifest に残っているものを明示する。
    # 除去の適用状況を可視化するための情報であり、終了コードには影響させない
    # （R7-4 により未確認の dependency は `undetermined` として保留されるため、
    # 残存していること自体は不適合ではない）。
    remaining_targets = tuple(sorted(JUDGEMENT_TARGET_DEPENDENCIES & manifest_names))
    _emit(
        f"[R7-11] 判定対象 {len(JUDGEMENT_TARGET_DEPENDENCIES)} 件のうち "
        f"Dependency_Manifest に残存: {len(remaining_targets)} 件"
        + (f" — {', '.join(remaining_targets)}" if remaining_targets else "")
    )

    if not report.coherent:
        violations = tuple(
            [
                f"R7-7: Dependency_Manifest にのみ存在: {name}"
                for name in report.manifest_only
            ]
            + [
                f"R7-7: License_Ledger にのみ存在: {name}"
                for name in report.ledger_only
            ]
        )
        _emit(
            f"判定: 不適合（manifest_only {len(report.manifest_only)} 件 / "
            f"ledger_only {len(report.ledger_only)} 件。R7-7）"
        )
        _emit_violations("台帳不整合（R7-7）:", violations)
        return EXIT_NON_CONFORMANT

    _emit("判定: 適合（Dependency_Manifest と License_Ledger の記載集合が一致。R7-7）")
    return EXIT_CONFORMANT


# ---------------------------------------------------------------------------
# エントリーポイント
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """コマンドライン引数パーサを構築する（内部関数）.

    引数:
        なし。

    戻り値:
        `argparse.ArgumentParser`。サブコマンドは design.md C13 の表に対応する
        5 つの排他フラグとし、いずれか 1 つの指定を必須とする（既定動作を持たない。
        暗黙の実行を避ける。第二原則2）。

    例外:
        送出しない。
    """
    parser = argparse.ArgumentParser(
        description=(
            "旧資産除去（legacy-asset-cleanup）の検証 CLI（design.md C13）: "
            "Inventory 検証・出典行番号照合・残存走査・完了判定・台帳整合を行う。"
        )
    )
    # 排他かつ必須。複数指定や無指定での暗黙実行を許さない。
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--validate-inventory",
        action="store_true",
        help="Inventory の構造的不変条件を検証する（R1）。",
    )
    group.add_argument(
        "--verify-lines",
        action="store_true",
        help=(
            "各項目の source_path:source_lines を Inventory が記録する revision 時点"
            "の実体（git show <revision>:<source_path>）へ照合する。対象は当該 "
            "revision の追跡集合に含まれる source_path に限る"
            "（R1-5、Glossary（Repository））。"
        ),
    )
    group.add_argument(
        "--check-residual",
        action="store_true",
        help=(
            "除去確認コマンド（git ls-files / git grep / git check-ignore）を実行し"
            "一致件数を期待と照合する（R3、R4、R6、R10-1）。"
        ),
    )
    group.add_argument(
        "--evaluate",
        action="store_true",
        help=(
            "非退行レコードを読み込み、非退行判定・除去済み計上・系統 B 完了判定を"
            "適用する（R2、R9-5、R4-14）。"
        ),
    )
    group.add_argument(
        "--audit-dependencies",
        action="store_true",
        help=(
            "Dependency_Manifest と License_Ledger の記載集合の一致を判定する"
            "（R7-7）。"
        ),
    )
    parser.add_argument(
        "--records-path",
        default=str(_DEFAULT_RECORDS_PATH),
        help=(
            "--evaluate が読み込む非退行レコードファイルのパス（既定: "
            f"{_DEFAULT_RECORDS_PATH}）。存在しない場合は終了コード 2 で失敗する。"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """サブコマンドを実行し、判定に応じた終了コードを返すエントリーポイント.

    引数:
        argv: コマンドライン引数（テスト用途に注入可能。既定は `sys.argv[1:]`）。

    戻り値:
        `EXIT_CONFORMANT`（0）= 要求された検査がすべて適合、
        `EXIT_NON_CONFORMANT`（1）= 不適合あり、
        `EXIT_INPUT_FAILURE`（2）= 入力・コマンド実行の失敗または判定不能。

    例外:
        送出しない。`CleanupCliError` と判定層の `ValueError` は捕捉して内容を
        標準エラーへ日本語で出力し、終了コード 2 を返す（トレースバックのみで
        終わらせず、失敗理由を報告として残す。握りつぶしではなく非ゼロ終了で
        表面化させる）。それ以外の例外は捕捉しない（想定外の失敗を隠さない。
        第三原則3）。
    """
    args = _build_parser().parse_args(argv)

    try:
        if args.validate_inventory:
            return run_validate_inventory(_INVENTORY_PATH)
        if args.verify_lines:
            return run_verify_lines(_INVENTORY_PATH)
        if args.check_residual:
            return run_check_residual(_INVENTORY_PATH)
        if args.evaluate:
            return run_evaluate(_INVENTORY_PATH, Path(args.records_path))
        # 排他必須グループのため、ここに到達するのは --audit-dependencies のみ。
        return run_audit_dependencies(_MANIFEST_PATH, _LEDGER_PATH)
    except CleanupCliError as exc:
        # 入力の不備・コマンドの異常終了・判定不能。既定値で補完せず失敗させる。
        sys.stderr.write(f"入力またはコマンド実行の失敗: {exc}\n")
        return EXIT_INPUT_FAILURE
    except ValueError as exc:
        # 判定層（inventory / completion / dependency_audit）が矛盾入力に対して
        # 送出する例外。記録側の誤りであり、判定結果へ吸収しない。
        sys.stderr.write(f"判定層が入力の矛盾を検出した: {exc}\n")
        return EXIT_INPUT_FAILURE


if __name__ == "__main__":
    # スクリプト直接起動時はサブコマンドを実行し、判定に応じた終了コードで終了する。
    raise SystemExit(main())
