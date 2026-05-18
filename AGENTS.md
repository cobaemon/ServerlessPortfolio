## branch-finalize-next

ユーザーが明示的に `branch-finalize-next` の実行を指示した場合のみ実行する。

### 目的

現在の `vA.B.C` 作業ブランチを完了処理する。未コミット変更がある場合のみ commit し、現在ブランチを `dev` に merge し、`dev` から次の作業ブランチ `vA.B.(C+1)` を作成して checkout する。

### 実行コマンド

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\branch-finalize-next.ps1 -ConfirmExecution
```

### スクリプト仕様

- 現在ブランチは `vA.B.C` 形式でなければならない。
- 次ブランチは `A` と `B` を維持し、`C` のみ 1 増やす。
- 未コミット変更がない場合は commit を作成しない。
- 未コミット変更がある場合は、スクリプトが staged diff から title / 対応目的 / コミット内容の概要 / 対応範囲 / ブランチ処理 / 検証を含む commit message を自動生成する。
- commit message はファイル単位の変更点列挙ではなく、変更カテゴリと差分統計に基づく概要を記録する。
- 自動生成した commit message は `git rev-parse --git-path branch-finalize-next-commit-message.txt` で取得される Git 管理外パスに保存する。
- `dev` への merge は `git merge --no-ff` を使用する。

### 禁止

- push
- force push
- reset --hard
- git clean
- rebase
- squash merge
- --no-verify
- 既存ブランチの強制作成・上書き
- 保護対象ドキュメントの無断変更
- タイトルのみの commit message
- スクリプト失敗時の手動 commit / merge / branch 作成代替

### 停止条件

- 現在ブランチが `dev`
- detached HEAD
- 現在ブランチ名が `vA.B.C` 形式ではない
- 次ブランチが既に存在する
- merge conflict
- 保護対象ドキュメント変更
- コマンド終了コードまたはログを確認できない

### 完了報告

以下を必ず報告する。

- 実行コマンド
- 終了ステータス
- source branch
- integration branch
- next branch
- commit 作成有無
- commit SHA
- commit message path
- merge 結果
- 最終作業ツリー状態

### 失敗時

スクリプトが失敗した場合は停止する。手動で commit / merge / branch 作成を代替実行してはならない。失敗箇所、失敗ログ、終了ステータス、継続可否を報告する。
