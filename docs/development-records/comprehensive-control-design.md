# 包括制御系 実装記録

## 根拠

- 正式設計書: `docs/comprehensive-control-design-formal.md`
- 実装対象: `controls/`, `scripts/control/`, `.codex/hooks.json`, `.codex/hooks/`, `.codex/bin/`, `.githooks/`, `buildspec.yml`, `buildspec-deps.yml`

## 実装方針

- 第一〜第四原則の原文は `controls/principles.yml` を正本とする。
- 不変条件、資産到達可能性、現在ターン契約、報告成立条件、Git、deploy、incident、audit、self-test は `scripts.control.policy_engine` を共通入口にする。
- `controls/*.yml` と `controls/test_cases/*.yml` は、外部 YAML パーサー追加を避けるため JSON 互換 YAML とする。
- CodexHook、Shell wrapper、GitHook、CI gate は判断ロジックを持たず、共通 policy engine を呼び出す。

## 検証コマンド

```bash
python -m json.tool .codex/hooks.json
python -B -m scripts.control.cli --validate-policy
python -B -m scripts.control.cli --validate-hooks
python -B -m scripts.control.cli --validate-githooks
python -B -m scripts.control.self_test
python -B -m scripts.control.cli --self-test
```

## 未確認事項

- project-local CodexHook が実行環境で trusted layer として有効化されているかは未確認。
- remote repository rule、branch protection、AWS IAM、Git credential 分離の実設定は未確認。
- AWS / deploy 検証は現在ターンで deploy 許可がないため未実施。
