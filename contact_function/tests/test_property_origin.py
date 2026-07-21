"""Property 3（問い合わせ POST の Origin 検証）のプロパティテストモジュール.

本モジュールは design.md「Correctness Properties > Property 3」を検証する
（出典: design.md 行388-390、tasks.md 2.4）。
    Property 3: 問い合わせ POST の Origin 検証
    *For any* リクエストの Origin 値（許可リスト内・許可リスト外・欠落・空文字の
    いずれか）について、Contact_Function は Origin が許可リストと一致する場合に
    のみ後続の検証および Email_Sender への引き渡しを継続し、一致しない・欠落・
    空の場合は HTTP 4xx 系エラー応答を返して Contact_Payload を Email_Sender へ
    引き渡さない。

検証対象（Validates: Requirements 8.1, 8.2, 8.3, 8.4）:
    - R8-1: 許可 Origin と一致するリクエストのみ受理し、一致時のみ後続の検証・
      Email_Sender への引き渡しを継続する（出典: requirements.md 要件8-1）。
    - R8-2: Origin が許可リストに含まれない場合は HTTP 4xx を返し、Email_Sender
      へ引き渡さない（出典: requirements.md 要件8-2）。
    - R8-3: Origin ヘッダが欠落または空の場合は HTTP 4xx を返し、Email_Sender へ
      引き渡さない（出典: requirements.md 要件8-3）。
    - R8-4: Django の CSRF 保護に相当する送信元検証を新構成でも提供する
      （出典: requirements.md 要件8-4。本テストは Origin 検証の網羅で担保する）。

テスト方針（出典: design.md「Testing Strategy」行445-458）:
    - PBT ライブラリは Hypothesis（MPL-2.0。ライセンスは requirements-dev.txt に
      明記。task 1.4 で導入済みのため再導入しない）。
    - 単一プロパティを 1 テストで実装し、最小 100 反復（@settings(max_examples=100)）。
    - Property 3 の検証対象は `handler.py` の Origin 検証（出典: design.md 行455）。
      Django をロードしない（R4-1/R4-2）。handler は adapters/domain のみに依存する。
    - フォールバック禁止: 生成・検証で問題を握りつぶさず、期待を明示アサートする。

共有ハーネスの再利用（出典: tasks.md 2.4、task 1.4 が確立したハーネス）:
    - `valid_contact_fields()`: 検証を通過する 4 項目入力を生成する合成ストラテジ。
      Origin のみを変数化するため、ボディは常に有効入力とする。
    - `RecordingEmailSender`: `ports.EmailSender` を実装する記録用テストダブル。
      Email_Sender への引き渡し（＝後続継続）の有無を観測する。

依存注入（出典: design.md C3、handler.handle_contact_request のシグネチャ）:
    - `handle_contact_request(event, config_provider, email_sender)` を直接呼ぶ。
      実 AWS 呼び出しを避けるため、`ConfigProvider` の記録なしフェイク実装
      `_FakeConfigProvider` で許可 Origin と送信元/宛先アドレスを供給する。

実行コマンド（プロジェクトルートから、Django 非ロード）:
    python -m unittest contact_function.tests.test_property_origin -v
"""

from __future__ import annotations

import json
import string
import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

from contact_function.domain.ports import ConfigProvider
from contact_function.handler import handle_contact_request
from contact_function.tests.test_property_valid_payload import (
    RecordingEmailSender,
    valid_contact_fields,
)

# 送信元・宛先アドレス（設定値由来の代表値）。Property 3 は Origin 検証を対象と
# するため固定値を用いる（値の内容は本プロパティの検証対象ではない）。
_FROM_ADDR = "noreply@example.com"
_TO_ADDR = "owner@example.com"

# Origin 文字列のホスト部に用いる安全な文字集合（英小文字・数字・ドット・ハイフン）。
# handler は Origin を文字列完全一致で判定するため、区別可能な文字列であればよい
# （出典: handler.py `is_origin_allowed = origin in allowed_origins`）。
_ORIGIN_HOST_ALPHABET = string.ascii_lowercase + string.digits + ".-"

# Origin 値のカテゴリ（許可リスト内・外・欠落・空）。Property 3 の入力空間を網羅する。
_CATEGORY_INSIDE = "inside"  # 許可リストに含まれる Origin
_CATEGORY_OUTSIDE = "outside"  # 許可リストに含まれない Origin
_CATEGORY_MISSING = "missing"  # Origin ヘッダ欠落
_CATEGORY_EMPTY = "empty"  # Origin ヘッダが空文字

# 欠落カテゴリを表す番兵（ヘッダに Origin キー自体を含めないことを示す）。
_ORIGIN_ABSENT = object()


