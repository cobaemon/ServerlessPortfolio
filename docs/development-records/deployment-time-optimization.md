# デプロイ時間短縮方針

## 目的

CodePipeline と CodeBuild の実行時間を短縮し、開発待ち時間と無料利用枠の消費を抑える。

## 確認対象

- AWS 実行履歴: CodePipeline execution history、CodePipeline action execution history、CodeBuild build details、Source artifact S3 object。
- ローカル定義: `pipeline.yaml`、`buildspec.yml`、`buildspec-deps.yml`、`template.yaml`、`.gitignore`、`.dockerignore`。
- Git 管理状態: tracked files 数、`staticfiles/` tracked files 数、`staticfiles/` tracked size。
- AWS 公式情報: CodePipeline execution / action history、CodeBuild cache、CodeBuild buildspec cache、SAM build cache / parallel option。

## 確認結果

既存 AWS ログ、ローカル定義、Git 管理状態、AWS 公式情報を確認し、Source artifact と dependencies stage を主要な短縮対象として特定した。

### AWS 実測

直近 5 件の CodePipeline execution のうち、成功した 3 件を確認した。

| Pipeline execution id | source revision | Pipeline 全体 | BuildDependencies | DeployDependencies | Build | CloudFormationDeploy | BucketPolicyDeploy |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `b8e68a5f-7ad4-4e5e-a267-f31057b841ef` | `5ecb77c3ddd52f9bdef2ab6c6d12c157b18610b4` | 約 12 分 40 秒 | 279 秒 | 33 秒 | 403 秒 | 33 秒 | 2 秒 |
| `be5b75ee-51e9-4df0-9bc8-60c9313f5213` | `2daad62dbc99c56167b3ce7d55ae4304e1927198` | 約 13 分 10 秒 | 247 秒 | 33 秒 | 401 秒 | 33 秒 | 2 秒 |
| `0c3e7ca9-8edf-4f41-a58b-5f8c8aa051e1` | `f959be5403bbcbb18968dbb7b6776377785bc8eb` | 約 14 分 13 秒 | 340 秒 | 33 秒 | 402 秒 | 64 秒 | 2 秒 |

確認コマンド:

```powershell
aws codepipeline list-pipeline-executions --pipeline-name cobaemon-serverless-portfolio-pipeline --max-results 5 --region ap-northeast-1 --profile aws_portfolio_profile
aws codepipeline list-action-executions --pipeline-name cobaemon-serverless-portfolio-pipeline --filter pipelineExecutionId=<execution id> --region ap-northeast-1 --profile aws_portfolio_profile
```

### CodeBuild phase

3 件の成功 execution に紐づく Deps / Build の 6 build を確認した。全 build の `cache.type` は `NO_CACHE` だった。

| Build id | 用途 | total | QUEUED | PROVISIONING | DOWNLOAD_SOURCE | INSTALL | PRE_BUILD | BUILD | POST_BUILD |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `Deps:7f968797-e1fe-4f8d-a6eb-ccb39d49d2ab` | dependencies | 334 秒 | 71 秒 | 3 秒 | 242 秒 | 11 秒 | 0 秒 | 2 秒 | 0 秒 |
| `Build:e0254c2a-e1bb-463d-9b2e-f386c043f297` | app | 389 秒 | 0 秒 | 7 秒 | 224 秒 | 46 秒 | 33 秒 | 62 秒 | 11 秒 |
| `Deps:e3673bee-55a7-4712-9b16-5e926f7f507e` | dependencies | 246 秒 | 0 秒 | 4 秒 | 225 秒 | 11 秒 | 0 秒 | 2 秒 | 0 秒 |
| `Build:b76d7d3b-aa0d-4469-826d-348b1ebd8d09` | app | 388 秒 | 0 秒 | 7 秒 | 223 秒 | 49 秒 | 29 秒 | 64 秒 | 11 秒 |
| `Deps:6096c8a2-d59e-448a-911f-b79e8b763ebf` | dependencies | 247 秒 | 0 秒 | 4 秒 | 226 秒 | 11 秒 | 0 秒 | 2 秒 | 0 秒 |
| `Build:ce247664-a96d-410f-9946-cd38e03c43b4` | app | 373 秒 | 0 秒 | 7 秒 | 211 秒 | 45 秒 | 29 秒 | 61 秒 | 15 秒 |

