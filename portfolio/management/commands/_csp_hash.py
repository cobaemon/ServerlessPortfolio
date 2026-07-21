"""静的配信ページ向けハッシュベース CSP を生成する純粋関数モジュール.

本モジュールは、ビルド時に事前レンダリングされた表示ページ（Prerendered_Page）の
HTML からインライン `<script>` / `<style>` の内容を抽出し、その SHA-256 を
base64 エンコードした CSP ハッシュソース（`'sha256-...'`）を算出して、
`script-src(-elem)` / `style-src(-elem)` へ反映した Content-Security-Policy を
組み立てる（出典: design.md「Components > C6. CSP ハッシュ生成」、
requirements.md R7-2, R7-5, R7-6）。

設計上の位置づけ（出典: design.md C5/C6、requirements.md R7）:
    - 静的配信では Django の per-request nonce を発行できないため、nonce を廃し
      ビルド時ハッシュへ置換する（R7-2）。生成される CSP は
      `csp_constants.NONCE` 相当の per-request nonce 値を一切含めない。
    - 許可元（配信元）は現行 `config/settings/base.py` の
      `CONTENT_SECURITY_POLICY.DIRECTIVES` と、`config/settings/prod.py` が
      追記する CloudFront ドメインを包含し、現行で許可されていない配信元を
      新規に緩和しない（R7-5）。本モジュールが新規に加える配信元は
      「インライン内容の `'sha256-...'`」と「CloudFront ドメイン」のみである。

実装方針（出典: 本タスク制約、principles.md 第三原則）:
    - すべて副作用の無い純粋関数として実装する（I/O・グローバル状態を持たない）。
    - Django・django-csp を import しない（Django 非依存）。標準ライブラリ
      （hashlib / base64 / html.parser）のみで実装する。
    - フォールバック禁止。想定外の入力（空の CloudFront ドメイン、CSP ソースに
      現れ得ない非文字列トークン）はエラーを握りつぶさず明示的に例外送出する。

なお本モジュールはビルド用ヘルパーであり Django の管理コマンドではないため、
ファイル名を `_` 始まりとして `BaseCommand` 自動探索の対象外にしている（出典:
Django management command のローダはコマンドモジュールのみを探索する）。
"""

import base64
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser

# prod.py が CloudFront ドメイン（`https://<AWS_S3_CUSTOM_DOMAIN>`）を追記する
# ディレクティブ集合（出典: config/settings/prod.py の CSP 追記ロジック。
# `default-src` / `script-src` / `script-src-elem` / `style-src` /
# `style-src-elem` / `font-src` / `img-src` へ `.setdefault(...).append(...)`）。
# 本モジュールは静的配信向けに prod.py と同等の許可元集合を再現する。
_CLOUDFRONT_DOMAIN_DIRECTIVES: tuple[str, ...] = (
    "default-src",
    "script-src",
    "script-src-elem",
    "style-src",
    "style-src-elem",
    "font-src",
    "img-src",
)

# インライン `<script>` のハッシュを反映するディレクティブ（出典: design.md C6
# 表「script-src / script-src-elem」、base.py の該当ディレクティブ）。
_SCRIPT_DIRECTIVES: tuple[str, ...] = ("script-src", "script-src-elem")

# インライン `<style>` のハッシュを反映するディレクティブ（出典: design.md C6
# 表「style-src / style-src-elem」、base.py の該当ディレクティブ）。
_STYLE_DIRECTIVES: tuple[str, ...] = ("style-src", "style-src-elem")

# django-csp の per-request nonce センチネル（`csp.constants.NONCE`、単一
# インスタンスの `csp.constants.Nonce`）の repr 表現（出典: django-csp 4.0 の
# `csp.constants.Nonce.__repr__`）。本モジュールは csp を import しないため、
# repr と型名で構造的に判定して除去する（R7-2: nonce 相当を含めない）。
_NONCE_SENTINEL_REPR = "csp.constants.NONCE"


