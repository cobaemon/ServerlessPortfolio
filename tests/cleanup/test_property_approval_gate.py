"""Property 10（破壊的操作の承認ゲートと対象限定・停止規則）のプロパティテスト.

Feature: legacy-asset-cleanup, Property 10: *For any* DestructiveOperationRequest と任意の先行操作失敗状態について、Approval_Gate が実行を許可するのは、`approved` が真であり、`target_kind` が許可 2 種（Parameter Store パラメータ / Secrets Manager シークレットキー）のいずれかであり、かつ先行操作が失敗していない 3 条件が同時に成立する場合に限る。また提示内容の検証は、対象識別子・実行コマンド・影響範囲・取り消し可否・対象環境のいずれかが欠落したとき必ず違反を列挙する。

本モジュールは design.md「Correctness Properties > Property 10」および tasks.md 4.5 を
検証する（出典: `.kiro/specs/legacy-asset-cleanup/design.md:667-672`、
同 tasks.md「4.5 承認ゲートのプロパティテストを書く」、同 design.md「Testing Strategy >
プロパティテスト」の対応表 `Property 10 | tests/cleanup/test_property_approval_gate.py`
（`design.md:744`））。

**Validates: Requirements 8.1, 8.2, 8.3, 8.6, 8.7, 8.8**

    - R8-1: Destructive_Operation を Approver の承認を前提とする運用手順として記述する
      （出典: `requirements.md:294`）。本テストは検証対象 `approval.py` が AWS 操作を
      実行せず可否判定のみを返すこと（許可判定が運用手順の前提として機能すること）を
      戻り値の検査により確認する。
    - R8-2: 対象リソース識別子、実行コマンド、影響範囲、取り消し可否を提示する
      （出典: `requirements.md:295`）。
    - R8-3: 承認が得られていない間は実行を保留する（出典: `requirements.md:296`）。
    - R8-6: 失敗時は後続の Destructive_Operation を停止する（出典:
      `requirements.md:299`）。
    - R8-7: 記録は対象環境（staging または prod）を明記する（出典:
      `requirements.md:300`）。
    - R8-8: 対象を Parameter Store パラメータ削除および Secrets Manager シークレット
      キー削除に限定する（出典: `requirements.md:301`）。

検証対象（tasks.md 4.4 実装、design.md C11「Approval_Gate（Destructive_Operation）」
（`design.md:336-352`））:
    - `scripts/cleanup/approval.py` の
      `is_executable(request: DestructiveOperationRequest, preceding_failed: bool) -> bool`
    - `scripts/cleanup/approval.py` の
      `validate_request(request: DestructiveOperationRequest) -> tuple[str, ...]`

検証する 2 つの半分（Property 10 本文の 2 文に対応）:
    前半（許可の双条件）: `is_executable` の戻り値が「`approved` が真」「`target_kind`
    が `ALLOWED_TARGET_KINDS` のいずれか」「先行操作が失敗していない」の 3 条件の
    同時成立と厳密に一致する（いずれか 1 つでも不成立なら False）。
    後半（提示内容の検証）: `validate_request` が、欠落している提示必須項目に対して
    必ず違反を列挙し、提示されている項目に対しては違反を列挙しない。

入力域（DM4 が宣言する型と R8-7 が定める値域）:
    - `approved` と `reversible` は `bool` として宣言される（出典: design.md DM4 の
      `DestructiveOperationRequest`）。`preceding_failed` も `is_executable` の
      シグネチャで `bool` として宣言される（出典: design.md C11「インターフェース」）。
      したがって本テストは `approved` / `preceding_failed` を真偽値のみで生成する。
      真偽値以外の値に対する振る舞い（同一性比較の意味論）は Property 10 も
      requirements.md の受入基準も規定しないため、検証対象としない。
    - `reversible` は真偽値に加えて `None`（未記載）を生成する。Property 10 は
      「取り消し可否…が欠落したとき必ず違反を列挙する」ことを求めており（出典:
      design.md Property 10 第 2 文、requirements.md:295）、`bool` 型の項目における
      「欠落」は値が提示されていない状態（`None`）である。
    - 空白のみの文字列は欠落として扱う（出典: `scripts/cleanup/approval.py` の
      `_is_blank`。`scripts/cleanup/inventory.py` の `_is_blank` と同一の扱い）。
    - `environment` は R8-7 が定める `staging` / `prod` のみを生成する（出典:
      requirements.md:300「対象環境（staging または prod）を明記する」）。
    - `validate_request` の結果は `is_executable` の許可条件に含まれない（design.md
      C11 および Property 10 が定める許可条件は 3 条件のみ。出典: `design.md:349-350`、
      `design.md:669`）。本テストは提示内容の欠落が許可判定へ影響しないことも検証する。

検証しない事項（受入基準・Property 10 が規定しないため対象外とする）:
    - 違反文字列の形式（条項識別子・キーの表記・文面）。Property 10 は「欠落した
      とき必ず違反を列挙する」ことのみを定め、報告形式を定めない。本テストは
      違反件数が欠落項目数と一致すること、および各欠落項目名に言及する違反が
      存在することのみを検証する。
    - `environment` の値が `staging` / `prod` のいずれかであるかの値域検証。
      requirements.md:300 は対象環境の明記を求める一方、design.md C11 の検証内容は
      値域検証を挙げていない（出典: `design.md:344`）。いずれの読み方を採るかは
      **未確定であり Approver の判断を要する**。本テストは値域検証の有無を
      いずれの向きにも主張せず、生成する `environment` を R8-7 が挙げる 2 値に
      限定する。

独立オラクル方針（出典: tasks.md 4.5、design.md「Testing Strategy」）:
    - 前半は、実装の分岐を参照せず Property 10 本文の 3 条件を本モジュール内で
      再宣言して期待値を算出する（`_expected_executable`）。許可対象種別は
      `scripts/cleanup/models.py` の `ALLOWED_TARGET_KINDS` を import して用い、
      2 種の値をテスト側で再列挙しない（tasks.md 4.5 の指示、第三原則2 整合性）。
    - 後半は、requirements.md 基準 2・基準 7 が列挙する提示必須項目を本モジュール内に
      独立宣言し、欠落判定（空文字列または空白のみ／`reversible` の未記載）を独立
      実装して期待欠落項目集合を算出する（`_expected_missing_fields`）。実装の違反
      文字列は解析せず、件数の一致と欠落項目名への言及のみを検査する。

機密値の取り扱い（出典: design.md「機密値の取り扱い（ゼロトラスト・GDPR）」、
`.kiro/steering/principles.md` 第二原則2・第二原則4）:
    - 本テストはシークレットの平文値を一切含まない。Secrets Manager 対象は
      **キー名のみ**を識別子として用いる（例:
      `"staging/portfolio/secret#EMAIL_HOST_USER"`）。Parameter Store 対象は
      パラメータ名（例: `"/staging/portfolio/parameter/email_host"`）のみを用いる。
    - 平文のシークレット値をテストデータとして捏造しない。

ライセンス注記（第二原則6・要ライセンス確認）:
    - Hypothesis は Mozilla Public License 2.0（MPL-2.0）で配布される（出典:
      `requirements-dev.txt:18` の `hypothesis==6.158.0` および同ファイル 6-14 行の
      ライセンス注記、公式リポジトリ LICENSE.txt）。開発・テスト時のみ使用し、改変せず
      Lambda 配布物へ同梱しないため、MPL-2.0 のソース開示義務の実務的対象外である
      （非配布・非改変）。

実行コマンド（プロジェクトルートから）:
    $env:DJANGO_SETTINGS_MODULE="config.settings.dev"; python manage.py test tests.cleanup.test_property_approval_gate
  もしくは（検証対象が Django 非依存であるため単体でも実行可能）:
    python -m unittest tests.cleanup.test_property_approval_gate -v
"""