確認コマンド:

```powershell
aws codebuild batch-get-builds --ids <build ids> --region ap-northeast-1 --profile aws_portfolio_profile
```

### Source artifact と Git 管理状態

| 項目 | 確認結果 | 根拠 |
| --- | ---: | --- |
| Source artifact size | 15,476,662 bytes、15,470,220 bytes、15,428,470 bytes | `aws s3api head-object` |
| Git tracked files | 731 files | `git ls-files` |
| `staticfiles/` tracked files | 612 files | `git ls-files staticfiles` |
| `staticfiles/` tracked size | 15,640,822 bytes | `git ls-files staticfiles` と `Get-Item` |
| `staticfiles/` actual files | 620 files | `Get-ChildItem staticfiles -Recurse -File` |
| `.dockerignore` | `staticfiles` を除外している | `.dockerignore` |
| `.gitignore` | `staticfiles/assets/fonts/` のみ除外している | `.gitignore` |

### ローカル構成

- `pipeline.yaml` は `Source`、`UpdatePipeline`、`BuildDependencies`、`DeployDependencies`、`Build`、`Deploy` の stage を定義している。
- `BuildDependencies` と `Build` はどちらも同じ Source artifact を input にする。
- `BuildDependencies` は `buildspec-deps.yml` を使用し、実測では `BUILD` phase が 2 秒だった。
- `Build` は `buildspec.yml` を使用し、`pip install`、Django check、翻訳処理、font 取得、静的ファイル生成、S3 sync、`sam build --use-container`、`sam package` を実行する。
- `pipeline.yaml`、`buildspec.yml`、`buildspec-deps.yml` に CodeBuild cache 設定は確認できない。
- `CodeBuildProject` は `PrivilegedMode: true`、`CodeBuildDepsProject` は `PrivilegedMode: false`。

### AWS 公式情報

- CodePipeline は execution history と action execution details を確認できる。AWS 公式ドキュメントは `list-pipeline-executions` と `list-action-executions` を案内している。
- CodeBuild は S3 cache または local cache を使用できる。local cache は source cache、Docker layer cache、custom cache を選べる。
- CodeBuild buildspec は `cache` section と `paths` を定義できる。
- SAM CLI `sam build` は `--cached` と `--parallel` を持つ。`--cached` は変更されていない build artifacts を再利用する。

## 未確認事項

- `staticfiles/` を Git 管理から外した場合の公開サイト差分、S3 sync 差分、rollback 手順。
- `BuildDependencies` / `DeployDependencies` を通常デプロイから外す場合の初回構築、drift 対応、依存テンプレート変更時の運用手順。
- CodeBuild local cache を有効化した場合の hit 率。
- `sam build --use-container --cached` を有効化した場合の cache hit 条件と非 cache build 手順。
- CodeBuild 標準 image に `aws-sam-cli==1.160.1` と `csscompressor==0.9.5` が導入済みかどうか。
- 直近 1 か月の CodeBuild build minutes の課金実績。

## 判断

追加のコマンド単位ログを入れる前に、既存 AWS ログだけで主要ボトルネックは確認できた。

3 件の成功実行では、`DOWNLOAD_SOURCE` が Deps build で 225-242 秒、app build で 211-224 秒だった。Deps build は実処理の `BUILD` phase が 2 秒で、ほぼ source download と install のために 4 分以上を消費している。

したがって、最優先は `buildspec.yml` への実測ログ追加ではなく、Source artifact 削減と dependencies stage の通常経路からの分離である。