@dataclass(frozen=True, slots=True)
class InlineContents:
    """HTML から抽出したインライン内容を保持する不変オブジェクト.

    Attributes:
        scripts: インライン `<script>`（`src` 属性を持たない）のテキスト内容を
            出現順に並べた列。
        styles: インライン `<style>` のテキスト内容を出現順に並べた列。
    """

    # インライン script の内容（抽出した生テキスト、UTF-8 前提）。
    scripts: tuple[str, ...]
    # インライン style の内容（抽出した生テキスト、UTF-8 前提）。
    styles: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InlineHashes:
    """インライン内容から算出した CSP ハッシュソースを保持する不変オブジェクト.

    Attributes:
        scripts: インライン `<script>` 内容の `'sha256-...'` を重複排除し
            出現順に並べた列。
        styles: インライン `<style>` 内容の `'sha256-...'` を重複排除し
            出現順に並べた列。
    """

    # script 用ハッシュソース（`'sha256-<base64>'`）。
    scripts: tuple[str, ...]
    # style 用ハッシュソース（`'sha256-<base64>'`）。
    styles: tuple[str, ...]


class _InlineTagCollector(HTMLParser):
    """インライン `<script>` / `<style>` の内容を収集する内部パーサ.

    標準ライブラリ `html.parser.HTMLParser` を用いる。`script` / `style` は
    CDATA 相当として扱われ、`handle_data` に実体参照変換前の生テキストが
    渡されるため、ブラウザが CSP ハッシュ計算に用いるバイト列と一致する
    （出典: CPython `html.parser` の CDATA_CONTENT_ELEMENTS 挙動）。

    `src` 属性を持つ `<script>` は外部スクリプト（インラインではない）ため
    内容抽出の対象外とする（出典: design.md C6「インライン」限定）。
    """

    def __init__(self) -> None:
        """収集用バッファと状態を初期化する."""
        # convert_charrefs は既定 True。script/style は CDATA 扱いのため
        # いずれにせよ内容は変換されないが、明示的に既定へ委ねる。
        super().__init__()
        # 抽出したインライン script 内容（出現順）。
        self.scripts: list[str] = []
        # 抽出したインライン style 内容（出現順）。
        self.styles: list[str] = []
        # 現在キャプチャ中の対象タグ名（"script" / "style"）。対象外は None。
        self._active_tag: str | None = None
        # 現在の対象要素が収集対象か（外部 script は False）。
        self._capture: bool = False
        # 現在の対象要素のテキスト断片を貯めるバッファ。
        self._buffer: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        """開始タグを検出し、インライン対象要素のキャプチャを開始する.

        Args:
            tag: 小文字化された開始タグ名。
            attrs: 属性名と値の組の一覧。
        """
        # 対象は script / style のみ。
        if tag not in ("script", "style"):
            return
        # 現在の対象タグとバッファを設定する。
        self._active_tag = tag
        self._buffer = []
        if tag == "script":
            # src 属性を持つ script は外部参照でありインライン内容が無いため、
            # 収集対象外とする（出典: design.md C6）。
            has_src = any(name.lower() == "src" for name, _ in attrs)
            self._capture = not has_src
        else:
            # style は常にインライン。
            self._capture = True

    def handle_data(self, data: str) -> None:
        """対象要素内のテキストを収集する.

        Args:
            data: タグ内の生テキスト断片。
        """
        # 対象要素をキャプチャ中の場合のみ貯める。
        if self._active_tag is not None and self._capture:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        """終了タグを検出し、収集した内容を確定する.

        Args:
            tag: 小文字化された終了タグ名。
        """
        # 現在キャプチャ中の対象要素の終了時のみ確定する。
        if tag != self._active_tag:
            return
        if self._capture:
            # 断片を連結して 1 要素分の内容とする。空要素（内容なし）は
            # 認可すべきインラインコードが無いため収集しない。
            content = "".join(self._buffer)
            if content != "":
                if tag == "script":
                    self.scripts.append(content)
                else:
                    self.styles.append(content)
        # 状態をリセットする。
        self._active_tag = None
        self._capture = False
        self._buffer = []


