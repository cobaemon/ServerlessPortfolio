"""Property 6（CSP 許可元は現行を包含し新規緩和がない）のプロパティテスト.

本モジュールは design.md「Correctness Properties > Property 6」および tasks.md 4.3 を
検証する（出典: tasks.md「4.3 CSP 許可元包含のプロパティテストを作成（新規緩和なし）」、
design.md「### Property 6: CSP 許可元は現行を包含し新規緩和がない」）。

    Property 6: CSP 許可元は現行を包含し新規緩和がない
    *For any* 生成された CSP ディレクティブ集合について、現行
    `config/settings/base.py` の `CONTENT_SECURITY_POLICY.DIRECTIVES` および
    `prod.py` が追記する CloudFront ドメインで許可されている配信元をすべて包含し、
    かつ現行で許可されていない配信元を新規に含まない（`'sha256-...'` ハッシュ追加
    および現行同等の CloudFront ドメイン追加を除く）。

検証対象（Validates: Requirements 7.5）:
    - R7-5: ハッシュベース CSP の許可元は現行 `CONTENT_SECURITY_POLICY.DIRECTIVES`
      （出典: config/settings/base.py, E-4）で許可している配信元と同等以上に整合し、
      現行で許可されていない配信元を新規に緩和しない（出典: requirements.md 要件7
      Acceptance Criteria 5）。

検証対象モジュール（tasks.md 4.1 実装、出典: portfolio/management/commands/_csp_hash.py）:
    - build_csp_directives(base_directives, cloudfront_domain, inline_hashes)
        -> dict[str, tuple[str, ...]]
      現行 CSP ディレクティブ（base.py 出典）から per-request nonce を除去し、
      prod.py と同等に CloudFront ドメイン（`https://<domain>`）を所定ディレクティブへ
      冪等追加し、インライン内容の `'sha256-...'` を script/style 系ディレクティブへ
      追加した、正規化済みディレクティブ集合を返す（出典: _csp_hash.build_csp_directives
      docstring、design.md C6）。

現行許可元の出典（source of truth・事実）:
    - base.py の `CONTENT_SECURITY_POLICY['DIRECTIVES']` を実際に import して基準とする
      （固定値のハードコードではなく現行設定そのものを参照する）。base.py は
      モジュールロード時に Django settings へアクセスしないため、Django のセットアップ
      なしで import 可能である（確認済み: `import config.settings.base`）。
      `csp_constants.NONCE`（per-request nonce センチネル）は配信元ではないため、
      現行許可「配信元」集合からは除外して比較する（R7-2 と整合）。
    - prod.py は CloudFront ドメイン `https://<AWS_S3_CUSTOM_DOMAIN>` を
      `default-src` / `script-src` / `script-src-elem` / `style-src` /
      `style-src-elem` / `font-src` / `img-src` へ追記する（出典:
      config/settings/prod.py の CSP 追記ロジック `_csp.setdefault(...).append(_STATIC_DOMAIN)`）。
      本テストは検証の独立性を保つため、この現行同等の対象ディレクティブ集合を
      実装の内部定数ではなく prod.py を出典として本テスト内に明示定義する
      （実装のバグを実装由来の定数で見逃さないため）。本テストでは CloudFront ドメインを
      任意生成し、その「現行同等の追加」が許容例外として扱われることを検証する。

ライセンス注記（第二原則6・要ライセンス確認）:
    - Hypothesis は Mozilla Public License 2.0（MPL-2.0）で配布される
      （出典: requirements-dev.txt 行9-18、`hypothesis==6.158.0`、
      公式リポジトリ LICENSE.txt）。
      ※ tasks.md 4.3 の指示文および design.md は「BSD」と記載するが、事実は
        MPL-2.0 であり相違する（出典: requirements-dev.txt の訂正注記）。本テストは
        事実に基づき MPL-2.0 を採用ライセンスとして明記する。非配布・非改変での
        開発・テスト利用のため、MPL-2.0 のソース開示義務の実務的対象外である。

テスト方針（出典: design.md「Testing Strategy」、兄弟テスト test_property_csp_hash.py）:
    - 単一プロパティを 1 テストで実装し、最小 100 反復（@settings(max_examples=100)）。
    - 検証対象 `_csp_hash.py` は Django 非依存のため Django をロードしない。基準となる
      base.py の CSP 辞書のみを import する（現行設定を事実として参照するため）。
    - フォールバック禁止: 期待を明示アサートし、問題を握りつぶさない。
    - インライン内容（script/style）を任意生成し、その `'sha256-...'` ハッシュソースを
      テスト内で hashlib / base64 により独立算出して InlineHashes を組み立てる
      （実装の hash_source を再利用せず、許容される新規追加を独立に定義する）。

実行コマンド（プロジェクトルートから）:
    python manage.py test portfolio.tests.test_property_csp_allowlist --verbosity=2
  もしくは（Django 非ロードでも実行可能）:
    python -m unittest portfolio.tests.test_property_csp_allowlist -v
"""