## 対応案 A: Source artifact を削減する

### 内容

- `staticfiles/` を Git tracked source から外す。
- `staticfiles/` は build 時の `collectstatic` と `render_static` で生成し、S3 sync へ渡す。
- 移行時は、削除対象、生成対象、S3 sync 結果、公開 URL を確認する。

### 効果見込み

Source artifact は 15.4 MB 台で、`staticfiles/` tracked size は 15.6 MB、tracked files 731 件中 612 件が `staticfiles/` 配下だった。

Deps / Build の両方が Source artifact を取得しており、`DOWNLOAD_SOURCE` は 1 execution あたり合計 437-466 秒だった。Source artifact 削減が効けば、両方の CodeBuild に効果が出る。

### 注意点

- `staticfiles/` を外す前に、`collectstatic` と `render_static` だけで必要な成果物が再生成できることを確認する。
- S3 sync の `--delete` があるため、生成漏れがあると配信ファイル削除につながる。
- static manifest の検査が必要である。

### 優先度

最優先。

## 追加対応案 B: docs / 制御系のみの push で pipeline を起動しない

### 確認対象

- AWS CodePipeline pipeline type: `cobaemon-serverless-portfolio-pipeline`、`cobaemon-serverless-portfolio-staging-pipeline`。
- AWS CodePipeline trigger 仕様: V2 pipeline の Git push file path filter。
- ローカル定義: `pipeline.yaml`、`buildspec.yml`、`buildspec-deps.yml`、`template.yaml`、`dependencies.yaml`、`bucketpolicy.yaml`、`requirements.txt`、`samconfig.toml`、`Dockerfile`、`.dockerignore`、`manage.py`、`asgi_lambda.py`、`config/`、`portfolio/`、`templates/`、`locale/`、`scripts/generate_static_assets.py`、`scripts/check_static_manifest.py`。

### 確認結果

- prod pipeline と staging pipeline はどちらも AWS 側で `pipelineType = V2`、`triggers = null` だった。
- AWS CodePipeline trigger は push event に branch filter と file path filter を設定でき、exclude pattern は include pattern より優先される。
- 現行の deploy、build、runtime に影響する source から、denylist 候補の `docs/**`、`AGENTS.md`、`.githooks/**`、`scripts/agents-compliance-check.ps1`、`scripts/branch-finalize-next.ps1`、`README.md`、`LICENSE`、`.kiro/**` への参照は確認されなかった。
- CodePipeline の `FilePaths.Excludes` は AWS 側 validation で最大8件に制限されるため、denylist は上記8件に限定する。
- `pipeline.yaml` に V2 trigger を明示し、`FilePaths.Excludes` で denylist を設定する。
- `scripts/agents-compliance-check.ps1` に、deploy、build、runtime に影響する source が CodePipeline trigger denylist path を参照する staged 変更を停止する検査を追加する。

### 未確認事項

- staging 反映後に、docs-only push で pipeline が起動しないこと。
- staging 反映後に、docs と deploy 対象 path が混在する push で pipeline が起動すること。
- staging 反映後に、unknown root file の push で pipeline が起動すること。
- unknown root file 検証で追加する一時ファイルを削除した後も、最終作業ツリーに検証用ファイルが残らないこと。

### 採用条件

- include allowlist は使用しない。
- denylist は deploy、build、runtime に影響しないと確認済みの path だけに限定する。
- 未知の新規ファイルは pipeline 起動側に倒す。
- staging で docs-only、mixed、unknown root file の検証を実施し、source revision、execution id、pipeline 起動有無を記録する。

### staging 実装反映確認

確認対象:

- `cobaemon-serverless-portfolio-staging-pipeline` の pipeline 定義。
- source revision `fb29525618f05c37d35e2aa5ac1135e1c66a9e3c` の pipeline execution。
- CloudFormation stack `cobaemon-serverless-portfolio-staging-pipeline`。

