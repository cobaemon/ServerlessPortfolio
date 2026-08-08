"""Feature: legacy-asset-cleanup, Property 11: 確定更新の冪等性と単調性

    *For any* Legacy_Asset_Item と、`result` が `除去対象` / `保全対象` のいずれか
    単一値であり `evidence_command` が非空である任意の Confirmation について、
    `apply_confirmation` を 2 回適用した結果は 1 回適用した結果と等しく（冪等）、
    かつ適用後の `disposition` は `result` と一致して `undetermined` に戻らず、
    更新後の項目は確認に用いた実行コマンドを非空の出典として保持する。

本モジュールは design.md「Correctness Properties > Property 11」および tasks.md 1.5 を
検証する（出典: `.kiro/specs/legacy-asset-cleanup/design.md:673-676`、同 tasks.md
「1.5 確定更新のプロパティテストを書く」、同 design.md:745 の対応表
`| Property 11 | tests/cleanup/test_property_confirmation_update.py |`）。

検証対象（Validates: Requirements 5.8, 9.3）:
    - R5-8: ビルド時依存の最小集合が Prerender_Command の実行結果により確定した時、
      Legacy_Asset_Inventory は当該範囲の記録を `undetermined` から「保全対象」または
      「除去対象」へ更新し、確定に用いた実行コマンドを出典として付す（出典:
      `.kiro/specs/legacy-asset-cleanup/requirements.md:252`）。
    - R9-3: ある `undetermined` 項目について確認結果が得られた時、Executor は当該項目の
      記録を確認結果と出典で更新する（出典: 同 requirements.md:311）。

検証対象モジュール（tasks.md 1.2 実装）:
    - `scripts/cleanup/inventory.py` の
      `apply_confirmation(item: LegacyAssetItem, confirmation: Confirmation)
       -> LegacyAssetItem`
      （出典: `scripts/cleanup/inventory.py` の同関数 docstring「振る舞い（出典:
      design.md Property 11）」）。

入力域（Property 11 が自ら定める適用域。design.md の文面に一致させる）:
    - Property 11 は対象とする `Confirmation` を「`result` が `除去対象` /
      `保全対象` のいずれか単一値であり `evidence_command` が非空である任意の
      Confirmation」に限定し、当該値域外の `Confirmation` に対する
      `apply_confirmation` の振る舞いを規定しない（出典: design.md
      「Correctness Properties > Property 11」本文および同「値域の根拠は DM1」）。
      DM1 は `Confirmation.result` を「確認により確定した扱い。`除去対象` /
      `保全対象` の単一値（R5-8）」と定義する（出典: design.md DM1）。したがって
      本モジュールの生成器が `result` を 2 値に限定し `evidence_command` を非空と
      するのは、Property 11 が定める適用域そのものである。
    - 値域外の `Confirmation` は C2 `validate_item` の検証で違反として列挙される
      （出典: design.md Property 11 の第 2 段落、同 C13「ゼロトラスト」）。当該
      入力に対する `apply_confirmation` の振る舞いは Property 11 も requirements.md
      の受入基準も規定しないため、本モジュールは検証しない。
    - 開始状態の `disposition` は R1-3 の 3 値を網羅する（出典: requirements.md
      Requirement 1 基準 3）。確定済み項目へは同一の確定値のみを適用する
      （異なる確定値の適用は R5-8 / R9-3 が想定する確定更新ではない）。
    - 冪等性は `apply_confirmation(apply_confirmation(item, c), c)
      == apply_confirmation(item, c)` として検証する。`LegacyAssetItem` は
      `@dataclass(frozen=True)` であり `==` は構造的等価である（出典:
      `scripts/cleanup/models.py` の `@dataclass(frozen=True)` 宣言）。

ライセンス注記（第二原則6・要ライセンス確認）:
    - Hypothesis は Mozilla Public License 2.0（MPL-2.0）で配布される（出典:
      `requirements-dev.txt:18` の `hypothesis==6.158.0` および同ファイルの
      ライセンス注記、公式リポジトリ LICENSE.txt）。開発・テスト時のみ使用し、
      改変せず、Lambda 配布物へ同梱しないため MPL-2.0 のソース開示義務の実務的
      対象外である（非配布・非改変）。

テスト方針（出典: design.md「Testing Strategy」、既存 `portfolio/tests/
test_property_csp_allowlist.py` と同一様式）:
    - 単一プロパティを 1 テストで実装し、最小 100 反復（`@settings(max_examples=100)`）。
    - 検証対象 `scripts/cleanup/inventory.py` は Django 非依存のため Django を
      セットアップしない（出典: design.md:747「Property 1〜8、10、11 の対象モジュールは
      Django 非依存であるため Django のセットアップを行わない」）。
    - フォールバック禁止: 期待を明示アサートし、問題を握りつぶさない。
    - 生成器は Property 11 が定める適用域（上記「入力域」）へ入力空間を制約する。

実行コマンド（プロジェクトルートから）:
    $env:DJANGO_SETTINGS_MODULE="config.settings.dev"; python manage.py test tests.cleanup.test_property_confirmation_update
  もしくは（Django 非ロードでも実行可能）:
    python -m unittest tests.cleanup.test_property_confirmation_update -v
"""