from __future__ import annotations

import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

from scripts.cleanup.approval import is_executable, validate_request

# 許可対象種別は実装側の定数（DM4）を再利用し、テスト側で 2 種を再列挙しない
# （出典: tasks.md 4.5 の指示、`scripts/cleanup/models.py` の
# `ALLOWED_TARGET_KINDS`、R8-8）。
from scripts.cleanup.models import ALLOWED_TARGET_KINDS, DestructiveOperationRequest

# ---------------------------------------------------------------------------
# 独立オラクルの宣言（requirements.md の基準文面を出典とし、実装の分岐を写さない）
# ---------------------------------------------------------------------------

# 提示必須項目のうち文字列で提示される 4 項目と、欠落時に期待する条項識別子。
# 出典: requirements.md:295（基準 2「対象リソース識別子、実行コマンド、影響範囲、
# および取り消し可否を提示し」）、requirements.md:300（基準 7「対象環境（staging
# または prod）を明記する」）。本テスト独自の宣言であり、実装の
# `_REQUIRED_TEXT_FIELDS` を import しない。
_EXPECTED_TEXT_FIELDS: tuple[str, ...] = (
    "target_identifier",
    "command",
    "impact",
    "environment",
)

# 取り消し可否（真偽値項目）の項目名（出典: requirements.md:295 基準 2 の
# 「取り消し可否」、design.md DM4 の `reversible: bool`）。
_EXPECTED_REVERSIBLE_FIELD = "reversible"

