# プロジェクト全体レビュー報告書兼TODO

## 目的

Codex などの AI 作業者が、プロジェクト全体レビューの結果、未確認事項、対応 TODO を継続作業に利用できる状態で記録する。

## 対象

- リポジトリ: `D:\Users\mgnco\WorkSpace\ServerlessPortfolio`
- 対象範囲: Django アプリケーション、SAM テンプレート、CodePipeline、CodeBuild、IAM、静的ファイル配信、Git hooks、既存テスト
- 作業内容: 読み取りレビューとローカル検証
- 未実施内容: 実装変更、AWS 実環境確認、CodePipeline 実行確認、CloudFormation validate

## 確認済みの状態

- 作業ツリーは `main...origin/main` で未コミット差分なし。
  - 根拠: `git status --short --branch` の出力。
- Git hooks は `.githooks` を参照している。
  - 根拠: `git config --get core.hooksPath` の出力が `.githooks`。
- `.githooks` には `pre-commit`、`commit-msg`、`pre-push` が存在し、いずれも `scripts/agents-compliance-check.ps1` を呼び出す。
  - 根拠: `.githooks/pre-commit`、`.githooks/commit-msg`、`.githooks/pre-push`。
- Django のローカル check は 1 件の warning を出した。
  - 根拠: `.venv\Scripts\python.exe manage.py check` の出力で `staticfiles.W004`。
- Django test は 0 件だった。
  - 根拠: `.venv\Scripts\python.exe manage.py test` の出力で `Found 0 test(s).`、`NO TESTS RAN`。
- 静的 manifest 検査は成功した。
  - 根拠: `.venv\Scripts\python.exe scripts\check_static_manifest.py` の出力で `All static file references are valid.`。

## 重要指摘

### P1: 問い合わせフォーム送信 URL と CSRF 実装が不整合

フォームは `action="/contact"` を指定しているが、URLConf では `portfolio/` 配下に include され、問い合わせ view は `portfolio/contact` に定義されている。

また、JavaScript はフォーム内の `csrfmiddlewaretoken` を参照するが、テンプレート内の `{% csrf_token %}` は問い合わせフォームではなく言語切替フォーム側に存在する。

根拠:

- `templates/portfolio_base.html`: `form id="contactForm"` が `action="/contact"` を指定。
- `portfolio/static/js/scripts.js`: `contactForm.querySelector('[name="csrfmiddlewaretoken"]').value` を参照。
- `config/urls.py`: `path('portfolio/', include('portfolio.urls'))`。
- `portfolio/urls.py`: `path('contact', contact, name='contact')`。
- `rg -n "csrf_token" templates\portfolio_base.html` の結果は言語切替フォーム側のみ。

TODO:

- [x] 問い合わせフォームの action を URL 名から生成する。
- [x] 問い合わせフォーム内に CSRF token を配置する。
- [x] JavaScript 送信で参照する CSRF token が問い合わせフォーム内に存在することをテストする。
- [x] `/portfolio/top/` から問い合わせフォームの送信先と CSRF token を確認する回帰テストを追加する。

対応状況:

- 2026-05-21 に `templates/portfolio_base.html`、`portfolio/views.py`、`portfolio/tests.py` を更新。
- `portfolio.tests.ContactFormSecurityTests` と全 Django test は成功。

### P1: 問い合わせ POST が CSRF exempt

`contact` view に `@csrf_exempt` が付いている。テンプレートと JavaScript は CSRF token を使う前提の実装であり、実装方針が一致していない。

根拠:

- `portfolio/views.py`: `@csrf_exempt`。
- `portfolio/static/js/scripts.js`: `X-CSRFToken` ヘッダーを設定。

TODO:

- [x] `@csrf_exempt` を削除する。
- [x] CSRF 有効状態で POST が view まで到達するテストを追加する。
- [x] CSRF token なしの POST が拒否されるテストを追加する。

対応状況:

- 2026-05-21 に `contact` view から `@csrf_exempt` を削除。
- CSRF token なしの POST が `403` になることをテストで確認。

### P1: `dependencies.yaml` の S3 bucket policy が CloudFront distribution に限定されていない

`dependencies.yaml` は CloudFront サービスプリンシパルに `s3:GetObject` を許可しているが、`AWS:SourceArn` 条件がない。後段の `bucketpolicy.yaml` には `AWS:SourceArn` 条件があるが、パイプラインでは `DeployDependencies` が先に実行され、`BucketPolicyDeploy` は後段である。

根拠:

- `dependencies.yaml`: `AllowCloudFrontOAC` が `cloudfront.amazonaws.com` に `s3:GetObject` を許可。
- `dependencies.yaml`: 同 Statement に `Condition` が確認できない。
- `bucketpolicy.yaml`: `AWS:SourceArn` 条件が存在。
- `pipeline.yaml`: `DeployDependencies` は `BucketPolicyDeploy` より前に実行。

TODO:

- [x] 初回依存リソース作成時点で CloudFront distribution 未限定の bucket policy を作成しない構成へ変更する。
- [x] `dependencies.yaml` と `bucketpolicy.yaml` の責務重複を整理する。
- [ ] staging で bucket policy の実体を確認する。

対応状況:

- 2026-05-21 に `dependencies.yaml` から `AWS::S3::BucketPolicy` を削除し、bucket policy の責務を `bucketpolicy.yaml` に集約。
- 2026-05-21 に `StaticFilesBucket` へ `PublicAccessBlockConfiguration` を追加。
- 2026-05-21 に `docs/architecture.md` の依存リソース説明を更新。
- `dependencies.yaml` と `bucketpolicy.yaml` は CloudFormation validate 済み。

### P2: IAM 権限最適化後も `Resource: "*"` が複数残存

`pipeline.yaml` に `Resource: "*"` が複数残っている。AWS サービス仕様上必要な可能性があるものと、限定可能なものを分離して確認する必要がある。

根拠:

- `pipeline.yaml`: `cloudformation:ValidateTemplate` の `Resource: "*"`。
- `pipeline.yaml`: Route53 read 系の `Resource: "*"`。
- `pipeline.yaml`: CloudFront OAC 系の `Resource: "*"`。
- `pipeline.yaml`: ACM、Route53、CloudFront 管理系の `Resource: "*"`。

TODO:

- [ ] 各 `Resource: "*"` の必要性を AWS 公式仕様で確認する。
- [ ] 限定可能な権限は ARN、条件、タグ条件で縮小する。
- [ ] 限定不能な権限は理由をドキュメント化する。
- [ ] staging pipeline で不足権限の有無を確認する。

### P2: buildspec が翻訳生成とコンパイル失敗を継続する

`makemessages` と `compilemessages` が失敗しても処理を継続する実装がある。プロジェクト規則ではフォールバック禁止が定義されている。

根拠:

- `buildspec.yml`: 各 `makemessages` に `|| echo "...処理を継続します..."` がある。
- `buildspec.yml`: `compilemessages` に `|| echo "...処理を継続します..."` がある。
- `AGENTS.md`: フォールバック禁止を定義。

TODO:

- [ ] 翻訳生成を必須工程にするか、生成工程をデプロイから分離するかを決定する。
- [ ] 失敗時に build を停止する。
- [ ] 翻訳ファイル更新を CI で検出する。

### P2: 静的ファイル配信設計と `public-read` ACL 設定が不整合

ドキュメントは静的ファイルを CloudFront と S3 で配信すると説明しているが、本番設定に `AWS_DEFAULT_ACL = 'public-read'` が残っている。

根拠:

- `docs/architecture.md`: 静的ファイルは Django から直接配信せず、S3 と CloudFront で配信すると記載。
- `config/settings/prod.py`: `AWS_DEFAULT_ACL = 'public-read'`。

TODO:

- [ ] `AWS_DEFAULT_ACL` の必要性を確認する。
- [ ] 不要であれば private 前提の設定に変更する。
- [ ] S3 bucket policy と OAC 前提の配信確認を staging で行う。

### P3: 自動テストが実質存在しない

`portfolio/tests.py` は雛形のみで、Django test は 0 件だった。

根拠:

- `portfolio/tests.py`: `from django.test import TestCase` と雛形コメントのみ。
- `docs/current-state.md`: テストケース未定義と記載。
- `.venv\Scripts\python.exe manage.py test`: `Found 0 test(s).`、`NO TESTS RAN`。

TODO:

- [ ] 問い合わせフォームの validation test を追加する。
- [ ] CSRF 有効時の POST test を追加する。
- [ ] URL routing test を追加する。
- [ ] settings check を CI に追加する。

### P3: `STATICFILES_DIRS` が存在しない `static` ディレクトリを参照

`STATICFILES_DIRS` が `BASE_DIR / "static"` を参照しているが、リポジトリ直下の `static` ディレクトリは存在しない。

根拠:

- `config/settings/base.py`: `STATICFILES_DIRS = [BASE_DIR / "static"]`。
- `Test-Path static`: `False`。
- `manage.py check`: `staticfiles.W004`。

TODO:

- [ ] `STATICFILES_DIRS` の参照先を実在ディレクトリに合わせる。
- [ ] 不要であれば `STATICFILES_DIRS` から削除する。
- [ ] `manage.py check` の warning を 0 件にする。

## 外部資産と依存関係の確認事項

`buildspec.yml` は Google Fonts から `Montserrat.ttf` と `Lato.ttf` を取得し、`requirements.txt` と追加 pip install によって外部パッケージを取得する。ライセンスとバージョン固定の確認が必要である。

根拠:

- `buildspec.yml`: `pip install -r requirements.txt`。
- `buildspec.yml`: `pip install aws-sam-cli`。
- `buildspec.yml`: `pip install csscompressor`。
- `buildspec.yml`: Google Fonts の raw URL から `Montserrat.ttf` と `Lato.ttf` を取得。
- `requirements.txt`: バージョン未固定の依存が列挙されている。
- `.gitignore`: `portfolio/static/assets/fonts/` と `staticfiles/assets/fonts/` は Git 管理外。

TODO:

- [ ] 依存パッケージのバージョン固定方針を決める。
- [ ] `aws-sam-cli` と `csscompressor` のバージョンを固定する。
- [ ] Google Fonts のライセンス記載と取得元の固定方針を決める。
- [ ] 外部資産のライセンス一覧を追加する。

## 優先対応順

1. 問い合わせフォーム URL と CSRF の不整合を修正する。
2. `dependencies.yaml` の S3 bucket policy を CloudFront distribution に限定する。
3. buildspec の継続処理を停止条件へ変更する。
4. `public-read` ACL 設定の必要性を確認し、OAC 前提へ整理する。
5. `Resource: "*"` の必要性を分類し、限定可能な権限を縮小する。
6. 自動テストを追加する。
7. `STATICFILES_DIRS` warning を解消する。
8. 外部資産と依存関係のライセンス、バージョン固定方針を文書化する。

## 未確認事項

- AWS 実環境の現行 bucket policy。
- staging pipeline の最新 execution id、source revision、status。
- CloudFormation validate の結果。
- AWS 各サービスで `Resource: "*"` が仕様上必須かどうか。
- Google Fonts 取得ファイルのライセンス同梱要件。
- 本番環境で問い合わせフォーム送信が実際に失敗しているかどうか。

## 次回作業候補

- `vA.B.C` 作業ブランチで問い合わせフォームと CSRF の修正を行う。
- 先にテストを追加し、現状の失敗を確認してから修正する。
- 修正後に `.venv\Scripts\python.exe manage.py check` と `.venv\Scripts\python.exe manage.py test` を実行する。
- AWS 反映が必要な TODO は、staging pipeline の source revision と実行状態を確認してから完了扱いにする。
