"""Property 2（必須項目の網羅と扱いの固定）のプロパティテスト.

Feature: legacy-asset-cleanup, Property 2: *For any* Inventory について、
Inventory_Validator が適合と判定するのは、E-3 / E-4 / E-6 / E-7 由来の必須キー集合、
E-5 由来の保全対象キー集合、E-8 由来の 3 キー、E-9 由来の未検証事項キーをすべて包含し、
かつ E-8 由来キーの `disposition` が `undetermined`、E-5 由来キーの `disposition` が
`保全対象` である場合に限る。

本モジュールは design.md「Correctness Properties > Property 2」および tasks.md 1.4 を
検証する（出典: `.kiro/specs/legacy-asset-cleanup/design.md:619-624`、
`.kiro/specs/legacy-asset-cleanup/tasks.md`「1.4 必須項目網羅のプロパティテストを書く」）。

検証対象（Validates: Requirements 1.4, 1.7, 1.8, 7.11, 9.1, 9.2）:
    - R1-4: Inventory は E-3 / E-4 / E-6 / E-7 由来の必須キーをすべて含む。
    - R1-7: E-8 由来の 3 キーは扱いを `undetermined` に固定する。
    - R1-8: 系統 C（E-5 由来）の対象を扱い `保全対象` として含む。
    - R7-11: 判定対象の dependency 12 件（E-7）を含む。
    - R9-1 / R9-2: E-9 由来の未検証事項キーを `undetermined_notes` に含む。

検証対象モジュール（tasks.md 1.2 実装、出典: `scripts/cleanup/inventory.py`）:
    - `validate_inventory(inventory) -> tuple[str, ...]`
      必須キー網羅・扱い固定・キー重複を含む文書全体の違反を列挙する。空タプルが
      「適合」である（出典: `scripts/cleanup/inventory.py` の `validate_inventory`
      docstring）。

必須キー集合の出典（source of truth）:
    - キー名を本テストへ再列挙せず、`scripts/cleanup/inventory.py` が公開する定数
      （`REQUIRED_ITEM_KEYS_E3` / `_E4` / `_E6` / `_E7` / `_E8`、
      `REQUIRED_PRESERVED_KEYS_E5`、`REQUIRED_NOTE_KEYS_E9_CRITERION_1` / `_2`、
      `REQUIRED_ITEM_KEYS_NEW_DETECTION`）を参照する。これらは design.md DM2
      「必須キー集合」表の写像である（出典: design.md DM2 表）。
    - 条項識別子（`R1-4` / `R1-7` / `R1-8` / `R9-1` / `R9-2` / `DM2-新規検出` /
      `DM2-キー重複`）は design.md DM2 表の「要件」列および同 C2 の検証内容を出典と
      して本テスト内に期待値として明示定義する。

本テストが前提とする既定解釈（実装の検証内容に一致。Approver 承認済み）:
    1. `validate_inventory` は design.md DM2 表の「本設計の新規検出」4 キー
       （`base_contrib_sites` / `template_two_factor_url` /
       `docs_deployment_time_record` / `prod_email_backend_policy`）の包含も条項
       `DM2-新規検出` として要求する。Property 2 の本文はこの 4 キーに言及しないため、
       適合側の生成では常に含める（出典: design.md DM2 表「本設計の新規検出」行、
       `scripts/cleanup/inventory.py` の `REQUIRED_ITEM_KEYS_NEW_DETECTION`）。
    2. `validate_inventory` は `preserved` の全要素について `disposition` が
       `保全対象` であることを要求する（E-5 由来キーに限らない）。これは
       `PreservedAssetItem.disposition` が「保全対象 固定」であることに対応する
       （出典: `scripts/cleanup/models.py` の `PreservedAssetItem` docstring、
       design.md DM1）。
    3. `validate_inventory` は各 `items` 要素の `validate_item` 違反を集約し、
       `validate_item` は `Confirmation.evidence_command` の非空を要求する（R9-3）。
       したがって適合側の生成では `evidence_command` を常に非空とする。
    4. キー重複は `items` + `preserved` を同一名前空間として `DM2-キー重複` で報告し、
       `undetermined_notes` は別名前空間として扱う（出典:
       `scripts/cleanup/inventory.py` の `validate_inventory` docstring）。

ライセンス注記（第二原則6・要ライセンス確認）:
    - Hypothesis は Mozilla Public License 2.0（MPL-2.0）で配布される
      （出典: `requirements-dev.txt:18` の `hypothesis==6.158.0`、公式リポジトリの
      LICENSE.txt）。非配布・非改変での開発・テスト利用である。

テスト方針（出典: design.md「Testing Strategy」、既存
`portfolio/tests/test_property_csp_allowlist.py` と同一様式）:
    - プロパティは「〜である場合に限る」（if and only if）であるため、双方向を検証する。
      適合方向（必須キーを網羅し扱いが固定された Inventory は違反 0 件）と、不適合方向
      （必須キーの欠落・E-8 の扱いの逸脱・`preserved` の扱いの逸脱・キー重複はいずれも
      違反として列挙される）。
    - 最小 100 反復（`@settings(max_examples=100)`）。
    - 検証対象 `scripts/cleanup/inventory.py` は Django 非依存であり、本テストは Django の
      セットアップを必要としない（出典: 同モジュール docstring「Django・boto3 を一切
      用いない」）。
    - フォールバック禁止: 期待を明示アサートし、違反 0 件を黙って許容しない。

実行コマンド（プロジェクトルートから）:
    $env:DJANGO_SETTINGS_MODULE="config.settings.dev"; python manage.py test tests.cleanup.test_property_inventory_required_items
  もしくは（Django 非ロードでも実行可能）:
    python -m unittest tests.cleanup.test_property_inventory_required_items -v
"""