# ---------------------------------------------------------------------------
# 生成用の固定候補（機密値を含めない。上記「機密値の取り扱い」を参照）
# ---------------------------------------------------------------------------

# 対象リソース識別子の候補。Parameter Store はパラメータ名、Secrets Manager は
# シークレット名とキー名のみを用いる（出典: requirements.md:225 の対象 6 件、
# `scripts/cleanup/models.py` の `STREAM_B_AWS_TARGETS`）。
_IDENTIFIER_POOL: tuple[str, ...] = (
    "/staging/portfolio/parameter/email_host",
    "/staging/portfolio/parameter/email_port",
    "/prod/portfolio/parameter/email_use_tls",
    "/prod/portfolio/parameter/email_use_ssl",
    "staging/portfolio/secret#EMAIL_HOST_USER",
    "prod/portfolio/secret#EMAIL_HOST_PASSWORD",
    # 前後に空白を含む値（`strip()` 後が非空であるため欠落ではない。本モジュール
    # 冒頭の「入力域」）。
    "  /staging/portfolio/parameter/email_host  ",
)

# 実行コマンドの候補（コマンド文面のみを保持し、本テストは実行しない。R8-2）。
_COMMAND_POOL: tuple[str, ...] = (
    "aws ssm delete-parameter --name /staging/portfolio/parameter/email_host",
    "aws ssm delete-parameter --name /prod/portfolio/parameter/email_port",
    "aws secretsmanager put-secret-value --secret-id staging/portfolio/secret",
)

# 影響範囲の候補（R8-2）。
_IMPACT_POOL: tuple[str, ...] = (
    "staging の SMTP 設定参照が失われる（除去後は console バックエンド）",
    "prod の SMTP 設定参照が失われる（除去後は console バックエンド）",
    "影響なし（照会時点で不在）",
)

# 対象環境の候補。R8-7 が挙げる 2 値のみとする（値域検証の有無は未確定であり、
# 本テストはいずれの向きにも主張しない。本モジュール冒頭の「検証しない事項」）。
_ENVIRONMENT_POOL: tuple[str, ...] = ("staging", "prod")

# 欠落（空文字列・空白のみ）を表す候補（出典: `scripts/cleanup/approval.py` の
# `_is_blank`）。
_BLANK_POOL: tuple[str, ...] = ("", " ", "   ", "\t", "\n", " \t \n ")

