"""Legacy_Asset_Inventory の行番号一致テスト（例示・整合テスト。プロパティテストではない）.

目的:
    `docs/legacy-asset-inventory.json` の各項目（`items` および `preserved`）が持つ出典
    `source_path:source_lines` を、Inventory が `revision` として記録した時点のリポジトリ
    実体（`git show <revision>:<source_path>`）へ照合し、記録された行番号が当該時点の実体と
    一致することを機械的に検証する。R1-5 を自動で守るガードであり、Inventory と記録時点の
    実体の乖離を除去作業の前に表面化させる。

出典:
    - `.kiro/specs/legacy-asset-cleanup/requirements.md` Requirement 1 基準 5（R1-5）:
      「WHEN Executor が Legacy_Asset_Inventory を作成する時、THE Executor SHALL 各項目の
      行番号を作成時点のリポジトリ実体に対して再確認し、実体と一致する値を記録する。」
      照合先が「作成時点」であるため、本テストは作業ツリーの現在の内容とは照合しない。
    - 同 requirements.md Glossary「**Repository**: git 追跡下のファイル集合（`git ls-files`
      が返す集合）。`.kiro` は `.gitignore:173` により Repository に含まれない。」
    - `.kiro/specs/legacy-asset-cleanup/design.md` C13「`--verify-lines` の照合基準（R1-5）」
      および「Repository 外の `source_path` の扱い（R1-5 の適用範囲）」: 照合先は
      `git show <revision>:<source_path>`、照合対象は `source_path` が Repository に含まれる
      項目に限る。Repository 外の項目は「照合対象外」の事実として扱い、R1-5 が求めていない
      理由による不一致としない。
    - 同 design.md Error Handling 表「行番号が記録 `revision` 時点の実体と不一致」。
    - 同 design.md Testing Strategy 単体・example テスト表の
      `tests/cleanup/test_inventory_line_numbers.py` 行。
    - 検証対象データの正本は `docs/legacy-asset-inventory.json`（design.md C1 / DM2）。本
      テストは同ファイルを読み込み、その内容をテスト側へ再記述しない（二重記述による乖離の
      防止。第三原則2）。

本テストが検証すること:
    S  適用範囲の導出: 照合対象（Repository 内）と照合対象外（Repository 外）の区分を、
       記録 `revision` の追跡パス集合から導出する。区分をテスト側の固定値として書かない。
    L1 経路の実在性: 照合対象の各 `source_path` が記録 `revision` 時点に実体として存在する
       こと（`git show <revision>:<source_path>` が成功すること）。
    L2 表記の妥当性: `source_lines` が「単一行番号」または「開始-終了」のカンマ区切り列
       （例 `6,8,12` / `72-86` / `112-113,121-122`）として厳密に解釈できること。行番号は
       1 以上、区間は開始 <= 終了であること。解釈できない値は失敗とする（既定値による補完を
       行わない。第三原則3）。
    L3 行番号の実在性: 照合対象の `source_lines` が参照する全行番号が、記録 `revision` 時点の
       当該ファイルの行数以内であること。

本テストが検証しないこと（限界。過大な主張をしない）:
    - 当該行の意味内容が記録どおりであることは検証しない。検証するのは「その行番号が記録
      `revision` 時点に実在する」ことまでである（L3）。
    - 作業ツリー・git インデックス・`HEAD` の内容とは照合しない（照合先は記録 `revision` に
      限る）。したがって除去の適用によって当該行が作業ツリーから失われても本テストは失敗
      しない。R1-5 が求めるのは作成時点の実体との一致だけである。
    - Repository 外の `source_path` を持つ項目（Glossary により `.kiro` 配下）については、
      L1 / L3 の実体照合を行わない。区分の正しさ（当該パスが記録 `revision` の追跡集合に
      含まれないこと）のみを検証する。
    - `confirmation.result` / `build_time_dependency` / `description` に含まれる行番号は
      照合しない。R1-1 が出典として求める要素はファイルパス・行番号・検出に用いた実行
      コマンドであり、`description`（DM1 では「対象の説明」）は出典要素ではないため、その
      文面と実体の一致は R1-5 の要求範囲外である。
    - `undetermined_notes` は出典 3 要素を持たない（design.md DM1 の `UndeterminedNote`）
      ため対象外である。

追跡パス集合の取得方法（`git ls-tree -r --name-only <revision>` を用いる理由）:
    Glossary は Repository を `git ls-files` が返す集合と定義するが、`git ls-files` は現在の
    インデックスを対象とし、過去 revision の集合は返さない。R1-5 の照合時点は記録
    `revision` であるため、当該 revision のツリーに含まれるパス集合、すなわち
    `git ls-tree -r --name-only <revision>` の結果を用いる。`--with-tree` はインデックスと
    ツリーの合成を返すため、記録時点の集合を厳密に得る目的には用いない。パスは `-z` により
    NUL 区切りで受け取り、`git` によるパスの引用（非 ASCII 文字を含む場合の `"..."` 表記）を
    介さずそのまま比較する。

読み取り方針:
    - `git` の出力は UTF-8 固定で解釈する。デコード失敗は例外として表面化させる（代替
      エンコーディングへのフォールバックを行わない）。
    - 行数は CRLF / LF の双方でエディタおよび `git grep -n` の行番号と一致するよう、`"\n"`
      分割後に末尾の空要素を除き、各行末に残る `"\r"` を除去して数える（`str.splitlines()` は
      `\x0b` / `\u2028` 等も行境界として扱うため使用しない）。
    - `git` の実行は本ファイル位置から導出したリポジトリルートを作業ディレクトリとし、
      カレントディレクトリに依存しない。非ゼロ終了は失敗として扱い、読み飛ばさない。
    - Inventory の `revision` は外部入力であるため、`git` の引数へ渡す前に SHA-1 の 16 進
      表記であることを検証する（オプション文字列の混入を防ぐ。第二原則2 ゼロトラスト）。

実行コマンド（プロジェクトルートから）:
    $env:DJANGO_SETTINGS_MODULE="config.settings.dev"; python manage.py test tests.cleanup.test_inventory_line_numbers
  もしくは（Django 非ロードでも実行可能。本テストは `git` 実行とファイル読み取りのみを行う）:
    python -m unittest tests.cleanup.test_inventory_line_numbers -v
"""

