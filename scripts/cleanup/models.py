"""旧資産除去（legacy-asset-cleanup）判定層のデータモデルと定数.

本モジュールは design.md「Data Models」の DM1〜DM6 を実装し、判定層
（`inventory.py` / `removal_plan.py` / `removal_verification.py` /
`completion.py` / `dependency_audit.py` / `approval.py`）が共有する不変値型と
定数のみを定義する（出典: `.kiro/specs/legacy-asset-cleanup/design.md`
「Data Models」DM1〜DM6、同 tasks.md 1.1）。

設計上の制約（出典: design.md「Architecture > 依存方向」、
`.kiro/steering/principles.md` 第二原則5、第三原則3）:
    - 全モデルを `@dataclass(frozen=True)` とし、意図しない書き換えによる判定
      汚染を防ぐ（出典: design.md「Data Models」冒頭）。
    - 標準ライブラリ `dataclasses` のみを import する。Django・boto3・
      ファイル I/O・`subprocess` を import しない。
    - 既定値を与えない。未確認・判定不能は呼び出し側が `undetermined`
      （`disposition`）または `None`（`confirmation` / `error` など）として
      明示的に渡す。既定値による補完はフォールバックに相当するため行わない。

本モジュールは値の保持のみを担い、検証・判定ロジックを持たない（単一責務。
構造的不変条件の検証は `inventory.py`、各判定は判定モジュールが担う。出典:
design.md「Architecture > 依存方向」の「モジュール分割は責務単位とする」、
同 C2〜C5、C10、C11）。

対応要件: R1-1、R1-2、R1-3、R1-8、R2-10、R4-13、R7-11、R8-7、R8-8、R9-1
（出典: `.kiro/specs/legacy-asset-cleanup/requirements.md`）。
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# DM4 の定数: 破壊的操作の許可対象種別
# ---------------------------------------------------------------------------

# R8-8 は Destructive_Operation の対象を Parameter Store パラメータの削除と
# Secrets Manager シークレットキーの削除に限定する（出典: requirements.md
# Requirement 8 基準 8、design.md DM4）。本集合に含まれない種別は
# `approval.py` の承認判定で実行許可を得られない。
ALLOWED_TARGET_KINDS: frozenset[str] = frozenset({
    "parameter_store_parameter",     # Parameter Store パラメータ削除（R8-8）
    "secrets_manager_secret_key",    # Secrets Manager シークレットキー削除（R8-8）
})

# ---------------------------------------------------------------------------
# DM6 の定数: 系統 B の変更区分と AWS 側対象
# ---------------------------------------------------------------------------

# 系統 B（SMTP 経路）は 8 区分すべてを同一の変更単位として適用する（R4-9）。
# 一部のみが適用された状態は未完了として扱う（R4-10）。区分
# `B-1_prod_settings` は基準 1 の除去（`config/settings/prod.py:72-86`）と
# 基準 17 の `EMAIL_BACKEND` 明示設定の双方を担う（出典: design.md DM6、
# 同 C8「変更単位のスコープに関する整合注記」、requirements.md:220、:221、:225）。
STREAM_B_SEGMENTS: frozenset[str] = frozenset({
    "B-1_prod_settings",       # config/settings/prod.py:72-86 の除去（R4-1）+ EMAIL_BACKEND の console バックエンド明示設定（R4-17）
    "B-2_prod_comment",        # config/settings/prod.py:36-39
    "B-3_dev_settings",        # config/settings/dev.py:4,34-51
    "B-4_forms_log",           # portfolio/forms.py:84-91
    "B-5_forms_exception",     # portfolio/forms.py:93-99
    "B-6_views_callsite",      # portfolio/views.py:22-26,46-54
    "B-7_buildspec",           # buildspec.yml:60-63,84-87
    "B-8_tests_and_docs",      # portfolio/tests/test_regression.py:107-122, docs/*
})

# 系統 B の AWS 側対象 6 件。削除実施前に現存有無を照会して記録する（R4-13）。
# 照会時点で不在であれば削除を実行せず不在確認成立として扱う（R4-16）。
STREAM_B_AWS_TARGETS: frozenset[str] = frozenset({
    "parameter:email_host",
    "parameter:email_port",
    "parameter:email_use_tls",
    "parameter:email_use_ssl",
    "secret:EMAIL_HOST_USER",
    "secret:EMAIL_HOST_PASSWORD",
})

# ---------------------------------------------------------------------------
# DM1. LegacyAssetItem / PreservedAssetItem / Confirmation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Confirmation:
    """参照有無・依存要求有無の確認結果（R9-3、R5-8）.

    属性:
        result: 確認結果の記述。
        evidence_command: 確認に用いた実行コマンド（非空必須）。空文字列は
            `inventory.py` の検証で違反として列挙される。
    """

    result: str
    evidence_command: str


@dataclass(frozen=True)
class LegacyAssetItem:
    """除去対象・保留対象の 1 項目（系統 A / B / D）.

    属性:
        key: 一意識別子（例: `"A1.asgi_lambda"`）。
        description: 対象の説明。
        stream: 系統。`"A"` / `"B"` / `"D"` の排他 1 値（R1-2）。
        disposition: 扱い。`"除去対象"` / `"保全対象"` / `"undetermined"` の
            排他 1 値（R1-3）。
        source_path: 出典のファイルパス（例: `"asgi_lambda.py"`。R1-1）。
        source_lines: 出典の行番号（例: `"6,9,12"` / `"72-86"`。R1-1、R1-5）。
        detection_command: 検出に用いた実行コマンド（R1-1）。
        confirmation: 参照有無の確認結果。`None` は未確認を意味し、この場合の
            `disposition` は `"undetermined"` でなければならない（R1-6）。
        removal_check_command: 除去後の確認コマンド。除去対象のみが持つ。
        approver_decision_required: Approver 判断が必要か（R6-5 等）。
    """

    key: str
    description: str
    stream: str
    disposition: str
    source_path: str
    source_lines: str
    detection_command: str
    confirmation: Confirmation | None
    removal_check_command: str | None
    approver_decision_required: bool


@dataclass(frozen=True)
class PreservedAssetItem:
    """系統 C の保全対象 1 項目（R1-8、R5-1〜R5-4）.

    系統 C を `LegacyAssetItem` と別モデルにした理由は、`stream` を `A|B|D` の
    排他 3 値に保ちながら（R1-2）系統 C を Inventory に含める（R1-8）という
    2 要件を同時に満たすためである（出典: design.md DM1 の注記）。

    属性:
        key: 一意識別子。
        description: 対象の説明。
        disposition: 扱い。`"保全対象"` 固定（R1-8）。
        source_path: 出典のファイルパス。
        source_lines: 出典の行番号。
        detection_command: 検出に用いた実行コマンド。
        build_time_dependency: ビルド時依存の根拠（出典付き）。
    """

    key: str
    description: str
    disposition: str
    source_path: str
    source_lines: str
    detection_command: str
    build_time_dependency: str


@dataclass(frozen=True)
class UndeterminedNote:
    """未検証事項 1 件（R9-1、R9-2、R9-6）.

    確定手段を必ず伴わせ、推測で埋めない（第一原則、第三原則3）。

    属性:
        key: 対応する Inventory 項目キー。
        reason: 未検証である理由。
        pending_check: 確定に必要な確認コマンドまたは判断者。
    """

    key: str
    reason: str
    pending_check: str


# ---------------------------------------------------------------------------
# DM2. Inventory
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Inventory:
    """Legacy_Asset_Inventory の文書全体（`docs/legacy-asset-inventory.json` の写像）.

    属性:
        revision: 記録時の git revision（例: `"5f4ad0d"`）。
        items: 系統 A / B / D の項目（R1-4、R1-7）。
        preserved: 系統 C の保全対象（R1-8）。
        undetermined_notes: 未検証事項（R9-1、R9-2）。
    """

    revision: str
    items: tuple[LegacyAssetItem, ...]
    preserved: tuple[PreservedAssetItem, ...]
    undetermined_notes: tuple[UndeterminedNote, ...]


# ---------------------------------------------------------------------------
# DM3. NonRegressionRecord / VerificationResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NonRegressionRecord:
    """1 回の非退行確認の実測記録（R2-10、R10-6）.

    属性:
        stream: 対象系統。`"A"` / `"B"` / `"D"`。
        commands: 実行したコマンド（非空必須。R2-10）。
        tests_passed: `python manage.py test` の pass 件数（期待 133 以上。R2-1）。
        tests_failed: failure 件数（期待 0。R2-1）。
        tests_errored: error 件数（期待 0。R2-1）。
        django_check_exit_code: `python manage.py check --fail-level WARNING`
            の終了コード（期待 0。R2-2）。
        control_platform_exit_code:
            `python -m scripts.control_platform.cli --self-test` の終了コード
            （期待 0。R2-3）。
        self_test_exit_code: `python tests/self_test.py` の終了コード
            （期待 0。R2-3）。
        non_regression_exit_code:
            `python -m scripts.measurement.non_regression_check` の終了コード
            （期待 0。R2-4）。
        prerendered_pages: 言語別 Prerendered_Page 件数（期待 7。R2-5）。
        manifest_files: `prerender_manifest.json` の件数（期待 1。R2-5）。
        content_security_policy: manifest の CSP 値（期待 長さ 1 以上。R2-6）。

    Baseline 133 件の出典: design.md 作成時の実測 `Ran 133 tests` / `OK`
    （`$env:DJANGO_SETTINGS_MODULE="config.settings.dev"; python manage.py test`）。
    """

    stream: str
    commands: tuple[str, ...]
    tests_passed: int
    tests_failed: int
    tests_errored: int
    django_check_exit_code: int
    control_platform_exit_code: int
    self_test_exit_code: int
    non_regression_exit_code: int
    prerendered_pages: int
    manifest_files: int
    content_security_policy: str


@dataclass(frozen=True)
class VerificationResult:
    """非退行判定の結果.

    属性:
        conformant: R2-1〜R2-6 の全条件が同時成立したか。
        violations: 不適合条項の識別子（例: `("R2-1", "R2-5")`）。出典可能な形
            で保持し、不適合を握りつぶさない（第三原則3）。
    """

    conformant: bool
    violations: tuple[str, ...]


# ---------------------------------------------------------------------------
# DM4. DestructiveOperationRequest / DestructiveOperationRecord
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DestructiveOperationRequest:
    """破壊的操作 1 件の提示内容（R8-2、R8-7、R8-8）.

    属性:
        target_kind: 対象種別。`ALLOWED_TARGET_KINDS` のいずれか（R8-8）。
        target_identifier: 対象リソース識別子
            （例: `"/staging/portfolio/parameter/email_host"`。R8-2）。
        environment: 対象環境。`"staging"` / `"prod"`（R8-7）。
        command: 実行コマンド（R8-2）。
        impact: 影響範囲（R8-2）。
        reversible: 取り消し可否（R8-2）。
        approved: Approver 承認の有無（R8-3）。
    """

    target_kind: str
    target_identifier: str
    environment: str
    command: str
    impact: str
    reversible: bool
    approved: bool


@dataclass(frozen=True)
class DestructiveOperationRecord:
    """破壊的操作 1 件の実施記録（R8-4、R8-5、R8-6、R8-7）.

    属性:
        request: 対応する提示内容。
        pre_value_evidence: 実行前の現在値取得結果（R8-4）。対象が Secrets
            Manager の場合はキー名と存在有無および取得に用いたコマンドのみを
            格納し、平文値を格納しない（出典: design.md「Error Handling」の
            DM4 に関する注記、第二原則2 ゼロトラスト、GDPR）。
        post_absence_evidence: 実行後の不在確認結果（R8-5）。
        error: 失敗内容。`None` は成功を意味する。失敗時は後続操作を停止する
            判断材料となる（R8-6）。
    """

    request: DestructiveOperationRequest
    pre_value_evidence: str
    post_absence_evidence: str
    error: str | None


# ---------------------------------------------------------------------------
# DM5. DependencyCandidate / DependencyDecision / LedgerCoherenceReport
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DependencyCandidate:
    """依存除去判定の入力 1 件（R7-1、R7-2）.

    属性:
        name: パッケージ名。
        manifest_line: `requirements.txt` の行番号。
        marker: 環境マーカー（例: `"sys_platform != 'win32'"`）。`None` は
            マーカーなし。
        direct_reference_checked: `git grep` による直接参照確認を実施したか
            （R7-1）。
        direct_reference_sources: 直接参照の一致箇所（空タプル = 直接参照なし）。
        transitive_checked: 依存グラフ解決を実施したか（R7-2）。
        required_by: 要求元パッケージ名（空タプル = 要求なし。R7-3）。
        resolution_environment: 解決環境。`"windows-venv"` /
            `"docker-python312"`（出典: design.md「実行環境の差異」）。
    """

    name: str
    manifest_line: int
    marker: str | None
    direct_reference_checked: bool
    direct_reference_sources: tuple[str, ...]
    transitive_checked: bool
    required_by: tuple[str, ...]
    resolution_environment: str


@dataclass(frozen=True)
class DependencyDecision:
    """依存 1 件の判定結果（R7-3、R7-4、R7-5）.

    属性:
        name: パッケージ名。
        disposition: 判定。`"除去対象"` / `"保持"` / `"undetermined"`。
        reason: 判定根拠。`"保持"` の場合は要求元パッケージ名を含める（R7-3）。
    """

    name: str
    disposition: str
    reason: str


@dataclass(frozen=True)
class LedgerCoherenceReport:
    """Dependency_Manifest と License_Ledger の集合差分（R7-7）.

    属性:
        coherent: 両集合が一致したか。
        manifest_only: Dependency_Manifest にのみ存在するパッケージ名。
        ledger_only: License_Ledger にのみ存在するパッケージ名。
    """

    coherent: bool
    manifest_only: tuple[str, ...]
    ledger_only: tuple[str, ...]


# ---------------------------------------------------------------------------
# DM6. 系統 B の AWS 側状態
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AwsSmtpState:
    """系統 B の AWS 側状態（R4-13、R4-14、R4-16）.

    属性:
        queried: 照会を実施したか。未実施の場合、系統 B の完了判定は常に偽と
            なる（既定値による補完を行わない。第三原則3）。
        absent_targets: 不在確認が成立した対象（R4-16）。
        deleted_targets: 承認済み削除が完了した対象（R4-14）。
        expected_targets: 期待対象集合。`STREAM_B_AWS_TARGETS` を渡す。

    完了条件（`completion.py` が判定する）: `queried` が真、かつ
    `absent_targets | deleted_targets == expected_targets`、かつ
    適用済み区分集合が `STREAM_B_SEGMENTS` と一致すること（R4-14）。
    """

    queried: bool
    absent_targets: frozenset[str]
    deleted_targets: frozenset[str]
    expected_targets: frozenset[str]