# 許可外の対象種別候補（R8-8 の 2 種以外。境界値として空文字列・空白付き・
# 大文字化・複数値の連結を含める）。
_DISALLOWED_TARGET_KIND_POOL: tuple[str, ...] = (
    "",
    " ",
    "parameter_store_parameter ",
    " secrets_manager_secret_key",
    "PARAMETER_STORE_PARAMETER",
    "s3_bucket",
    "cloudformation_stack",
    "parameter_store_parameter|secrets_manager_secret_key",
)

# 許可外候補が実際に許可集合の外にあることをモジュール読み込み時に確認する
# （テスト自身の前提を暗黙に信頼しない。第二原則2、第三原則3）。
assert not (frozenset(_DISALLOWED_TARGET_KIND_POOL) & ALLOWED_TARGET_KINDS)

def _expected_executable(
    request: DestructiveOperationRequest, preceding_failed: bool
) -> bool:
    """Property 10 前半の 3 条件から実行許可の期待値を独立に算出する.

    Args:
        request: 判定対象の `DestructiveOperationRequest`。
        preceding_failed: 先行操作の失敗状態（DM4 / C11 の宣言に従い真偽値）。

    Returns:
        bool: 「`approved` が真」「`target_kind` が許可 2 種のいずれか」「先行操作が
            失敗していない」の 3 条件が同時成立する場合のみ True。

    例外:
        送出しない。
    """
    # R8-3: Approver 承認が得られていること（出典: requirements.md:296）。
    approved = request.approved is True
    # R8-8: 対象種別が許可 2 種のいずれかであること（出典: requirements.md:301）。
    target_allowed = request.target_kind in ALLOWED_TARGET_KINDS
    # R8-6: 先行操作が失敗していないこと（出典: requirements.md:299）。
    not_stopped = preceding_failed is False
    return approved and target_allowed and not_stopped


def _is_missing(value: object) -> bool:
    """文字列項目が欠落しているか（空または空白のみか）を独立に判定する.

    Args:
        value: 判定対象の値。

    Returns:
        bool: 文字列で、かつ空または空白のみであれば True。

    例外:
        送出しない。

    空白のみを欠落として扱う根拠は本モジュール冒頭の「入力域」（`scripts/cleanup/
    approval.py` の `_is_blank`、`scripts/cleanup/inventory.py` の `_is_blank` と
    同一の扱い）。
    """
    return isinstance(value, str) and not value.strip()


def _expected_missing_fields(
    request: DestructiveOperationRequest,
) -> frozenset[str]:
    """提示必須項目のうち欠落している項目名の集合を独立に算出する.

    Args:
        request: 検証対象の `DestructiveOperationRequest`。

    Returns:
        frozenset[str]: 欠落している提示必須項目の項目名。

    例外:
        送出しない。

    出典: requirements.md:295（基準 2「対象リソース識別子、実行コマンド、影響範囲、
    および取り消し可否を提示し」）、requirements.md:300（基準 7「対象環境（staging
    または prod）を明記する」）。実装の制御フローを参照せず、基準文面から導いた
    `_EXPECTED_TEXT_FIELDS` と取り消し可否の提示要件のみに基づいて算出する。
    """
    missing: set[str] = set()

    # 文字列 4 項目: 空または空白のみであれば欠落として数える。
    for field_name in _EXPECTED_TEXT_FIELDS:
        if _is_missing(getattr(request, field_name)):
            missing.add(field_name)

    # 取り消し可否: `bool` 型の項目における欠落は値が提示されていない状態である
    # （DM4 は `reversible: bool` を宣言する。本モジュール冒頭の「入力域」）。
    if request.reversible is None:
        missing.add(_EXPECTED_REVERSIBLE_FIELD)

    return frozenset(missing)


