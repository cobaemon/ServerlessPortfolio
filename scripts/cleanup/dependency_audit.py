"""旧資産除去（legacy-asset-cleanup）判定層の Dependency_Audit（系統 D）.

目的:
    Dependency_Manifest（`requirements.txt`）上の 1 件の dependency について、
    直接参照の有無・推移要求（要求元）の有無・両確認の実施状態から
    `除去対象` / `保持` / `undetermined` を決定し、Dependency_Manifest と
    License_Ledger（`docs/external-assets.md`）の記載集合の一致を判定する。

    判定に用いるのは引数として渡された値だけであり、`git grep` / `pip` の実行、
    ファイル I/O、`subprocess`、Django、boto3 を一切用いない（出典:
    `.kiro/specs/legacy-asset-cleanup/design.md` C10「系統 D 除去手順（依存関係）」、
    同「Architecture > 依存方向」、同 tasks.md 4.1）。コマンド実行と入出力は
    design.md C13（`scripts/cleanup/cli.py --audit-dependencies`、tasks.md 5.1）
    が担う。`requirements.txt` および `docs/external-assets.md` の行編集は
    tasks.md 12.2 の範囲であり、本モジュールは行わない（単一責務）。

出典:
    - `.kiro/specs/legacy-asset-cleanup/design.md` C10（`decide` /
      `check_ledger_coherence` のシグネチャ、判定規則、正規化規則、確認手順、
      判定対象 12 件）、同「実行環境の差異（系統 D の設計制約）」、
      同 Property 7 / Property 8、同「Error Handling」の C10 該当行。
    - `.kiro/specs/legacy-asset-cleanup/requirements.md` Requirement 7 基準
      1、2、3、4、5、7、11。
    - `scripts/cleanup/models.py`（DM5 の `DependencyCandidate` /
      `DependencyDecision` / `LedgerCoherenceReport`。型は再定義せず再利用する）。
    - `scripts/cleanup/inventory.py`（`DISPOSITION_REMOVAL_TARGET` /
      `DISPOSITION_UNDETERMINED`。R1-3 の扱い語彙を二重定義しないため import
      する。出典: `.kiro/steering/principles.md` 第三原則1・2）。

設計上の制約（出典: `.kiro/steering/principles.md` 第二原則5、第三原則3）:
    - フォールバックを実装しない。いずれかの確認が未実施であれば `undetermined`
      を返し、既定値や推測で扱いを補完しない（R7-4）。
    - 確認未実施であるのに確認結果（一致箇所・要求元）が存在する入力は事実として
      矛盾するため、`ValueError` を送出して表面化させる（ゼロトラスト。未収集の
      証拠に基づく判定を行わない）。
    - `marker` と `resolution_environment` から確認状態を推論しない。marker
      `sys_platform != 'win32'` を持つ 5 件（awsgi / httptools / uvloop /
      websockets / werkzeug）が Windows 環境で解決対象外となる事実（出典:
      design.md「実行環境の差異」）は、`transitive_checked` を偽として記録する
      側（tasks.md 12.1）の責務であり、本モジュールは渡された確認状態のみを
      用いる（決めつけを行わない。第四原則3）。

対応要件: R7-1、R7-2、R7-3、R7-4、R7-5、R7-7、R7-11
（出典: `.kiro/specs/legacy-asset-cleanup/requirements.md` Requirement 7）。
"""

from __future__ import annotations

from .inventory import DISPOSITION_REMOVAL_TARGET, DISPOSITION_UNDETERMINED
from .models import DependencyCandidate, DependencyDecision, LedgerCoherenceReport

# ---------------------------------------------------------------------------
# 判定語彙（C10）
# ---------------------------------------------------------------------------