確認結果:

- `aws codepipeline get-pipeline` で、`FilePaths.Excludes` に `docs/**`、`AGENTS.md`、`.githooks/**`、`scripts/agents-compliance-check.ps1`、`scripts/branch-finalize-next.ps1`、`README.md`、`LICENSE`、`.kiro/**` が反映済みであることを確認した。
- execution `54edf18a-7507-4784-b011-bfa32923c123` は source revision `fb29525618f05c37d35e2aa5ac1135e1c66a9e3c` で起動し、`Source` action と `UpdatePipeline / SelfMutate` action は `Succeeded` だった。
- 同 execution の最終 status は `Cancelled`、status summary は `Pipeline definition was updated` だった。
- CloudFormation stack `cobaemon-serverless-portfolio-staging-pipeline` は `UPDATE_COMPLETE` だった。

追加確認結果:

- docs-only push: source revision `badfd3b01c1bd714ac7065b56943a565cff0017c` を `dev` に push 後、75 秒後の最新 execution は `54edf18a-7507-4784-b011-bfa32923c123` のままで、同 revision の execution は作成されなかった。
- docs と deploy 対象 path の mixed push: source revision `34b069e12a92568432dae24b839178dcf6008b9c` で execution `a6b56902-c4a3-4653-9aed-3dd44a825819` が起動し、`Succeeded` になった。
- unknown root file push: source revision `0c0d9de781a16a878e3b89a1492d88f127a1faf2` で execution `2de15534-d4a1-4d7e-a6c4-b3bb1cf1967a` が起動し、`Succeeded` になった。
- cleanup push: source revision `49a1e993c2d5164629040164150f4cda3542c504` で execution `57421bc7-f822-4356-aae1-42e8c35156db` が起動し、`Succeeded` になった。
- cleanup 後、`git ls-files pipeline-trigger-verification.tmp` は空で、検証用一時ファイルは Git 管理に残っていない。
- cleanup 後の staging site `https://staging.serverless.portfolio.cobaemon.com/` は HTTP 200、title `Portfolio`、content length `40650` だった。
- cleanup 後の staging site が参照する主要静的ファイルは HTTP 200 だった。対象は `fonts.f852bbc34226.css`、`styles.min.e55cb46da026.css`、`scripts.4539c5f9bede.js`。

未確認事項:

- prod pipeline への反映は未実施。

## 対応案 B: dependencies stage を通常デプロイから分離する

### 内容

- `BuildDependencies` と `DeployDependencies` を通常アプリ更新 pipeline から外す。
- `dependencies.yaml`、`bucketpolicy.yaml`、CloudFront OAC、静的 bucket、bucket policy に関わる変更時だけ依存リソース手順を実行する。
- 通常デプロイは app build と app stack deploy に集中させる。

### 効果見込み

直近 3 件では `BuildDependencies` が 247-340 秒、`DeployDependencies` が 33 秒だった。合計で 280-373 秒を通常デプロイから外せる可能性がある。

Deps build の `BUILD` phase は 2 秒で、`DOWNLOAD_SOURCE` が 225-242 秒だったため、毎回実行する効率が悪い。

### 注意点

- 初回構築、依存リソース変更、drift 復旧の runbook が必要。
- pipeline 自体の設計変更になるため、staging 相当の検証手順が必要。
- dependencies stack の更新漏れを防ぐ条件を明文化する必要がある。

### 優先度

Source artifact 削減と並行検討。通常デプロイ短縮効果は大きい。

## 対応案 C: CodeBuild cache と SAM cache を導入する

### 内容

- CodeBuild project cache を設定する。
- buildspec の cache paths に pip cache と SAM cache を追加する。
- app build では `sam build --use-container --cached` を検討する。
- Docker layer cache は `PrivilegedMode: true` の app build だけ候補にする。

### 効果見込み