def _request(**overrides: object) -> DestructiveOperationRequest:
    """提示必須項目がすべて揃った提示内容を作り、指定項目のみ差し替える.

    Args:
        **overrides: 差し替える属性名と値。

    Returns:
        DestructiveOperationRequest: 既定値（全項目提示済み・許可対象種別・承認済み）
            に `overrides` を適用した提示内容。

    例外:
        送出しない。

    既定値にシークレットの平文値を含めない（識別子はパラメータ名／キー名のみ）。
    """
    base: dict[str, object] = {
        # 許可 2 種のうち辞書順先頭（`parameter_store_parameter`）を既定とし、
        # 値をテスト側で直書きしない（第三原則2 整合性）。
        "target_kind": sorted(ALLOWED_TARGET_KINDS)[0],
        "target_identifier": "/staging/portfolio/parameter/email_host",
        "environment": "staging",
        "command": (
            "aws ssm delete-parameter --name /staging/portfolio/parameter/email_host"
        ),
        "impact": "staging の SMTP 設定参照が失われる",
        "reversible": False,
        "approved": True,
    }
    base.update(overrides)
    return DestructiveOperationRequest(**base)  # type: ignore[arg-type]


def _target_kinds() -> st.SearchStrategy[str]:
    """対象種別を許可 2 種と許可外の双方で生成する.

    Returns:
        SearchStrategy[str]: `ALLOWED_TARGET_KINDS` の要素、または許可外の候補。
    """
    return st.one_of(
        # 許可 2 種（`sorted` で列挙順を固定し、生成を決定的にする）。
        st.sampled_from(sorted(ALLOWED_TARGET_KINDS)),
        st.sampled_from(_DISALLOWED_TARGET_KIND_POOL),
    )


def _reversible_values() -> st.SearchStrategy[bool | None]:
    """取り消し可否を提示済み（真偽値）と未記載（`None`）の双方で生成する.

    Returns:
        SearchStrategy[bool | None]: `True` / `False`（提示済み）または `None`
            （未記載。Property 10 第 2 文が言う「取り消し可否の欠落」）。
    """
    return st.one_of(st.booleans(), st.none())


@st.composite
def _requests(draw: st.DrawFn) -> DestructiveOperationRequest:
    """`DestructiveOperationRequest` を提示欠落・許可外種別・非真偽値を含めて生成する.

    Args:
        draw: Hypothesis の draw 関数。

    Returns:
        DestructiveOperationRequest: 各文字列項目が欠落／提示済み、対象種別が許可／
            許可外、`reversible` が提示済み／未記載を取り得る提示内容。`approved` は
            DM4 の宣言に従い真偽値のみとする（本モジュール冒頭の「入力域」）。
    """
    return DestructiveOperationRequest(
        target_kind=draw(_target_kinds()),
        # 各文字列項目は欠落候補と提示済み候補の双方から生成する。
        target_identifier=draw(
            st.one_of(st.sampled_from(_BLANK_POOL), st.sampled_from(_IDENTIFIER_POOL))
        ),
        environment=draw(
            st.one_of(st.sampled_from(_BLANK_POOL), st.sampled_from(_ENVIRONMENT_POOL))
        ),
        command=draw(
            st.one_of(st.sampled_from(_BLANK_POOL), st.sampled_from(_COMMAND_POOL))
        ),
        impact=draw(
            st.one_of(st.sampled_from(_BLANK_POOL), st.sampled_from(_IMPACT_POOL))
        ),
        # 未記載（None）は DM4 の `bool` 宣言に対する「欠落」を表す（Property 10）。
        reversible=draw(_reversible_values()),  # type: ignore[arg-type]
        approved=draw(st.booleans()),
    )