from __future__ import annotations

import string
import unittest
from dataclasses import replace

from hypothesis import given, settings
from hypothesis import strategies as st

from scripts.cleanup.inventory import (
    DISPOSITION_PRESERVED,
    DISPOSITION_REMOVAL_TARGET,
    DISPOSITION_UNDETERMINED,
    REQUIRED_ITEM_KEYS_E3,
    REQUIRED_ITEM_KEYS_E4,
    REQUIRED_ITEM_KEYS_E6,
    REQUIRED_ITEM_KEYS_E7,
    REQUIRED_ITEM_KEYS_E8,
    REQUIRED_ITEM_KEYS_NEW_DETECTION,
    REQUIRED_NOTE_KEYS_E9_CRITERION_1,
    REQUIRED_NOTE_KEYS_E9_CRITERION_2,
    REQUIRED_PRESERVED_KEYS_E5,
    VALID_DISPOSITIONS,
    VALID_STREAMS,
    validate_inventory,
)
from scripts.cleanup.models import (
    Confirmation,
    Inventory,
    LegacyAssetItem,
    PreservedAssetItem,
    UndeterminedNote,
)

# 出典 3 要素・確認コマンドに用いる文字集合。空白のみの値は R1-1 の違反として扱われる
# ため（出典: `scripts/cleanup/inventory.py` の `_is_blank`）、空白を含めない。
_EVIDENCE_ALPHABET = string.ascii_letters + string.digits + "/:.,-_="

# `items` に対する必須キー集合と、欠落時に報告される条項識別子の期待対応
# （出典: design.md DM2 表の「要件」列）。キー名は実装が公開する定数を参照する。
_REQUIRED_ITEM_KEY_EXPECTATIONS: tuple[tuple[str, frozenset[str]], ...] = (
    ("R1-4", REQUIRED_ITEM_KEYS_E3),
    ("R1-4", REQUIRED_ITEM_KEYS_E4),
    ("R1-4", REQUIRED_ITEM_KEYS_E6),
    ("R1-4,R7-11", REQUIRED_ITEM_KEYS_E7),
    ("R1-7", REQUIRED_ITEM_KEYS_E8),
    ("DM2-新規検出", REQUIRED_ITEM_KEYS_NEW_DETECTION),
)