from __future__ import annotations

import base64
import hashlib
import string
import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

# 現行 CSP 許可元の source of truth（現行設定そのもの）を import する。
# base.py はロード時に Django settings へアクセスしないため直接 import できる。
from config.settings.base import CONTENT_SECURITY_POLICY
from portfolio.management.commands._csp_hash import (
    InlineHashes,
    build_csp_directives,
)

# prod.py が CloudFront ドメイン（`https://<AWS_S3_CUSTOM_DOMAIN>`）を追記する対象
# ディレクティブ集合（出典: config/settings/prod.py の CSP 追記ロジック
# `_csp.setdefault("default-src"/... ).append(_STATIC_DOMAIN)`）。検証の独立性を保つため
# 実装の内部定数ではなく prod.py を出典として本テストに明示定義する。
_PROD_CLOUDFRONT_DIRECTIVES: tuple[str, ...] = (
    "default-src",
    "script-src",
    "script-src-elem",
    "style-src",
    "style-src-elem",
    "font-src",
    "img-src",
)

# インライン内容に用いる文字集合。ここでは HTML 往復を経ず内容から直接ハッシュを
# 算出するため文字制約は不要だが、多様な入力（記号・空白・多バイト境界近傍）を与える
# ため広めの ASCII 記号と空白系を含める。
_INLINE_ALPHABET = (
    string.ascii_letters
    + string.digits
    + " \t\n"
    + "!#$%&()*+,-./:;<=>?@[]^_{|}~'\"\\"
)

# CloudFront ドメインに用いる文字集合（英小文字・数字・ドット・ハイフン）。
# build_csp_directives は非空ドメインを要求するため非空文字列を生成する
# （出典: _csp_hash.build_csp_directives の ValueError 検証）。
_DOMAIN_ALPHABET = string.ascii_lowercase + string.digits + ".-"

# CSP ハッシュソースの接頭辞（先頭の単一引用符を含む）。新規追加として許容される
# `'sha256-...'` を判定するために用いる（出典: R7-5 の許容例外）。
_SHA256_PREFIX = "'sha256-"


def _current_allowed_sources() -> dict[str, tuple[str, ...]]:
    """現行 base.py の CSP 許可「配信元」集合を出典から構築する.

    base.py の `CONTENT_SECURITY_POLICY['DIRECTIVES']` を基準に、各ディレクティブの
    文字列ソースのみを抽出する。`csp_constants.NONCE`（per-request nonce センチネル、
    非文字列）は配信元ではないため除外する（R7-2 と整合）。

    Returns:
        dict[str, tuple[str, ...]]: ディレクティブ名から現行許可「配信元」列への
            マッピング（nonce センチネルを除外済み）。
    """
    directives = CONTENT_SECURITY_POLICY["DIRECTIVES"]
    result: dict[str, tuple[str, ...]] = {}
    for name, sources in directives.items():
        # 文字列ソースのみを現行許可配信元とみなす（NONCE センチネルは非文字列）。
        result[name] = tuple(s for s in sources if isinstance(s, str))
    return result


