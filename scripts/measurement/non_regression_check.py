"""デプロイ後非退行検証スクリプト（R9-7）.

本モジュールは tasks.md 8.5 に対応し、cost-performance-optimization の最適化
（静的ファースト配信・脱 Django・SES 直連携・CSP のエッジ再配置）によって、
既存のセキュリティおよび多言語対応が退行していないことを検証する（出典:
tasks.md 8.5、design.md「Testing Strategy > 統合/スモーク/実測 > デプロイ後
非退行検証（R9-7）」、requirements.md R9-1/R9-2/R9-4/R9-5/R9-7、R7）。

検証項目（requirements.md R9-7 が列挙する維持対象）:
    1. HTTPS 強制・HTTP→HTTPS リダイレクト（R9-1）:
       `config/settings/prod.py` の `SECURE_SSL_REDIRECT = True`、および
       `template.yaml` CloudFront の全 Behavior が
       `ViewerProtocolPolicy: redirect-to-https` であること。
    2. S3 直アクセス禁止・CloudFront OAC 経由のみ（R9-2/R9-6）:
       `bucketpolicy.yaml` が CloudFront サービスプリンシパル＋`AWS:SourceArn`
       条件でのみ許可し、`dependencies.yaml` が PublicAccessBlock を全 true に
       する構成であること。
    3. 7 言語（ja, en, fr, es, ru, zh-hans, ar）表示ページ配信維持（R9-4）:
       `config/settings/base.py` の `LANGUAGES` が当該 7 言語であり、`locale/`
       に各言語のカタログディレクトリが存在すること。
    4. Contact_Payload 4 項目限定（R9-5）:
       `contact_function/domain/contact_payload.py` の `ContactPayload` が
       氏名・メール・電話番号・メッセージの 4 項目のみを保持すること。
    5. CSP 付与（R7）:
       `template.yaml` のセキュリティヘッダ用 ResponseHeadersPolicy が
       Content-Security-Policy を持ち、表示 Default Behavior に適用され、
       per-request nonce を含まない（ハッシュベース）こと。

検証境界と誠実性（第一原則・design.md「移行手順」）:
    本スクリプトは「デプロイされる構成（IaC・Django 設定・ドメインソース）が
    非退行の不変条件を維持しているか」を、認証情報・ネットワーク・Docker に
    依存せず決定的に検証する（ビルド検証段で実行可能）。実配信エンドポイントに
    対する実測（実 HTTP 応答の観測）は、DNS 切替を伴う運用手順であり本計画の
    コードタスク範囲外である（出典: design.md「移行手順」/Notes）。実測を
    行いたい場合は任意で `--base-url` を与えると、観測可能な項目（HTTPS
    リダイレクト・CSP ヘッダ）のみを追加検証する。実測を行わない場合、当該
    実配信次元は `undetermined` として明示記録する（決めつけない、フォール
    バック禁止、出典: requirements.md R9-7/R12、principles.md 第一原則）。

判定と終了コード:
    各項目を COMPLIANT（適合）/ NON_COMPLIANT（不適合）/ UNDETERMINED（未確認）
    で判定し、不適合は出典付きで記録する。NON_COMPLIANT が 1 件でもあれば
    非ゼロ終了しビルドを失敗させる。UNDETERMINED は既定では失敗させないが、
    `--fail-on-undetermined` 指定時は失敗させる（既存
    `python manage.py check --fail-level WARNING` の段階的失敗方針に整合）。

ビルド検証段への接続（tasks.md 8.5、design.md C9）:
    既存 `buildspec.yml` の検証段（`python manage.py check --fail-level WARNING`、
    Control Platform self-test）に、本スクリプトの構成検証実行を非破壊で追加する
    （既存段は保持する）。

外部依存とライセンス（第二原則6・着手時ライセンス確認）:
    - PyYAML 6.0.3（MIT License）を使用し `template.yaml` / `bucketpolicy.yaml` /
      `dependencies.yaml` を解析する。CloudFormation 短縮タグ（`!Ref` / `!Sub`
      / `!GetAtt` 等）を解釈するため `yaml.SafeLoader` を継承した専用ローダに
      マルチコンストラクタを登録する（cfn-lint / aws-sam-cli と同一手法。出典:
      `pip show PyYAML` の License 欄 = MIT）。PyYAML はビルド専用依存として
      `requirements-dev.txt`（pyyaml==6.0.3）に固定され、`buildspec.yml` の install 段で
      個別導入される（Lambda 配布物 `requirements.txt` へは非同梱、出典: requirements-dev.txt
      のライセンス注記、buildspec.yml）。
    - 標準ライブラリ `argparse` / `ast` / `dataclasses` / `enum` / `pathlib` /
      `urllib`（実測時のみ）を用いる。

実行コマンド（プロジェクトルートから）:
    構成検証のみ:   python -m scripts.measurement.non_regression_check
    実測併用（任意）: python -m scripts.measurement.non_regression_check \\
                        --base-url https://serverless.portfolio.cobaemon.com
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field, fields
from enum import Enum
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

import yaml

# ------------------------------------------------------------------------------
# 検証対象ファイルの所在（リポジトリルート基準）。
# 本ファイルは scripts/measurement/ に置かれるため parents[2] がリポジトリルート
# である（scripts/measurement/non_regression_check.py -> scripts/measurement ->
# scripts -> ルート）。
# ------------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]

# 維持対象の 7 言語（順序を含めて requirements.md R9-4 / base.py LANGUAGES と一致）。
# 出典: config/settings/base.py LANGUAGES、requirements.md R9-4。
_EXPECTED_LANGUAGES: tuple[str, ...] = (
    "ja",
    "en",
    "fr",
    "es",
    "ru",
    "zh-hans",
    "ar",
)

# Contact_Payload が保持してよい 4 項目（順序不問。集合として一致を要求する）。
# 出典: contact_function/domain/contact_payload.py、design.md DM1、requirements.md R5-1/R9-5。
_EXPECTED_PAYLOAD_FIELDS: frozenset[str] = frozenset(
    {"full_name", "email", "phone_number", "message"}
)

# HTTPS へのリダイレクトとみなす HTTP ステータス（恒久/一時いずれのリダイレクトも許容）。
_REDIRECT_STATUS_CODES: frozenset[int] = frozenset({301, 302, 307, 308})

# CloudFront で HTTPS 強制とみなす ViewerProtocolPolicy 値（出典: requirements.md R9-1/R7-4、
# template.yaml CloudFrontDistribution の全 Behavior、AWS 公式 CacheBehavior.ViewerProtocolPolicy）。
_HTTPS_ENFORCED_VIEWER_POLICY: str = "redirect-to-https"

# S3 バケットポリシーで OAC 経由に限定するために要求するサービスプリンシパル
# （出典: bucketpolicy.yaml AllowCloudFrontServicePrincipalReadOnly、requirements.md R9-2/R9-6）。
_CLOUDFRONT_SERVICE_PRINCIPAL: str = "cloudfront.amazonaws.com"

# S3 の公開アクセスを完全遮断するために全 true を要求する PublicAccessBlock の各設定キー
# （出典: dependencies.yaml StaticFilesBucket.PublicAccessBlockConfiguration、requirements.md R9-2/R9-6）。
_PUBLIC_ACCESS_BLOCK_KEYS: tuple[str, ...] = (
    "BlockPublicAcls",
    "BlockPublicPolicy",
    "IgnorePublicAcls",
    "RestrictPublicBuckets",
)

# 表示応答へセキュリティヘッダを付与する ResponseHeadersPolicy の論理 ID
# （出典: template.yaml DisplayResponseHeadersPolicy、design.md C5/C6）。
_DISPLAY_RESPONSE_HEADERS_POLICY_ID: str = "DisplayResponseHeadersPolicy"


# ------------------------------------------------------------------------------
# 判定区分と検証結果の値オブジェクト。
# 各検証項目は三値（適合/不適合/未確認）で判定し、不適合・未確認は出典付きで
# 記録する（推測補完・フォールバック禁止、出典: requirements.md R9-7/R12、
# principles.md 第一原則）。
# ------------------------------------------------------------------------------
class Verdict(Enum):
    """非退行検証項目の判定区分（三値）.

    UNDETERMINED は「実測未実施等により事実を確認できていない」ことを表し、
    達成/未達を決めつけない（出典: requirements.md R9-7/R12、principles.md
    第一原則、フォールバック禁止）。
    """

    # 適合（維持すべき不変条件を満たす）。
    COMPLIANT = "COMPLIANT"
    # 不適合（維持すべき不変条件を満たさない。出典付きで記録し失敗させる）。
    NON_COMPLIANT = "NON_COMPLIANT"
    # 未確認（事実を確認できていない。推測補完せず明示する）。
    UNDETERMINED = "UNDETERMINED"


@dataclass(frozen=True, slots=True)
class CheckResult:
    """個々の非退行検証項目の判定結果を保持する不変の値オブジェクト.

    Attributes:
        check_id: 検証項目の一意識別子（例: "R9-1-cloudfront-https"）。
        requirement: 対応する requirements.md の条項（例: "R9-1"）。
        title: 人間可読の項目名。
        verdict: 判定（COMPLIANT / NON_COMPLIANT / UNDETERMINED）。
        detail: 判定根拠の説明（事実のみ）。
        evidence: 出典（ファイルパス・要件条項・実測対象等）のタプル。
    """

    # 検証項目の一意識別子。
    check_id: str
    # 対応する requirements.md の条項。
    requirement: str
    # 人間可読の項目名。
    title: str
    # 判定（三値）。
    verdict: Verdict
    # 判定根拠の説明（事実のみ）。
    detail: str
    # 出典のタプル（既定は空。全項目に出典を付す方針）。
    evidence: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """JSON 直列化用の辞書へ変換する.

        Returns:
            dict[str, Any]: verdict を文字列値へ、evidence をリストへ落とした辞書表現。
        """
        # asdict は Enum/タプルをそのまま残すため、verdict と evidence のみ明示変換する。
        data = asdict(self)
        data["verdict"] = self.verdict.value
        data["evidence"] = list(self.evidence)
        return data


# ------------------------------------------------------------------------------
# CloudFormation/SAM テンプレート読み取り（PyYAML, MIT License）。
# `!Ref` / `!Sub` / `!GetAtt` / `!If` / `!ImportValue` / `!Equals` 等の短縮タグを
# 完全表記（`Ref` / `Fn::Sub` 等）の辞書へ変換して読み込む（cfn-lint / aws-sam-cli
# と同一手法）。SafeLoader を基底とし任意 Python オブジェクトの実体化を許さない
# （ゼロトラスト: 信頼できない構文を実行しない、出典: principles.md 第二原則2）。
# ------------------------------------------------------------------------------
class _CloudFormationLoader(yaml.SafeLoader):
    """CloudFormation 短縮タグを解釈する `yaml.SafeLoader` 派生ローダ."""


def _construct_cfn_tag(
    loader: _CloudFormationLoader, tag_suffix: str, node: yaml.Node
) -> dict[str, Any]:
    """CloudFormation 短縮タグノードを完全表記の辞書へ変換する.

    Args:
        loader: 呼び出し元ローダ。
        tag_suffix: `!` を除いたタグ名（例: "Ref", "Sub", "GetAtt"）。
        node: 対象 YAML ノード（スカラ/シーケンス/マッピングのいずれか）。

    Returns:
        dict[str, Any]: 完全表記のキー（"Ref"/"Condition" または "Fn::<name>"）を持つ辞書。
    """
    # ノード種別に応じて素の Python 値を構築する（deep=True で入れ子も解決する）。
    if isinstance(node, yaml.ScalarNode):
        value: Any = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    else:
        value = loader.construct_mapping(node, deep=True)

    # !GetAtt はスカラ "A.B" を ["A", "B"] へ分割する（CFN 正規表記に整合させる）。
    if tag_suffix == "GetAtt" and isinstance(value, str):
        value = value.split(".")

    # Ref / Condition は Fn:: 接頭辞を持たない。それ以外は Fn::<name> とする。
    if tag_suffix in ("Ref", "Condition"):
        return {tag_suffix: value}
    return {f"Fn::{tag_suffix}": value}


# `!` で始まる全短縮タグを上記コンストラクタで処理させる（cfn-lint と同一手法）。
_CloudFormationLoader.add_multi_constructor("!", _construct_cfn_tag)


def _load_cfn_yaml(path: Path) -> dict[str, Any]:
    """CloudFormation/SAM テンプレートを短縮タグ対応で読み込む.

    Args:
        path: テンプレートファイルの絶対パス。

    Returns:
        dict[str, Any]: 解析済みテンプレート辞書。

    Raises:
        FileNotFoundError: ファイルが存在しない場合（握りつぶさず明示的に失敗させる）。
        TypeError: トップレベルがマッピングでない場合（想定外を握りつぶさない）。
    """
    # ファイル欠落は握りつぶさず明示的に失敗させる（第三原則3、事実報告）。
    if not path.exists():
        raise FileNotFoundError(f"テンプレートが見つからない: {path}")

    # SafeLoader 派生の専用ローダで読み込む（任意オブジェクトの実体化はしない）。
    with path.open(encoding="utf-8") as stream:
        document = yaml.load(stream, Loader=_CloudFormationLoader)

    # トップレベルがマッピングでない構成は想定外として明示的に失敗させる。
    if not isinstance(document, dict):
        raise TypeError(f"テンプレートのトップレベルがマッピングでない: {path}")
    return document


def _dig(mapping: Any, *keys: str) -> Any:
    """ネストした辞書を順にたどり、途中が欠落すれば None を返す.

    「あるべき制御が構成に存在しない」ことを不適合として記録するための安全な
    ナビゲーションである。値の欠落は判定側で NON_COMPLIANT として明示記録する
    （フォールバックではなく、欠落という事実の検出）。

    Args:
        mapping: 起点の辞書（または任意値）。
        *keys: たどるキー列。

    Returns:
        Any: たどり着いた値。途中が辞書でない、またはキーが無い場合は None。
    """
    current = mapping
    for key in keys:
        # 途中が辞書でない/キーが無い場合は欠落として None を返す（呼び出し側が判定）。
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


# ------------------------------------------------------------------------------
# Django 設定ソースの AST 読み取り。
# Django 本体の起動（機密情報の環境変数展開が必要）に依存せず、設定ソース
# （base.py / prod.py）を AST 解析してモジュールトップレベルの代入値のみを
# 事実として取り出す。これにより本スクリプトは自己完結・決定的に動作する。
# ------------------------------------------------------------------------------
def _read_module_assignment(path: Path, name: str) -> ast.expr:
    """Python ソースのモジュールトップレベル代入の右辺 AST を返す.

    Args:
        path: 解析対象 Python ソースの絶対パス。
        name: 取得する代入先の変数名（例: "LANGUAGES"）。

    Returns:
        ast.expr: 当該変数へ代入された右辺式の AST ノード。

    Raises:
        FileNotFoundError: ソースファイルが存在しない場合（明示的に失敗させる）。
        KeyError: 当該変数のトップレベル代入が存在しない場合（決めつけず失敗）。
    """
    # ファイル欠落は握りつぶさず明示的に失敗させる（第三原則3、事実報告）。
    if not path.exists():
        raise FileNotFoundError(f"設定ソースが見つからない: {path}")

    # ソースを AST へ解析する（構文エラーは SyntaxError として自然に伝播させる）。
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    # モジュール直下の代入文（Assign）のうち、対象名への代入の右辺を探す。
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node.value

    # 対象変数のトップレベル代入が無い場合は握りつぶさず明示的に失敗させる。
    raise KeyError(f"{path} にトップレベル代入 {name} が存在しない")


def _read_language_codes(base_settings_path: Path) -> list[str]:
    """`base.py` の `LANGUAGES` から言語コードの一覧を AST 解析で取り出す.

    `LANGUAGES = [('ja', 'Japanese'), ('en', 'English'), ...]` の各要素の
    第 1 要素（言語コード文字列）のみを、実行時副作用なく静的に抽出する。

    Args:
        base_settings_path: `config/settings/base.py` の絶対パス。

    Returns:
        list[str]: 定義順の言語コード一覧。

    Raises:
        TypeError: `LANGUAGES` がリスト/タプルのリテラルでない場合、または各要素が
            `(code, name)` の文字列リテラルタプルでない場合（想定外を握りつぶさない）。
    """
    # LANGUAGES への代入右辺 AST を取得する。
    value = _read_module_assignment(base_settings_path, "LANGUAGES")

    # 右辺はリスト/タプルのリテラルであること（動的生成は想定外として失敗させる）。
    if not isinstance(value, (ast.List, ast.Tuple)):
        raise TypeError(
            f"LANGUAGES がリスト/タプルのリテラルでない: {type(value)!r} "
            f"({base_settings_path})"
        )

    # 各要素 (code, name) の第 1 要素（言語コード文字列）を順に取り出す。
    codes: list[str] = []
    for element in value.elts:
        if not isinstance(element, (ast.Tuple, ast.List)) or not element.elts:
            raise TypeError(
                f"LANGUAGES の要素が (code, name) 形式でない: {ast.dump(element)}"
            )
        code_node = element.elts[0]
        # 言語コードは文字列リテラルであること（定数畳み込みを避け素の Constant を要求）。
        if not isinstance(code_node, ast.Constant) or not isinstance(
            code_node.value, str
        ):
            raise TypeError(
                f"LANGUAGES の言語コードが文字列リテラルでない: {ast.dump(code_node)}"
            )
        codes.append(code_node.value)
    return codes


def _read_bool_assignment(settings_path: Path, name: str) -> bool:
    """Python 設定ソースのトップレベル真偽値代入を AST 解析で取り出す.

    Args:
        settings_path: 解析対象設定ソースの絶対パス。
        name: 取得する変数名（例: "SECURE_SSL_REDIRECT"）。

    Returns:
        bool: 代入された真偽値。

    Raises:
        TypeError: 右辺が真偽値リテラル（True/False）でない場合（想定外を握りつぶさない）。
    """
    # 対象変数への代入右辺 AST を取得する。
    value = _read_module_assignment(settings_path, name)

    # 右辺は True/False の定数リテラルであること（式・変数参照は想定外として失敗）。
    if not isinstance(value, ast.Constant) or not isinstance(value.value, bool):
        raise TypeError(
            f"{name} が真偽値リテラルでない: {ast.dump(value)} ({settings_path})"
        )
    return value.value


def check_seven_languages(project_root: Path) -> list[CheckResult]:
    """7 言語表示ページ配信の構成維持を検証する（R9-4）.

    (a) `config/settings/base.py` の `LANGUAGES` が維持対象 7 言語
    （ja, en, fr, es, ru, zh-hans, ar）と一致すること、(b) `locale/` に各言語の
    翻訳カタログディレクトリが存在することを検証する（出典: requirements.md
    R9-4、design.md C1/C2、E-4）。

    Args:
        project_root: リポジトリルートの絶対パス。

    Returns:
        list[CheckResult]: (a)(b) それぞれの判定結果。
    """
    results: list[CheckResult] = []

    # (a) base.py の LANGUAGES を AST で読み取り、維持対象 7 言語と集合一致を確認する。
    base_path = project_root / "config" / "settings" / "base.py"
    codes = _read_language_codes(base_path)
    codes_set = set(codes)
    expected_set = set(_EXPECTED_LANGUAGES)
    missing = sorted(expected_set - codes_set)
    unexpected = sorted(codes_set - expected_set)
    languages_ok = not missing and not unexpected
    results.append(
        CheckResult(
            check_id="R9-4-languages-setting",
            requirement="R9-4",
            title="Django 設定 LANGUAGES が維持対象 7 言語を網羅",
            verdict=Verdict.COMPLIANT if languages_ok else Verdict.NON_COMPLIANT,
            detail=(
                f"LANGUAGES が維持対象 7 言語と一致する（定義: {codes}）"
                if languages_ok
                else f"LANGUAGES が 7 言語と不一致（欠落: {missing}, 想定外: {unexpected}）"
            ),
            evidence=(
                f"config/settings/base.py: LANGUAGES = {codes}",
                f"requirements.md R9-4（維持対象: {list(_EXPECTED_LANGUAGES)}）",
            ),
        )
    )

    # (b) locale/ に各言語のカタログディレクトリが存在するか確認する。
    # Django は zh-hans を locale ディレクトリ名 zh_Hans に変換するため、両表記を許容する
    # （出典: Django i18n の to_locale 変換。ja/en 等は変換後も同一）。
    locale_root = project_root / "locale"
    missing_locales: list[str] = []
    for code in _EXPECTED_LANGUAGES:
        candidates = {code, _to_locale_dir_name(code)}
        # いずれかの表記のディレクトリが存在すれば当該言語のカタログありと判定する。
        if not any((locale_root / name).is_dir() for name in candidates):
            missing_locales.append(code)
    locales_ok = not missing_locales
    results.append(
        CheckResult(
            check_id="R9-4-locale-catalogs",
            requirement="R9-4",
            title="locale に 7 言語すべての翻訳カタログディレクトリが存在",
            verdict=Verdict.COMPLIANT if locales_ok else Verdict.NON_COMPLIANT,
            detail=(
                "維持対象 7 言語すべての locale ディレクトリが存在する"
                if locales_ok
                else f"locale ディレクトリが欠落する言語が存在する: {missing_locales}"
            ),
            evidence=(
                f"locale/ 配下ディレクトリ探索（ルート: {locale_root}）",
                "requirements.md R9-4、design.md C2（7 言語の Prerendered_Page 生成）",
            ),
        )
    )
    return results


def _to_locale_dir_name(language_code: str) -> str:
    """言語コードを Django の locale ディレクトリ名表記へ変換する.

    Django の `django.utils.translation.to_locale` に準じ、`zh-hans` を
    `zh_Hans` のように「言語は小文字、地域/表記は大文字頭・アンダースコア区切り」
    へ変換する。Django 本体に依存せず同等の最小変換を行う（本スクリプトの
    自己完結性のため）。

    Args:
        language_code: `settings.LANGUAGES` の言語コード（例: "zh-hans"）。

    Returns:
        str: locale ディレクトリ名表記（例: "zh_Hans"）。
    """
    # ハイフン区切りが無ければそのまま（ja, en, fr, es, ru, ar 等）。
    if "-" not in language_code:
        return language_code
    language, _, remainder = language_code.partition("-")
    # 2 文字の残余は国コードとみなし全大文字、それ以外は先頭大文字（スクリプト表記）。
    if len(remainder) == 2:
        return f"{language}_{remainder.upper()}"
    return f"{language}_{remainder.capitalize()}"


def check_contact_payload_fields() -> list[CheckResult]:
    """Contact_Payload 4 項目限定の構成維持を検証する（R9-5）.

    `contact_function/domain/contact_payload.py` の `ContactPayload` データクラスが
    氏名・メール・電話番号・メッセージの 4 項目のみを保持することを、実際に
    import してデータクラスフィールドを内省して検証する（純粋モジュールであり
    Django 起動に依存しない。出典: requirements.md R5-1/R9-5、design.md DM1）。

    Returns:
        list[CheckResult]: 4 項目限定判定の結果（単一要素）。
    """
    # 純粋ドメインモジュールを import する（副作用なし。sys.path 準備は main が担う）。
    from contact_function.domain.contact_payload import ContactPayload

    # データクラスフィールド名の集合を取り出す。
    actual_fields = {f.name for f in fields(ContactPayload)}
    extra = sorted(actual_fields - _EXPECTED_PAYLOAD_FIELDS)
    missing = sorted(_EXPECTED_PAYLOAD_FIELDS - actual_fields)
    payload_ok = not extra and not missing
    return [
        CheckResult(
            check_id="R9-5-contact-payload-fields",
            requirement="R9-5",
            title="Contact_Payload が 4 項目のみを保持（GDPR データ最小化）",
            verdict=Verdict.COMPLIANT if payload_ok else Verdict.NON_COMPLIANT,
            detail=(
                f"ContactPayload は 4 項目のみを保持する（{sorted(actual_fields)}）"
                if payload_ok
                else "ContactPayload の保持項目が 4 項目限定でない"
                f"（想定外: {extra}, 欠落: {missing}）"
            ),
            evidence=(
                "contact_function/domain/contact_payload.py: ContactPayload の"
                f" dataclass フィールド = {sorted(actual_fields)}",
                f"requirements.md R5-1/R9-5、design.md DM1（4 項目: "
                f"{sorted(_EXPECTED_PAYLOAD_FIELDS)}）",
            ),
        )
    ]


# ------------------------------------------------------------------------------
# 任意の実配信エンドポイント実測（--base-url 指定時のみ）。
# 実測は DNS 切替を伴う運用手順であり本計画のコードタスク範囲外だが（design.md
# 「移行手順」/Notes）、運用担当が任意に実施できるよう最小の観測手段を提供する。
# ネットワーク越しの取得は DIP に従い抽象（EndpointProber）へ依存させ、テスト
# 容易性と差し替え可能性を確保する。
# ------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ProbeResponse:
    """HTTP 実測の応答を保持する不変の値オブジェクト.

    Attributes:
        status: HTTP ステータスコード。
        headers: 応答ヘッダ（ヘッダ名は小文字へ正規化して保持する）。
        final_url: リダイレクト追従後の最終 URL（追従しない場合は要求 URL）。
    """

    # HTTP ステータスコード。
    status: int
    # 応答ヘッダ（キーは小文字へ正規化。大文字小文字差の照合を避けるため）。
    headers: dict[str, str]
    # 追従後の最終 URL（HTTPS リダイレクト判定に用いる）。
    final_url: str


class EndpointProber(Protocol):
    """実配信エンドポイントへの HTTP 実測ポート（抽象）.

    具体実装（urllib 等）へ依存せず、検証ロジックを差し替え可能にする
    （依存性逆転、出典: principles.md 第二原則3 SOLID/DIP）。
    """

    def probe(self, url: str, follow_redirects: bool) -> ProbeResponse:
        """指定 URL へ GET 実測を行い応答を返す.

        Args:
            url: 実測対象 URL（http/https）。
            follow_redirects: True でリダイレクトを追従、False で追従しない。

        Returns:
            ProbeResponse: 実測結果。

        Raises:
            urllib.error.URLError: 取得に失敗した場合（呼び出し側が明示記録する）。
        """
        ...


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """リダイレクトを追従せず、リダイレクト応答をそのまま返すハンドラ.

    HTTP→HTTPS リダイレクトの有無自体を観測するため、標準の自動追従を無効化する。
    """

    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        """リダイレクト要求を生成しない（追従を抑止する）.

        Returns:
            None: 常に None を返し、呼び出し元は受領したリダイレクト応答を扱う。
        """
        # None を返すと urllib はリダイレクトを追従せず応答をそのまま返す。
        return None


class UrllibEndpointProber:
    """`urllib` による EndpointProber 具体実装.

    標準ライブラリのみで HTTP 実測を行う（追加依存を持たない）。リダイレクト
    追従の有無を切り替えられる。
    """

    def __init__(self, timeout_seconds: float = 10.0) -> None:
        """タイムアウト秒を受け取り実測器を初期化する.

        Args:
            timeout_seconds: 1 リクエストあたりのタイムアウト秒。
        """
        # ネットワーク不通時に無限待機しないようタイムアウトを保持する。
        self._timeout_seconds = timeout_seconds

    def probe(self, url: str, follow_redirects: bool) -> ProbeResponse:
        """指定 URL へ GET 実測を行い ProbeResponse を返す（EndpointProber 実装）.

        Args:
            url: 実測対象 URL（http/https のみ）。
            follow_redirects: True でリダイレクト追従、False で追従しない。

        Returns:
            ProbeResponse: 実測結果。

        Raises:
            ValueError: URL スキームが http/https でない場合（ゼロトラスト入力検証）。
            urllib.error.URLError: 取得に失敗した場合（握りつぶさず伝播させる）。
        """
        # ゼロトラスト: スキームを検証し、想定外スキーム（file 等）を拒否する。
        scheme = urlsplit(url).scheme.lower()
        if scheme not in ("http", "https"):
            raise ValueError(f"http/https 以外の URL は実測対象外: {url!r}")

        # 追従有無に応じたオープナーを構築する（追従しない場合は専用ハンドラを使用）。
        opener = (
            urllib.request.build_opener()
            if follow_redirects
            else urllib.request.build_opener(_NoRedirectHandler)
        )
        request = urllib.request.Request(url, method="GET")
        try:
            # with で確実にクローズする。
            with opener.open(request, timeout=self._timeout_seconds) as response:
                # ヘッダ名を小文字へ正規化して保持する（照合時の大文字小文字差を排除）。
                headers = {key.lower(): value for key, value in response.headers.items()}
                return ProbeResponse(
                    status=response.status,
                    headers=headers,
                    final_url=response.url,
                )
        except urllib.error.HTTPError as http_error:
            # リダイレクト非追従時の 3xx（例: HTTP→HTTPS の 301）や 4xx/5xx は urllib が
            # HTTPError を送出するが、これらは「取得失敗」ではなく有効な HTTP 応答
            # （ステータス・ヘッダ・URL を持つ）である。リダイレクト検証等のため応答として扱う。
            # 真の取得失敗（接続不可・DNS 解決失敗等）は URLError（HTTPError の親）として
            # 送出され本 except では捕捉されず、呼び出し側が undetermined として明示記録する
            # （握りつぶさない、出典: requirements.md R9-1、design.md「移行手順」）。
            headers = {key.lower(): value for key, value in http_error.headers.items()}
            return ProbeResponse(
                status=http_error.code,
                headers=headers,
                final_url=http_error.url,
            )


def _to_http_url(base_url: str) -> str:
    """base-url（通常 https）から HTTP スキームの同一ホスト URL を導出する.

    HTTP→HTTPS リダイレクト実測のため、スキームのみを http へ変えた URL を作る。

    Args:
        base_url: 実測の基準 URL（https 前提）。

    Returns:
        str: スキームを http にした URL。
    """
    # スキームのみ http へ置換し、他の構成要素（ホスト/パス）は保持する。
    parts = urlsplit(base_url)
    return urlunsplit(("http", parts.netloc, parts.path or "/", parts.query, ""))


def run_live_checks(
    base_url: str | None, prober: EndpointProber
) -> list[CheckResult]:
    """任意の実配信実測を行い、実測できた観測結果を返す（--base-url 指定時のみ）.

    base_url が未指定の場合、実測は運用手順として未実施であり、実配信次元を
    `undetermined` として明示記録する（決めつけない、フォールバック禁止）。

    Args:
        base_url: 実測の基準 URL（未指定なら None）。
        prober: HTTP 実測ポートの具体実装。

    Returns:
        list[CheckResult]: HTTPS リダイレクトと CSP ヘッダの実測結果、または
            未実施を示す undetermined 結果。
    """
    # base-url 未指定時は実配信実測を行わず、未確認として明示記録する。
    if base_url is None:
        undetermined_evidence = (
            "本実行では --base-url 未指定のため実配信エンドポイント実測を行っていない",
            "実配信の実測は DNS 切替を伴う運用手順（design.md「移行手順」/Notes）",
        )
        return [
            CheckResult(
                check_id="R9-1-live-https-redirect",
                requirement="R9-1",
                title="[実測] HTTP→HTTPS リダイレクト（実配信）",
                verdict=Verdict.UNDETERMINED,
                detail="実配信への実測は未実施（undetermined）。構成検証は別項目で実施済み。",
                evidence=undetermined_evidence,
            ),
            CheckResult(
                check_id="R7-live-csp-header",
                requirement="R7-1",
                title="[実測] Content-Security-Policy 応答ヘッダ付与（実配信）",
                verdict=Verdict.UNDETERMINED,
                detail="実配信への実測は未実施（undetermined）。構成検証は別項目で実施済み。",
                evidence=undetermined_evidence,
            ),
        ]

    # base-url 指定時は観測可能な 2 項目（HTTPS リダイレクト・CSP ヘッダ）を実測する。
    return [
        _live_check_https_redirect(base_url, prober),
        _live_check_csp_header(base_url, prober),
    ]


def _live_check_https_redirect(
    base_url: str, prober: EndpointProber
) -> CheckResult:
    """HTTP アクセスが HTTPS へリダイレクトされることを実測する（R9-1）.

    Args:
        base_url: 実測の基準 URL（https 前提）。
        prober: HTTP 実測ポート。

    Returns:
        CheckResult: 実測判定。取得失敗時は undetermined（接続失敗を出典に明示）。
    """
    http_url = _to_http_url(base_url)
    # 取得失敗（ネットワーク/DNS 未切替等）は握りつぶさず、事実として undetermined 記録する。
    try:
        response = prober.probe(http_url, follow_redirects=False)
    except urllib.error.URLError as error:
        return CheckResult(
            check_id="R9-1-live-https-redirect",
            requirement="R9-1",
            title="[実測] HTTP→HTTPS リダイレクト（実配信）",
            verdict=Verdict.UNDETERMINED,
            detail=f"実測の取得に失敗したため未確認（undetermined）: {error}",
            evidence=(f"実測対象: {http_url}", "取得失敗を事実として記録（推測補完しない）"),
        )

    # リダイレクトステータスかつ Location が https であることを確認する。
    location = response.headers.get("location", "")
    is_redirect = response.status in _REDIRECT_STATUS_CODES
    to_https = location.lower().startswith("https://")
    redirect_ok = is_redirect and to_https
    return CheckResult(
        check_id="R9-1-live-https-redirect",
        requirement="R9-1",
        title="[実測] HTTP→HTTPS リダイレクト（実配信）",
        verdict=Verdict.COMPLIANT if redirect_ok else Verdict.NON_COMPLIANT,
        detail=(
            f"HTTP 要求が HTTPS へリダイレクトされる（status={response.status}, "
            f"Location={location}）"
            if redirect_ok
            else f"HTTPS へのリダイレクトを確認できない（status={response.status}, "
            f"Location={location!r}）"
        ),
        evidence=(
            f"実測対象: {http_url}",
            f"応答 status={response.status}, Location={location!r}",
            "requirements.md R9-1",
        ),
    )


def _live_check_csp_header(base_url: str, prober: EndpointProber) -> CheckResult:
    """表示応答に Content-Security-Policy ヘッダが付与されることを実測する（R7-1）.

    Args:
        base_url: 実測の基準 URL（https 前提）。
        prober: HTTP 実測ポート。

    Returns:
        CheckResult: 実測判定。取得失敗時は undetermined（接続失敗を出典に明示）。
    """
    # 表示応答（追従後の最終応答）のヘッダを観測する。
    try:
        response = prober.probe(base_url, follow_redirects=True)
    except urllib.error.URLError as error:
        return CheckResult(
            check_id="R7-live-csp-header",
            requirement="R7-1",
            title="[実測] Content-Security-Policy 応答ヘッダ付与（実配信）",
            verdict=Verdict.UNDETERMINED,
            detail=f"実測の取得に失敗したため未確認（undetermined）: {error}",
            evidence=(f"実測対象: {base_url}", "取得失敗を事実として記録（推測補完しない）"),
        )

    # Content-Security-Policy ヘッダの有無と、per-request nonce を含まないことを確認する。
    csp_header = response.headers.get("content-security-policy", "")
    has_csp = bool(csp_header)
    has_no_nonce = "nonce" not in csp_header.lower()
    csp_ok = has_csp and has_no_nonce
    return CheckResult(
        check_id="R7-live-csp-header",
        requirement="R7-1",
        title="[実測] Content-Security-Policy 応答ヘッダ付与（実配信）",
        verdict=Verdict.COMPLIANT if csp_ok else Verdict.NON_COMPLIANT,
        detail=(
            "応答に Content-Security-Policy が付与され nonce を含まない"
            if csp_ok
            else "Content-Security-Policy が欠落、または per-request nonce を含む"
            f"（CSP 有={has_csp}, nonce 不在={has_no_nonce}）"
        ),
        evidence=(
            f"実測対象: {response.final_url}",
            f"Content-Security-Policy={csp_header!r}",
            "requirements.md R7-1/R7-2",
        ),
    )


# ------------------------------------------------------------------------------
# 構成検証（IaC・Django 設定を静的解析して非退行の不変条件を確認する）。
# 実配信への実測に依存せず決定的に判定できるため、ビルド検証段で実行できる
# （出典: design.md「移行手順」/Notes、tasks.md 8.5）。
# ------------------------------------------------------------------------------
def check_https_enforcement(project_root: Path) -> list[CheckResult]:
    """HTTPS 強制・HTTP→HTTPS リダイレクトの構成維持を検証する（R9-1）.

    (a) `config/settings/prod.py` の `SECURE_SSL_REDIRECT = True`、(b) `template.yaml`
    の CloudFront ディストリビューションの全 Behavior（Default および追加 Behavior）が
    `ViewerProtocolPolicy: redirect-to-https` であることを検証する（出典:
    requirements.md R9-1、R7-4、design.md C5、E-4、template.yaml CloudFrontDistribution）。

    Args:
        project_root: リポジトリルートの絶対パス。

    Returns:
        list[CheckResult]: (a)(b) それぞれの判定結果。
    """
    results: list[CheckResult] = []

    # (a) prod.py の SECURE_SSL_REDIRECT を AST で読み取り、True であることを確認する。
    prod_path = project_root / "config" / "settings" / "prod.py"
    ssl_redirect = _read_bool_assignment(prod_path, "SECURE_SSL_REDIRECT")
    results.append(
        CheckResult(
            check_id="R9-1-secure-ssl-redirect",
            requirement="R9-1",
            title="Django 本番設定で HTTPS 強制（SECURE_SSL_REDIRECT）",
            verdict=Verdict.COMPLIANT if ssl_redirect else Verdict.NON_COMPLIANT,
            detail=(
                "prod.py は SECURE_SSL_REDIRECT = True で HTTPS を強制する"
                if ssl_redirect
                else "prod.py の SECURE_SSL_REDIRECT が True でない（HTTPS 強制が退行）"
            ),
            evidence=(
                f"config/settings/prod.py: SECURE_SSL_REDIRECT = {ssl_redirect}",
                "requirements.md R9-1、E-4",
            ),
        )
    )

    # (b) template.yaml の CloudFront 全 Behavior が redirect-to-https であることを確認する。
    template = _load_cfn_yaml(project_root / "template.yaml")
    dist_cfg = _dig(
        template,
        "Resources",
        "CloudFrontDistribution",
        "Properties",
        "DistributionConfig",
    )
    # Default Behavior と追加 Behavior の ViewerProtocolPolicy を収集する。
    default_policy = _dig(dist_cfg or {}, "DefaultCacheBehavior", "ViewerProtocolPolicy")
    extra_behaviors = _dig(dist_cfg or {}, "CacheBehaviors") or []
    # (パス, ポリシー値) の一覧を組み立てる（Default は擬似パス "(default)" とする）。
    behavior_policies: list[tuple[str, Any]] = [("(default)", default_policy)]
    for behavior in extra_behaviors:
        if isinstance(behavior, dict):
            path_pattern = behavior.get("PathPattern", "(unnamed)")
            behavior_policies.append(
                (str(path_pattern), behavior.get("ViewerProtocolPolicy"))
            )
    # Default Behavior が存在し、全 Behavior が redirect-to-https であることを要求する。
    non_conforming = [
        f"{path}={policy!r}"
        for path, policy in behavior_policies
        if policy != _HTTPS_ENFORCED_VIEWER_POLICY
    ]
    cloudfront_https_ok = default_policy is not None and not non_conforming
    results.append(
        CheckResult(
            check_id="R9-1-cloudfront-https-redirect",
            requirement="R9-1",
            title="CloudFront 全 Behavior が HTTPS へリダイレクト（redirect-to-https）",
            verdict=(
                Verdict.COMPLIANT if cloudfront_https_ok else Verdict.NON_COMPLIANT
            ),
            detail=(
                "CloudFront の全 Behavior が ViewerProtocolPolicy: redirect-to-https で"
                f" HTTPS を強制する（検査対象 {len(behavior_policies)} Behavior）"
                if cloudfront_https_ok
                else "redirect-to-https でない Behavior が存在するか Default Behavior が欠落する"
                f"（不適合: {non_conforming or 'DefaultCacheBehavior 欠落'}）"
            ),
            evidence=(
                "template.yaml: Resources.CloudFrontDistribution.Properties."
                "DistributionConfig の DefaultCacheBehavior/CacheBehaviors "
                f"ViewerProtocolPolicy = {[p for _, p in behavior_policies]}",
                "requirements.md R9-1/R7-4、design.md C5",
            ),
        )
    )
    return results


def check_s3_oac_only(project_root: Path) -> list[CheckResult]:
    """S3 直アクセス禁止・CloudFront OAC 経由のみを検証する（R9-2/R9-6）.

    (a) `bucketpolicy.yaml` が CloudFront サービスプリンシパル＋`AWS:SourceArn`
    条件でのみ `s3:GetObject` を許可し、ワイルドカード権限や公開プリンシパルを
    含まないこと、(b) `dependencies.yaml` の `StaticFilesBucket` が PublicAccessBlock
    を 4 項目すべて true にしていることを検証する（出典: requirements.md R9-2/R9-6、
    bucketpolicy.yaml、dependencies.yaml、design.md C1）。

    Args:
        project_root: リポジトリルートの絶対パス。

    Returns:
        list[CheckResult]: (a)(b) それぞれの判定結果。
    """
    results: list[CheckResult] = []

    # (a) bucketpolicy.yaml のバケットポリシー Statement を検証する。
    bucket_policy = _load_cfn_yaml(project_root / "bucketpolicy.yaml")
    statements = (
        _dig(
            bucket_policy,
            "Resources",
            "StaticFilesBucketPolicy",
            "Properties",
            "PolicyDocument",
            "Statement",
        )
        or []
    )
    # 全 Allow Statement が OAC 限定（CloudFront プリンシパル＋SourceArn 条件、
    # 読み取り専用・ワイルドカードなし）であることを要求する。不適合理由を収集する。
    policy_violations: list[str] = []
    if not statements:
        policy_violations.append("BucketPolicy に Statement が存在しない")
    for statement in statements:
        if not isinstance(statement, dict) or statement.get("Effect") != "Allow":
            # Allow 以外（Deny 等）は S3 直アクセス禁止の妨げにならないため検査対象外。
            continue
        # プリンシパルは CloudFront サービスに限定され、公開（"*"）でないこと。
        principal_service = _dig(statement, "Principal", "Service")
        if principal_service != _CLOUDFRONT_SERVICE_PRINCIPAL:
            policy_violations.append(
                f"Allow の Principal.Service が CloudFront 限定でない: {principal_service!r}"
            )
        # アクションはワイルドカードを含まず読み取り（s3:GetObject）に限定されること。
        action = statement.get("Action")
        actions = action if isinstance(action, list) else [action]
        if any(a in ("*", "s3:*") for a in actions):
            policy_violations.append(f"Allow の Action にワイルドカードを含む: {actions!r}")
        # SourceArn 条件（特定 CloudFront ディストリビューション限定）が存在すること。
        source_arn = _dig(statement, "Condition", "StringEquals", "AWS:SourceArn")
        if source_arn is None:
            policy_violations.append("Allow に AWS:SourceArn 条件が存在しない")
    bucket_policy_ok = not policy_violations
    results.append(
        CheckResult(
            check_id="R9-2-bucket-policy-oac-only",
            requirement="R9-2",
            title="S3 バケットポリシーは CloudFront OAC 経由のみ許可",
            verdict=Verdict.COMPLIANT if bucket_policy_ok else Verdict.NON_COMPLIANT,
            detail=(
                "バケットポリシーは CloudFront サービスプリンシパル＋AWS:SourceArn 条件で"
                " s3:GetObject のみを許可する（S3 直アクセス禁止）"
                if bucket_policy_ok
                else f"バケットポリシーが OAC 限定でない（不適合: {policy_violations}）"
            ),
            evidence=(
                "bucketpolicy.yaml: Resources.StaticFilesBucketPolicy.Properties."
                "PolicyDocument.Statement",
                "requirements.md R9-2/R9-6、design.md C1",
            ),
        )
    )

    # (b) dependencies.yaml の PublicAccessBlock が 4 項目すべて true であることを確認する。
    dependencies = _load_cfn_yaml(project_root / "dependencies.yaml")
    public_access_block = (
        _dig(
            dependencies,
            "Resources",
            "StaticFilesBucket",
            "Properties",
            "PublicAccessBlockConfiguration",
        )
        or {}
    )
    # 各キーが厳密に True であることを要求する（未設定/False は公開遮断の退行）。
    not_blocked = [
        key
        for key in _PUBLIC_ACCESS_BLOCK_KEYS
        if public_access_block.get(key) is not True
    ]
    public_access_ok = not not_blocked
    results.append(
        CheckResult(
            check_id="R9-6-public-access-block",
            requirement="R9-6",
            title="S3 バケットの公開アクセスを全項目で遮断（PublicAccessBlock）",
            verdict=Verdict.COMPLIANT if public_access_ok else Verdict.NON_COMPLIANT,
            detail=(
                "StaticFilesBucket は PublicAccessBlock の 4 項目すべてを true にし公開を遮断する"
                if public_access_ok
                else f"PublicAccessBlock で true でない/欠落する項目が存在する: {not_blocked}"
            ),
            evidence=(
                "dependencies.yaml: Resources.StaticFilesBucket.Properties."
                f"PublicAccessBlockConfiguration = {public_access_block}",
                "requirements.md R9-2/R9-6",
            ),
        )
    )
    return results


def check_csp_configuration(project_root: Path) -> list[CheckResult]:
    """表示応答への CSP 付与（ハッシュベース・nonce 不在）の構成維持を検証する（R7/R9-7）.

    (a) `template.yaml` の `DisplayResponseHeadersPolicy` が Content-Security-Policy を
    持ち、CloudFront の表示 Default Behavior にのみ適用され（問い合わせ API Behavior には
    適用しない）ること、(b) CSP パラメータ `ContentSecurityPolicy` の既定値が per-request
    nonce（`nonce` 相当）を含まないハッシュベース方式であることを検証する（出典:
    requirements.md R7-1/R7-2、R9-7、design.md C5/C6、template.yaml
    DisplayResponseHeadersPolicy/ContentSecurityPolicy パラメータ）。

    Args:
        project_root: リポジトリルートの絶対パス。

    Returns:
        list[CheckResult]: (a) 付与・適用範囲、(b) nonce 不在の判定結果。
    """
    results: list[CheckResult] = []
    template = _load_cfn_yaml(project_root / "template.yaml")

    # (a) ResponseHeadersPolicy に CSP が定義され、表示 Default Behavior に適用されること。
    policy_cfg = _dig(
        template,
        "Resources",
        _DISPLAY_RESPONSE_HEADERS_POLICY_ID,
        "Properties",
        "ResponseHeadersPolicyConfig",
    )
    # CSP 値ノード（SecurityHeadersConfig.ContentSecurityPolicy.ContentSecurityPolicy）を取得する。
    csp_value_node = _dig(
        policy_cfg or {},
        "SecurityHeadersConfig",
        "ContentSecurityPolicy",
        "ContentSecurityPolicy",
    )
    has_csp = bool(csp_value_node)

    dist_cfg = _dig(
        template,
        "Resources",
        "CloudFrontDistribution",
        "Properties",
        "DistributionConfig",
    )
    # Default Behavior が本セキュリティポリシーを参照していること（!Ref → {"Ref": 論理ID}）。
    default_policy_ref = _dig(dist_cfg or {}, "DefaultCacheBehavior", "ResponseHeadersPolicyId")
    applied_to_display = default_policy_ref == {
        "Ref": _DISPLAY_RESPONSE_HEADERS_POLICY_ID
    }
    # 問い合わせ API Behavior には本ポリシーを適用しないこと（design.md C6）。
    api_behaviors = _dig(dist_cfg or {}, "CacheBehaviors") or []
    api_uses_security_policy = any(
        _dig(behavior, "ResponseHeadersPolicyId")
        == {"Ref": _DISPLAY_RESPONSE_HEADERS_POLICY_ID}
        for behavior in api_behaviors
        if isinstance(behavior, dict)
    )
    csp_applied_ok = has_csp and applied_to_display and not api_uses_security_policy
    results.append(
        CheckResult(
            check_id="R7-csp-configured-and-applied",
            requirement="R7-1",
            title="表示応答に CSP を付与（ResponseHeadersPolicy を Default Behavior へ適用）",
            verdict=Verdict.COMPLIANT if csp_applied_ok else Verdict.NON_COMPLIANT,
            detail=(
                "DisplayResponseHeadersPolicy が Content-Security-Policy を持ち、表示 Default"
                " Behavior にのみ適用される（API Behavior には非適用）"
                if csp_applied_ok
                else "CSP 付与または適用範囲が不適合"
                f"（CSP 定義={has_csp}, Default 適用={applied_to_display},"
                f" API 誤適用={api_uses_security_policy}）"
            ),
            evidence=(
                "template.yaml: Resources.DisplayResponseHeadersPolicy."
                "Properties.ResponseHeadersPolicyConfig.SecurityHeadersConfig."
                "ContentSecurityPolicy、および CloudFrontDistribution の"
                " DefaultCacheBehavior.ResponseHeadersPolicyId",
                "requirements.md R7-1、design.md C5/C6",
            ),
        )
    )

    # (b) CSP の値供給元（ContentSecurityPolicy パラメータの既定値）が nonce を含まないこと。
    # 値は !Ref で当該パラメータから供給される（build が sha256 を付加、出典: パラメータ注記）。
    csp_default = _dig(template, "Parameters", "ContentSecurityPolicy", "Default")
    # 既定値が存在する場合はその文字列に per-request nonce（"nonce"）が無いことを確認する。
    if isinstance(csp_default, str):
        no_nonce = "nonce" not in csp_default.lower()
        results.append(
            CheckResult(
                check_id="R7-2-csp-no-nonce",
                requirement="R7-2",
                title="CSP はハッシュベースで per-request nonce を含まない",
                verdict=Verdict.COMPLIANT if no_nonce else Verdict.NON_COMPLIANT,
                detail=(
                    "ContentSecurityPolicy パラメータの既定値は nonce を含まない"
                    " ハッシュベース方式である"
                    if no_nonce
                    else "ContentSecurityPolicy パラメータの既定値に per-request nonce を含む"
                ),
                evidence=(
                    "template.yaml: Parameters.ContentSecurityPolicy.Default",
                    "requirements.md R7-2、design.md C6",
                ),
            )
        )
    else:
        # 既定値が無い場合、配信される CSP 文字列の nonce 不在は実測（--base-url）でのみ
        # 観測可能なため、構成検証では未確認として明示する（決めつけない）。
        results.append(
            CheckResult(
                check_id="R7-2-csp-no-nonce",
                requirement="R7-2",
                title="CSP はハッシュベースで per-request nonce を含まない",
                verdict=Verdict.UNDETERMINED,
                detail=(
                    "ContentSecurityPolicy パラメータに既定値が無く、配信 CSP の literal は"
                    " build 供給のため構成検証では未確認（undetermined）。実測は live チェックで確認。"
                ),
                evidence=(
                    "template.yaml: Parameters.ContentSecurityPolicy（Default 未設定）",
                    "requirements.md R7-2、design.md C6",
                ),
            )
        )
    return results


# ------------------------------------------------------------------------------
# 集約・出力・エントリーポイント。
# 構成検証（決定的）と任意の実配信実測（--base-url 指定時）を集約し、判定を
# 出典付きで出力する。NON_COMPLIANT が 1 件でもあれば非ゼロ終了しビルドを失敗
# させる（既存 `check --fail-level WARNING` の段階的失敗方針に整合）。
# ------------------------------------------------------------------------------
def collect_check_results(
    project_root: Path, base_url: str | None, prober: EndpointProber
) -> list[CheckResult]:
    """全非退行検証項目を実行し結果を集約する.

    Args:
        project_root: リポジトリルートの絶対パス。
        base_url: 実配信実測の基準 URL（未指定なら実測を行わず undetermined 記録）。
        prober: 実測ポートの具体実装。

    Returns:
        list[CheckResult]: 全検証項目の判定結果。
    """
    # 構成検証（R9-1/R9-2/R9-6/R9-4/R9-5/R7）と任意の実測を順に集約する。
    results: list[CheckResult] = []
    results.extend(check_https_enforcement(project_root))
    results.extend(check_s3_oac_only(project_root))
    results.extend(check_seven_languages(project_root))
    results.extend(check_contact_payload_fields())
    results.extend(check_csp_configuration(project_root))
    results.extend(run_live_checks(base_url, prober))
    return results


def build_report(results: list[CheckResult]) -> dict[str, Any]:
    """検証結果を集計し JSON 直列化可能なレポート辞書へ変換する.

    Args:
        results: 全検証項目の判定結果。

    Returns:
        dict[str, Any]: 判定内訳の要約と各項目の詳細を含むレポート。
    """
    # 判定区分ごとの件数を集計する（誠実な要約のため三値すべてを明示する）。
    summary = {verdict.value: 0 for verdict in Verdict}
    for result in results:
        summary[result.verdict.value] += 1
    return {
        "feature": "cost-performance-optimization",
        "task": "8.5 デプロイ後非退行検証",
        "summary": summary,
        "results": [result.to_dict() for result in results],
    }


def _emit_report(report: dict[str, Any]) -> None:
    """レポートを標準出力へ JSON（UTF-8, 整形）で出力する.

    Args:
        report: `build_report` が生成したレポート辞書。
    """
    # ensure_ascii=False で日本語をそのまま出力し、可読性のため 2 スペース整形する。
    sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    """非退行検証を実行し、判定に応じた終了コードを返すエントリーポイント.

    構成検証（決定的）を必ず実行し、`--base-url` 指定時は観測可能な実配信実測を
    追加する。NON_COMPLIANT が 1 件でもあれば非ゼロ（1）で終了しビルドを失敗させる。
    `--fail-on-undetermined` 指定時は UNDETERMINED でも非ゼロ（2）で終了する
    （出典: tasks.md 8.5、requirements.md R9-7、design.md C9）。

    Args:
        argv: コマンドライン引数（テスト用途に注入可能。既定は `sys.argv[1:]`）。

    Returns:
        int: 0=全適合、1=不適合あり、2=（--fail-on-undetermined 時）未確認あり。
    """
    # 引数を定義する（ゼロトラスト: 明示指定のみを受理し、既定は最も安全側とする）。
    parser = argparse.ArgumentParser(
        description=(
            "デプロイ後非退行検証（R9-7）: HTTPS 強制・S3 OAC 経由のみ・7 言語表示配信・"
            "Contact_Payload 4 項目限定・CSP 付与を検証する。"
        )
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help=(
            "実配信エンドポイントの基準 URL（https）。指定時のみ HTTPS リダイレクト・CSP "
            "ヘッダを実測する。未指定時は実配信次元を undetermined として記録する。"
        ),
    )
    parser.add_argument(
        "--fail-on-undetermined",
        action="store_true",
        help="UNDETERMINED（未確認）が存在する場合も非ゼロ終了する。",
    )
    args = parser.parse_args(argv)

    # contact_function（純粋ドメイン）を import できるよう、リポジトリルートを import パスへ追加する。
    root_str = str(_REPO_ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    # 全検証を集約し、レポートを出力する（実測ポートは urllib 具体実装を注入）。
    results = collect_check_results(_REPO_ROOT, args.base_url, UrllibEndpointProber())
    report = build_report(results)
    _emit_report(report)

    # 不適合・未確認を集計し、終了コードを決定する（不適合は握りつぶさず失敗させる）。
    non_compliant = [r for r in results if r.verdict is Verdict.NON_COMPLIANT]
    undetermined = [r for r in results if r.verdict is Verdict.UNDETERMINED]
    if non_compliant:
        # 不適合の要点を標準エラーへ出典付きで明示する（フォールバック禁止）。
        sys.stderr.write(
            "非退行検証で不適合を検出した（NON_COMPLIANT）:\n"
            + "\n".join(
                f"- [{r.requirement}] {r.title}: {r.detail}" for r in non_compliant
            )
            + "\n"
        )
        return 1
    if args.fail_on_undetermined and undetermined:
        # --fail-on-undetermined 指定時は未確認も失敗として扱う。
        sys.stderr.write(
            "未確認項目が存在する（UNDETERMINED、--fail-on-undetermined 指定）:\n"
            + "\n".join(f"- [{r.requirement}] {r.title}" for r in undetermined)
            + "\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    # スクリプト直接起動時は非退行検証を実行し、判定に応じた終了コードで終了する。
    raise SystemExit(main())