class ApprovalGateProperty(unittest.TestCase):
    """Property 10 のプロパティテストを保持するテストケース."""

    # 反復回数は tasks.md「Overview」および design.md「プロパティテスト」が求める
    # `max_examples=100` 以上とし、3 条件 × 提示 5 項目 × 真偽値／非真偽値の組合せを
    # 十分に踏むため 300 とする。判定は純関数であり I/O を伴わないが、生成データに
    # よる per-example の締切超過による誤検知を避けるため deadline を無効化する。
    @settings(max_examples=300, deadline=None)
    @given(request=_requests(), preceding_failed=st.booleans())
    def test_permission_iff_three_conditions_and_missing_fields_enumerated(
        self, request: DestructiveOperationRequest, preceding_failed: bool
    ) -> None:
        """Feature: legacy-asset-cleanup, Property 10: 破壊的操作の承認ゲートと対象限定・停止規則

        **Validates: Requirements 8.1, 8.2, 8.3, 8.6, 8.7, 8.8**

        任意の `DestructiveOperationRequest` と任意の先行操作失敗状態について次を
        検証する（出典: `design.md:669`、requirements.md:294-301）。
            (1) `is_executable` が True を返すのは「`approved` が真」「`target_kind`
                が許可 2 種のいずれか」「先行操作が失敗していない」の 3 条件が同時
                成立する場合に限る（双条件）。
            (2) `validate_request` が列挙する違反の件数が欠落項目数と一致し、欠落
                項目ごとに当該項目名へ言及する違反が存在する（欠落がなければ空
                タプル）。違反文字列の形式は検証しない（本モジュール冒頭の
                「検証しない事項」）。
            (3) 提示内容の欠落は許可判定へ影響しない（許可条件は 3 条件のみ。
                出典: `design.md:349-350`）。
        """
        # ---- (1) 前半: 許可の双条件（R8-3 / R8-8 / R8-6）----
        expected_permission = _expected_executable(request, preceding_failed)
        actual_permission = is_executable(request, preceding_failed)

        self.assertIs(
            actual_permission,
            expected_permission,
            msg=(
                "実行許可の判定が 3 条件の同時成立と一致しない: "
                f"actual={actual_permission!r} / expected={expected_permission!r} / "
                f"approved={request.approved!r} / "
                f"target_kind={request.target_kind!r} / "
                f"preceding_failed={preceding_failed!r}"
            ),
        )

        # 許可された場合、3 条件が個別に成立していること（双条件の逆方向の明示）。
        if actual_permission:
            self.assertIs(
                request.approved,
                True,
                msg=f"未承認（{request.approved!r}）で許可された（R8-3 違反）",
            )
            self.assertIn(
                request.target_kind,
                ALLOWED_TARGET_KINDS,
                msg=(
                    f"許可外の対象種別（{request.target_kind!r}）で許可された"
                    "（R8-8 違反）"
                ),
            )
            self.assertIs(
                preceding_failed,
                False,
                msg=(
                    f"先行操作の失敗状態（{preceding_failed!r}）で許可された"
                    "（R8-6 違反）"
                ),
            )

        # ---- (2) 後半: 提示必須項目の欠落列挙（R8-2 / R8-7）----
        violations = validate_request(request)
        expected_missing = _expected_missing_fields(request)

        # 欠落項目 1 件につき違反 1 件（重複列挙・取りこぼしがない）。件数のみを
        # 比較し、違反文字列の形式は検証しない。
        self.assertEqual(
            len(violations),
            len(expected_missing),
            msg=(
                "違反件数が欠落項目数と一致しない: "
                f"len={len(violations)} / expected={len(expected_missing)} / "
                f"missing={sorted(expected_missing)!r} / {violations!r}"
            ),
        )
        # 欠落した項目ごとに、当該項目名へ言及する違反が存在すること（どの項目が
        # 欠落したかが提示者へ伝わること。Property 10 第 2 文）。
        for field_name in sorted(expected_missing):
            self.assertTrue(
                any(field_name in violation for violation in violations),
                msg=(
                    f"欠落項目 {field_name!r} に言及する違反が列挙されない: "
                    f"{violations!r}"
                ),
            )
        # 欠落がなければ空タプル（適合）。
        if not expected_missing:
            self.assertEqual(
                violations,
                (),
                msg=f"全項目が提示済みの提示で違反が列挙された: {violations!r}",
            )

        # ---- (3) 提示内容の欠落は許可条件に含まれない（出典: design.md:349-350）----
        self.assertIs(
            is_executable(request, preceding_failed),
            expected_permission,
            msg=(
                "提示内容の検証結果が許可判定へ影響している（設計外の条件が追加された）: "
                f"violations={violations!r} / expected={expected_permission!r}"
            ),
        )