from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

# 本ファイルは <repo>/tests/cleanup/ に配置されるため、2 階層上がリポジトリルートである。
_REPO_ROOT = Path(__file__).resolve().parents[2]

# Inventory 正本（design.md C1）。内容はテスト側へ再記述しない。
_INVENTORY_PATH = _REPO_ROOT / "docs" / "legacy-asset-inventory.json"

# 出典 `source_path` / `source_lines` を持つセクション。
_SECTIONS_WITH_SOURCE: tuple[str, ...] = ("items", "preserved")

# `source_lines` の 1 トークン。単一行番号（`170`）または閉区間（`72-86`）のみを許す。
_SOURCE_LINES_TOKEN = re.compile(r"\A(?:(?P<single>\d+)|(?P<start>\d+)-(?P<end>\d+))\Z")

# 記録 `revision` として受理する表記（短縮または完全な SHA-1 の 16 進表記）。
_REVISION_PATTERN = re.compile(r"\A[0-9a-f]{7,40}\Z")


def _read_inventory() -> dict:
    """Inventory 正本を UTF-8 で読み込み、辞書として返す。

    Returns:
        `docs/legacy-asset-inventory.json` をデコードした辞書。

    Raises:
        FileNotFoundError: 正本が存在しない場合。
        UnicodeDecodeError: UTF-8 として解釈できない場合。
        json.JSONDecodeError: JSON として解釈できない場合。
    """
    return json.loads(_INVENTORY_PATH.read_bytes().decode("utf-8"))