from __future__ import annotations

import string
import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

from scripts.cleanup.inventory import (
    CONFIRMABLE_DISPOSITIONS,
    DISPOSITION_PRESERVED,
    DISPOSITION_REMOVAL_TARGET,
    DISPOSITION_UNDETERMINED,
    VALID_STREAMS,
    apply_confirmation,
    validate_item,
)
from scripts.cleanup.models import Confirmation, LegacyAssetItem

# 確定先として実装が受け付ける 2 値（出典: `scripts/cleanup/inventory.py` の
# `CONFIRMABLE_DISPOSITIONS`）。生成順序を決定的にするためソート済みタプルへ固定する。
_CONFIRMABLE: tuple[str, ...] = tuple(sorted(CONFIRMABLE_DISPOSITIONS))

# 系統の 3 値（出典: 同モジュールの `VALID_STREAMS`）。同上の理由でソートする。
_STREAMS: tuple[str, ...] = tuple(sorted(VALID_STREAMS))

# 出典文字列・コマンド文字列に用いる文字集合。空白のみの値が生成されると R5-8 の
# 非空要求に抵触するため、非空白トークンを必ず 1 つ含む形で組み立てる（下記
# `_non_blank_text`）。多バイト文字も混在させ、`str.strip()` 依存の判定を広く試す。
_TOKEN_ALPHABET = string.ascii_letters + string.digits + "-_./:=*'\"日本語"

# 空白のみの文字列（実装の `_is_blank` が真を返す実体）に用いる文字集合。
_BLANK_ALPHABET = " \t\n"


def _non_blank_text(max_token: int = 24) -> st.SearchStrategy[str]:
    """空白のみにならない非空文字列を生成する.

    引数:
        max_token: 中核トークンの最大長。

    戻り値:
        SearchStrategy[str]: 前後に空白を含み得るが、必ず 1 文字以上の非空白文字を
            含む文字列（`str.strip()` が非空となる）。

    例外:
        送出しない。

    `filter` による棄却ではなく構成によって非空を保証し、Hypothesis の生成効率を
    落とさない（生成器は入力空間を意図的に制約する方針）。
    """
    return st.builds(
        lambda leading, token, trailing: f"{leading}{token}{trailing}",
        st.text(alphabet=_BLANK_ALPHABET, min_size=0, max_size=2),
        st.text(alphabet=_TOKEN_ALPHABET, min_size=1, max_size=max_token),
        st.text(alphabet=_BLANK_ALPHABET, min_size=0, max_size=2),
    )


