# AI 作業進捗

このディレクトリは、AI 作業進捗、作業途中の AI 用 TODO、AI が使用する確認記録を配置する。

## 配置ルール

AI が作業継続のために使用する進捗、未完了タスク、確認結果、作業メモを配置する。

プロジェクト仕様、設計、設定、運用、デプロイ、開発環境など、継続的に参照するプロジェクトドキュメントは `docs/` 直下に配置する。

作業中に発生した指示違反、手順逸脱、影響発生、復旧対応の記録は `docs/incidents/` に配置する。

開発過程で発生または使用する調査、方針、対応案、検討記録は `docs/development-records/` に配置する。

外部環境、pipeline、stack、site、デプロイ、検証サイトの検証完了または成功を記録する場合は、確認対象、確認結果、source revision、対象差分、commit、execution id など、確認対象を一意に特定できる情報を同じ記録に含める。

## 記録一覧

- [IAM 権限最適化](iam-permission-optimization.md): staging で IAM 権限縮小を検証してから prod へ反映する手順。
- [プロジェクトレビュー TODO](project-review-report-todo.md): プロジェクトレビューに基づく TODO と確認記録。
