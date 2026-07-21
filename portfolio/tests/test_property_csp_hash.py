"""Property 5（CSP ハッシュ生成は nonce を含まずインラインの SHA-256 を含む）のプロパティテスト.

本モジュールは design.md「Correctness Properties > Property 5」および tasks.md 4.2 を
検証する（出典: tasks.md 行104-108）。
    Property 5: CSP ハッシュ生成は nonce を含まずインラインの SHA-256 を含む
    *For any* 任意のインライン `<script>` / `<style>` 内容について、生成される
    Content-Security-Policy は (a) per-request nonce 相当（django-csp の
    `csp.constants.NONCE` センチネルおよび `'nonce-...'` ソース）を一切含まず、
    (b) 各インライン内容の SHA-256 ハッシュソース `'sha256-...'` を含む。

検証対象（Validates: Requirements 7.2）:
    - R7-2: 静的ページの CSP を per-request nonce 方式ではなくハッシュベース方式で
      構成し、CSP に `csp_constants.NONCE` 相当の nonce 値を含めない
      （出典: requirements.md 要件7 Acceptance Criteria 2）。

検証対象モジュール（tasks.md 4.1 実装、出典: portfolio/management/commands/_csp_hash.py）:
    - generate_csp_header(html, base_directives, cloudfront_domain) -> str
      HTML からインライン内容を抽出（extract_inline_contents）→ SHA-256→base64→
      `'sha256-...'` を算出（compute_inline_hashes）→ nonce 相当を除去し CloudFront
      ドメインとハッシュを反映（build_csp_directives）→ ヘッダ値へ整形
      （render_csp_header_value）を合成した最上位エントリポイント。

ライセンス注記（第二原則6・要ライセンス確認）:
    - Hypothesis は Mozilla Public License 2.0（MPL-2.0）で配布される
      （出典: requirements-dev.txt 行7-18、`hypothesis==6.158.0`、
      `pip show hypothesis` の License-Expression = MPL-2.0）。
      ※ tasks.md 行16 および design.md 行451 は「BSD」と記載するが事実と相違する
        （出典: requirements-dev.txt 行12 の訂正注記）。本テストは事実に基づき
        MPL-2.0 を採用ライセンスとして明記する。
    - django-csp（`csp` パッケージ）は本プロジェクトの既存依存であり、本テストで
      新規導入する外部資産ではない（出典: config/settings/base.py の
      `from csp import constants as csp_constants`、INSTALLED_APPS の `'csp'`）。
      `csp/__init__.py` は空、`csp/constants.py` は標準ライブラリのみに依存し
      Django をロードしない（出典: .venv 内 csp パッケージ実装の確認）。

テスト方針（出典: design.md「Testing Strategy」、兄弟テスト contact_function/tests/）:
    - 単一プロパティを 1 テストで実装し、最小 100 反復（@settings(max_examples=100)）。
    - 検証対象 `_csp_hash.py` は Django 非依存のため Django をロードしない。
    - フォールバック禁止: 期待を明示アサートし、問題を握りつぶさない。
    - 期待ハッシュはテスト内で hashlib / base64 により独立算出し、実装の hash_source
      を再利用しない（同一関数による同語反復を避け、R7-2 の算出仕様を独立に検証する）。
    - インライン内容は '<' を含まない文字集合で生成する。'<' を除けば html.parser の
      CDATA（script/style の生内容）が途中終了せず往復一致するため、抽出後の内容から
      算出したハッシュがテストの独立算出値と厳密に一致する（出典: _csp_hash.py
      `_InlineTagCollector` と html.parser の CDATA_CONTENT_ELEMENTS 挙動）。

実行コマンド（プロジェクトルートから、Django 非ロード）:
    python -m unittest portfolio.tests.test_property_csp_hash -v
"""

from __future__ import annotations

import base64
import hashlib
import string
import unittest

from csp.constants import NONCE
from hypothesis import given, settings
from hypothesis import strategies as st

from portfolio.management.commands._csp_hash import generate_csp_header

# インライン内容に用いる安全な文字集合。'<' はタグ開始とみなされ CDATA を途中終了
# させ得るため除外する（'<' が無ければ html.parser は script/style 内容を変換せず
# 生のまま渡し、抽出内容が生成入力と往復一致する）。'\r' は改行正規化の曖昧さを避け
# るため除外し、'\n' / '\t' / 半角空白は含めて空白系の内容も網羅する。
_INLINE_ALPHABET = (
    string.ascii_letters
    + string.digits
    + " \t\n"
    + "!#$%&()*+,-./:;=>?@[]^_{|}~'\"\\"
)

# per-request nonce ソース `'nonce-<base64>'` の base64 部分に用いる文字集合
# （標準 base64 のアルファベット。実際の nonce 値の表現に近づける）。
_NONCE_BODY_ALPHABET = string.ascii_letters + string.digits + "+/="