def extract_inline_contents(html: str) -> InlineContents:
    """HTML からインライン `<script>` / `<style>` の内容を抽出する純粋関数.

    `src` 属性を持たない `<script>`（インライン）と、すべての `<style>` の
    テキスト内容を出現順に抽出する。内容が空の要素は認可対象のインラインコードが
    無いため抽出しない（出典: design.md C6）。

    Args:
        html: 対象の Prerendered_Page の HTML 文字列（UTF-8 前提）。

    Returns:
        InlineContents: 抽出したインライン script / style 内容。

    Raises:
        TypeError: `html` が文字列でない場合（フォールバック禁止・明示失敗）。
    """
    # ゼロトラスト検証: 文字列以外は不正入力として明示的に失敗させる。
    if not isinstance(html, str):
        raise TypeError(f"html は str である必要があります: {type(html)!r}")
    # パーサへ入力し、収集結果を不変オブジェクトへ変換して返す。
    collector = _InlineTagCollector()
    collector.feed(html)
    collector.close()
    return InlineContents(
        scripts=tuple(collector.scripts),
        styles=tuple(collector.styles),
    )


def hash_source(content: str) -> str:
    """インライン内容から CSP ハッシュソース `'sha256-<base64>'` を算出する純粋関数.

    内容を UTF-8 でエンコードし、その SHA-256 ダイジェストを base64 エンコードして
    CSP のハッシュソース構文（前後の単一引用符を含む）へ整形する（出典: design.md
    C6 手順 2、requirements.md R7-2）。

    Args:
        content: インライン `<script>` / `<style>` のテキスト内容。

    Returns:
        str: `'sha256-<base64>'` 形式のハッシュソース。

    Raises:
        TypeError: `content` が文字列でない場合（フォールバック禁止・明示失敗）。
    """
    # ゼロトラスト検証: 文字列以外は不正入力として明示的に失敗させる。
    if not isinstance(content, str):
        raise TypeError(f"content は str である必要があります: {type(content)!r}")
    # UTF-8 バイト列の SHA-256 を base64 エンコードする（出典: R7-2）。
    digest = hashlib.sha256(content.encode("utf-8")).digest()
    encoded = base64.b64encode(digest).decode("ascii")
    return f"'sha256-{encoded}'"


def _dedupe_preserving_order(values: Sequence[str]) -> tuple[str, ...]:
    """出現順を保ちつつ重複を排除する内部ヘルパー.

    Args:
        values: 対象の文字列列。

    Returns:
        tuple[str, ...]: 重複を除いた出現順の列。
    """
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return tuple(seen)


def compute_inline_hashes(contents: InlineContents) -> InlineHashes:
    """インライン内容集合から CSP ハッシュソース集合を算出する純粋関数.

    同一内容が複数存在する場合はハッシュも同一になるため、出現順を保ちつつ
    重複を排除する（CSP 上は同一ソースの重複を持たない）。

    Args:
        contents: `extract_inline_contents` が返すインライン内容。

    Returns:
        InlineHashes: script / style それぞれのハッシュソース集合。
    """
    # 各内容をハッシュソースへ変換し、重複排除する。
    script_hashes = _dedupe_preserving_order(
        [hash_source(content) for content in contents.scripts]
    )
    style_hashes = _dedupe_preserving_order(
        [hash_source(content) for content in contents.styles]
    )
    return InlineHashes(scripts=script_hashes, styles=style_hashes)