class _FakeConfigProvider(ConfigProvider):
    """`ports.ConfigProvider` を実装する記録なしフェイク（テスト用設定供給）.

    実 Parameter Store / AWS 呼び出しを行わず、コンストラクタで受領した許可 Origin
    一覧と送信元/宛先アドレスをそのまま返す（依存性逆転・クリーンアーキテクチャ、
    出典: design.md C3、ports.py）。設定値の取得失敗系は本プロパティの対象外の
    ため模擬しない（Origin 検証のみに焦点を当てる、単一責務の分離）。
    """

    def __init__(
        self, allowed_origins: tuple[str, ...], from_addr: str, to_addr: str
    ) -> None:
        """フェイク設定プロバイダを初期化する.

        Args:
            allowed_origins: 許可 Origin の不変な列（handler が照合に用いる）。
            from_addr: SES 送信元アドレス（設定値由来の代表値）。
            to_addr: SES 宛先アドレス（設定値由来の代表値）。
        """
        # 受領した許可 Origin 一覧と送信元/宛先を保持する（改変しない）。
        self._allowed_origins = allowed_origins
        self._from_addr = from_addr
        self._to_addr = to_addr

    def get_from_address(self) -> str:
        """SES 送信元アドレスを返す（出典: ports.ConfigProvider.get_from_address）."""
        return self._from_addr

    def get_to_address(self) -> str:
        """SES 宛先アドレスを返す（出典: ports.ConfigProvider.get_to_address）."""
        return self._to_addr

    def get_allowed_origins(self) -> tuple[str, ...]:
        """許可 Origin の不変な列を返す（出典: ports.ConfigProvider.get_allowed_origins）."""
        return self._allowed_origins


def _origin_value() -> st.SearchStrategy[str]:
    """許可リスト内外で区別可能な非空の Origin 文字列を生成するストラテジ.

    scheme（https/http）+ ホスト（英小文字・数字・ドット・ハイフンから成る非空
    文字列）を連結し、`https://example.com` 形式に近い Origin を生成する。ホストは
    min_size=1 のため空文字にはならない（空 Origin は EMPTY カテゴリで別途生成する）。

    Returns:
        SearchStrategy[str]: 非空の Origin 文字列ストラテジ。
    """
    # scheme は代表的な 2 種類から選択する（値の内容は完全一致判定にのみ用いる）。
    scheme = st.sampled_from(["https://", "http://"])
    # ホスト部は安全な文字集合から非空・最大 30 文字で生成する。
    host = st.text(alphabet=_ORIGIN_HOST_ALPHABET, min_size=1, max_size=30)
    # scheme とホストを連結して Origin 文字列を構築する。
    return st.builds(lambda s, h: s + h, scheme, host)


@st.composite
def _origin_scenario(
    draw: st.DrawFn,
) -> tuple[dict[str, str], tuple[str, ...], str, object]:
    """Origin のみを変数化した検証シナリオを生成する合成ストラテジ.

    ボディは常に有効入力（`valid_contact_fields`）とし、許可 Origin 一覧・Origin
    カテゴリ・実際に付与する Origin 値の組を生成する。これにより「Origin だけが
    変化する」入力空間（許可リスト内/外/欠落/空）を網羅する（出典: tasks.md 2.4）。

    Args:
        draw: Hypothesis の draw 関数。

    Returns:
        tuple: (有効入力 4 項目, 許可 Origin 一覧, カテゴリ, 付与する Origin 値)。
            付与する Origin 値は文字列、または欠落を表す番兵 `_ORIGIN_ABSENT`。
    """
    # 常に有効なボディを用いる（Origin 以外を固定するため）。
    fields = draw(valid_contact_fields())

    # 許可 Origin 一覧を 1 件以上・重複なしで生成する（R8-1 の許可リスト）。
    allowlist = draw(
        st.lists(_origin_value(), min_size=1, max_size=5, unique=True)
    )

    # 4 カテゴリを一様に選択し入力空間を網羅する。
    category = draw(
        st.sampled_from(
            [_CATEGORY_INSIDE, _CATEGORY_OUTSIDE, _CATEGORY_MISSING, _CATEGORY_EMPTY]
        )
    )

    if category == _CATEGORY_INSIDE:
        # 許可リスト内: 一覧から 1 件を選び、そのまま付与する。
        origin_value: object = draw(st.sampled_from(allowlist))
    elif category == _CATEGORY_OUTSIDE:
        # 許可リスト外: 候補を生成し、許可リストに含まれないことを保証する。
        # 万一衝突した場合は末尾に文字を追加して一意化する（assume の棄却率を避ける）。
        candidate = draw(_origin_value())
        while candidate in allowlist:
            candidate = candidate + "x"
        origin_value = candidate
    elif category == _CATEGORY_MISSING:
        # 欠落: ヘッダに Origin キー自体を含めない（番兵で表現する）。
        origin_value = _ORIGIN_ABSENT
    else:
        # 空: Origin ヘッダを空文字として付与する。
        origin_value = ""

    return fields, tuple(allowlist), category, origin_value