# C10 の判定語彙は `除去対象` / `保持` / `undetermined` の 3 値である（出典:
# design.md C10「判定規則」、同 Property 7、requirements.md Requirement 7 基準
# 3〜5）。うち `除去対象` と `undetermined` は R1-3 の扱い語彙と同一であるため
# `inventory.py` の定数を再利用する。
#
# 一方 `保持` は依存判定に固有の値であり、R1-3 の 3 値（`除去対象` /
# `保全対象` / `undetermined`）には含まれない。系統 C の「保全対象」（誤除去の
# 防止対象。R1-8、R5-1〜R5-4）とは意味が異なり、本値は「Dependency_Manifest に
# 残置する」判定を表す（R7-3、R7-6）。両者を混同しないため別定数として本
# モジュールで定義する。
DISPOSITION_RETAINED = "保持"

# ---------------------------------------------------------------------------
# 判定対象の dependency 集合（R7-11）
# ---------------------------------------------------------------------------

# R7-11 は判定対象集合が E-7 の 12 件を含むことを求める（出典:
# requirements.md Requirement 7 基準 11、design.md C10「判定対象」）。
# 各要素は本モジュールの `normalize_package_name` を適用済みの表記
# （小文字・ハイフン統一）で保持する。以下の行番号は本タスク実施時点の
# `requirements.txt` の実体で再確認した値である。
#
#   awsgi           requirements.txt:2  （marker `sys_platform != 'win32'`）
#   django-allauth  requirements.txt:11
#   django-otp      requirements.txt:14
#   gunicorn        requirements.txt:16
#   httptools       requirements.txt:17 （marker `sys_platform != 'win32'`）
#   mangum          requirements.txt:20
#   psycopg2-binary requirements.txt:25
#   pyjwt           requirements.txt:27
#   qrcode          requirements.txt:30
#   uvloop          requirements.txt:38 （marker `sys_platform != 'win32'`）
#   websockets      requirements.txt:39 （marker `sys_platform != 'win32'`）
#   werkzeug        requirements.txt:40 （marker `sys_platform != 'win32'`）
#
# 本集合は「判定対象が網羅されているか」を確認する側（Inventory の必須キー検証
# `scripts/cleanup/inventory.py` の `REQUIRED_ITEM_KEYS_E7`、および C13
# `--audit-dependencies`）が参照する参照集合である。`decide` は本集合に含まれる
# か否かで振る舞いを変えない（R7 の各基準は「ある dependency」一般に適用される
# ため、対象を暗黙に絞り込まない）。
JUDGEMENT_TARGET_DEPENDENCIES: frozenset[str] = frozenset({
    "awsgi",
    "django-allauth",
    "django-otp",
    "gunicorn",
    "httptools",
    "mangum",
    "psycopg2-binary",
    "pyjwt",
    "qrcode",
    "uvloop",
    "websockets",
    "werkzeug",
})


def normalize_package_name(name: str) -> str:
    """台帳比較用にパッケージ名を正規化する（小文字化・アンダースコアをハイフンへ統一）.

    正規化が必要な理由（出典: design.md C10「正規化」）:
        Dependency_Manifest と License_Ledger は同一パッケージを異なる表記で
        記載している。本タスク実施時点の実体で再確認した差異は次の 2 件である。
            - `docs/external-assets.md:43` は `PyJWT`、`requirements.txt:27` は
              `pyjwt`（design.md C10 が挙げる差異。実体で一致を確認済み）。
            - `docs/external-assets.md:26` は `Django`、`requirements.txt:10` は
              `django`（本タスクで追加確認した同種の差異）。
        表記差を正規化せずに集合比較すると、実体が一致していても R7-7 の整合
        判定が偽となる。

    引数:
        name: 正規化前のパッケージ名。

    戻り値:
        小文字化し、アンダースコア（`_`）をハイフン（`-`）へ置換した名前。

    例外:
        送出しない（純粋な文字列変換であり、全入力に対する全域関数とする）。

    設計との対応:
        design.md C10 が定める変換は「小文字化」と「ハイフン／アンダースコアの
        統一」の 2 点のみである。PEP 503 のようなドット（`.`）や連続する区切り
        文字の畳み込みは行わず、前後の空白除去も行わない。設計に記述のない変換を
        追加すると表記差の検出漏れ（不整合の握りつぶし）になり得るため、変換範囲
        を設計どおりに限定する（第二原則1、第三原則3）。
    """
    return name.lower().replace("_", "-")