class ApprovalGatePermissionExampleTests(unittest.TestCase):
    """3 条件を個別に不成立とした例示テスト（前半の境界の明示確認）."""

    def test_all_conditions_satisfied_permits_execution(self) -> None:
        """3 条件が同時成立する提示が許可されること（R8-3 / R8-6 / R8-8）."""
        for target_kind in sorted(ALLOWED_TARGET_KINDS):
            with self.subTest(target_kind=target_kind):
                self.assertIs(
                    is_executable(_request(target_kind=target_kind), False),
                    True,
                )

    def test_each_condition_independently_denies_execution(self) -> None:
        """各条件を 1 つずつ不成立にすると許可されないこと."""
        # (差し替え内容, 先行操作の失敗状態, 不成立となる条項) の組。
        cases: tuple[tuple[dict[str, object], bool, str], ...] = (
            ({"approved": False}, False, "R8-3"),
            ({"target_kind": "s3_bucket"}, False, "R8-8"),
            ({"target_kind": ""}, False, "R8-8"),
            ({}, True, "R8-6"),
        )
        for overrides, preceding_failed, clause in cases:
            with self.subTest(overrides=overrides, clause=clause):
                self.assertIs(
                    is_executable(_request(**overrides), preceding_failed),
                    False,
                )


class ApprovalGateValidationExampleTests(unittest.TestCase):
    """提示必須項目の欠落列挙の例示テスト（後半の境界の明示確認）."""

    def test_complete_request_has_no_violations(self) -> None:
        """全項目が提示された提示で違反が列挙されないこと（R8-2 / R8-7）."""
        self.assertEqual(validate_request(_request()), ())

    def test_each_missing_field_is_enumerated(self) -> None:
        """項目を 1 つずつ欠落させると、当該項目名に言及する違反が 1 件列挙されること."""
        # (差し替え内容, 期待項目名) の組。空白のみの値も欠落として扱う。
        cases: tuple[tuple[dict[str, object], str], ...] = (
            ({"target_identifier": ""}, "target_identifier"),
            ({"target_identifier": "   "}, "target_identifier"),
            ({"command": ""}, "command"),
            ({"command": "\t"}, "command"),
            ({"impact": ""}, "impact"),
            ({"environment": ""}, "environment"),
            ({"environment": " "}, "environment"),
            ({"reversible": None}, "reversible"),
        )
        for overrides, field_name in cases:
            with self.subTest(overrides=overrides):
                violations = validate_request(_request(**overrides))
                self.assertEqual(
                    len(violations),
                    1,
                    msg=f"欠落 1 件に対する違反が 1 件でない: {violations!r}",
                )
                self.assertIn(
                    field_name,
                    violations[0],
                    msg=f"違反が欠落項目名に言及しない: {violations!r}",
                )

    def test_all_fields_missing_enumerates_every_field(self) -> None:
        """全 5 項目が欠落した提示で 5 件の違反が列挙されること（R8-2 4 項目 + R8-7）."""
        request = _request(
            target_identifier="",
            command=" ",
            impact="",
            environment="\t",
            reversible=None,
        )
        violations = validate_request(request)
        expected_missing = _expected_missing_fields(request)
        self.assertEqual(len(expected_missing), 5, msg=f"{sorted(expected_missing)!r}")
        self.assertEqual(len(violations), len(expected_missing), msg=f"{violations!r}")
        for field_name in sorted(expected_missing):
            with self.subTest(field_name=field_name):
                self.assertTrue(
                    any(field_name in violation for violation in violations),
                    msg=f"欠落項目 {field_name!r} に言及する違反がない: {violations!r}",
                )


if __name__ == "__main__":
    # 単体実行用エントリ（`python -m unittest` による探索でも実行可能）。
    unittest.main()