def _inline_text() -> st.SearchStrategy[str]:
    """非空のインライン内容（script/style のテキスト）を生成する.

    Returns:
        SearchStrategy[str]: 非空文字列（最大 200 文字）。
    """
    # 空内容は _csp_hash が認可対象外として扱うため min_size=1 とする。
    return st.text(alphabet=_INLINE_ALPHABET, min_size=1, max_size=200)


def _cloudfront_domain() -> st.SearchStrategy[str]:
    """非空の CloudFront ドメイン文字列を生成する.

    Returns:
        SearchStrategy[str]: 英小文字・数字・ドット・ハイフンから成る非空文字列。
    """
    # build_csp_directives は空ドメインを ValueError で拒否するため min_size=1。
    return st.text(alphabet=_DOMAIN_ALPHABET, min_size=1, max_size=40)


def _hash_source(content: str) -> str:
    """インライン内容の CSP ハッシュソース `'sha256-<base64>'` を独立に算出する.

    実装の hash_source を用いず、テスト内で hashlib / base64 により算出する
    （実装と同語反復にならないよう、許容される新規追加を独立に定義する）。

    Args:
        content: インライン内容（UTF-8 前提）。

    Returns:
        str: `'sha256-<base64>'` 形式のハッシュソース。
    """
    digest = hashlib.sha256(content.encode("utf-8")).digest()
    return "'sha256-" + base64.b64encode(digest).decode("ascii") + "'"


@st.composite
def _allowlist_scenario(
    draw: st.DrawFn,
) -> tuple[list[str], list[str], str]:
    """CSP 許可元検証シナリオ（インライン内容・CloudFront ドメイン）を生成する.

    Args:
        draw: Hypothesis の draw 関数。

    Returns:
        tuple: (インライン script 内容列, インライン style 内容列, CloudFront ドメイン)。
            内容列は空（インライン無し＝ハッシュ追加無しのエッジ）も許容する。
    """
    # script / style 内容は 0〜4 件（空リスト＝ハッシュ追加無しのエッジも含める）。
    scripts = draw(st.lists(_inline_text(), min_size=0, max_size=4))
    styles = draw(st.lists(_inline_text(), min_size=0, max_size=4))
    # CloudFront ドメイン（非空）。
    cloudfront_domain = draw(_cloudfront_domain())
    return scripts, styles, cloudfront_domain


