"""ビルド検証段接続テスト（`buildspec.yml`）.

本モジュールは tasks.md 6.2 に対応し、CodeBuild ビルド仕様 `buildspec.yml` が
要件・設計で定めた「7 言語生成成功時のみ S3 同期・失敗時は部分同期せず中断」
および「既存検証段の保持」を満たすことを、`buildspec.yml` を構造的に解析
（パース）して検証する（出典: tasks.md 6.2、design.md C9「Build_Pipeline」、
requirements.md R3-2 / R3-6 / R9-7）。

検証項目（解析した `buildspec.yml` に対して）:
    1. 7 言語生成→S3 同期のゲーティング（R3-2/R3-6）: `aws s3 sync staticfiles/ ...`
       は `python manage.py render_static` の成功時にのみ実行される。すなわち
       同一シェルコマンド内で `render_static` の後段に `&&` 連結で配置され、
       render_static が非ゼロ終了すると sync に到達しない構造である。
    2. 部分同期経路の不在（R3-6）: `staticfiles/` への `aws s3 sync` は 1 箇所のみ
       で、render_static の `&&` ゲートを経ない無条件同期経路が存在しない
       （いずれかの言語で生成が失敗した場合、S3 への部分同期を行わない）。
    3. 同期先バケットの整合（R3-2）: 同期先が
       `cobaemon-serverless-portfolio-${ENV}-static` バケットである。
    4. 既存検証段の保持（R9-7 非退行）: `python manage.py check --fail-level WARNING`
       段が存在する。
    5. 既存検証段の保持（R9-7 非退行）: Control Platform self-test 段
       （`python ... scripts.control_platform.cli --self-test`）が存在する。

「解析対象は原本 `buildspec.yml`」についての事実（誠実性のため明記）:
    R3-2/R3-6 のゲーティングは、`buildspec.yml` の `pre_build.commands` に記述された
    シェルコマンド文字列（`render_static && ... && aws s3 sync ...`）として表現される。
    本モジュールは当該コマンド文字列を YAML から取り出し、シェルの `&&` 連結
    （前段コマンドが成功（終了コード 0）した場合にのみ後段を実行する POSIX シェル
    仕様）に基づいて順序・ゲート関係を検証する。render_static がいずれかの言語で
    失敗した際に非ゼロ終了する挙動そのものは
    `portfolio/management/commands/render_static.py` の責務であり、本モジュールは
    「buildspec 側が sync を render_static 成功にゲートしているか」のみを対象とする
    （検証境界を明示）。AWS 認証情報・ネットワーク・Docker に依存せず決定的に検証する。

外部依存とライセンス（第二原則6・着手時ライセンス確認）:
    - PyYAML 6.0.3（MIT License）を使用し `buildspec.yml` を解析する。`buildspec.yml`
      には CloudFormation 短縮タグが含まれないため、標準の `yaml.safe_load` で足りる
      （出典: `pip show PyYAML` の License 欄 = MIT、requirements-dev.txt 記載済み）。
    - 標準ライブラリ `unittest` を用いる（既存 IaC テスト
      `tests/iac/test_template_policies.py` と一貫）。

実行コマンド（プロジェクトルートから）:
    python -m unittest tests.iac.test_buildspec -v
"""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

import yaml

# ------------------------------------------------------------------------------
# buildspec.yml の所在（リポジトリルート基準）。
# 本ファイルは tests/iac/ に置かれるため parents[2] がリポジトリルートである
# （tests/iac/test_buildspec.py -> tests/iac -> tests -> ルート）。
# ------------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
_BUILDSPEC_PATH = _REPO_ROOT / "buildspec.yml"

# 検証対象の固定文字列（buildspec.yml 原本と一致。出典: buildspec.yml）。
# リテラルの散在を避け整合性を保つ。
_RENDER_STATIC = "python manage.py render_static"
_S3_SYNC_STATICFILES = "aws s3 sync staticfiles/"
_STATIC_BUCKET_NAME = "cobaemon-serverless-portfolio-${ENV}-static"
_CHECK_FAIL_LEVEL_WARNING = "python manage.py check --fail-level WARNING"
_SELF_TEST_MODULE = "scripts.control_platform.cli"
_SELF_TEST_FLAG = "--self-test"


def _load_buildspec(path: Path) -> dict[str, Any]:
    """`buildspec.yml` を解析してトップレベルのマッピングを返す.

    Args:
        path: 解析対象 `buildspec.yml` の絶対パス。

    Returns:
        dict[str, Any]: buildspec のトップレベルマッピング。

    Raises:
        FileNotFoundError: `buildspec.yml` が存在しない場合（フォールバックせず
            明示的に失敗させ、事実として欠落を報告する）。
        TypeError: 解析結果がマッピングでない場合（想定外構造を握りつぶさない）。
    """
    # ファイル欠落は握りつぶさず明示的に失敗させる（第三原則3、事実報告）。
    if not path.exists():
        raise FileNotFoundError(f"buildspec が見つからない: {path}")

    # buildspec には CFN 短縮タグが無いため標準の SafeLoader で解析する。
    with path.open(encoding="utf-8") as stream:
        document = yaml.safe_load(stream)

    # トップレベルがマッピングでない場合は想定外構造として明示的に失敗させる。
    if not isinstance(document, dict):
        raise TypeError(
            f"buildspec のトップレベルがマッピングでない: {path} "
            f"(実際: {type(document)!r})"
        )
    return document