@st.composite
def _item_and_confirmation(
    draw: st.DrawFn,
) -> tuple[LegacyAssetItem, Confirmation]:
    """Property 11 の適用域内の（LegacyAssetItem, Confirmation）の組を生成する.

    引数:
        draw: Hypothesis の draw 関数。

    戻り値:
        tuple[LegacyAssetItem, Confirmation]: 適用対象の項目と適用する確認結果。

    例外:
        送出しない。

    生成方針（本モジュール冒頭の「入力域」に対応する）:
        - 開始状態は `disposition` の 3 値すべてを網羅する。未確認（`confirmation`
          が `None`）は R1-6 により `undetermined` のみが構造的に妥当であるため
          （出典: `scripts/cleanup/inventory.py` の `validate_item` の R1-6 検証）、
          `undetermined` の場合に限り未確認・既確認の両状態を生成する。
        - 適用する `Confirmation.result` は `除去対象` / `保全対象` に限定する
          （Property 11 が定める値域。出典: design.md Property 11、DM1）。
        - 開始状態が既に確定済み（`除去対象` / `保全対象`）の場合、適用値は同一値に
          限定する。異なる確定値の適用は R5-8 / R9-3 が想定する確定更新ではなく、
          Property 11 の適用域外である。
    """
    # 開始状態の disposition を 3 値から選ぶ（単調性を全状態で確認するため）。
    disposition = draw(st.sampled_from((
        DISPOSITION_UNDETERMINED,
        DISPOSITION_REMOVAL_TARGET,
        DISPOSITION_PRESERVED,
    )))

    if disposition == DISPOSITION_UNDETERMINED:
        # 未確定項目は未確認・既確認（部分的な確認記録が付いた状態）の双方を生成する。
        has_existing_confirmation = draw(st.booleans())
        # 既存確認記録の result は DM1 が定める 2 値から選ぶ（出典: design.md DM1
        # 「確認により確定した扱い。`除去対象` / `保全対象` の単一値（R5-8）」）。
        existing_result = draw(st.sampled_from(_CONFIRMABLE))
        # 適用値は 2 値から自由に選べる（未確定からの確定は両方向が妥当）。
        applied_result = draw(st.sampled_from(_CONFIRMABLE))
    else:
        # 確定済み項目は必ず確認記録を持つ（R1-6 に整合する構造）。
        has_existing_confirmation = True
        existing_result = disposition
        # 確定済み項目へは同一の確定値のみを適用する（異なる確定値の適用は R5-8 /
        # R9-3 が想定する確定更新ではなく、Property 11 の適用域外）。
        applied_result = disposition

    existing_confirmation = (
        Confirmation(
            result=existing_result,
            evidence_command=draw(_non_blank_text()),
        )
        if has_existing_confirmation
        else None
    )

    item = LegacyAssetItem(
        key=draw(_non_blank_text(max_token=16)),
        description=draw(st.text(max_size=40)),
        stream=draw(st.sampled_from(_STREAMS)),
        disposition=disposition,
        source_path=draw(_non_blank_text()),
        source_lines=draw(_non_blank_text(max_token=12)),
        detection_command=draw(_non_blank_text()),
        confirmation=existing_confirmation,
        removal_check_command=draw(st.one_of(st.none(), _non_blank_text())),
        approver_decision_required=draw(st.booleans()),
    )

    confirmation = Confirmation(
        result=applied_result,
        evidence_command=draw(_non_blank_text()),
    )
    return item, confirmation