def _is_nonce_token(token: object) -> bool:
    """トークンが per-request nonce 相当か（除去対象か）を判定する内部ヘルパー.

    django-csp の `NONCE` センチネル（`csp.constants.Nonce`）と、`'nonce-...'`
    形式の nonce ソース文字列を per-request nonce 相当として検出する（出典:
    requirements.md R7-2「nonce 値を含めない」、django-csp 4.0 の Nonce 表現）。

    Args:
        token: CSP ソースのトークン（文字列または django-csp のセンチネル）。

    Returns:
        bool: nonce 相当であれば True。
    """
    # csp を import せず、型名と repr で構造的にセンチネルを検出する。
    if type(token).__name__ == "Nonce" or repr(token) == _NONCE_SENTINEL_REPR:
        return True
    # 念のため、'nonce-...' 形式の文字列ソースも per-request nonce 相当として除去。
    if isinstance(token, str) and token.strip().lower().startswith("'nonce-"):
        return True
    return False


def _strip_nonce(sources: Sequence[object]) -> list[str]:
    """1 ディレクティブのソース列から nonce 相当を除去し文字列列へ正規化する.

    nonce 相当（django-csp センチネル・`'nonce-...'`）は除去する。それ以外の
    非文字列トークンは CSP ソースとして想定外であり、握りつぶさず明示的に
    例外送出する（フォールバック禁止、出典: principles.md 第三原則3）。

    Args:
        sources: 1 ディレクティブ分のソース列（文字列または nonce センチネル）。

    Returns:
        list[str]: nonce を除去した文字列ソースの列（順序保持）。

    Raises:
        TypeError: nonce 以外の非文字列トークンが含まれる場合。
    """
    result: list[str] = []
    for token in sources:
        # per-request nonce 相当は除去する（R7-2）。
        if _is_nonce_token(token):
            continue
        # nonce 以外の非文字列は想定外。明示的に失敗させる。
        if not isinstance(token, str):
            raise TypeError(
                f"CSP ソースに想定外の非文字列トークンが含まれます: {token!r}"
            )
        result.append(token)
    return result


def build_csp_directives(
    base_directives: Mapping[str, Sequence[object]],
    cloudfront_domain: str,
    inline_hashes: InlineHashes,
) -> dict[str, tuple[str, ...]]:
    """現行許可元を包含したハッシュベース CSP ディレクティブを組み立てる純粋関数.

    現行 `config/settings/base.py` の `CONTENT_SECURITY_POLICY.DIRECTIVES` を
    出典（`base_directives`）として受け取り、次の変換を施す（出典: design.md C6、
    requirements.md R7-2, R7-5）:
        1. すべてのディレクティブから per-request nonce 相当を除去する（R7-2）。
        2. prod.py と同等に、CloudFront ドメイン（`https://<domain>`）を所定の
           ディレクティブへ追加する（出典: config/settings/prod.py）。
        3. インライン内容の `'sha256-...'` を `script-src(-elem)` /
           `style-src(-elem)` へ追加する（R7-2）。

    追加される配信元は「CloudFront ドメイン」と「`'sha256-...'`」のみであり、
    現行で許可されていない配信元を新規に緩和しない（R7-5）。追加は冪等であり、
    既に存在するソースを重複させない。したがって `base_directives` に base.py の
    ディレクティブ（CloudFront ドメイン未追記）を渡しても、prod.py 実効の
    ディレクティブ（CloudFront ドメイン追記済み）を渡しても同一の結果になる。

    Args:
        base_directives: 現行 CSP ディレクティブ（ディレクティブ名→ソース列）。
            nonce センチネルを含み得る。
        cloudfront_domain: CloudFront 配信ドメイン（`AWS_S3_CUSTOM_DOMAIN` 相当。
            例: `static.example.com`）。`https://` は付けない。
        inline_hashes: インライン内容から算出したハッシュソース集合。

    Returns:
        dict[str, tuple[str, ...]]: ディレクティブ名から正規化済みソース列への
            順序保持マッピング。

    Raises:
        ValueError: `cloudfront_domain` が空（フォールバック禁止・明示失敗）。
        TypeError: ソースに nonce 以外の非文字列トークンが含まれる場合。
    """
    # ゼロトラスト検証: CloudFront ドメイン欠落はフォールバックせず明示失敗させる
    # （出典: 第三原則3、prod.py の ImproperlyConfigured パターンに整合）。
    if not isinstance(cloudfront_domain, str) or cloudfront_domain.strip() == "":
        raise ValueError("cloudfront_domain は空にできません")

    # prod.py と同一の CSP ソース表現（`https://<domain>`）を構築する
    # （出典: config/settings/prod.py の `_STATIC_DOMAIN`）。
    cloudfront_source = f"https://{cloudfront_domain}"

    # 現行ディレクティブを順序保持でコピーしつつ nonce を除去する。
    directives: dict[str, list[str]] = {}
    for name, sources in base_directives.items():
        directives[name] = _strip_nonce(sources)

    # prod.py と同等に CloudFront ドメインを所定ディレクティブへ冪等追加する。
    # prod.py は setdefault で未定義ディレクティブを生成するため同挙動を再現する。
    for name in _CLOUDFRONT_DOMAIN_DIRECTIVES:
        bucket = directives.setdefault(name, [])
        if cloudfront_source not in bucket:
            bucket.append(cloudfront_source)

    # インライン script のハッシュを script 系ディレクティブへ冪等追加する。
    for name in _SCRIPT_DIRECTIVES:
        bucket = directives.setdefault(name, [])
        for source in inline_hashes.scripts:
            if source not in bucket:
                bucket.append(source)

    # インライン style のハッシュを style 系ディレクティブへ冪等追加する。
    for name in _STYLE_DIRECTIVES:
        bucket = directives.setdefault(name, [])
        for source in inline_hashes.styles:
            if source not in bucket:
                bucket.append(source)

    # 不変なタプルへ変換して返す。
    return {name: tuple(sources) for name, sources in directives.items()}