def _format_evidence(values: tuple[str, ...]) -> str:
    """判定根拠へ埋め込む出典列を文字列化する（内部関数）.

    引数:
        values: 一致箇所または要求元パッケージ名。

    戻り値:
        `", "` で連結した文字列。

    例外:
        送出しない。

    記録順を並べ替えないのは、`git grep` の出力順や依存グラフ解決の出力順自体が
    出典として意味を持つためである（第一原則3）。
    """
    return ", ".join(values)


def decide(candidate: DependencyCandidate) -> DependencyDecision:
    """直接参照・推移要求・確認状態から 除去対象 / 保持 / undetermined を決める.

    判定規則（出典: design.md C10「判定規則」、同 Property 7、
    requirements.md Requirement 7 基準 1〜5）。上から順に評価する:
        1. 直接参照の一致が 1 件以上 → `保持`（R7-1 の確認結果に基づく）。
        2. 要求元が 1 件以上 → `保持`。判定根拠に要求元パッケージ名を含める
           （R7-3）。この場合は直接参照の確認状態にかかわらず結論が `保持` に
           定まるため `undetermined` としない（R7-4 が `undetermined` を求めるの
           は「要求有無が確認されていない」場合である）。
        3. 直接参照の確認が実施済みで一致 0 件、かつ推移要求の確認が実施済みで
           要求元 0 件 → `除去対象`（R7-5）。
        4. 上記以外（いずれかの確認が未実施）→ `undetermined`（R7-4）。除去は
           保留され、推測で扱いを確定しない。

    引数:
        candidate: 判定対象 1 件の `DependencyCandidate`（DM5）。

    戻り値:
        `DependencyDecision`。`disposition` は `除去対象` / `保持` /
        `undetermined` のいずれか、`reason` は条項識別子・確認状態・出典
        （一致箇所または要求元名、解決環境）を含む判定根拠。

    例外:
        ValueError: 確認未実施であるのに確認結果が存在する入力の場合。
            - `direct_reference_checked` が偽かつ `direct_reference_sources`
              が非空。
            - `transitive_checked` が偽かつ `required_by` が非空。
            いずれも「実施していない確認の結果が存在する」という事実の矛盾で
            あり、未収集の証拠に基づいて判定しないため既定値で補完せず送出する
            （ゼロトラスト、第三原則3）。矛盾の解消は記録側（tasks.md 12.1）が
            行う。
    """
    # 入力の内部矛盾を先に排除する（未実施の確認に結果が存在する状態を判定へ
    # 持ち込まない）。
    if not candidate.direct_reference_checked and candidate.direct_reference_sources:
        raise ValueError(
            f"R7-1 違反: {candidate.name}: direct_reference_checked が偽であるのに "
            f"direct_reference_sources が非空である"
            f"（{_format_evidence(candidate.direct_reference_sources)}）"
        )
    if not candidate.transitive_checked and candidate.required_by:
        raise ValueError(
            f"R7-2 違反: {candidate.name}: transitive_checked が偽であるのに "
            f"required_by が非空である"
            f"（{_format_evidence(candidate.required_by)}）"
        )

    # 解決環境は判定に用いないが、判定根拠の出典として全分岐に残す（第一原則3）。
    environment = f"解決環境: {candidate.resolution_environment}"

    # 規則 1: 直接参照が確認された dependency は Dependency_Manifest に残す。
    if candidate.direct_reference_sources:
        return DependencyDecision(
            name=candidate.name,
            disposition=DISPOSITION_RETAINED,
            reason=(
                f"R7-1: 直接参照あり（一致箇所: "
                f"{_format_evidence(candidate.direct_reference_sources)}、"
                f"{environment}）"
            ),
        )

    # 規則 2: 要求元が 1 件以上あるときは Transitive_Dependency として保持し、
    # 要求元パッケージ名を判定根拠へ含める（R7-3）。
    if candidate.required_by:
        return DependencyDecision(
            name=candidate.name,
            disposition=DISPOSITION_RETAINED,
            reason=(
                f"R7-3: Transitive_Dependency として要求されている（要求元: "
                f"{_format_evidence(candidate.required_by)}、{environment}）"
            ),
        )

    # 規則 3: 両方の確認が実施済みで双方 0 件のときに限り除去対象とする（R7-5）。
    if candidate.direct_reference_checked and candidate.transitive_checked:
        return DependencyDecision(
            name=candidate.name,
            disposition=DISPOSITION_REMOVAL_TARGET,
            reason=(
                "R7-5: 直接参照の確認（R7-1）実施済みで一致 0 件、"
                f"かつ推移要求の確認（R7-2）実施済みで要求元 0 件（{environment}）"
            ),
        )

    # 規則 4: いずれかの確認が未実施であれば undetermined とし、除去を保留する
    # （R7-4）。未実施の確認を列挙し、確定に必要な作業を出典として残す。
    unchecked: list[str] = []
    if not candidate.direct_reference_checked:
        unchecked.append("R7-1: 直接参照の確認（git grep）が未実施")
    if not candidate.transitive_checked:
        unchecked.append("R7-2: 推移要求の確認（依存グラフ解決）が未実施")

    return DependencyDecision(
        name=candidate.name,
        disposition=DISPOSITION_UNDETERMINED,
        reason=f"R7-4: {' / '.join(unchecked)}（{environment}）",
    )