def _phase_commands(buildspec: dict[str, Any], phase: str) -> list[str]:
    """指定フェーズの `commands` を文字列リストとして取り出す.

    Args:
        buildspec: 解析済み buildspec 辞書。
        phase: 取得対象フェーズ名（例: "install", "pre_build"）。

    Returns:
        list[str]: 当該フェーズの各コマンド文字列。

    Raises:
        KeyError: `phases` または当該フェーズ、`commands` が存在しない場合
            （明示的に失敗させる）。
        TypeError: `commands` がリストでない、または要素が文字列でない場合
            （想定外構造を握りつぶさない）。
    """
    # phases セクションの欠落は握りつぶさず失敗させる（buildspec として不正）。
    if "phases" not in buildspec:
        raise KeyError("buildspec に phases セクションが存在しない")
    phases = buildspec["phases"]
    if phase not in phases:
        raise KeyError(f"buildspec の phases に {phase} フェーズが存在しない")
    commands = phases[phase].get("commands")
    if not isinstance(commands, list):
        raise TypeError(f"{phase}.commands がリストでない (実際: {type(commands)!r})")
    # 各コマンドは文字列であること（YAML ブロックスカラも文字列として読み込まれる）。
    for command in commands:
        if not isinstance(command, str):
            raise TypeError(
                f"{phase}.commands に文字列でない要素が存在する: {command!r}"
            )
    return commands


def _all_commands(buildspec: dict[str, Any]) -> list[str]:
    """全フェーズの全コマンド文字列を平坦化して返す.

    Args:
        buildspec: 解析済み buildspec 辞書。

    Returns:
        list[str]: 全フェーズを通じたコマンド文字列の一覧。
    """
    # 全フェーズの commands を順に収集する（commands を持たないフェーズは無視）。
    collected: list[str] = []
    for phase_body in buildspec.get("phases", {}).values():
        if isinstance(phase_body, dict) and isinstance(
            phase_body.get("commands"), list
        ):
            for command in phase_body["commands"]:
                if isinstance(command, str):
                    collected.append(command)
    return collected


def _join_line_continuations(command: str) -> str:
    """シェルの行継続（バックスラッシュ+改行）を空白へ畳み込む.

    `render_static \\\n  && aws s3 sync ...` のように複数行へ折り返された 1 つの
    論理コマンドを、`&&` 連結の順序解析ができる 1 行文字列へ正規化する。

    Args:
        command: 解析対象のコマンド文字列（YAML ブロックスカラ由来の複数行を含む）。

    Returns:
        str: 行継続を畳み込んだ文字列。
    """
    # バックスラッシュ直後の改行（および続く空白）を単一空白へ置換して論理行を連結する。
    result: list[str] = []
    index = 0
    length = len(command)
    while index < length:
        char = command[index]
        # 行継続 "\\\n" を検出したら空白へ畳み込み、次行先頭の空白を読み飛ばす。
        if char == "\\" and index + 1 < length and command[index + 1] == "\n":
            result.append(" ")
            index += 2
            while index < length and command[index] in " \t":
                index += 1
            continue
        result.append(char)
        index += 1
    return "".join(result)


# ------------------------------------------------------------------------------
# buildspec はモジュール読み込み時に一度だけ解析し、各テストで共有する
# （解析は副作用のない純粋な読み取りであり、テスト間で不変）。
# ------------------------------------------------------------------------------
_BUILDSPEC = _load_buildspec(_BUILDSPEC_PATH)


