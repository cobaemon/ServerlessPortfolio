"""Property 4 のプロパティテスト（送信結果に応じた応答マッピング）.

本モジュールは design.md「Correctness Properties > Property 4」および tasks.md
1.6 を検証する（出典: tasks.md 行50-55）。
    Property 4: 送信結果に応じた応答マッピング（失敗を握りつぶさない）

検証対象（Validates: Requirements 6.4, 6.5, 6.6, 12.5）:
    - R6-6: Email_Sender 送信成功時は成功結果（`Success`、HTTP 200 系へマッピング）
      を返す（出典: send_contact.py docstring、design.md DM2）。
    - R6-4 / R6-5 / R12-5: Email_Sender が例外を送出した場合、当該例外を握りつぶさ
      ず `exc_info` 付きで明示ログ記録した上で失敗結果（`SendFailed`、HTTP 500 系へ
      マッピング）を返し、呼び出し元へ失敗を伝播する。成功として扱わない
      （フォールバック禁止、出典: send_contact.py docstring、design.md
      Error Handling、第三原則3）。

テスト方針（出典: design.md「Testing Strategy」、tasks.md 冒頭 PBT 方針）:
    - PBT ライブラリは Hypothesis（MPL-2.0。ライセンスは requirements-dev.txt に
      明記済み。本タスクで再追加・再インストールしない）。
    - 単一プロパティを 1 テストで実装し、最小 100 反復（@settings(max_examples=100)）。
    - Django をロードしない（R4-1/R4-2）。ドメイン純粋ロジックのみを対象とする。
    - フォールバック禁止: 送信失敗を握りつぶさず、明示ログ記録と失敗結果の返却を
      明示アサートする。逆に成功時は ERROR ログが発生しないことも明示アサートする。

共有ハーネスの再利用（出典: tasks.md 1.6「reuse the existing harness」）:
    - `test_property_valid_payload.valid_contact_fields`: 全 4 項目が検証制約を満たす
      入力を生成する合成ストラテジ（有効入力の生成に再利用する）。
    - `test_property_valid_payload.RecordingEmailSender`: 送信成功系のテストダブル
      （実送信の副作用を持たず引き渡しを記録する）。
    - 送信失敗系は本モジュールで `FailingEmailSender`（`ports.EmailSender` を実装し
      注入された例外を送出するテストダブル）を新規定義する（単一責務の分離）。

実行コマンド（プロジェクトルートから、Django 非ロード）:
    python -m unittest contact_function.tests.test_property_send_result -v
"""

from __future__ import annotations

import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

from contact_function.domain.contact_payload import ContactPayload
from contact_function.domain.ports import EmailSender
from contact_function.domain.send_contact import (
    SendFailed,
    Success,
    send_contact,
)
from contact_function.domain.send_contact import logger as send_contact_logger

# 共有ハーネス（task 1.4 で確立）を再利用する。有効入力生成ストラテジと
# 送信成功系テストダブルを流用する（出典: tasks.md 1.6、
# test_property_valid_payload.py）。送信元・宛先の代表値はモジュール private な
# 定数への依存を避けるため本モジュールで独自に定義する（カプセル化の尊重）。
from contact_function.tests.test_property_valid_payload import (
    RecordingEmailSender,
    valid_contact_fields,
)

# 送信元・宛先アドレス（設定値由来の代表値）。Property 4 は送信結果の応答
# マッピングを対象とするため固定値を用い、成功/失敗の結果種別を検証する。
_FROM_ADDR = "noreply@example.com"
_TO_ADDR = "owner@example.com"

# 送信失敗の網羅性を高めるため、複数の例外型を注入対象とする。ドメインの
# send_contact は `except Exception` で捕捉する契約のため、これら派生型は
# すべて捕捉・記録・伝播の対象となる（出典: send_contact.py）。型に依存せず
# 「握りつぶさない」ことを検証する目的で複数型を用意する。
_EXCEPTION_TYPES: tuple[type[Exception], ...] = (
    RuntimeError,
    ValueError,
    ConnectionError,
    TimeoutError,
    Exception,
)


class FailingEmailSender(EmailSender):
    """`ports.EmailSender` を実装する送信失敗系テストダブル.

    ドメイン抽象にのみ依存し（依存性逆転・クリーンアーキテクチャ、出典:
    design.md C3, DM3）、`send` 呼び出し時に注入された例外を送出することで SES
    送信失敗を模擬する。呼び出しの発生を記録し、送信が実際に試行されたこと
    （握りつぶし不在）を検証可能にする。
    """

    def __init__(self, exc: Exception) -> None:
        """送出する例外と呼び出し記録用の内部状態を初期化する.

        Args:
            exc: `send` 呼び出し時に送出する例外インスタンス。
        """
        # send で送出する例外（送信失敗の模擬対象）。
        self._exc = exc
        # send が受領した (payload, from_addr, to_addr) を出現順に保持する。
        self.calls: list[tuple[ContactPayload, str, str]] = []

    def send(self, payload: ContactPayload, from_addr: str, to_addr: str) -> None:
        """送信を試行し、必ず注入された例外を送出する（送信失敗の模擬）.

        Args:
            payload: 引き渡された Contact_Payload。
            from_addr: 送信元アドレス（設定値由来）。
            to_addr: 宛先アドレス（設定値由来）。

        Raises:
            Exception: コンストラクタで受領した例外を送出する（ポート契約に整合、
                出典: ports.py「送信に失敗した場合は例外を送出する」）。
        """
        # 送信試行の事実を記録してから例外を送出する。記録により、失敗系でも
        # 送信がスキップされずに試行されたこと（握りつぶし不在）を検証できる。
        self.calls.append((payload, from_addr, to_addr))
        raise self._exc