# CloudFront ドメインに用いる文字集合（英小文字・数字・ドット・ハイフン）。ドメイン
# 値は Property 5 の検証対象ではないが、build_csp_directives が非空を要求するため
# 非空文字列を生成して入力空間に変化を与える（出典: _csp_hash.build_csp_directives）。
_DOMAIN_ALPHABET = string.ascii_lowercase + string.digits + ".-"

# nonce 相当がヘッダ値へ漏出していないことを判定するための照合パターン（小文字比較）。
# per-request nonce ソースの接頭辞（先頭の単一引用符を含むため 'self' や 'none' 等の
# 他キーワードや `'sha256-...'`・ドメイン値と誤衝突しない）。
_NONCE_SOURCE_PREFIX = "'nonce-"
# django-csp センチネル `csp.constants.NONCE` の repr 文字列（小文字化して照合）。
_NONCE_SENTINEL_REPR_LOWER = "csp.constants.nonce"


def _inline_text() -> st.SearchStrategy[str]:
    """往復一致する非空のインライン内容（script/style のテキスト）を生成する.

    Returns:
        SearchStrategy[str]: '<' を含まない非空文字列（最大 200 文字）。
    """
    # 空内容は _csp_hash が認可対象外として収集しないため min_size=1 とする。
    return st.text(alphabet=_INLINE_ALPHABET, min_size=1, max_size=200)


def _nonce_source() -> st.SearchStrategy[str]:
    """per-request nonce ソース `'nonce-<base64>'` を生成する.

    Returns:
        SearchStrategy[str]: base.py が保持する nonce と同形式のソース文字列。
    """
    # base64 本体を非空で生成し、CSP の nonce ソース構文へ整形する。
    body = st.text(alphabet=_NONCE_BODY_ALPHABET, min_size=1, max_size=32)
    return st.builds(lambda b: f"'nonce-{b}'", body)


def _cloudfront_domain() -> st.SearchStrategy[str]:
    """非空の CloudFront ドメイン文字列を生成する.

    Returns:
        SearchStrategy[str]: 英小文字・数字・ドット・ハイフンから成る非空文字列。
    """
    # build_csp_directives は空ドメインを ValueError で拒否するため min_size=1。
    return st.text(alphabet=_DOMAIN_ALPHABET, min_size=1, max_size=40)


@st.composite
def _csp_scenario(
    draw: st.DrawFn,
) -> tuple[list[str], list[str], str, str]:
    """CSP 生成の検証シナリオ（インライン内容・nonce ソース・ドメイン）を生成する.

    Args:
        draw: Hypothesis の draw 関数。

    Returns:
        tuple: (インライン script 内容列, インライン style 内容列, nonce ソース,
            CloudFront ドメイン)。内容列は空（インライン無し）も許容し、nonce 不在の
            エッジ（ハッシュ付与無し）も網羅する。
    """
    # script / style 内容は 0〜4 件（空リスト＝インライン無しのエッジも含める）。
    scripts = draw(st.lists(_inline_text(), min_size=0, max_size=4))
    styles = draw(st.lists(_inline_text(), min_size=0, max_size=4))
    # base_directives に混入させる per-request nonce ソース（除去対象）。
    nonce_source = draw(_nonce_source())
    # CloudFront ドメイン（非空）。
    cloudfront_domain = draw(_cloudfront_domain())
    return scripts, styles, nonce_source, cloudfront_domain


def _build_html(scripts: list[str], styles: list[str]) -> str:
    """インライン script / style を埋め込んだ HTML 文字列を構築する.

    各内容を個別の `<script>` / `<style>` 要素として直列に埋め込む（要素間の結合を
    避けるため 1 内容 1 要素とする）。内容は '<' を含まないため CDATA が途中終了せず
    往復一致する。

    Args:
        scripts: インライン script 内容列。
        styles: インライン style 内容列。

    Returns:
        str: インライン要素を含む HTML 文字列。
    """
    parts: list[str] = []
    # インライン script を個別要素として埋め込む。
    for content in scripts:
        parts.append(f"<script>{content}</script>")
    # インライン style を個別要素として埋め込む。
    for content in styles:
        parts.append(f"<style>{content}</style>")
    return (
        "<!doctype html><html><head></head><body>"
        + "".join(parts)
        + "</body></html>"
    )