def _build_event(fields: dict[str, str], origin_value: object) -> dict[str, object]:
    """Origin のみが変化する API Gateway プロキシ統合イベントを構築する.

    ボディは有効入力を JSON で表現する（handler は Content-Type に
    `application/json` を含む場合に JSON として解釈する。出典: handler.py
    `_parse_body`）。JSON 化により任意文字列を bytes へエンコードせずに往復でき、
    Origin 以外の要因での失敗を排除する。

    Args:
        fields: 有効な 4 項目入力（JSON ボディへ格納する）。
        origin_value: 付与する Origin 値。文字列の場合は Origin ヘッダに設定し、
            番兵 `_ORIGIN_ABSENT` の場合は Origin キー自体を含めない（欠落）。

    Returns:
        dict[str, object]: httpMethod=POST の API Gateway プロキシ統合イベント。
    """
    # Content-Type は JSON を明示する（handler の JSON 解釈経路に整合させる）。
    headers: dict[str, str] = {"Content-Type": "application/json"}
    # 欠落カテゴリ以外は Origin ヘッダを設定する（空文字もここで設定される）。
    if origin_value is not _ORIGIN_ABSENT:
        # 番兵でないことは上で確認済みのため文字列として設定する。
        headers["Origin"] = origin_value  # type: ignore[assignment]

    return {
        "httpMethod": "POST",
        "headers": headers,
        # 有効入力を JSON 文字列化する。ensure_ascii は既定（True）で全文字を
        # ASCII エスケープし、bytes エンコードを介さず値を厳密に往復させる。
        "body": json.dumps(fields),
        # base64 エンコードは行わない（body はプレーンな JSON 文字列）。
        "isBase64Encoded": False,
    }


class OriginValidationProperty(unittest.TestCase):
    """Property 3 のプロパティテストを保持するテストケース."""

    # 最小 100 反復（出典: design.md 行452、tasks.md 2.4）。生成データ（最大 5000
    # 文字の message 等）による per-example 締切超過の誤検知を避けるため deadline を
    # 無効化する（検証ロジックは決定的でありエラーは握りつぶさない）。
    @settings(max_examples=100, deadline=None)
    @given(scenario=_origin_scenario())
    def test_origin_validation_gates_handoff(
        self, scenario: tuple[dict[str, str], tuple[str, ...], str, object]
    ) -> None:
        """Feature: cost-performance-optimization, Property 3: 問い合わせ POST の Origin 検証

        Validates: Requirements 8.1, 8.2, 8.3, 8.4

        任意の Origin 値（許可リスト内/外/欠落/空）について、(1) 許可リストと一致
        する場合にのみ後続を継続し（2xx 応答かつ Email_Sender へちょうど 1 回引き
        渡し）、(2) 一致しない・欠落・空の場合は HTTP 4xx 系応答を返し Email_Sender
        へ一切引き渡さないことを検証する（出典: design.md 行388-390、handler.py
        Origin 検証、requirements.md R8-1〜R8-4）。
        """
        # シナリオを分解する（ボディ・許可 Origin 一覧・カテゴリ・付与 Origin 値）。
        fields, allowlist, category, origin_value = scenario

        # Origin のみが変化するイベントを構築する（ボディは常に有効入力）。
        event = _build_event(fields, origin_value)

        # フェイク設定プロバイダと記録用 Email_Sender を注入して handler を実行する。
        config_provider = _FakeConfigProvider(allowlist, _FROM_ADDR, _TO_ADDR)
        sender = RecordingEmailSender()
        response = handle_contact_request(event, config_provider, sender)

        # 応答からステータスコードを取り出す（API Gateway プロキシ統合形式）。
        status_code = response["statusCode"]

        if category == _CATEGORY_INSIDE:
            # 許可リスト一致時（R8-1）: 後続を継続し、有効ボディゆえ送信成功となる。
            # ステータスは 2xx 系であること（成功=200 系、出典: handler.py DM2）。
            self.assertTrue(
                200 <= status_code < 300,
                msg=f"許可 Origin では 2xx を期待したが {status_code} が返った",
            )
            # Email_Sender へちょうど 1 回引き渡されたこと（後続継続の観測）。
            self.assertEqual(
                len(sender.calls),
                1,
                msg="許可 Origin では Email_Sender へちょうど 1 回引き渡すべき",
            )
        else:
            # 不一致・欠落・空（R8-2, R8-3）: HTTP 4xx 系で拒否されること。
            self.assertTrue(
                400 <= status_code < 500,
                msg=(
                    f"許可外/欠落/空 Origin（{category}）では 4xx を期待したが "
                    f"{status_code} が返った"
                ),
            )
            # Email_Sender へ一切引き渡していないこと（非引き渡しの観測、R8-2/R8-3）。
            self.assertEqual(
                len(sender.calls),
                0,
                msg=(
                    f"許可外/欠落/空 Origin（{category}）では Email_Sender へ"
                    "引き渡してはならない"
                ),
            )


if __name__ == "__main__":
    # 単体実行用エントリ（`python -m unittest` による探索でも実行可能）。
    unittest.main()