class ConfirmationUpdateProperty(unittest.TestCase):
    """Property 11 のプロパティテストを保持するテストケース."""

    # 最小 100 反復（出典: tasks.md「`@settings(max_examples=100)` 以上」）。判定は
    # 決定的であり、per-example 締切超過による誤検知を避けるため deadline を無効化する。
    @settings(max_examples=100, deadline=None)
    @given(case=_item_and_confirmation())
    def test_apply_confirmation_is_idempotent_and_monotonic(
        self, case: tuple[LegacyAssetItem, Confirmation]
    ) -> None:
        """Feature: legacy-asset-cleanup, Property 11: 確定更新の冪等性と単調性

        Validates: Requirements 5.8, 9.3

        任意の `LegacyAssetItem` と、Property 11 が定める値域内の任意の
        `Confirmation`（`result` が 2 値、`evidence_command` が非空）について、
        (1) `apply_confirmation` を 2 回適用した結果が 1 回適用した結果と等しいこと
        （冪等）、(2) 適用後の `disposition` が `undetermined` へ戻らないこと（単調）、
        (3) 更新後の項目が確認に用いた実行コマンドを非空の出典として保持すること
        （R5-8、R9-3）を検証する。
        """
        item, confirmation = case

        # 生成した開始状態が Inventory の構造的不変条件（R1-1〜R1-3、R1-6、R9-3）を
        # 満たすことを先に確認する。満たさない入力で本プロパティを評価すると、検証
        # 対象ではない生成器側の欠陥を性質違反として誤報する可能性があるため。
        self.assertEqual(
            validate_item(item),
            (),
            msg=f"生成した開始状態が構造的不変条件に違反している: {item!r}",
        )

        once = apply_confirmation(item, confirmation)
        twice = apply_confirmation(once, confirmation)

        # ---- (1) 冪等性: 2 回適用は 1 回適用と等しい（frozen dataclass の構造的等価）----
        self.assertEqual(
            twice,
            once,
            msg=(
                "apply_confirmation が冪等でない: "
                f"1 回適用={once!r} / 2 回適用={twice!r}"
            ),
        )

        # ---- (2) 単調性 / (3) 出典保持: 1 回適用・2 回適用の双方で確認する ----
        for label, result_item in (("1 回適用", once), ("2 回適用", twice)):
            # (2) 単調性: 適用後の disposition は undetermined へ戻らない。
            self.assertNotEqual(
                result_item.disposition,
                DISPOSITION_UNDETERMINED,
                msg=(
                    f"{label}後の disposition が undetermined へ戻っている: "
                    f"開始状態={item.disposition!r} / 結果={result_item!r}"
                ),
            )
            # 確定先は適用した確認結果の値と一致する（R5-8 の更新先は「保全対象」
            # または「除去対象」であり、推測による補完を行わない）。
            self.assertEqual(
                result_item.disposition,
                confirmation.result,
                msg=(
                    f"{label}後の disposition が確認結果の値と一致しない: "
                    f"結果={result_item.disposition!r} / "
                    f"確認結果={confirmation.result!r}"
                ),
            )
            self.assertIn(
                result_item.disposition,
                CONFIRMABLE_DISPOSITIONS,
                msg=(
                    f"{label}後の disposition が 除去対象/保全対象 のいずれでもない: "
                    f"{result_item.disposition!r}"
                ),
            )

            # (3) 出典保持: 確認に用いた実行コマンドを非空で保持する。
            # None の場合は以降の属性参照が成立しないため、その場で失敗させる
            # （握りつぶさず、判定不能を明示的な失敗として表面化させる）。
            result_confirmation = result_item.confirmation
            if result_confirmation is None:
                self.fail(f"{label}後の confirmation が None である: {result_item!r}")
            self.assertEqual(
                result_confirmation.evidence_command,
                confirmation.evidence_command,
                msg=(
                    f"{label}後の evidence_command が適用した確認結果と一致しない: "
                    f"{result_confirmation.evidence_command!r} != "
                    f"{confirmation.evidence_command!r}"
                ),
            )
            self.assertNotEqual(
                result_confirmation.evidence_command.strip(),
                "",
                msg=(
                    f"{label}後の evidence_command が空または空白のみである: "
                    f"{result_confirmation.evidence_command!r}"
                ),
            )
            self.assertEqual(
                result_confirmation.result,
                confirmation.result,
                msg=(
                    f"{label}後の confirmation.result が適用値と一致しない: "
                    f"{result_confirmation.result!r} != {confirmation.result!r}"
                ),
            )


if __name__ == "__main__":
    # 単体実行用エントリ（`python -m unittest` による探索でも実行可能）。
    unittest.main()