def render_csp_header_value(directives: Mapping[str, Sequence[str]]) -> str:
    """CSP ディレクティブ集合を Content-Security-Policy ヘッダ値へ整形する純粋関数.

    各ディレクティブを `名前 ソース1 ソース2 ...` の形式にし、`; ` で連結する。
    ソースの順序・ディレクティブの順序は入力の順序を保持し、結果を決定的にする。

    Args:
        directives: ディレクティブ名からソース列へのマッピング。

    Returns:
        str: `Content-Security-Policy` ヘッダの値。
    """
    parts: list[str] = []
    for name, sources in directives.items():
        if sources:
            # ソースを持つディレクティブは「名前 空白区切りソース」で表現する。
            parts.append(f"{name} {' '.join(sources)}")
        else:
            # ソースを持たないディレクティブ名のみのケース（現状は非該当）。
            parts.append(name)
    return "; ".join(parts)


def generate_csp_header(
    html: str,
    base_directives: Mapping[str, Sequence[object]],
    cloudfront_domain: str,
) -> str:
    """HTML から静的配信用のハッシュベース CSP ヘッダ値を生成する純粋関数.

    `extract_inline_contents` → `compute_inline_hashes` → `build_csp_directives`
    → `render_csp_header_value` を合成した最上位のエントリポイント（出典:
    design.md C6 手順 1〜4）。生成結果は per-request nonce を含まず、現行許可元と
    CloudFront ドメインを包含し、インライン内容の `'sha256-...'` を含む
    （requirements.md R7-2, R7-5）。

    Args:
        html: 対象 Prerendered_Page の HTML 文字列（UTF-8 前提）。
        base_directives: 現行 CSP ディレクティブ（base.py 出典。nonce を含み得る）。
        cloudfront_domain: CloudFront 配信ドメイン（`https://` は付けない）。

    Returns:
        str: `Content-Security-Policy` ヘッダの値。
    """
    # インライン内容を抽出し、ハッシュソースを算出し、ディレクティブを組み立てる。
    contents = extract_inline_contents(html)
    inline_hashes = compute_inline_hashes(contents)
    directives = build_csp_directives(base_directives, cloudfront_domain, inline_hashes)
    return render_csp_header_value(directives)