# `undetermined_notes` に対する必須キー集合と条項識別子の期待対応（R9-1、R9-2）。
_REQUIRED_NOTE_KEY_EXPECTATIONS: tuple[tuple[str, frozenset[str]], ...] = (
    ("R9-1", REQUIRED_NOTE_KEYS_E9_CRITERION_1),
    ("R9-2", REQUIRED_NOTE_KEYS_E9_CRITERION_2),
)

# 適合方向で `items` に含めるキーの全体（E-3 / E-4 / E-6 / E-7 / E-8 / 新規検出の和集合）。
# `dep_mangum` は E-3 と E-7 の双方に列挙されるため、和集合としてキー重複を生じさせない。
_ALL_REQUIRED_ITEM_KEYS: frozenset[str] = frozenset().union(
    *(keys for _clause, keys in _REQUIRED_ITEM_KEY_EXPECTATIONS)
)

# 適合方向で `undetermined_notes` に含めるキーの全体（R9-1 + R9-2）。
_ALL_REQUIRED_NOTE_KEYS: frozenset[str] = frozenset().union(
    *(keys for _clause, keys in _REQUIRED_NOTE_KEY_EXPECTATIONS)
)


def _evidence_text() -> st.SearchStrategy[str]:
    """非空（空白のみでない）の出典文字列を生成する.

    戻り値:
        SearchStrategy[str]: 空白を含まない非空文字列（最大 24 文字）。

    例外:
        送出しない。
    """
    return st.text(alphabet=_EVIDENCE_ALPHABET, min_size=1, max_size=24)


@st.composite
def _conformant_inventory(draw: st.DrawFn) -> Inventory:
    """Property 2 に適合する Inventory を生成する.

    生成条件（出典: design.md Property 2、同 DM2 表、`scripts/cleanup/inventory.py`）:
        - `items` は E-3 / E-4 / E-6 / E-7 / E-8 由来および本設計の新規検出キーの
          和集合を過不足なく含む。
        - E-8 由来キーの `disposition` は `undetermined` に固定する（R1-7）。
        - それ以外の `items` は 3 値のいずれかを取り、`confirmation` が `None` の
          ときのみ `undetermined` とする（R1-6。`validate_item` の違反が集約される
          ため、適合方向では R1-6 も満たす必要がある）。
        - `preserved` は E-5 由来キーを過不足なく含み、`disposition` は `保全対象`
          に固定する（R1-8）。
        - `undetermined_notes` は E-9 由来キーを過不足なく含む（R9-1、R9-2）。
        - 出典 3 要素と `Confirmation.evidence_command` はいずれも非空とする
          （R1-1、R9-3）。

    引数:
        draw: Hypothesis の draw 関数。

    戻り値:
        Inventory: Property 2 に適合する Inventory。

    例外:
        送出しない。
    """
    # 出典 3 要素の基底値を 1 組だけ引き、各項目ではキーを連結して非空値を与える。
    # Property 2 は出典文字列の内容を対象としないため、内容の多様性より生成コストの
    # 抑制を優先する（非空性は R1-1 の要件であり必ず満たす）。
    base_path = draw(_evidence_text())
    base_lines = draw(_evidence_text())
    base_command = draw(_evidence_text())

    items: list[LegacyAssetItem] = []
    for key in sorted(_ALL_REQUIRED_ITEM_KEYS):
        stream = draw(st.sampled_from(sorted(VALID_STREAMS)))
        if key in REQUIRED_ITEM_KEYS_E8:
            # R1-7: E-8 由来キーの扱いは undetermined 固定。
            disposition = DISPOSITION_UNDETERMINED
        else:
            disposition = draw(st.sampled_from(sorted(VALID_DISPOSITIONS)))

        if disposition == DISPOSITION_UNDETERMINED:
            # 未確定項目は未確認（None）でも確認済みでもよい（R1-6 は confirmation が
            # None のとき undetermined であることのみを要求する）。
            confirmed = draw(st.booleans())
        else:
            # 確定済みの扱いには確認結果が必要（R1-6）。
            confirmed = True

        confirmation = (
            Confirmation(result=disposition, evidence_command=f"{base_command}:{key}")
            if confirmed
            else None
        )

        items.append(
            LegacyAssetItem(
                key=key,
                description=f"item:{key}",
                stream=stream,
                disposition=disposition,
                source_path=f"{base_path}/{key}",
                source_lines=base_lines,
                detection_command=f"{base_command} {key}",
                confirmation=confirmation,
                removal_check_command=(
                    f"{base_command} --check {key}"
                    if disposition == DISPOSITION_REMOVAL_TARGET
                    else None
                ),
                approver_decision_required=draw(st.booleans()),
            )
        )

    preserved = [
        PreservedAssetItem(
            key=key,
            description=f"preserved:{key}",
            # R1-8: preserved の扱いは 保全対象 固定。
            disposition=DISPOSITION_PRESERVED,
            source_path=f"{base_path}/{key}",
            source_lines=base_lines,
            detection_command=f"{base_command} {key}",
            build_time_dependency=f"{base_command} --render {key}",
        )
        for key in sorted(REQUIRED_PRESERVED_KEYS_E5)
    ]

    notes = [
        UndeterminedNote(
            key=key,
            reason=f"note:{key}",
            pending_check=f"{base_command} --pending {key}",
        )
        for key in sorted(_ALL_REQUIRED_NOTE_KEYS)
    ]

    return Inventory(
        revision=draw(_evidence_text()),
        items=tuple(items),
        preserved=tuple(preserved),
        undetermined_notes=tuple(notes),
    )


