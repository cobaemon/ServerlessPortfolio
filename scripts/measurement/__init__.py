"""計測・検証スクリプト用パッケージ.

本パッケージは cost-performance-optimization spec の「コスト帰属・実測・
エビデンス記録・非退行検証」（tasks.md 8. 系）に属する Python 成果物を収める
名前空間である（出典: tasks.md 8.1〜8.5、design.md「Testing Strategy > 統合/
スモーク/実測」）。

本パッケージのモジュールは、事実のみを出典付きで記録し、未実測値は
`undetermined`・欠落値は `missing` と明記する（フォールバック禁止、出典:
`.kiro/steering/principles.md` 第一原則・第三原則3、requirements.md R12）。
"""