def _validated_revision(value: object) -> str:
    """Inventory の `revision` を `git` へ渡せる値として検証して返す。

    Args:
        value: Inventory の `revision` の値（外部入力であるため型も検証する）。

    Returns:
        SHA-1 の 16 進表記（短縮を含む）である `revision`。

    Raises:
        ValueError: 文字列でない場合、または SHA-1 の 16 進表記でない場合。表記外の値を
            `git` の引数へ渡さない（`-` で始まる値がオプションとして解釈される余地を残さない。
            第二原則2）。既定値での代替を行わず失敗として表面化させる（第三原則3）。
    """
    if not isinstance(value, str) or _REVISION_PATTERN.match(value) is None:
        raise ValueError(f"Inventory の revision が SHA-1 の 16 進表記でない: {value!r}")
    return value


def _run_git(argv: tuple[str, ...]) -> subprocess.CompletedProcess[bytes]:
    """`git` を引数配列で実行し、完了プロセスをそのまま返す。

    Args:
        argv: `git` に続く引数の並び。

    Returns:
        標準出力・標準エラーをバイト列で保持する完了プロセス。終了コードの判定は呼び出し側が
        行う（本関数は非ゼロを隠さない）。

    Raises:
        OSError: `git` 実行ファイルを起動できない場合。

    `shell=True` を用いないため、引数中のシェルメタ文字は解釈されない（第二原則2）。
    """
    return subprocess.run(
        ["git", *argv],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        check=False,
    )


def _tracked_paths_at_revision(revision: str) -> frozenset[str]:
    """記録 `revision` 時点の追跡パス集合を返す（当該時点の Repository の実体）。

    Args:
        revision: `_validated_revision` を通した `revision`。

    Returns:
        当該 revision のツリーに含まれるパス（リポジトリルート相対・`/` 区切り）の集合。

    Raises:
        RuntimeError: `git ls-tree` が非ゼロ終了した場合。
        UnicodeDecodeError: 出力を UTF-8 として解釈できない場合。
            いずれも読み飛ばさず失敗として伝播させる（第三原則3）。
    """
    completed = _run_git(("ls-tree", "-r", "-z", "--name-only", revision))
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"git ls-tree が非ゼロ終了した（revision={revision}、"
            f"終了コード={completed.returncode}、標準エラー={stderr!r}）"
        )
    # `-z` により NUL 区切りで得られるため、末尾の空要素のみを除いてそのまま比較する。
    text = completed.stdout.decode("utf-8")
    return frozenset(path for path in text.split("\0") if path != "")


def _read_lines_at_revision(revision: str, source_path: str) -> tuple[str, ...]:
    """記録 `revision` 時点のファイル内容を、行番号と一致する行内容の並びで返す。

    Args:
        revision: `_validated_revision` を通した `revision`。
        source_path: リポジトリルート相対のパス（`/` 区切り）。

    Returns:
        行末の改行を除いた行内容のタプル。要素数が当該時点の当該ファイルの行数である。

    Raises:
        RuntimeError: `git show` が非ゼロ終了した場合（当該 revision に当該パスが存在しない
            場合を含む）。存在しない出典を読み飛ばさず失敗として扱う（第三原則3）。
        UnicodeDecodeError: 出力を UTF-8 として解釈できない場合。
    """
    completed = _run_git(("show", f"{revision}:{source_path}"))
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"git show が非ゼロ終了した（{revision}:{source_path}、"
            f"終了コード={completed.returncode}、標準エラー={stderr!r}）"
        )
    text = completed.stdout.decode("utf-8")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        # 末尾改行が生む空要素は行として数えない（`git grep -n` の行番号と一致させる）。
        lines.pop()
    # CRLF のファイルでは分割後の各行末に `\r` が残るため除去する。
    return tuple(line[:-1] if line.endswith("\r") else line for line in lines)