def _base_directives(nonce_source: str) -> dict[str, list[object]]:
    """base.py の CSP ディレクティブを模した入力を構築する（nonce 相当を含む）.

    config/settings/base.py の `CONTENT_SECURITY_POLICY.DIRECTIVES`（出典: 行181-223）
    を模し、script/style 系ディレクティブへ実センチネル `NONCE` と `'nonce-...'`
    ソースの双方を含める。これにより generate_csp_header が 2 種類の per-request nonce
    表現をいずれも除去することを検証できる（R7-2）。

    Args:
        nonce_source: 混入させる `'nonce-<base64>'` 形式のソース。

    Returns:
        dict[str, list[object]]: ディレクティブ名からソース列（nonce 相当を含む）。
    """
    return {
        "default-src": ["'self'", "https:"],
        "script-src": ["'self'", "https://cdn.jsdelivr.net", NONCE, nonce_source],
        "script-src-elem": ["'self'", "https://use.fontawesome.com", NONCE],
        "style-src": ["'self'", "https://fonts.googleapis.com", NONCE, nonce_source],
        "style-src-elem": ["'self'", "https://cdn.jsdelivr.net", NONCE],
        "font-src": ["'self'"],
        "img-src": ["'self'", "data:"],
        "object-src": ["'none'"],
        "base-uri": ["'self'"],
        "frame-src": ["'none'"],
        "frame-ancestors": ["'none'"],
        "report-uri": ["/csp-report-endpoint"],
    }


def _expected_hash_source(content: str) -> str:
    """インライン内容の CSP ハッシュソース `'sha256-<base64>'` を独立に算出する.

    実装の hash_source を用いず、テスト内で hashlib / base64 により算出する
    （同一関数による同語反復を避け、R7-2 の算出仕様を独立に検証する）。

    Args:
        content: インライン内容（UTF-8 前提）。

    Returns:
        str: `'sha256-<base64>'` 形式のハッシュソース。
    """
    # UTF-8 バイト列の SHA-256 を base64 エンコードし CSP ソース構文へ整形する。
    digest = hashlib.sha256(content.encode("utf-8")).digest()
    return "'sha256-" + base64.b64encode(digest).decode("ascii") + "'"


class CspHashGenerationProperty(unittest.TestCase):
    """Property 5 のプロパティテストを保持するテストケース."""

    # 最小 100 反復（出典: tasks.md 4.2「100+ 反復」、design「PBT」）。生成データに
    # よる per-example 締切超過の誤検知を避けるため deadline を無効化する（検証は
    # 決定的でありエラーは握りつぶさない）。
    @settings(max_examples=100, deadline=None)
    @given(scenario=_csp_scenario())
    def test_csp_excludes_nonce_and_includes_inline_sha256(
        self, scenario: tuple[list[str], list[str], str, str]
    ) -> None:
        """Feature: cost-performance-optimization, Property 5: CSP ハッシュ生成は nonce を含まずインラインの SHA-256 を含む

        Validates: Requirements 7.2

        任意のインライン `<script>` / `<style>` 内容について、生成 CSP が
        (a) per-request nonce 相当（`csp.constants.NONCE` センチネルおよび
        `'nonce-...'` ソース）を一切含まず、(b) 各インライン内容の `'sha256-...'`
        を含むことを検証する（出典: requirements.md R7-2、_csp_hash.generate_csp_header）。
        """
        # シナリオを分解する（script 内容・style 内容・nonce ソース・ドメイン）。
        scripts, styles, nonce_source, cloudfront_domain = scenario

        # インライン内容を埋め込んだ HTML と nonce 相当を含む base_directives を用意する。
        html = _build_html(scripts, styles)
        base_directives = _base_directives(nonce_source)

        # 検証対象: HTML と現行ディレクティブから CSP ヘッダ値を生成する。
        csp = generate_csp_header(html, base_directives, cloudfront_domain)

        # 大小無視で照合するため小文字化した比較用文字列を用意する。
        lowered = csp.lower()

        # (a1) per-request nonce ソース `'nonce-...'` を含まないこと（R7-2）。
        self.assertNotIn(
            _NONCE_SOURCE_PREFIX,
            lowered,
            msg=f"生成 CSP に per-request nonce ソースが残存している: {csp!r}",
        )
        # (a2) django-csp センチネル `csp.constants.NONCE` の repr が漏出しないこと（R7-2）。
        self.assertNotIn(
            _NONCE_SENTINEL_REPR_LOWER,
            lowered,
            msg=f"生成 CSP に nonce センチネル repr が漏出している: {csp!r}",
        )

        # (b) 各インライン内容（script/style の重複排除集合）の `'sha256-...'` を含むこと。
        for content in set(scripts) | set(styles):
            expected = _expected_hash_source(content)
            self.assertIn(
                expected,
                csp,
                msg=(
                    f"インライン内容 {content!r} のハッシュ {expected} が"
                    f"生成 CSP に含まれていない: {csp!r}"
                ),
            )


if __name__ == "__main__":
    # 単体実行用エントリ（`python -m unittest` による探索でも実行可能）。
    unittest.main()