@st.composite
def _required_key_selection(draw: st.DrawFn) -> tuple[str, str, str]:
    """欠落させる必須キーを 1 件選ぶ（名前空間・条項識別子・キー）.

    引数:
        draw: Hypothesis の draw 関数。

    戻り値:
        tuple[str, str, str]: (`items` / `preserved` / `undetermined_notes` の
            いずれかの名前空間名, 期待条項識別子, キー名)。

    例外:
        送出しない。
    """
    candidates: list[tuple[str, str, str]] = []
    for clause, keys in _REQUIRED_ITEM_KEY_EXPECTATIONS:
        candidates.extend(("items", clause, key) for key in sorted(keys))
    candidates.extend(
        ("preserved", "R1-8", key) for key in sorted(REQUIRED_PRESERVED_KEYS_E5)
    )
    for clause, keys in _REQUIRED_NOTE_KEY_EXPECTATIONS:
        candidates.extend(
            ("undetermined_notes", clause, key) for key in sorted(keys)
        )
    return draw(st.sampled_from(candidates))


def _has_violation(violations: tuple[str, ...], clause: str, key: str) -> bool:
    """指定の条項識別子とキーに対応する違反が列挙されているかを判定する.

    引数:
        violations: `validate_inventory` の戻り値。
        clause: 期待する条項識別子（例 `"R1-7"`）。
        key: 期待する対象キー。

    戻り値:
        bool: `"<条項識別子>: <キー>: "` で始まる違反が 1 件以上あれば True
            （違反文字列の形式は `scripts/cleanup/inventory.py` の違反生成箇所に
            一致する）。

    例外:
        送出しない。
    """
    prefix = f"{clause}: {key}: "
    return any(violation.startswith(prefix) for violation in violations)