class CspAllowlistContainmentProperty(unittest.TestCase):
    """Property 6 のプロパティテストを保持するテストケース."""

    # 最小 100 反復（出典: tasks.md 4.3「100+ 反復」、design「PBT」）。生成データに
    # よる per-example 締切超過の誤検知を避けるため deadline を無効化する（検証は
    # 決定的でありエラーは握りつぶさない）。
    @settings(max_examples=100, deadline=None)
    @given(scenario=_allowlist_scenario())
    def test_csp_contains_current_sources_and_no_new_relaxation(
        self, scenario: tuple[list[str], list[str], str]
    ) -> None:
        """Feature: cost-performance-optimization, Property 6: CSP 許可元は現行を包含し新規緩和がない

        Validates: Requirements 7.5

        生成された CSP ディレクティブ集合について、(1) 現行 base.py の
        `CONTENT_SECURITY_POLICY.DIRECTIVES` の各配信元をすべて包含し、prod.py 同等の
        CloudFront ドメイン（`https://<domain>`）を所定ディレクティブへ含むこと（包含）、
        (2) いずれのディレクティブにも、現行許可配信元・CloudFront ドメイン同等・
        `'sha256-...'` ハッシュ以外の配信元を新規に含まないこと（新規緩和なし）を検証する
        （出典: requirements.md R7-5、_csp_hash.build_csp_directives）。
        """
        # シナリオを分解する（script 内容・style 内容・CloudFront ドメイン）。
        scripts, styles, cloudfront_domain = scenario

        # 現行許可配信元（source of truth）を出典 base.py から構築する。
        current_allowed = _current_allowed_sources()

        # 許容される新規追加を独立に定義する:
        #   (a) CloudFront ドメイン同等ソース（prod.py と同一表現 `https://<domain>`）。
        cloudfront_source = f"https://{cloudfront_domain}"
        #   (b) インライン内容の `'sha256-...'` ハッシュソース（独立算出）。
        script_hashes = tuple(_hash_source(c) for c in scripts)
        style_hashes = tuple(_hash_source(c) for c in styles)
        allowed_hash_sources = set(script_hashes) | set(style_hashes)

        # 検証対象: 現行ディレクティブ・CloudFront ドメイン・インラインハッシュから
        # 正規化済み CSP ディレクティブ集合を生成する。
        inline_hashes = InlineHashes(scripts=script_hashes, styles=style_hashes)
        generated = build_csp_directives(
            current_allowed, cloudfront_domain, inline_hashes
        )

        # ---- (1) 包含: 現行許可配信元をすべて含むこと ----
        for name, sources in current_allowed.items():
            generated_sources = generated.get(name)
            self.assertIsNotNone(
                generated_sources,
                msg=f"現行ディレクティブ {name!r} が生成結果から欠落している",
            )
            for source in sources:
                self.assertIn(
                    source,
                    generated_sources,
                    msg=(
                        f"現行許可配信元 {source!r} がディレクティブ {name!r} の"
                        f"生成結果に含まれていない: {generated_sources!r}"
                    ),
                )

        # ---- (1) 包含: prod.py 同等の CloudFront ドメインを所定ディレクティブへ含むこと ----
        for name in _PROD_CLOUDFRONT_DIRECTIVES:
            self.assertIn(
                cloudfront_source,
                generated.get(name, ()),
                msg=(
                    f"CloudFront ドメイン同等ソース {cloudfront_source!r} が"
                    f"ディレクティブ {name!r} に含まれていない: {generated.get(name)!r}"
                ),
            )

        # ---- (2) 新規緩和なし: 生成された各ソースが許容集合のいずれかに属すること ----
        # 許容集合 = 当該ディレクティブの現行許可配信元
        #            ∪ CloudFront ドメイン同等（現行同等の追加として許容）
        #            ∪ `'sha256-...'` ハッシュ（ハッシュ追加として許容）
        for name, generated_sources in generated.items():
            allowed_for_directive = set(current_allowed.get(name, ()))
            for source in generated_sources:
                is_current = source in allowed_for_directive
                is_cloudfront = source == cloudfront_source
                is_hash = source in allowed_hash_sources
                self.assertTrue(
                    is_current or is_cloudfront or is_hash,
                    msg=(
                        f"ディレクティブ {name!r} に現行未許可の新規配信元が含まれる: "
                        f"{source!r}（現行許可・CloudFront ドメイン同等・"
                        f"'sha256-...' のいずれでもない）: {generated_sources!r}"
                    ),
                )
                # `'sha256-...'` 接頭辞を持つソースは独立算出したハッシュ集合に一致する
                # こと（想定外のハッシュ源が混入していないことを追加検証する）。
                if source.startswith(_SHA256_PREFIX):
                    self.assertIn(
                        source,
                        allowed_hash_sources,
                        msg=(
                            f"ディレクティブ {name!r} に想定外の "
                            f"'sha256-...' ソースが含まれる: {source!r}"
                        ),
                    )


if __name__ == "__main__":
    # 単体実行用エントリ（`python -m unittest` による探索でも実行可能）。
    unittest.main()
