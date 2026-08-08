"""旧資産除去（legacy-asset-cleanup）用パッケージ.

本パッケージは legacy-asset-cleanup spec の「判定層（Decision）」および
その I/O 層に属する Python 成果物を収める名前空間である（出典:
`.kiro/specs/legacy-asset-cleanup/design.md`「Architecture > 依存方向」、
同 tasks.md 1.1）。

判定層のモジュール（`models.py`、`inventory.py`、`removal_plan.py`、
`removal_verification.py`、`completion.py`、`dependency_audit.py`、
`approval.py`）は標準ライブラリのみに依存し、Django・boto3・ファイル I/O・
`subprocess` を import しない。外部 I/O は `cli.py` のみが担う（出典:
design.md「Architecture > 依存方向（クリーンアーキテクチャ・第二原則5）」）。

判定不能・確認未実施は `undetermined` として保留し、既定値で埋めない
（フォールバック禁止、出典: `.kiro/steering/principles.md` 第三原則3、
requirements.md R9-4）。

既存 `scripts/measurement/` パッケージと同一の配置・命名方針に倣う（出典:
design.md「設計上の基本方針 > 既存資産との一貫性」）。
"""