class InventoryRequiredItemsProperty(unittest.TestCase):
    """Property 2 のプロパティテストを保持するテストケース."""

    # 生成データによる per-example 締切超過の誤検知を避けるため deadline を無効化する
    # （検証は決定的であり、失敗を握りつぶさない）。
    @settings(max_examples=100, deadline=None)
    @given(inventory=_conformant_inventory())
    def test_conformant_inventory_has_no_violations(
        self, inventory: Inventory
    ) -> None:
        """Feature: legacy-asset-cleanup, Property 2: 必須項目の網羅と扱いの固定（適合方向）

        Validates: Requirements 1.4, 1.7, 1.8, 7.11, 9.1, 9.2

        必須キー集合（E-3 / E-4 / E-6 / E-7 / E-8 / 新規検出、E-5、E-9）をすべて包含し、
        E-8 由来キーの `disposition` が `undetermined`、`preserved` の `disposition` が
        `保全対象` である Inventory について、`validate_inventory` が違反 0 件（空タプル）
        を返すことを検証する。
        """
        violations = validate_inventory(inventory)
        self.assertEqual(
            violations,
            (),
            msg=f"必須項目を網羅した Inventory が適合と判定されない: {violations!r}",
        )

    @settings(max_examples=100, deadline=None)
    @given(
        inventory=_conformant_inventory(),
        selection=_required_key_selection(),
    )
    def test_missing_required_key_is_reported(
        self, inventory: Inventory, selection: tuple[str, str, str]
    ) -> None:
        """Feature: legacy-asset-cleanup, Property 2: 必須項目の網羅と扱いの固定（欠落方向）

        Validates: Requirements 1.4, 1.7, 1.8, 7.11, 9.1, 9.2

        適合 Inventory から必須キーを 1 件だけ除去すると、`validate_inventory` が当該
        キーの欠落を対応する条項識別子（`R1-4` / `R1-4,R7-11` / `R1-7` / `R1-8` /
        `R9-1` / `R9-2` / `DM2-新規検出`）付きで列挙することを検証する。
        """
        namespace, clause, key = selection

        # 選ばれた名前空間から当該キーの要素のみを除去する。
        if namespace == "items":
            mutated = replace(
                inventory,
                items=tuple(item for item in inventory.items if item.key != key),
            )
        elif namespace == "preserved":
            mutated = replace(
                inventory,
                preserved=tuple(
                    item for item in inventory.preserved if item.key != key
                ),
            )
        else:
            mutated = replace(
                inventory,
                undetermined_notes=tuple(
                    note for note in inventory.undetermined_notes if note.key != key
                ),
            )

        violations = validate_inventory(mutated)
        self.assertNotEqual(
            violations,
            (),
            msg=f"必須キー {key!r}（{namespace}）の欠落が違反として列挙されない",
        )
        # 期待するのは「当該条項・当該キーの違反が列挙されること」のみである。
        # 違反メッセージの文面は requirements.md / design.md のいずれも規定しない
        # ため検証対象としない（Property 2 は必須キーの包含と扱いの固定を定める）。
        self.assertTrue(
            _has_violation(violations, clause, key),
            msg=(
                f"必須キー {key!r} の欠落が条項 {clause} として列挙されない: "
                f"{violations!r}"
            ),
        )

    @settings(max_examples=100, deadline=None)
    @given(
        inventory=_conformant_inventory(),
        key=st.sampled_from(sorted(REQUIRED_ITEM_KEYS_E8)),
        disposition=st.sampled_from(
            sorted({DISPOSITION_REMOVAL_TARGET, DISPOSITION_PRESERVED})
        ),
    )
    def test_e8_disposition_must_stay_undetermined(
        self, inventory: Inventory, key: str, disposition: str
    ) -> None:
        """Feature: legacy-asset-cleanup, Property 2: 必須項目の網羅と扱いの固定（E-8 の扱い）

        Validates: Requirements 1.7

        E-8 由来キーの `disposition` を `undetermined` 以外へ変更すると、
        `validate_inventory` が条項 `R1-7` の違反を列挙することを検証する。
        """
        mutated = replace(
            inventory,
            items=tuple(
                replace(item, disposition=disposition) if item.key == key else item
                for item in inventory.items
            ),
        )

        violations = validate_inventory(mutated)
        self.assertNotEqual(
            violations,
            (),
            msg=f"E-8 由来キー {key!r} の扱い逸脱が違反として列挙されない",
        )
        self.assertTrue(
            _has_violation(violations, "R1-7", key),
            msg=(
                f"E-8 由来キー {key!r} の disposition={disposition!r} が条項 R1-7 "
                f"として列挙されない: {violations!r}"
            ),
        )

    @settings(max_examples=100, deadline=None)
    @given(
        inventory=_conformant_inventory(),
        key=st.sampled_from(sorted(REQUIRED_PRESERVED_KEYS_E5)),
        disposition=st.sampled_from(
            sorted({DISPOSITION_REMOVAL_TARGET, DISPOSITION_UNDETERMINED})
        ),
    )
    def test_preserved_disposition_must_stay_preserved(
        self, inventory: Inventory, key: str, disposition: str
    ) -> None:
        """Feature: legacy-asset-cleanup, Property 2: 必須項目の網羅と扱いの固定（E-5 の扱い）

        Validates: Requirements 1.8

        E-5 由来の保全対象キーの `disposition` を `保全対象` 以外へ変更すると、
        `validate_inventory` が条項 `R1-8` の違反を列挙することを検証する。
        """
        mutated = replace(
            inventory,
            preserved=tuple(
                replace(item, disposition=disposition) if item.key == key else item
                for item in inventory.preserved
            ),
        )

        violations = validate_inventory(mutated)
        self.assertNotEqual(
            violations,
            (),
            msg=f"保全対象キー {key!r} の扱い逸脱が違反として列挙されない",
        )
        self.assertTrue(
            _has_violation(violations, "R1-8", key),
            msg=(
                f"保全対象キー {key!r} の disposition={disposition!r} が条項 R1-8 "
                f"として列挙されない: {violations!r}"
            ),
        )

    @settings(max_examples=100, deadline=None)
    @given(
        inventory=_conformant_inventory(),
        namespace=st.sampled_from(("items", "preserved", "undetermined_notes")),
        index_seed=st.integers(min_value=0, max_value=10**6),
    )
    def test_duplicated_key_is_reported(
        self, inventory: Inventory, namespace: str, index_seed: int
    ) -> None:
        """Feature: legacy-asset-cleanup, Property 2: 必須項目の網羅と扱いの固定（キー重複）

        Validates: design.md C2「検証内容」のキー重複検証

        適合 Inventory の要素を 1 件複製して同一キーを 2 回出現させると、
        `validate_inventory` が条項 `DM2-キー重複` の違反を列挙することを検証する。

        キーの一意性は requirements.md の受入基準ではなく design.md C2 が定める
        （出典: design.md C2 の `validate_inventory` 説明「必須キー網羅・扱い固定・
        キー重複を含む文書全体の違反を列挙する」、および同 C1「正本は 1 つに限定
        する」）。したがって本テストは R1-4 / R1-8 / R9-1 / R9-2 を検証対象として
        掲げない。
        """
        # 複製対象の位置は要素数で剰余を取り、生成した整数の範囲に依存させない。
        if namespace == "items":
            target = inventory.items[index_seed % len(inventory.items)]
            mutated = replace(inventory, items=inventory.items + (target,))
        elif namespace == "preserved":
            target = inventory.preserved[index_seed % len(inventory.preserved)]
            mutated = replace(inventory, preserved=inventory.preserved + (target,))
        else:
            target = inventory.undetermined_notes[
                index_seed % len(inventory.undetermined_notes)
            ]
            mutated = replace(
                inventory,
                undetermined_notes=inventory.undetermined_notes + (target,),
            )

        violations = validate_inventory(mutated)
        self.assertNotEqual(
            violations,
            (),
            msg=f"キー {target.key!r}（{namespace}）の重複が違反として列挙されない",
        )
        self.assertTrue(
            _has_violation(violations, "DM2-キー重複", target.key),
            msg=(
                f"キー {target.key!r}（{namespace}）の重複が条項 DM2-キー重複 として"
                f"列挙されない: {violations!r}"
            ),
        )


if __name__ == "__main__":
    # 単体実行用エントリ（`python -m unittest` による探索でも実行可能）。
    unittest.main()