class SendResultMappingProperty(unittest.TestCase):
    """Property 4（送信結果に応じた応答マッピング）のプロパティテストを保持する."""

    # 最小 100 反復（出典: tasks.md 1.6「Minimum 100 iterations」）。生成データ
    # （最大 5000 文字の message 等）による実行時間のばらつきで per-example の締切
    # 超過が誤検知を招くのを避けるため deadline を無効化する（判定ロジックは
    # 決定的であり、失敗を握りつぶさない）。
    @settings(max_examples=100, deadline=None)
    @given(
        fields=valid_contact_fields(),
        should_fail=st.booleans(),
        exc_index=st.integers(min_value=0, max_value=len(_EXCEPTION_TYPES) - 1),
        exc_message=st.text(max_size=200),
    )
    def test_send_result_is_mapped_and_failure_is_not_swallowed(
        self,
        fields: dict[str, str],
        should_fail: bool,
        exc_index: int,
        exc_message: str,
    ) -> None:
        """Feature: cost-performance-optimization, Property 4: 送信結果に応じた応答マッピング（失敗を握りつぶさない）

        Validates: Requirements 6.4, 6.5, 6.6, 12.5

        制約を満たす任意の有効入力について、注入した送信結果（成功/例外）に応じて
        ユースケースの結果が正しくマッピングされることを検証する（出典:
        send_contact.py、design.md DM2, Error Handling）。
            - 送信成功時: 結果は `Success`（HTTP 200 系へマッピング）であり、送信は
              ちょうど 1 回行われ、ERROR ログは発生しない（R6-6）。
            - 送信例外時: 例外を握りつぶさず ERROR レベルで `exc_info` 付きの明示
              ログを記録した上で、結果は `SendFailed`（HTTP 500 系へマッピング）で
              あり、例外メッセージが失敗結果へ伝播する。成功として扱わない
              （R6-4, R6-5, R12-5、フォールバック禁止）。
        """
        if should_fail:
            # 送信失敗系: 注入した例外を送出するテストダブルを用いる。例外型に
            # 依存せず「握りつぶさない」ことを検証するため複数型から選択する。
            exc = _EXCEPTION_TYPES[exc_index](exc_message)
            sender = FailingEmailSender(exc)

            # 例外送出時に ERROR レベルの明示ログがちょうど記録されることを
            # 確認する（記録されなければ assertLogs 自体が失敗する = 握りつぶし
            # 検出）。出典: send_contact.py `logger.error(..., exc_info=True)`。
            with self.assertLogs(send_contact_logger, level="ERROR") as captured:
                result = send_contact(
                    fields=fields,
                    from_addr=_FROM_ADDR,
                    to_addr=_TO_ADDR,
                    email_sender=sender,
                )

            # 送信が実際に試行されたこと（失敗をスキップ・握りつぶししていない）。
            self.assertEqual(
                len(sender.calls), 1, msg="送信失敗系でも送信はちょうど 1 回試行される"
            )

            # 結果は SendFailed（HTTP 500 系へマッピング、R6-4/R6-5/R12-5）。
            self.assertIsInstance(
                result, SendFailed, msg="送信例外時は SendFailed を返すべき"
            )

            # 例外を握りつぶさず、失敗の文脈（例外メッセージ）が結果へ伝播する。
            # SendFailed 以外はここに到達しないため型を絞り込んでから検証する。
            assert isinstance(result, SendFailed)
            self.assertEqual(
                result.error,
                str(exc),
                msg="送信例外のメッセージは失敗結果へ伝播すべき（握りつぶし禁止）",
            )

            # ERROR ログがちょうど 1 件、かつ exc_info 付きで記録されること
            # （明示ログ記録の証跡、出典: send_contact.py）。
            self.assertEqual(
                len(captured.records), 1, msg="ERROR ログはちょうど 1 件記録されるべき"
            )
            record = captured.records[0]
            self.assertEqual(record.levelname, "ERROR")
            self.assertIsNotNone(
                record.exc_info, msg="例外情報（exc_info）付きで記録されるべき"
            )
        else:
            # 送信成功系: 共有ハーネスの記録用テストダブルを用いる（例外を送出
            # しない）。成功時は失敗ログが一切発生しないことも明示検証する。
            sender = RecordingEmailSender()

            # 成功系では ERROR ログが発生しないことを検証する（誤った失敗記録が
            # 無いこと。assertNoLogs は Python 3.10+、ランタイム python3.12 で利用可）。
            with self.assertNoLogs(send_contact_logger, level="ERROR"):
                result = send_contact(
                    fields=fields,
                    from_addr=_FROM_ADDR,
                    to_addr=_TO_ADDR,
                    email_sender=sender,
                )

            # 結果は Success（HTTP 200 系へマッピング、R6-6）。
            self.assertIsInstance(
                result, Success, msg="送信成功時は Success を返すべき"
            )

            # 送信がちょうど 1 回行われたこと（成功系の引き渡し発生）。
            self.assertEqual(
                len(sender.calls), 1, msg="送信成功系でも送信はちょうど 1 回行われる"
            )


if __name__ == "__main__":
    # 単体実行用エントリ（`python -m unittest` による探索でも実行可能）。
    unittest.main()