def check_ledger_coherence(
    manifest_names: frozenset[str], ledger_names: frozenset[str]
) -> LedgerCoherenceReport:
    """Dependency_Manifest と License_Ledger の記載集合の一致を判定する.

    判定内容（出典: design.md C10「正規化」、同 Property 8、
    requirements.md Requirement 7 基準 7）:
        両集合の各名前へ `normalize_package_name` を適用したうえで比較し、
        完全一致した場合に限り整合（`coherent` が真）と判定する。不一致の場合は
        差分がどちらの側にあるかを列挙し、握りつぶさない（第三原則3）。

    引数:
        manifest_names: Dependency_Manifest（`requirements.txt`）の記載名集合。
        ledger_names: License_Ledger（`docs/external-assets.md`）の記載名集合。

    戻り値:
        `LedgerCoherenceReport`。`manifest_only` は Dependency_Manifest にのみ
        存在する名前、`ledger_only` は License_Ledger にのみ存在する名前で、
        いずれも**正規化後**の表記を昇順で保持する（複数の元表記が同一へ写り得る
        ため正規化前の表記は一意に復元できない。報告順は決定的とする）。
        `coherent` は両差分が空のときに限り真。

    例外:
        送出しない（差分は戻り値で表現する）。

    本関数は判定のみを行い、`requirements.txt` および `docs/external-assets.md`
    の編集は行わない（編集は tasks.md 12.2 の範囲）。不整合を非ゼロ終了へ変換
    するのは C13（`cli.py --audit-dependencies`）の責務である（出典: design.md
    「Error Handling」の「台帳不整合（集合差分あり）」行）。
    """
    normalized_manifest = frozenset(
        normalize_package_name(name) for name in manifest_names
    )
    normalized_ledger = frozenset(
        normalize_package_name(name) for name in ledger_names
    )

    manifest_only = tuple(sorted(normalized_manifest - normalized_ledger))
    ledger_only = tuple(sorted(normalized_ledger - normalized_manifest))

    return LedgerCoherenceReport(
        coherent=not manifest_only and not ledger_only,
        manifest_only=manifest_only,
        ledger_only=ledger_only,
    )
