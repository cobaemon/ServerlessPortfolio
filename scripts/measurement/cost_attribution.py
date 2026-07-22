"""Cost_Attribution 算出・記録モジュール（Portfolio_Operational_Cost）.

本モジュールは spec `cost-performance-optimization` の tasks.md 8.1 に対応し、
月次 AWS 請求から Portfolio_Operational_Cost を算出・検証・記録するための
「算出ロジック」と「記録様式（DM6）」をコードとして提供する（出典:
`.kiro/specs/cost-performance-optimization/design.md` C8「Cost_Attribution
計算」/「Cost 設計」/「Data Models > DM6」、`requirements.md` R1, R2, E-1, E-9,
Glossary）。

責務（本モジュールが担うこと）:
    - Cost_Attribution の「含める／除外（共通）／除外（開発）」集合を、根拠
      （`template.yaml` / `dependencies.yaml`、出典 E-9）付きの定義データとして
      保持し、費目をその定義に従って分類する（R1-1, R1-9）。
    - Secrets Manager を `${Env}/portfolio/secret` の 1 Secret 分（USD 0.40）
      のみ個別算出で算入する（R1-2、E-1）。
    - 固有分に帰属する税を、税抜総額に対する固有分の比率で比例配分する
      （R1-3）。
    - 含める費目の税抜合計＋Secrets（0.40）＋比例配分税として税込
      Portfolio_Operational_Cost を算出する（R1-1〜R1-4、design「Cost 設計」）。
    - Cost_Budget（税込 USD 10.00、境界値 10.00 を含む）以下かを検証し、超過時は
      超過額（実測値 − 10.00）と費目別内訳を出典付きで記録する（R1-4, R1-6,
      R1-7）。
    - 各費目記録に単位（USD）・出典・税区分（税込／税抜）・分類（含める／除外）を
      付す DM6 記録様式を提供する（R1-8）。
    - 費目 `SnapStart-Cached-GB-S` の実測記録に対応し、目標 USD 0.00 に対する
      超過を検出・記録する（R2-3, R2-4, R2-5、E-1）。

責務外（本モジュールが担わないこと。誠実性のため明記）:
    - AWS 請求 API 等からの実額取得は行わない。実額は呼び出し元（運用担当）が
      AWS 請求の概要から取得して入力する（R1-5、design「Cost 設計」）。設計段階で
      確定できない実額は `undetermined`（本モジュールでは `None`）として扱う。
    - パフォーマンス／コールドスタート実測（tasks 8.2/8.3）、エビデンス記録様式
      （8.4）、非退行検証（8.5）は別モジュールの責務である（SRP）。

フォールバック禁止（出典: `.kiro/steering/principles.md` 第三原則3、`AGENTS.md`、
`requirements.md` R12）:
    未実測値は `None`（= `undetermined`）として伝播させ、推測補完しない。金額が
    1 つでも `undetermined` であれば合計・判定も `undetermined` とし、予算内／
    超過を決めつけない。定義に無い費目は分類できないため、握りつぶさず明示的に
    例外を送出する（ゼロトラスト、第二原則2）。

金額表現:
    金額は誤差を避けるため `decimal.Decimal` で扱い、単位は USD 固定とする。
    未実測は `None` で表す（`Decimal("0.00")` = 確定した 0 と、未実測 `None` を
    明確に区別する）。

実行方法（プロジェクトルートから）:
    python -m scripts.measurement.cost_attribution --self-check
    python -m scripts.measurement.cost_attribution   # 定義と DM6 様式を表示
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

# ------------------------------------------------------------------------------
# 定数（すべて出典付き）。単位は USD 固定。
# ------------------------------------------------------------------------------

# Secrets Manager 1 Secret あたりの単価（USD）。ポートフォリオ固有分は
# `${Env}/portfolio/secret` の 1 Secret 分のみを個別算出で算入する
# （出典: requirements.md E-1「Secrets Manager は 1 Secret あたり USD 0.40」,
# R1-2、design.md「Cost 設計」）。税抜の単価として扱う。
SECRETS_MANAGER_UNIT_PRICE_USD: Decimal = Decimal("0.40")

# Cost_Budget（税込 USD 10.00、境界値 10.00 を含む）。固有分の税は比例配分で
# 算入済みの税込金額と比較する（出典: requirements.md Glossary「Cost_Budget」,
# R1-4, R1-6）。
COST_BUDGET_USD: Decimal = Decimal("10.00")

# SnapStart キャッシュ課金の請求費目名（出典: requirements.md E-1, R2-1, R2-3）。
SNAPSTART_LINE_ITEM_NAME: str = "SnapStart-Cached-GB-S"

# SnapStart 撤廃後の費目 `SnapStart-Cached-GB-S` の目標金額（USD 0.00）
# （出典: requirements.md R2-4）。
SNAPSTART_TARGET_USD: Decimal = Decimal("0.00")

# 未実測（undetermined）を表示する際の文字列（出典: requirements.md R12-3,
# E-7、`.kiro/steering/principles.md` 第一原則）。金額 `None` を推測補完せず
# そのまま「未実測」として提示するために用いる。
UNDETERMINED_LABEL: str = "undetermined"


class TaxClass(Enum):
    """税区分（DM6 の「税区分」列）.

    各費目金額が税込／税抜のいずれであるかを表す（出典: design.md DM6、
    requirements.md R1-8）。比例配分（R1-3）は税抜金額を基礎に行うため、
    含める費目は税抜（`TAX_EXCLUDED`）で保持することを想定する。
    """

    # 税込金額（税を含む）。
    TAX_INCLUDED = "税込"
    # 税抜金額（税を含まない）。
    TAX_EXCLUDED = "税抜"


class AttributionCategory(Enum):
    """Cost_Attribution 上の分類（DM6 の「分類」列）.

    費目が固有・運用として算入対象か、共通利用または開発コストとして除外対象か
    を表す（出典: requirements.md Glossary「Cost_Attribution」, R1-1, R1-8、
    design.md「Cost 設計」）。
    """

    # 含める（固有・運用）: Portfolio_Operational_Cost に算入する。
    INCLUDED = "含める"
    # 除外（共通利用）: Route53 / KMS / 他 Secret / Cost Explorer 等。
    EXCLUDED_COMMON = "除外(共通)"
    # 除外（開発コスト）: CodePipeline / CodeBuild。
    EXCLUDED_DEVELOPMENT = "除外(開発)"


@dataclass(frozen=True, slots=True)
class AttributionRule:
    """費目のコスト帰属判定ルール（1 リソース/費目分）.

    Cost_Attribution の定義（含める／除外）を、根拠出典付きで表す不変データ。
    帰属判定の根拠は `template.yaml` / `dependencies.yaml` が所有・参照する
    リソースである（出典: requirements.md E-9, R1-9）。

    Attributes:
        resource: リソース/費目の識別名（例: "Lambda(DjangoFunction)"）。
        category: Cost_Attribution 上の分類（含める／除外）。
        source: 帰属判定の根拠出典（E-9 に基づくファイル等）。
    """

    # リソース/費目の識別名。
    resource: str
    # Cost_Attribution 上の分類。
    category: AttributionCategory
    # 帰属判定の根拠出典（E-9）。
    source: str


# ------------------------------------------------------------------------------
# Cost_Attribution 定義（含める／除外の集合）。
# 根拠は E-9（`template.yaml` / `dependencies.yaml` が所有・参照するリソース、
# および pipeline.yaml / buildspec.yml）である（出典: requirements.md E-9,
# Glossary「Cost_Attribution」, R1-1, R1-9）。本定義は Cost_Attribution の
# 単一の正本であり、分類はすべて本定義を経由して行う（決めつけ禁止・整合性）。
# ------------------------------------------------------------------------------
COST_ATTRIBUTION_RULES: tuple[AttributionRule, ...] = (
    # 含める（固有・運用）。出典: requirements.md Glossary, R1-1, E-9。
    AttributionRule(
        "Lambda(DjangoFunction/Contact_Function)",
        AttributionCategory.INCLUDED,
        "template.yaml (E-9)",
    ),
    AttributionRule(
        "S3(cobaemon-serverless-portfolio-${Env}-static)",
        AttributionCategory.INCLUDED,
        "dependencies.yaml (E-9)",
    ),
    AttributionRule(
        "API Gateway(DjangoApi/ContactApi)",
        AttributionCategory.INCLUDED,
        "template.yaml (E-9)",
    ),
    AttributionRule(
        "CloudFront(CloudFrontDistribution)",
        AttributionCategory.INCLUDED,
        "template.yaml (E-9)",
    ),
    AttributionRule(
        "CloudWatch Logs(DjangoFunctionLogGroup)",
        AttributionCategory.INCLUDED,
        "template.yaml (E-9)",
    ),
    # Secrets Manager は個別算出で `${Env}/portfolio/secret` の 1 Secret 分
    # （USD 0.40）のみ算入する（出典: requirements.md R1-2, E-1）。
    AttributionRule(
        "Secrets Manager(${Env}/portfolio/secret, 1 Secret)",
        AttributionCategory.INCLUDED,
        "template.yaml (E-9), E-1",
    ),
    # 除外（共通利用）。出典: requirements.md Glossary, R1-1, E-9。
    AttributionRule("Route53", AttributionCategory.EXCLUDED_COMMON, "E-9"),
    AttributionRule("KMS", AttributionCategory.EXCLUDED_COMMON, "E-9"),
    AttributionRule(
        "Secrets Manager(他 Secret)",
        AttributionCategory.EXCLUDED_COMMON,
        "E-9",
    ),
    AttributionRule("Cost Explorer", AttributionCategory.EXCLUDED_COMMON, "E-9"),
    # 除外（開発コスト）。出典: requirements.md Glossary, R1-1, E-9。
    AttributionRule(
        "CodePipeline",
        AttributionCategory.EXCLUDED_DEVELOPMENT,
        "pipeline.yaml (E-9)",
    ),
    AttributionRule(
        "CodeBuild",
        AttributionCategory.EXCLUDED_DEVELOPMENT,
        "buildspec.yml (E-9)",
    ),
)

# 分類の高速参照用インデックス（リソース識別名 → ルール）。定義の単一正本
# `COST_ATTRIBUTION_RULES` から構築し、二重管理を避ける（整合性）。
_RULES_BY_RESOURCE: dict[str, AttributionRule] = {
    rule.resource: rule for rule in COST_ATTRIBUTION_RULES
}


def classify(resource: str) -> AttributionRule:
    """リソース/費目名を Cost_Attribution 定義に従って分類する.

    分類は定義の正本 `COST_ATTRIBUTION_RULES`（根拠 E-9）を経由して行い、
    決めつけない（出典: requirements.md R1-1, R1-9、第四原則3）。定義に存在しない
    費目は帰属を推測補完できないため、握りつぶさず明示的に例外を送出する
    （フォールバック禁止・ゼロトラスト、出典: 第三原則3、第二原則2）。

    Args:
        resource: 分類対象のリソース/費目識別名。

    Returns:
        AttributionRule: 当該費目の帰属ルール（分類と出典を含む）。

    Raises:
        KeyError: `resource` が Cost_Attribution 定義に存在しない場合。
            推測で分類せず、定義への追記（E-9 の根拠付き）を促す。
    """
    # 定義に無い費目は推測分類しない。事実として「定義未登録」を明示的に失敗
    # 報告し、E-9 を根拠に COST_ATTRIBUTION_RULES へ追記する運用へ誘導する。
    if resource not in _RULES_BY_RESOURCE:
        raise KeyError(
            f"Cost_Attribution 定義に未登録の費目です: {resource!r}。"
            "推測分類は行いません。E-9 を根拠に COST_ATTRIBUTION_RULES へ"
            "追記してください。"
        )
    return _RULES_BY_RESOURCE[resource]


@dataclass(frozen=True, slots=True)
class CostLineItem:
    """コスト記録の 1 行（DM6 記録様式）.

    DM6 の各列（費目／金額(USD)／税区分／分類／出典）を保持する不変データ
    （出典: design.md「Data Models > DM6」、requirements.md R1-8）。金額は単位
    USD 固定で、未実測は `None`（= `undetermined`）として推測補完しない
    （フォールバック禁止、出典: R12-3、第三原則3）。

    Attributes:
        item: 費目（DM6「費目」）。例: "Lambda", "SnapStart-Cached-GB-S"。
        amount_usd: 金額（DM6「金額(USD)」、単位 USD）。未実測は `None`。
        tax_class: 税区分（DM6「税区分」、税込／税抜）。
        category: 分類（DM6「分類」、含める／除外）。
        source: 出典（DM6「出典」、AWS 請求の概要の該当月・ファイル等）。
    """

    # 費目名（DM6「費目」）。
    item: str
    # 金額（USD）。未実測は None（undetermined）として扱う（推測しない）。
    amount_usd: Decimal | None
    # 税区分（DM6「税区分」）。
    tax_class: TaxClass
    # 分類（DM6「分類」）。
    category: AttributionCategory
    # 出典（DM6「出典」）。
    source: str


def secrets_line_item(
    source: str = "template.yaml (E-9), E-1",
) -> CostLineItem:
    """Secrets Manager の個別算出行（1 Secret 分 USD 0.40）を生成する.

    Portfolio_Operational_Cost は Secrets Manager について
    `${Env}/portfolio/secret` の 1 Secret 分（USD 0.40）のみを個別算出で算入し、
    他 Secret を算入しない（出典: requirements.md R1-2, E-1）。本値は請求実額では
    なく単価に基づく個別算出であり税抜として扱う（比例配分税は別途 R1-3）。

    Args:
        source: 出典（既定は E-9/E-1 の根拠）。

    Returns:
        CostLineItem: Secrets Manager（1 Secret 分・USD 0.40・税抜・含める）の
            DM6 記録行。
    """
    # 1 Secret 分の単価 USD 0.40 を確定値として算入する（推測ではない）。
    return CostLineItem(
        item="Secrets Manager(${Env}/portfolio/secret, 1 Secret)",
        amount_usd=SECRETS_MANAGER_UNIT_PRICE_USD,
        tax_class=TaxClass.TAX_EXCLUDED,
        category=AttributionCategory.INCLUDED,
        source=source,
    )


def sum_included_pretax(line_items: Iterable[CostLineItem]) -> Decimal | None:
    """含める費目の税抜金額を合計する（未実測が 1 件でもあれば undetermined）.

    Portfolio_Operational_Cost の税抜基礎額として、分類が「含める」の費目金額を
    合計する（出典: requirements.md R1-1、design.md「Cost 設計」の算出式
    `Σ(含める費目の税抜金額) + Secrets(0.40)`。Secrets 行も含める費目として
    合計に含めるため、Secrets を別途加算しない）。

    フォールバック禁止（出典: 第三原則3、R12-3）: 含める費目のいずれかの金額が
    `None`（未実測）の場合、合計を確定できないため `None` を返し、0 等で補完
    しない。税込金額（`TAX_INCLUDED`）が混入した場合は比例配分（税抜基礎）と
    矛盾するため、握りつぶさず例外を送出する（ゼロトラスト・整合性）。

    Args:
        line_items: DM6 記録行の反復可能。含める／除外が混在してよい
            （除外行は合計から自然に除かれる）。

    Returns:
        Decimal | None: 含める費目の税抜合計（USD）。未実測が含まれる場合は
            `None`（undetermined）。

    Raises:
        ValueError: 含める費目に税込金額（`TAX_INCLUDED`）が含まれる場合。
            税抜基礎の比例配分（R1-3）と矛盾するため明示的に失敗させる。
    """
    total = Decimal("0")
    # 未実測（None）を 1 件でも検出したら合計を undetermined とするフラグ。
    has_undetermined = False
    for item in line_items:
        # 除外費目は Portfolio_Operational_Cost に算入しない（R1-1）。
        if item.category is not AttributionCategory.INCLUDED:
            continue
        # 含める費目は税抜で保持されている前提。税込混入は矛盾として失敗させる。
        if item.tax_class is TaxClass.TAX_INCLUDED:
            raise ValueError(
                f"含める費目 {item.item!r} が税込で与えられました。"
                "比例配分（R1-3）は税抜金額を基礎とするため、税抜金額で"
                "与えてください。"
            )
        # 未実測は補完せず、undetermined として合計全体へ伝播させる。
        if item.amount_usd is None:
            has_undetermined = True
            continue
        total += item.amount_usd
    # 未実測が含まれる場合は合計を確定できない（推測補完しない）。
    if has_undetermined:
        return None
    return total


def allocate_tax_proportionally(
    total_tax_usd: Decimal | None,
    portfolio_pretax_usd: Decimal | None,
    total_pretax_usd: Decimal | None,
) -> Decimal | None:
    """固有分に帰属する税を税抜総額に対する固有分比率で比例配分する（R1-3）.

    比例配分税 = `total_tax_usd × (portfolio_pretax_usd / total_pretax_usd)`
    と定義する（出典: requirements.md R1-3「固有分に帰属する税を、税込金額に
    対する固有分の比率で比例配分」、design.md「Cost 設計」の算出式に含まれる
    「比例配分税」）。比率は税抜金額を基礎に算出する（比例配分の基礎は税抜、
    R1-3 と整合）。

    フォールバック禁止（出典: 第三原則3、R12-3）: いずれかの入力が `None`
    （未実測）の場合、税を確定できないため `None` を返し推測補完しない。
    ゼロトラスト（第二原則2）: 負値や、税があるのに税抜総額が 0 といった算術的に
    不整合な入力は握りつぶさず例外を送出する。

    Args:
        total_tax_usd: 当該月の税総額（USD、AWS 請求の概要由来）。未実測は
            `None`。
        portfolio_pretax_usd: 固有分（含める費目）の税抜合計（USD）。未実測は
            `None`。
        total_pretax_usd: 課税対象の税抜総額（USD、アカウント全体）。未実測は
            `None`。

    Returns:
        Decimal | None: 固有分へ比例配分された税額（USD）。入力に未実測が
            含まれる場合は `None`（undetermined）。

    Raises:
        ValueError: いずれかの金額が負値の場合、または税抜総額が 0 かつ税が
            正値（配分不能）の場合、あるいは固有分税抜が総額税抜を超える場合。
    """
    # 未実測が 1 つでもあれば税を確定できない（推測しない）。
    if (
        total_tax_usd is None
        or portfolio_pretax_usd is None
        or total_pretax_usd is None
    ):
        return None
    # ゼロトラスト: 負値は請求金額として不正であり握りつぶさない。
    if total_tax_usd < 0 or portfolio_pretax_usd < 0 or total_pretax_usd < 0:
        raise ValueError(
            "税・税抜金額に負値が与えられました（"
            f"税={total_tax_usd}, 固有分税抜={portfolio_pretax_usd}, "
            f"総額税抜={total_pretax_usd}）。"
        )
    # 固有分税抜が総額税抜を超えるのは論理矛盾であり握りつぶさない。
    if portfolio_pretax_usd > total_pretax_usd:
        raise ValueError(
            "固有分の税抜合計が課税対象の税抜総額を超えています（"
            f"固有分税抜={portfolio_pretax_usd} > 総額税抜={total_pretax_usd}）。"
        )
    # 税抜総額が 0 の場合、比率は算出不能。税も 0 なら配分税 0、税が正値なら矛盾。
    if total_pretax_usd == 0:
        if total_tax_usd == 0:
            return Decimal("0")
        raise ValueError(
            "課税対象の税抜総額が 0 なのに税が正値です（配分不能）: "
            f"税={total_tax_usd}。"
        )
    # 税抜金額を基礎とした固有分比率で税を比例配分する（R1-3）。Decimal 除算の
    # 精度は既定コンテキストに従い、丸めによる推測を避けるため量子化しない。
    return total_tax_usd * (portfolio_pretax_usd / total_pretax_usd)


@dataclass(frozen=True, slots=True)
class TaxContext:
    """比例配分税の算出に用いる当該月の税・税抜総額コンテキスト（R1-3）.

    固有分に帰属する税は、税抜総額に対する固有分の比率で比例配分する（出典:
    requirements.md R1-3、design.md「Cost 設計」）。その配分に必要なアカウント
    全体の値（当該月の税総額・課税対象の税抜総額）と出典を保持する不変データ。
    未実測は `None`（= `undetermined`）として保持し推測補完しない（R12-3）。

    Attributes:
        total_tax_usd: 当該月の税総額（USD、AWS 請求の概要由来）。未実測は `None`。
        total_pretax_usd: 課税対象の税抜総額（USD、アカウント全体）。未実測は
            `None`。
        source: 出典（AWS 請求の概要の該当月）。
    """

    # 当該月の税総額（USD）。未実測は None（undetermined）。
    total_tax_usd: Decimal | None
    # 課税対象の税抜総額（USD、アカウント全体）。未実測は None。
    total_pretax_usd: Decimal | None
    # 出典（AWS 請求の概要 該当月）。
    source: str


@dataclass(frozen=True, slots=True)
class PortfolioOperationalCost:
    """Portfolio_Operational_Cost の算出結果（税込合計と内訳）.

    含める費目の税抜合計、比例配分税、税込合計、および費目別内訳（含める費目の
    DM6 記録行）を保持する不変データ（出典: requirements.md R1-1〜R1-4, R1-7,
    R1-8、design.md「Cost 設計」の算出式
    `Portfolio_Operational_Cost = Σ(含める費目の税抜金額) + Secrets(0.40)
    + 比例配分税`）。未実測が含まれる場合は該当値を `None`（undetermined）とし、
    税込合計も `None` とする（推測補完しない、R12-3）。

    Attributes:
        included_line_items: 含める費目の DM6 記録行（費目別内訳、R1-7）。
        included_pretax_usd: 含める費目の税抜合計（USD）。未実測時は `None`。
        allocated_tax_usd: 固有分へ比例配分された税額（USD）。未実測時は `None`。
        total_usd: 税込 Portfolio_Operational_Cost（USD）。未実測時は `None`。
        tax_context: 比例配分に用いた税コンテキスト（出典保持）。
    """

    # 含める費目の DM6 記録行（費目別内訳、R1-7）。
    included_line_items: tuple[CostLineItem, ...]
    # 含める費目の税抜合計（USD）。未実測時は None。
    included_pretax_usd: Decimal | None
    # 比例配分された税額（USD）。未実測時は None。
    allocated_tax_usd: Decimal | None
    # 税込 Portfolio_Operational_Cost（USD）。未実測時は None。
    total_usd: Decimal | None
    # 比例配分に用いた税コンテキスト（出典保持）。
    tax_context: TaxContext


def compute_portfolio_operational_cost(
    line_items: Iterable[CostLineItem],
    tax_context: TaxContext,
) -> PortfolioOperationalCost:
    """含める費目と税コンテキストから税込 Portfolio_Operational_Cost を算出する.

    算出式（出典: design.md「Cost 設計」、requirements.md R1-1〜R1-4）:
    `Portfolio_Operational_Cost = Σ(含める費目の税抜金額) + 比例配分税`。
    Secrets Manager（USD 0.40）は `secrets_line_item()` により「含める」費目の
    記録行として `line_items` に含めて渡すことで合計へ算入される（二重計上を
    避けるため本関数内で別途加算しない、R1-2）。比例配分税は税抜総額に対する
    固有分（含める費目税抜合計）の比率で算出する（R1-3）。

    フォールバック禁止（出典: 第三原則3、R12-3）: 含める費目に未実測（`None`）が
    含まれる、または税コンテキストに未実測が含まれる場合、税込合計は確定できない
    ため `total_usd=None`（undetermined）とし、0 等で補完しない。

    Args:
        line_items: DM6 記録行の反復可能（含める／除外が混在してよい。除外行は
            合計から自然に除かれる）。
        tax_context: 当該月の税・税抜総額コンテキスト（比例配分用）。

    Returns:
        PortfolioOperationalCost: 税抜合計・比例配分税・税込合計・費目別内訳。

    Raises:
        ValueError: 含める費目に税込金額が混入している場合（sum_included_pretax
            由来）、または比例配分の入力が算術的に不整合な場合
            （allocate_tax_proportionally 由来）。握りつぶさない。
    """
    # 反復可能を一度だけ実体化し、複数回走査（内訳抽出・合計）で消費されないように
    # する（ジェネレータ入力にも対応）。
    materialized = tuple(line_items)
    # 費目別内訳（R1-7）として「含める」費目の記録行のみを保持する。
    included = tuple(
        item
        for item in materialized
        if item.category is AttributionCategory.INCLUDED
    )
    # 含める費目の税抜合計（未実測が含まれれば None）。
    pretax = sum_included_pretax(materialized)
    # 固有分に帰属する税を比例配分（未実測が含まれれば None）。
    allocated_tax = allocate_tax_proportionally(
        tax_context.total_tax_usd,
        pretax,
        tax_context.total_pretax_usd,
    )
    # 税抜合計・比例配分税のいずれかが未実測なら税込合計も未実測（推測しない）。
    if pretax is None or allocated_tax is None:
        total = None
    else:
        total = pretax + allocated_tax
    return PortfolioOperationalCost(
        included_line_items=included,
        included_pretax_usd=pretax,
        allocated_tax_usd=allocated_tax,
        total_usd=total,
        tax_context=tax_context,
    )


@dataclass(frozen=True, slots=True)
class BudgetEvaluation:
    """Cost_Budget（税込 USD 10.00）に対する予算判定と超過内訳（R1-4, R1-6, R1-7）.

    税込 Portfolio_Operational_Cost が Cost_Budget（境界値 USD 10.00 を含む）以下
    かを判定し、超過時は超過額（実測値 − 10.00）と費目別内訳を保持する（出典:
    requirements.md R1-4, R1-6, R1-7）。税込合計が未実測（`None`）の場合は予算内
    ／超過を決めつけず `within_budget=None` とする（R12-3、決めつけ禁止）。

    Attributes:
        cost: 算出済み Portfolio_Operational_Cost（内訳・出典を含む）。
        budget_usd: Cost_Budget（USD 10.00、境界値含む）。
        within_budget: 予算内（`total <= 10.00`）なら `True`、超過なら `False`、
            未実測なら `None`。
        excess_usd: 超過額（USD、超過時のみ = 税込合計 − 10.00）。それ以外は
            `None`。
        excess_breakdown: 超過時の費目別内訳（含める費目の DM6 記録行、出典付き、
            R1-7）。超過がない／未実測の場合は空タプル。
    """

    # 算出済み Portfolio_Operational_Cost。
    cost: PortfolioOperationalCost
    # Cost_Budget（USD 10.00、境界値含む）。
    budget_usd: Decimal
    # 予算内=True / 超過=False / 未実測=None。
    within_budget: bool | None
    # 超過額（USD、超過時のみ）。それ以外は None。
    excess_usd: Decimal | None
    # 超過時の費目別内訳（出典付き、R1-7）。
    excess_breakdown: tuple[CostLineItem, ...]


def evaluate_budget(cost: PortfolioOperationalCost) -> BudgetEvaluation:
    """税込 Portfolio_Operational_Cost を Cost_Budget（USD 10.00）と照合する.

    Cost_Budget は税込 USD 10.00 で境界値 10.00 を含む（出典: requirements.md
    Glossary「Cost_Budget」, R1-4, R1-6）。超過時は超過額（実測値 − 10.00）と
    費目別内訳を出典付きで保持し、是正要件起票の根拠とする（R1-7）。

    フォールバック禁止・決めつけ禁止（出典: 第三原則3、R12-3、第四原則3）:
    税込合計が未実測（`None`）の場合は予算内／超過を判定せず `within_budget=None`
    とし、超過額・内訳を付さない。

    Args:
        cost: 算出済み Portfolio_Operational_Cost。

    Returns:
        BudgetEvaluation: 予算判定（内／超過／未実測）・超過額・費目別内訳。
    """
    total = cost.total_usd
    # 税込合計が未実測なら予算内／超過を決めつけない（R12-3）。
    if total is None:
        return BudgetEvaluation(
            cost=cost,
            budget_usd=COST_BUDGET_USD,
            within_budget=None,
            excess_usd=None,
            excess_breakdown=(),
        )
    # 境界値 USD 10.00 を含めて予算内と判定する（R1-4, R1-6）。
    if total <= COST_BUDGET_USD:
        return BudgetEvaluation(
            cost=cost,
            budget_usd=COST_BUDGET_USD,
            within_budget=True,
            excess_usd=None,
            excess_breakdown=(),
        )
    # 超過時は超過額（実測値 − 10.00）と費目別内訳（出典付き）を記録する（R1-7）。
    return BudgetEvaluation(
        cost=cost,
        budget_usd=COST_BUDGET_USD,
        within_budget=False,
        excess_usd=total - COST_BUDGET_USD,
        excess_breakdown=cost.included_line_items,
    )


@dataclass(frozen=True, slots=True)
class SnapStartEvaluation:
    """費目 `SnapStart-Cached-GB-S` の実測記録と目標（USD 0.00）判定.

    SnapStart 撤廃後、当該費目は USD 0.00 であるべきであり（R2-4）、実測額を
    記録し目標超過を検出する（出典: requirements.md R2-3, R2-4, R2-5、E-1）。
    未実測の場合は達成／未達を決めつけず `meets_target=None` とする（R12-3、
    決めつけ禁止）。

    Attributes:
        line_item: DM6 記録行（費目 `SnapStart-Cached-GB-S`）。
        target_usd: 目標金額（USD 0.00、R2-4）。
        meets_target: 目標達成（`amount <= 0.00`）なら `True`、超過なら `False`、
            未実測なら `None`。
        excess_usd: 目標超過額（USD、超過時のみ = 実測額 − 0.00）。それ以外は
            `None`。
    """

    # DM6 記録行（費目 SnapStart-Cached-GB-S）。
    line_item: CostLineItem
    # 目標金額（USD 0.00、R2-4）。
    target_usd: Decimal
    # 目標達成=True / 超過=False / 未実測=None。
    meets_target: bool | None
    # 目標超過額（USD、超過時のみ）。それ以外は None。
    excess_usd: Decimal | None


def evaluate_snapstart(
    amount_usd: Decimal | None,
    source: str,
) -> SnapStartEvaluation:
    """費目 `SnapStart-Cached-GB-S` の実測額を記録し目標超過を判定する（R2-3〜R2-5）.

    SnapStart 撤廃後の当該費目は USD 0.00 が目標であり（R2-4）、実測額を単位 USD
    で記録する（R2-3）。実測額が USD 0.00 を超過した場合は超過額を保持し、是正
    要件起票の根拠とする（R2-5）。ゼロトラスト（第二原則2）: 負の請求額は不正
    として握りつぶさず例外を送出する。

    フォールバック禁止・決めつけ禁止（出典: 第三原則3、R12-3、第四原則3）:
    未実測（`None`）の場合は達成／未達を判定せず `meets_target=None` とする。

    Args:
        amount_usd: 当該月の費目 `SnapStart-Cached-GB-S` の実測額（USD）。
            未実測は `None`。
        source: 出典（AWS 請求の概要の該当月）。

    Returns:
        SnapStartEvaluation: 実測記録行・目標・達成判定・超過額。

    Raises:
        ValueError: 実測額が負値の場合（請求額として不正であり握りつぶさない）。
    """
    # ゼロトラスト: 負の請求額は不正であり明示的に失敗させる。
    if amount_usd is not None and amount_usd < 0:
        raise ValueError(
            f"SnapStart-Cached-GB-S の実測額が負値です: {amount_usd}。"
        )
    # DM6 記録行を構築する。当該費目は Lambda の請求費目であり分類は「含める」。
    line_item = CostLineItem(
        item=SNAPSTART_LINE_ITEM_NAME,
        amount_usd=amount_usd,
        tax_class=TaxClass.TAX_EXCLUDED,
        category=AttributionCategory.INCLUDED,
        source=source,
    )
    # 未実測は達成／未達を決めつけない（R12-3）。
    if amount_usd is None:
        return SnapStartEvaluation(
            line_item=line_item,
            target_usd=SNAPSTART_TARGET_USD,
            meets_target=None,
            excess_usd=None,
        )
    # 目標 USD 0.00 以下なら達成（R2-4）。超過時は超過額を記録する（R2-5）。
    if amount_usd <= SNAPSTART_TARGET_USD:
        return SnapStartEvaluation(
            line_item=line_item,
            target_usd=SNAPSTART_TARGET_USD,
            meets_target=True,
            excess_usd=None,
        )
    return SnapStartEvaluation(
        line_item=line_item,
        target_usd=SNAPSTART_TARGET_USD,
        meets_target=False,
        excess_usd=amount_usd - SNAPSTART_TARGET_USD,
    )


def build_included_line_items(
    amounts: Mapping[str, Decimal | None],
    source: str,
) -> tuple[CostLineItem, ...]:
    """含める費目（Secrets を除く）の税抜金額から DM6 記録行を構築する.

    Lambda / S3 / API Gateway / CloudFront / CloudWatch Logs といった含める費目の
    税抜実額（AWS 請求の概要由来）を DM6 記録行へ変換するヘルパー（出典:
    requirements.md R1-1, R1-8、design.md DM6）。Secrets Manager は個別算出
    （`secrets_line_item()`）で別途扱うため本ヘルパーの対象外とし、二重計上を
    避ける（R1-2）。

    ゼロトラスト（第二原則2）: 与えられた費目名は Cost_Attribution 定義に存在し
    かつ分類が「含める」であることを `classify` 経由で検証する。定義外・除外費目は
    握りつぶさず例外を送出する（推測分類しない）。未実測額は `None`（undetermined）
    のまま行に保持する（推測補完しない、R12-3）。

    Args:
        amounts: 費目識別名 → 税抜金額（USD、未実測は `None`）のマッピング。
        source: 出典（AWS 請求の概要の該当月）。

    Returns:
        tuple[CostLineItem, ...]: 含める費目の DM6 記録行（税抜・含める）。

    Raises:
        KeyError: 費目名が Cost_Attribution 定義に存在しない場合（classify 由来）。
        ValueError: 費目が「含める」分類でない、または Secrets（個別算出対象）を
            本ヘルパーへ渡した場合（二重計上防止のため明示的に失敗させる）。
    """
    items: list[CostLineItem] = []
    for resource, amount in amounts.items():
        # 定義を経由して分類を確定する（推測しない）。未登録は classify が失敗。
        rule = classify(resource)
        # 除外費目は算入対象でないため、含める費目ビルダーへの混入を失敗させる。
        if rule.category is not AttributionCategory.INCLUDED:
            raise ValueError(
                f"費目 {resource!r} は分類 {rule.category.value!r} であり"
                "「含める」ではありません。除外費目は算入しません（R1-1）。"
            )
        # Secrets は個別算出（0.40）で別途扱うため、本ヘルパーでは受け付けない。
        if resource == "Secrets Manager(${Env}/portfolio/secret, 1 Secret)":
            raise ValueError(
                "Secrets Manager は個別算出（secrets_line_item）で算入します。"
                "二重計上を避けるため build_included_line_items へ渡さないで"
                "ください（R1-2）。"
            )
        items.append(
            CostLineItem(
                item=resource,
                amount_usd=amount,
                tax_class=TaxClass.TAX_EXCLUDED,
                category=AttributionCategory.INCLUDED,
                source=source,
            )
        )
    return tuple(items)


def format_amount_usd(amount_usd: Decimal | None) -> str:
    """金額を「単位付き文字列」または `undetermined` として整形する（R1-8, R12-3）.

    確定額は単位 USD を明示して整形し、未実測（`None`）は推測せず
    `undetermined` と表記する（出典: requirements.md R1-8「各費目の金額に単位
    （USD）」, R12-3、第三原則3）。

    Args:
        amount_usd: 金額（USD）。未実測は `None`。

    Returns:
        str: 例 "USD 0.40"、未実測は "undetermined"。
    """
    # 未実測は 0 等で補完せず、そのまま undetermined と表記する（推測禁止）。
    if amount_usd is None:
        return UNDETERMINED_LABEL
    return f"USD {amount_usd}"


def render_attribution_definition() -> str:
    """Cost_Attribution 定義（含める／除外）を出典付きの表として整形する.

    Cost_Attribution の正本 `COST_ATTRIBUTION_RULES`（根拠 E-9）を、リソース／
    分類／出典の表として可読出力する（出典: requirements.md R1-1, R1-9、
    design.md「Cost 設計」）。

    Returns:
        str: 定義表（ヘッダ行 + 各ルール行）。
    """
    # DM6 の「分類」「出典」に対応する定義表を組み立てる。
    lines = [
        "Cost_Attribution 定義（根拠: E-9 template.yaml / dependencies.yaml）",
        "| リソース/費目 | 分類 | 出典 |",
        "| --- | --- | --- |",
    ]
    for rule in COST_ATTRIBUTION_RULES:
        lines.append(f"| {rule.resource} | {rule.category.value} | {rule.source} |")
    return "\n".join(lines)


def render_record_table(line_items: Iterable[CostLineItem]) -> str:
    """DM6 記録様式（費目／金額(USD)／税区分／分類／出典）の表を整形する.

    各費目記録に単位（USD）・出典・税区分・分類を付す DM6 様式で出力する
    （出典: design.md「Data Models > DM6」、requirements.md R1-8）。未実測額は
    `undetermined` と表記する（推測補完しない、R12-3）。

    Args:
        line_items: DM6 記録行の反復可能。

    Returns:
        str: DM6 記録表（ヘッダ行 + 各費目行）。
    """
    # DM6 の列順（費目／金額(USD)／税区分／分類／出典）でヘッダを構成する。
    lines = [
        "| 費目 | 金額(USD) | 税区分 | 分類 | 出典 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in line_items:
        lines.append(
            f"| {item.item} | {format_amount_usd(item.amount_usd)} "
            f"| {item.tax_class.value} | {item.category.value} | {item.source} |"
        )
    return "\n".join(lines)


def _self_check() -> None:
    """本モジュールの内部不変条件を自己検証する（実請求値は用いない）.

    CLI の `--self-check` から呼び出され、分類・比例配分・予算境界・SnapStart
    判定・未実測伝播といった算出ロジックの不変条件を、明示的なサンプル入力
    （実請求ではないと明記）に対して検証する（出典: requirements.md R1-1〜R1-4,
    R1-6, R1-7, R2-3〜R2-5、design.md「Cost 設計」）。実請求の実額はここで扱わず、
    未実測は `undetermined` として伝播することのみを確認する（推測禁止、R12-3）。

    Raises:
        AssertionError: いずれかの不変条件が満たされない場合（握りつぶさない）。
    """
    # 1) 分類が定義（E-9）どおりであること（含める／除外）。
    assert classify("Lambda(DjangoFunction/Contact_Function)").category is (
        AttributionCategory.INCLUDED
    )
    assert classify("Route53").category is AttributionCategory.EXCLUDED_COMMON
    assert classify("CodeBuild").category is AttributionCategory.EXCLUDED_DEVELOPMENT

    # 2) 定義外費目は推測分類せず KeyError で失敗すること（フォールバック禁止）。
    try:
        classify("未知の費目")
    except KeyError:
        pass
    else:
        raise AssertionError("定義外費目が KeyError を送出しませんでした。")

    # 3) Secrets は 1 Secret 分 USD 0.40・税抜・含めるであること（R1-2）。
    secrets = secrets_line_item()
    assert secrets.amount_usd == Decimal("0.40")
    assert secrets.tax_class is TaxClass.TAX_EXCLUDED
    assert secrets.category is AttributionCategory.INCLUDED

    # 4) 含める費目に未実測が 1 件でもあれば税抜合計は undetermined（推測禁止）。
    #    以下はサンプル入力であり実請求値ではない。
    undetermined_items = build_included_line_items(
        {"Lambda(DjangoFunction/Contact_Function)": None}, "サンプル(実請求ではない)"
    )
    assert sum_included_pretax((*undetermined_items, secrets)) is None

    # 5) 比例配分税の算術: 税 1.00・固有分税抜 2・総額税抜 10 → 0.20（R1-3）。
    assert allocate_tax_proportionally(
        Decimal("1.00"), Decimal("2"), Decimal("10")
    ) == Decimal("0.20")
    # 入力に未実測が含まれれば比例配分税も undetermined。
    assert allocate_tax_proportionally(None, Decimal("2"), Decimal("10")) is None

    # 6) 予算境界: 10.00 は予算内（境界値含む）、10.01 は超過（超過額 0.01・内訳有）。
    #    以下はサンプルであり実請求値ではない（R1-4, R1-6, R1-7 の境界検証のみ）。
    boundary_items = (
        CostLineItem(
            "Lambda(DjangoFunction/Contact_Function)",
            Decimal("10.00"),
            TaxClass.TAX_EXCLUDED,
            AttributionCategory.INCLUDED,
            "サンプル(実請求ではない)",
        ),
    )
    boundary_cost = compute_portfolio_operational_cost(
        boundary_items,
        TaxContext(Decimal("0"), Decimal("100"), "サンプル(実請求ではない)"),
    )
    boundary_eval = evaluate_budget(boundary_cost)
    assert boundary_eval.within_budget is True
    assert boundary_eval.excess_usd is None

    over_items = (
        CostLineItem(
            "Lambda(DjangoFunction/Contact_Function)",
            Decimal("10.01"),
            TaxClass.TAX_EXCLUDED,
            AttributionCategory.INCLUDED,
            "サンプル(実請求ではない)",
        ),
    )
    over_cost = compute_portfolio_operational_cost(
        over_items,
        TaxContext(Decimal("0"), Decimal("100"), "サンプル(実請求ではない)"),
    )
    over_eval = evaluate_budget(over_cost)
    assert over_eval.within_budget is False
    assert over_eval.excess_usd == Decimal("0.01")
    assert len(over_eval.excess_breakdown) == 1

    # 7) 税込合計が未実測なら予算内/超過を決めつけない（within_budget=None）。
    undetermined_cost = compute_portfolio_operational_cost(
        undetermined_items,
        TaxContext(Decimal("1.00"), Decimal("100"), "サンプル(実請求ではない)"),
    )
    assert evaluate_budget(undetermined_cost).within_budget is None

    # 8) SnapStart: 0.00 は達成、超過は超過額を記録、未実測は決めつけない
    #    （R2-3, R2-4, R2-5、R12-3）。
    assert evaluate_snapstart(Decimal("0.00"), "サンプル").meets_target is True
    over_snap = evaluate_snapstart(Decimal("15.61"), "サンプル")
    assert over_snap.meets_target is False
    assert over_snap.excess_usd == Decimal("15.61")
    assert evaluate_snapstart(None, "サンプル").meets_target is None


def main(argv: list[str] | None = None) -> int:
    """CLI エントリポイント（定義/DM6 様式の表示、または自己検証）.

    引数なしの場合は Cost_Attribution 定義（E-9）と DM6 記録様式を、含める費目の
    実額を未実測（`undetermined`）として表示する（実額は運用担当が AWS 請求から
    取得して入力する事項であり、本モジュールは推測補完しない、出典: R1-5, R12-3）。
    `--self-check` の場合は内部不変条件を検証する。

    Args:
        argv: コマンドライン引数（省略時は `sys.argv[1:]` を使用）。

    Returns:
        int: 終了コード（0=成功、1=自己検証失敗）。
    """
    parser = argparse.ArgumentParser(
        prog="cost_attribution",
        description=(
            "Cost_Attribution 算出・記録（Portfolio_Operational_Cost）。"
            "実額は AWS 請求から取得して入力する。未実測は undetermined。"
        ),
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="算出ロジックの内部不変条件を自己検証する（実請求値は用いない）。",
    )
    args = parser.parse_args(argv)

    if args.self_check:
        # 自己検証。失敗（AssertionError）は握りつぶさず終了コード 1 で報告する。
        try:
            _self_check()
        except AssertionError as exc:
            print(f"[self-check] 失敗: {exc}", file=sys.stderr)
            return 1
        print("[self-check] 成功: Cost_Attribution 算出ロジックの不変条件を確認。")
        return 0

    # 引数なし: 定義（E-9）を表示する。
    print(render_attribution_definition())
    print()
    # DM6 記録様式を、含める費目の実額を未実測として表示する（推測補完しない）。
    # 実額は運用担当が AWS 請求の概要から取得して入力する（R1-5）。
    undetermined_included = build_included_line_items(
        {
            "Lambda(DjangoFunction/Contact_Function)": None,
            "S3(cobaemon-serverless-portfolio-${Env}-static)": None,
            "API Gateway(DjangoApi/ContactApi)": None,
            "CloudFront(CloudFrontDistribution)": None,
            "CloudWatch Logs(DjangoFunctionLogGroup)": None,
        },
        "AWS 請求の概要 該当月（未取得=undetermined）",
    )
    # Secrets は個別算出（USD 0.40）、SnapStart は目標 0.00 に対する未実測行を含める。
    snapshot = evaluate_snapstart(None, "AWS 請求の概要 該当月（未取得=undetermined）")
    record_rows = (
        *undetermined_included,
        secrets_line_item(),
        snapshot.line_item,
    )
    print("DM6 記録様式（金額は未実測のため undetermined。実額は AWS 請求から取得）")
    print(render_record_table(record_rows))
    return 0


if __name__ == "__main__":
    # プロジェクトルートから `python -m scripts.measurement.cost_attribution` 実行。
    raise SystemExit(main())
