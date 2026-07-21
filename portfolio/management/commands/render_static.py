"""表示ページ（`/portfolio/top/`）を 7 言語分フルページ静的化する管理コマンド.

本コマンドは、Django on Lambda を経由せずに表示ページを配信する「静的ファースト配信」
（Static_Delivery_System）のためのビルド時成果物を生成する（出典: design.md
「Components > C2. Prerender_Command」「C1. Static_Delivery_System」、requirements.md
R3-1, R3-5）。

処理概要（出典: design.md C2, DM5、本サブタスク 4.4 制約）:
    1. `settings.LANGUAGES`（ja, en, fr, es, ru, zh-hans, ar）の各言語について
       `django.utils.translation.override` で言語を有効化し、Top ビューが使用する
       テンプレート `index.html`（`portfolio_base.html` を継承）を
       `render_to_string` でレンダリングする（出典: portfolio/views.py の
       `Top.template_name = 'index.html'` と `get_context_data` の `form` 供給）。
    2. 言語別出力 `<STATIC_ROOT>/<lang>/portfolio/top/index.html` を生成する
       （DM5 パス設計）。
    3. ルート `index.html` は既定言語 `settings.LANGUAGE_CODE`（= 'ja'）の
       フルページを複製生成する（CloudFront `DefaultRootObject: index.html` 整合。
       ルート言語はユーザー確認により既定言語複製と確定。出典: base.py
       `LANGUAGE_CODE = 'ja'`）。
    4. 各ページのハッシュベース CSP ヘッダ値とインライン `'sha256-...'` を
       `_csp_hash` モジュールで算出し、生成物一覧とともにマニフェストへ記録する
       （出典: design.md C6, DM5、requirements.md R7-2, R7-5）。

フォールバック禁止（出典: principles.md 第三原則3、requirements.md R3-6）:
    - いずれかの言語でレンダリングに失敗した場合は `CommandError` を送出して
      非ゼロ終了し、ビルドを失敗させる。
    - 全言語＋ルートのレンダリングが成功して初めてファイルを書き出す
      （二段階方式）。これにより部分的な出力を残さず、既存の配信状態を保全する
      （部分同期しない、他言語での代替を行わない、R3-5, R3-6）。
    - CloudFront ドメインが設定されていない場合は握りつぶさず明示的に失敗させる
      （prod.py の `ImproperlyConfigured` パターンに整合、R6-7 の設計思想）。

外部モジュール・ライセンス（出典: principles.md 第二原則6）:
    - 標準ライブラリ（json, pathlib）と Django 標準機能（BaseCommand,
      render_to_string, translation）のみを使用し、追加の外部依存を導入しない。
    - CSP 生成は同一パッケージの `_csp_hash`（自作、Django 非依存の純粋関数群）を
      利用する。
"""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.template.loader import render_to_string
from django.utils import translation

from portfolio.forms import ContactForm

# 同一パッケージの CSP ハッシュ生成モジュール（サブタスク 4.1 実装済み）。
# `_` 始まりのためコマンド自動探索の対象外であり、明示 import で利用する
# （出典: portfolio/management/commands/_csp_hash.py の冒頭ドキュメント）。
from ._csp_hash import (
    compute_inline_hashes,
    extract_inline_contents,
    generate_csp_header,
)

# 静的化対象ページのテンプレート名（出典: portfolio/views.py `Top.template_name`）。
# `index.html` は `portfolio_base.html` を継承する（出典: portfolio/templates/index.html）。
_TARGET_TEMPLATE = "index.html"

# 言語別 Prerendered_Page の出力相対パス書式（出典: design.md DM5 パス設計
# `/<lang>/portfolio/top/index.html`）。
_LANG_PAGE_RELATIVE_FORMAT = "{lang}/portfolio/top/index.html"

# ルート成果物の相対パス（出典: design.md DM5、CloudFront `DefaultRootObject`）。
_ROOT_PAGE_RELATIVE = "index.html"

# CSP ハッシュ・生成物一覧を記録するマニフェストの相対パス（出典: 本サブタスク 4.4
# 「マニフェスト（CSP ハッシュ・生成物一覧）を生成する」）。
_MANIFEST_RELATIVE = "prerender_manifest.json"