def _parse_source_lines(value: str) -> tuple[int, ...]:
    """`source_lines` を参照行番号の昇順タプルへ展開する。

    Args:
        value: `6,8,12` / `72-86` / `112-113,121-122` 形式の文字列。

    Returns:
        参照される全行番号（重複排除・昇順）。

    Raises:
        ValueError: 空文字、未知の表記、1 未満の行番号、または開始 > 終了の区間を含む場合。
            解釈できない値を既定値で補完せず、失敗として呼び出し元へ伝播させる。
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


class InventoryLineNumberTests(unittest.TestCase):
    """Inventory の出典行番号が記録 `revision` 時点の実体と一致することを検証する。"""

    # Inventory が記録する revision（DM2）。照合先の時点である。
    revision: str
    # (セクション名, key, source_path, source_lines) の並び。
    entries: tuple[tuple[str, str, str, str], ...]
    # 記録 revision 時点の追跡パス集合（当該時点の Repository の実体）。
    tracked_paths: frozenset[str]
    # `source_path` ごとの行内容キャッシュ（同一ファイルを複数項目が参照するため）。
    lines_cache: dict[str, tuple[str, ...]]

    @classmethod
    def setUpClass(cls) -> None:
        """Inventory と記録 revision の追跡パス集合を 1 度だけ取得する。"""
        inventory = _read_inventory()
        cls.revision = _validated_revision(inventory["revision"])
        entries: list[tuple[str, str, str, str]] = []
        for section in _SECTIONS_WITH_SOURCE:
            for item in inventory[section]:
                entries.append(
                    (
                        section,
                        item["key"],
                        item["source_path"],
                        item["source_lines"],
                    )
                )
        cls.entries = tuple(entries)
        cls.tracked_paths = _tracked_paths_at_revision(cls.revision)
        cls.lines_cache = {}

    def _in_scope_entries(self) -> tuple[tuple[str, str, str, str], ...]:
        """照合対象（`source_path` が記録 revision の追跡集合に含まれる項目）を返す。

        Returns:
            (セクション名, key, source_path, source_lines) のタプル。

        区分は `tracked_paths` から導出する。対象・対象外の一覧をテスト側の固定値として
        持たない（design.md C13「Repository 外の `source_path` の扱い」）。
        """
        tracked = type(self).tracked_paths
        return tuple(entry for entry in type(self).entries if entry[2] in tracked)

    def _lines_of(self, source_path: str) -> tuple[str, ...]:
        """記録 revision 時点の `source_path` の行内容を取得する（初回のみ `git show`）。

        Args:
            source_path: リポジトリルート相対のパス。

        Returns:
            行内容のタプル。
        """
        cached = type(self).lines_cache.get(source_path)
        if cached is None:
            cached = _read_lines_at_revision(type(self).revision, source_path)
            type(self).lines_cache[source_path] = cached
        return cached

    def test_inventory_records_revision_and_non_empty_sources(self) -> None:
        """記録 `revision` が SHA-1 表記であり、全項目が非空の出典要素を持つこと.

        検証条項: R1-5（照合先の時点である `revision` が一意に特定できること）および R1-1
        （出典としてファイルパスと行番号を持つこと）。後続テストが対象 0 件のまま無条件に
        成功する（無検証の成功）ことを防ぐ土台の確認でもある。
        """
        self.assertRegex(
            type(self).revision,
            _REVISION_PATTERN,
            "Inventory の revision が SHA-1 の 16 進表記でない",
        )
        self.assertGreater(len(self.entries), 0, "Inventory の照合対象が 0 件である")
        for section, key, source_path, source_lines in self.entries:
            with self.subTest(section=section, key=key):
                self.assertTrue(source_path.strip(), "source_path が空である")
                self.assertTrue(source_lines.strip(), "source_lines が空である")

    def test_scope_partition_matches_revision_tracked_paths(self) -> None:
        """照合対象外の項目が、記録 revision の追跡集合に無いパスと厳密に一致すること.

        検証条項: R1-5 の適用範囲、および requirements.md Glossary「Repository」（`.kiro` は
        `.gitignore:173` により Repository に含まれない）。design.md C13「Repository 外の
        `source_path` の扱い」に従い、区分は記録 revision の追跡集合から導出する。

        導出した区分を `git` へ 1 パスずつ問い直して確認する（集合演算の結果をそのまま
        期待値とせず、対象外のパスが当該 revision に実体を持たないことと、対象のパスが実体を
        持つことを個別に確かめる）。
        """
        in_scope = {entry[2] for entry in self._in_scope_entries()}
        out_of_scope = {entry[2] for entry in self.entries} - in_scope

        for source_path, expected_stdout in [
            *((path, "") for path in sorted(out_of_scope)),
            *((path, path + "\0") for path in sorted(in_scope)),
        ]:
            with self.subTest(source_path=source_path):
                completed = _run_git(
                    (
                        "ls-tree",
                        "-r",
                        "-z",
                        "--name-only",
                        type(self).revision,
                        "--",
                        source_path,
                    )
                )
                self.assertEqual(
                    completed.returncode,
                    0,
                    f"git ls-tree が非ゼロ終了した: {source_path}",
                )
                self.assertEqual(
                    completed.stdout.decode("utf-8"),
                    expected_stdout,
                    f"記録 revision {type(self).revision} の追跡集合に対する区分が"
                    f"一致しない: {source_path}",
                )

    def test_in_scope_source_paths_exist_at_revision(self) -> None:
        """照合対象の `source_path` が記録 revision 時点に実体として存在すること（L1）.

        検証条項: R1-5（「作成時点のリポジトリ実体」との一致）。`git show` の非ゼロ終了は
        読み飛ばさず失敗として扱う（`_read_lines_at_revision` が `RuntimeError` を送出する）。
        """
        in_scope = self._in_scope_entries()
        self.assertGreater(len(in_scope), 0, "照合対象の項目が 0 件である")
        for section, key, source_path, _source_lines in in_scope:
            with self.subTest(section=section, key=key, source_path=source_path):
                self.assertGreater(
                    len(self._lines_of(source_path)),
                    0,
                    f"{source_path} が記録 revision 時点で 0 行である",
                )

    def test_source_lines_are_parseable(self) -> None:
        """全項目の `source_lines` が定義した表記として厳密に解釈できること（L2）.

        検証条項: R1-5（行番号として解釈できる値が記録されていること）。表記の妥当性は記録側
        の性質であり実体の内容に依存しないため、照合対象外の項目も対象に含める（当該項目の
        実体については何も検証しない）。
        """
        for section, key, source_path, source_lines in self.entries:
            with self.subTest(section=section, key=key, source_lines=source_lines):
                try:
                    parsed = _parse_source_lines(source_lines)
                except ValueError as exc:
                    # 解釈不能は握りつぶさず、不一致と同様に失敗として報告する。
                    self.fail(f"{source_path}:{source_lines} を解釈できない: {exc}")
                self.assertGreater(
                    len(parsed),
                    0,
                    f"{source_path}:{source_lines} が行番号を 1 件も含まない",
                )

    def test_in_scope_line_numbers_within_revision_line_count(self) -> None:
        """照合対象の全行番号が記録 revision 時点の行数以内であること（L3）.

        検証条項: R1-5（記録した行番号が作成時点の実体に存在すること）。照合先は
        `git show <revision>:<source_path>` であり、作業ツリーとは照合しない。
        """
        for section, key, source_path, source_lines in self._in_scope_entries():
            lines = self._lines_of(source_path)
            for line_number in _parse_source_lines(source_lines):
                with self.subTest(section=section, key=key, line=line_number):
                    self.assertLessEqual(
                        line_number,
                        len(lines),
                        f"{key}: {source_path}:{source_lines} の行 {line_number} は記録 "
                        f"revision {type(self).revision} 時点の行数 {len(lines)} を超える",
                    )


if __name__ == "__main__":
    # 単体実行用エントリ（`python -m unittest` による探索でも実行可能）。
    unittest.main()