直近 3 件の app build では `INSTALL` が 45-49 秒、`BUILD` が 61-64 秒だった。Source artifact と dependencies stage の方が支配的だが、次点の短縮対象になる。

### 注意点

- CodeBuild local cache は同じ host に依存するため、常に hit する保証はない。
- Docker layer cache は privileged mode を使うため、セキュリティ影響の確認が必要。
- SAM `--cached` は未 pin の third-party module 更新を検出しない。現行 `requirements.txt` は pin 済みだが、依存変更時は非 cache build 手順が必要。

### 優先度

第 3 優先。

## 対応案 D: build tool と font 取得を事前化する

### 内容

- `aws-sam-cli==1.160.1`、`csscompressor==0.9.5`、Google Fonts TTF の毎回取得をやめる案を検討する。
- 候補は custom CodeBuild image、artifact bucket、または repository 管理。

### 効果見込み

app build の `INSTALL` は 45-49 秒だった。毎回の tool install と network download を削減できる可能性がある。

### 注意点

- custom image は ECR 管理と更新管理が増える。
- font や tool を repository / artifact 管理に変える場合は、ライセンス確認、通告、ユーザー明示許可が必要。
- Source artifact 削減前に font を repository 管理へ寄せると artifact 削減方針と衝突する可能性がある。

### 優先度

第 4 優先。

## 対応案 E: コマンド単位の追加ログを必要箇所だけ入れる

### 内容

- CodeBuild phase より細かい内訳が必要な箇所だけ、開始 / 終了時刻を出力する。
- 対象は app build の `PRE_BUILD` と `BUILD` に限定する。

### 効果見込み

現時点の最大ボトルネックは既存ログで確認済みのため、追加ログ自体は短縮策ではない。Source artifact 削減、stage 分離、cache 導入後に残った遅延を切り分ける用途に限定する。

### 注意点

- Secrets の値は出力しない。
- ログを増やしてもデプロイ時間は短縮しない。

### 優先度

第 5 優先。

## 優先順位

| 優先 | 対応案 | 理由 |
| --- | --- | --- |
| 1 | Source artifact 削減 | 3 件の成功実行で `DOWNLOAD_SOURCE` が最大。`staticfiles/` が tracked files の大半を占める。 |
| 2 | dependencies stage 分離 | 通常デプロイから 280-373 秒を外せる可能性がある。 |
| 3 | CodeBuild / SAM cache | app build の `INSTALL` と `BUILD` に効く可能性がある。 |
| 4 | build tool / font 取得の事前化 | install phase を削減できる可能性があるが管理負荷が増える。 |
| 5 | 追加ログ | 既存ログで主要ボトルネックは確認済み。残課題の切り分け用途に限定する。 |

## 推奨実施順

1. `staticfiles/` の Git 管理除外に向けた影響確認を行う。
2. `collectstatic`、`render_static`、`scripts/check_static_manifest.py` で生成物が揃うことをローカルで確認する。
3. Source artifact 削減差分を作成する。
4. dependencies stage 分離の設計を作成する。
5. CodeBuild / SAM cache 導入差分を作成する。

## 参照

- [AWS CodePipeline execution history](https://docs.aws.amazon.com/codepipeline/latest/userguide/executions-view.html)
- [AWS CodeBuild cache](https://docs.aws.amazon.com/codebuild/latest/userguide/build-caching.html)
- [AWS CodeBuild buildspec reference](https://docs.aws.amazon.com/codebuild/latest/userguide/build-spec-ref.html)
- [AWS SAM CLI sam build command reference](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-cli-command-reference-sam-build.html)
- [`pipeline.yaml`](../../pipeline.yaml)
- [`buildspec.yml`](../../buildspec.yml)
- [`buildspec-deps.yml`](../../buildspec-deps.yml)
- [`template.yaml`](../../template.yaml)
- [外部資産とライセンス](../external-assets.md)