class Command(BaseCommand):
    """7 言語の表示ページを事前レンダリングし CSP マニフェストを生成するコマンド."""

    # コマンドのヘルプ文（`python manage.py help render_static` に表示）。
    help = (
        "settings.LANGUAGES の各言語で表示ページ（/portfolio/top/）を"
        "事前レンダリングし、言語別 HTML・ルート index.html・CSP マニフェストを"
        "STATIC_ROOT へ生成する（Static_Delivery_System 用）。"
    )

    def handle(self, *args, **options):
        """コマンド本体. 7 言語＋ルートを生成し CSP マニフェストを書き出す.

        Args:
            *args: 位置引数（未使用）。
            **options: オプション引数（未使用）。

        Raises:
            CommandError: 対応言語が未設定、CloudFront ドメインが未設定、
                いずれかの言語のレンダリングに失敗、または書き出しに失敗した場合
                （フォールバック禁止・非ゼロ終了でビルドを失敗させる）。
        """
        # 出力先ルート（STATIC_ROOT）。collectstatic の成果物と同一ディレクトリ
        # （出典: base.py `STATIC_ROOT`、buildspec.yml の collectstatic→render_static）。
        output_root = Path(settings.STATIC_ROOT)

        # 対応言語一覧を settings.LANGUAGES から取得する（他言語代替なし、R3-5）。
        languages = self._resolve_languages()

        # 既定言語（ルート index.html の複製元）。settings.LANGUAGE_CODE を出典とし
        # 決めつけない（出典: base.py `LANGUAGE_CODE`、ユーザー確認による確定）。
        default_language = self._resolve_default_language(languages)

        # CloudFront 配信ドメイン。未設定はフォールバックせず明示失敗させる（R7-5）。
        cloudfront_domain = self._resolve_cloudfront_domain()

        # 現行 CSP ディレクティブ（base.py 出典、prod.py で CloudFront ドメイン追記済み
        # の場合もある）。generate_csp_header は冪等に扱う（出典: _csp_hash.py）。
        base_directives = self._resolve_base_directives()

        # --- 第 1 段階: 全言語＋ルートをメモリ上でレンダリングする ---
        # 途中失敗時にファイルを一切書き出さないため、先に全成果物を確定させる
        # （部分出力を残さない、R3-6・フォールバック禁止）。
        # 相対パス → HTML 文字列 の対応表。
        rendered_pages: dict[str, str] = {}
        # マニフェスト用のページメタ情報一覧。
        page_entries: list[dict[str, object]] = []

        for language in languages:
            # 対象言語を有効化してレンダリングする。失敗時は CommandError で中断。
            html = self._render_language_page(language)
            relative_path = _LANG_PAGE_RELATIVE_FORMAT.format(lang=language)
            rendered_pages[relative_path] = html
            # 当該ページの CSP ヘッダ値とインラインハッシュを算出しメタ情報へ記録。
            page_entries.append(
                self._build_page_entry(
                    language=language,
                    relative_path=relative_path,
                    role="language",
                    html=html,
                    base_directives=base_directives,
                    cloudfront_domain=cloudfront_domain,
                )
            )

        # ルート index.html は既定言語のフルページを複製する（同一内容を再利用）。
        default_relative = _LANG_PAGE_RELATIVE_FORMAT.format(lang=default_language)
        root_html = rendered_pages[default_relative]
        rendered_pages[_ROOT_PAGE_RELATIVE] = root_html
        page_entries.append(
            self._build_page_entry(
                language=default_language,
                relative_path=_ROOT_PAGE_RELATIVE,
                role="root",
                html=root_html,
                base_directives=base_directives,
                cloudfront_domain=cloudfront_domain,
            )
        )

        # マニフェスト（CSP ハッシュ・生成物一覧）を構築する（DM5）。
        manifest = {
            "default_language": default_language,
            "languages": list(languages),
            "cloudfront_domain": cloudfront_domain,
            "root_object": _ROOT_PAGE_RELATIVE,
            "target_page": "/portfolio/top/",
            "pages": page_entries,
        }

        # --- 第 2 段階: 全成果物が揃ったのでファイルへ書き出す ---
        # ここに到達した時点で全言語のレンダリングが成功している。
        self._write_outputs(output_root, rendered_pages, manifest)

        # 成功メッセージ（生成言語数とルートを明示）。
        self.stdout.write(
            self.style.SUCCESS(
                "Prerendered {n} languages ({langs}) + root index.html and "
                "CSP manifest into {root}".format(
                    n=len(languages),
                    langs=", ".join(languages),
                    root=output_root,
                )
            )
        )

    def _resolve_languages(self) -> tuple[str, ...]:
        """settings.LANGUAGES から対応言語コード一覧を取得する.

        Returns:
            tuple[str, ...]: 言語コードの列（例: ('ja', 'en', ...)）。

        Raises:
            CommandError: LANGUAGES が未設定または空の場合（フォールバック禁止）。
        """
        # settings.LANGUAGES は (code, name) のタプル列（出典: base.py `LANGUAGES`）。
        languages = getattr(settings, "LANGUAGES", None)
        if not languages:
            raise CommandError(
                "settings.LANGUAGES が未設定です。対応言語を確定できません。"
            )
        # 言語コードのみを抽出する。
        return tuple(code for code, _name in languages)

    def _resolve_default_language(self, languages: tuple[str, ...]) -> str:
        """ルート index.html の複製元となる既定言語を取得する.

        Args:
            languages: `_resolve_languages` が返す対応言語コード列。

        Returns:
            str: 既定言語コード（`settings.LANGUAGE_CODE`）。

        Raises:
            CommandError: LANGUAGE_CODE が未設定、または LANGUAGES に含まれない場合
                （整合性違反を握りつぶさず明示失敗させる）。
        """
        # 既定言語は settings.LANGUAGE_CODE を出典とする（決めつけない、base.py）。
        default_language = getattr(settings, "LANGUAGE_CODE", None)
        if not default_language:
            raise CommandError(
                "settings.LANGUAGE_CODE が未設定です。ルート index.html の"
                "複製元言語を確定できません。"
            )
        # 既定言語が対応言語一覧に含まれない構成矛盾は明示的に失敗させる。
        if default_language not in languages:
            raise CommandError(
                "settings.LANGUAGE_CODE={code} が settings.LANGUAGES に"
                "含まれていません。".format(code=default_language)
            )
        return default_language

    def _resolve_cloudfront_domain(self) -> str:
        """CSP に含める CloudFront 配信ドメインを設定から取得する.

        Returns:
            str: CloudFront ドメイン（`AWS_S3_CUSTOM_DOMAIN`。`https://` は含まない）。

        Raises:
            CommandError: 未設定または空の場合（フォールバック禁止・明示失敗。
                ハッシュベース CSP は現行許可元と CloudFront ドメインの包含が必須で
                あり、欠落したまま緩和・省略しないため。出典: R7-5、prod.py の
                `AWS_S3_CUSTOM_DOMAIN`）。
        """
        # prod.py が環境変数 CLOUDFRONT_DOMAIN_NAME から設定する値
        # （出典: config/settings/prod.py `AWS_S3_CUSTOM_DOMAIN`）。ハードコード禁止。
        cloudfront_domain = getattr(settings, "AWS_S3_CUSTOM_DOMAIN", None)
        if not cloudfront_domain:
            raise CommandError(
                "settings.AWS_S3_CUSTOM_DOMAIN が未設定です。CloudFront ドメインを"
                "包含したハッシュベース CSP を生成できないため中断します"
                "（環境変数 CLOUDFRONT_DOMAIN_NAME を設定してください）。"
            )
        return cloudfront_domain

    def _resolve_base_directives(self) -> dict:
        """現行 CSP ディレクティブ（出典）を settings から取得する.

        Returns:
            dict: `CONTENT_SECURITY_POLICY['DIRECTIVES']`（ディレクティブ名→ソース列）。

        Raises:
            CommandError: CSP 設定が存在しない場合（フォールバック禁止）。
        """
        # CSP の出典は base.py の CONTENT_SECURITY_POLICY.DIRECTIVES（R7-5）。
        policy = getattr(settings, "CONTENT_SECURITY_POLICY", None)
        if not policy or "DIRECTIVES" not in policy:
            raise CommandError(
                "settings.CONTENT_SECURITY_POLICY['DIRECTIVES'] が未設定です。"
                "CSP を生成できません。"
            )
        return policy["DIRECTIVES"]

    def _render_language_page(self, language: str) -> str:
        """指定言語で表示ページテンプレートをレンダリングする.

        Top ビューが供給するコンテキスト（`form`）を再現し、対象言語を有効化して
        `index.html` をレンダリングする（出典: portfolio/views.py `Top`）。

        Args:
            language: 有効化する言語コード（例: 'ja'）。

        Returns:
            str: レンダリング済み HTML 文字列。

        Raises:
            CommandError: レンダリングに失敗した場合。失敗言語を明示し、例外を
                握りつぶさず連鎖させる（フォールバック禁止、R3-6）。
        """
        try:
            # translation.override で対象言語のみ一時的に有効化し、確実に元へ戻す。
            with translation.override(language):
                # Top ビューと同じコンテキスト（未束縛の ContactForm）を供給する。
                context = {"form": ContactForm()}
                return render_to_string(_TARGET_TEMPLATE, context)
        except Exception as exc:
            # 失敗言語を明示してビルドを失敗させる（部分同期を防ぐ、R3-6）。
            raise CommandError(
                "言語 '{lang}' の Prerendered_Page 生成に失敗しました: {exc}".format(
                    lang=language, exc=exc
                )
            ) from exc

    def _build_page_entry(
        self,
        language: str,
        relative_path: str,
        role: str,
        html: str,
        base_directives: dict,
        cloudfront_domain: str,
    ) -> dict[str, object]:
        """1 ページ分のマニフェストエントリ（CSP・ハッシュ）を構築する.

        Args:
            language: 当該ページの言語コード。
            relative_path: STATIC_ROOT からの相対出力パス。
            role: 'language'（言語別ページ）または 'root'（ルート複製）。
            html: 当該ページの HTML。
            base_directives: 現行 CSP ディレクティブ（出典）。
            cloudfront_domain: CloudFront 配信ドメイン。

        Returns:
            dict[str, object]: マニフェストへ格納するページメタ情報。
        """
        # インライン script/style を抽出し、その `'sha256-...'` を算出する（DM5 記録用）。
        contents = extract_inline_contents(html)
        inline_hashes = compute_inline_hashes(contents)
        # ハッシュベース CSP ヘッダ値（nonce 除去済み・現行許可元＋CloudFront 包含）。
        csp_header_value = generate_csp_header(
            html, base_directives, cloudfront_domain
        )
        return {
            "language": language,
            "path": relative_path,
            "role": role,
            "content_security_policy": csp_header_value,
            "inline_script_hashes": list(inline_hashes.scripts),
            "inline_style_hashes": list(inline_hashes.styles),
        }

    def _write_outputs(
        self,
        output_root: Path,
        rendered_pages: dict[str, str],
        manifest: dict,
    ) -> None:
        """レンダリング済み全ページとマニフェストを STATIC_ROOT へ書き出す.

        本メソッドは全言語のレンダリング成功後にのみ呼ばれる（二段階方式）。
        非 ASCII 文字（ja, ar, ru, zh-hans 等）を保持するため UTF-8 で書き出す。

        Args:
            output_root: 出力先ルート（STATIC_ROOT）。
            rendered_pages: 相対パス→HTML の対応表。
            manifest: CSP ハッシュ・生成物一覧のマニフェスト。

        Raises:
            CommandError: ファイル書き出しに失敗した場合（握りつぶさない）。
        """
        try:
            # 各 HTML を対応する相対パスへ書き出す（親ディレクトリを作成）。
            for relative_path, html in rendered_pages.items():
                target = output_root / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(html, encoding="utf-8")

            # マニフェストを UTF-8・非 ASCII 保持の整形 JSON で書き出す。
            manifest_path = output_root / _MANIFEST_RELATIVE
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            # 書き出し失敗を握りつぶさず明示的に失敗させる（フォールバック禁止）。
            raise CommandError(
                "静的成果物の書き出しに失敗しました: {exc}".format(exc=exc)
            ) from exc