class RenderStaticSyncGatingTests(unittest.TestCase):
    """7 言語生成→S3 同期のゲーティング検証（R3-2/R3-6）.

    `aws s3 sync staticfiles/ ...` が `python manage.py render_static` の成功時に
    のみ実行される（`&&` 連結で後段に配置される）ことを検証する（出典:
    buildspec.yml pre_build、design.md C9、requirements.md R3-2/R3-6）。
    """

    def _sync_command(self) -> str:
        """`aws s3 sync staticfiles/` を含む唯一のコマンドを行継続畳み込み後に返す.

        Returns:
            str: 行継続を畳み込んだ同期コマンド文字列。
        """
        # staticfiles/ への sync を含むコマンドを全フェーズから収集する。
        matches = [
            _join_line_continuations(command)
            for command in _all_commands(_BUILDSPEC)
            if _S3_SYNC_STATICFILES in command
        ]
        # 同期コマンドはちょうど 1 箇所であること（部分同期経路の重複を排除）。
        self.assertEqual(
            len(matches),
            1,
            msg=(
                "aws s3 sync staticfiles/ を含むコマンドが 1 箇所でない"
                f"（検出数={len(matches)}、R3-6 部分同期経路の疑い）: {matches!r}"
            ),
        )
        return matches[0]

    def test_sync_is_gated_by_render_static_success(self) -> None:
        """S3 同期が render_static 成功に `&&` でゲートされる（R3-2/R3-6）."""
        command = self._sync_command()
        # 同一コマンド内に render_static と sync の双方が存在すること。
        self.assertIn(
            _RENDER_STATIC,
            command,
            msg=f"同期コマンドに render_static が含まれない（R3-2 違反）: {command!r}",
        )
        render_index = command.index(_RENDER_STATIC)
        sync_index = command.index(_S3_SYNC_STATICFILES)
        # render_static が sync より前段に位置すること（生成→同期の順序）。
        self.assertLess(
            render_index,
            sync_index,
            msg=f"render_static が sync より前段でない（R3-2 違反）: {command!r}",
        )
        # render_static と sync の間が `&&` 連結であること（成功時のみ後段実行）。
        between = command[render_index + len(_RENDER_STATIC) : sync_index]
        self.assertIn(
            "&&",
            between,
            msg=(
                "render_static と sync が && 連結されていない"
                f"（失敗時に部分同期する疑い、R3-6 違反）: {command!r}"
            ),
        )

    def test_no_ungated_partial_sync_path(self) -> None:
        """render_static ゲートを経ない無条件同期経路が存在しない（R3-6）."""
        # staticfiles/ への sync を含む全コマンドが render_static に `&&` ゲートされること。
        for command in _all_commands(_BUILDSPEC):
            if _S3_SYNC_STATICFILES not in command:
                continue
            joined = _join_line_continuations(command)
            with self.subTest(command=joined):
                # 同期を含むコマンドには必ず render_static が前段に存在すること。
                self.assertIn(
                    _RENDER_STATIC,
                    joined,
                    msg=(
                        "render_static を伴わない無条件の staticfiles 同期が存在する"
                        f"（R3-6 違反）: {joined!r}"
                    ),
                )
                render_index = joined.index(_RENDER_STATIC)
                sync_index = joined.index(_S3_SYNC_STATICFILES)
                between = joined[render_index + len(_RENDER_STATIC) : sync_index]
                self.assertIn(
                    "&&",
                    between,
                    msg=(
                        "staticfiles 同期が render_static に && ゲートされていない"
                        f"（R3-6 違反）: {joined!r}"
                    ),
                )

    def test_sync_targets_static_bucket(self) -> None:
        """同期先が cobaemon-serverless-portfolio-${ENV}-static バケットである（R3-2）."""
        command = self._sync_command()
        # 同期先バケット名（BUCKET_NAME 変数の定義）が要件のバケットと一致すること。
        self.assertIn(
            _STATIC_BUCKET_NAME,
            command,
            msg=(
                "同期先バケットが cobaemon-serverless-portfolio-${ENV}-static でない"
                f"（R3-2 違反）: {command!r}"
            ),
        )
        # 実際の sync 先が BUCKET_NAME 変数を参照していること（バケット指定の整合）。
        self.assertIn(
            "s3://${BUCKET_NAME}/",
            command,
            msg=f"sync 先が BUCKET_NAME を参照していない（R3-2 違反）: {command!r}",
        )


class ExistingVerificationStagesTests(unittest.TestCase):
    """既存検証段の保持検証（R9-7 非退行）.

    `check --fail-level WARNING` と Control Platform self-test が buildspec に
    保持されていることを検証する（出典: buildspec.yml install/pre_build、
    design.md C9、requirements.md R9-7、tasks.md 6.1 完了要件）。
    """

    def test_check_fail_level_warning_present(self) -> None:
        """`python manage.py check --fail-level WARNING` 段が存在する（R9-7）."""
        # pre_build のコマンドに Django システムチェック段が保持されていること。
        commands = _phase_commands(_BUILDSPEC, "pre_build")
        self.assertTrue(
            any(_CHECK_FAIL_LEVEL_WARNING in command for command in commands),
            msg=(
                "check --fail-level WARNING 段が pre_build に存在しない"
                "（R9-7 非退行違反）"
            ),
        )

    def test_control_platform_self_test_present(self) -> None:
        """Control Platform self-test 段が存在する（R9-7）."""
        # install フェーズに Control Platform CLI の self-test 段が保持されていること。
        commands = _phase_commands(_BUILDSPEC, "install")
        self.assertTrue(
            any(
                _SELF_TEST_MODULE in command and _SELF_TEST_FLAG in command
                for command in commands
            ),
            msg=(
                "Control Platform self-test 段（scripts.control_platform.cli "
                "--self-test）が install に存在しない（R9-7 非退行違反）"
            ),
        )


if __name__ == "__main__":
    # プロジェクトルートから `python -m unittest tests.iac.test_buildspec -v` で実行する。
    unittest.main()
