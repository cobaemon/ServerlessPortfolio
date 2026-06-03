# プロジェクト全体レビュー報告書兼TODO

## 目的

Codex などの AI 作業者が、プロジェクト全体レビューの結果、未確認事項、対応 TODO を継続作業に利用できる状態で記録する。

## 対象

- リポジトリ: `D:\Users\mgnco\WorkSpace\ServerlessPortfolio`
- 対象範囲: Django アプリケーション、SAM テンプレート、CodePipeline、CodeBuild、IAM、静的ファイル配信、既存テスト
- 作業内容: 読み取りレビューとローカル検証
- 未実施内容: 実装変更、AWS 実環境確認、CodePipeline 実行確認

## 確認済みの状態

- 作業ツリーは `main...origin/main` で未コミット差分なし。
  - 根拠: `git status --short --branch` の出力。
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
- [x] staging で bucket policy の実体を確認する。

対応状況:

- 2026-05-21 に `dependencies.yaml` から `AWS::S3::BucketPolicy` を削除し、bucket policy の責務を `bucketpolicy.yaml` に集約。
- 2026-05-21 に `StaticFilesBucket` へ `PublicAccessBlockConfiguration` を追加。
- 2026-05-21 に `docs/architecture.md` の依存リソース説明を更新。
- `dependencies.yaml` と `bucketpolicy.yaml` は CloudFormation validate 済み。
- 2026-05-21 に staging pipeline revision `a1f6a4ae0e505ead4a0606dd50607431b730a467` の成功を確認。
- 2026-05-21 に staging bucket policy が CloudFront distribution `E18LO9XBUTT6Y9` の `AWS:SourceArn` に限定されていることを確認。
- 2026-05-21 に CloudFront 経由の静的ファイル取得 `200` と S3 直アクセス `403 AccessDenied` を確認。

### P2: IAM 権限最適化後も `Resource: "*"` が複数残存

`pipeline.yaml` に `Resource: "*"` が複数残っていた。AWS サービス仕様上必要な action と ARN 制限可能な action を statement 分割して整理した。

根拠:

- `pipeline.yaml`: `cloudformation:ValidateTemplate` は AWS 公式 Service Authorization Reference で resource type が示されていない。
- `pipeline.yaml`: `route53:ListHostedZonesByName` は AWS 公式 Service Authorization Reference で resource type が示されていない。
- `pipeline.yaml`: `cloudfront:CreateDistribution`、`cloudfront:CreateOriginAccessControl`、`cloudfront:CreateResponseHeadersPolicy`、CloudFront list 系は AWS 公式 Service Authorization Reference で resource type が示されていない。
- `pipeline.yaml`: ACM、Route53、CloudFront、CloudFormation の resource type が示されている action は ARN へ分離済み。

TODO:

- [x] 各 `Resource: "*"` の必要性を AWS 公式仕様で確認する。
- [x] 限定可能な権限は ARN、条件、タグ条件で縮小する。
- [x] 限定不能な権限は理由をドキュメント化する。
- [x] staging pipeline で不足権限の有無を確認する。

対応状況:

- 2026-05-21 に `pipeline.yaml` の `CodeBuildRoute53ReadAccess`、`CodeBuildCloudFrontOACAccess`、`CloudFormationDeploymentAccess` を statement 分割。
- 2026-05-21 に `Resource: "*"` の残存を `cloudformation:ValidateTemplate`、`route53:ListHostedZonesByName`、CloudFront create/list 系、`acm:RequestCertificate` に限定。
- 2026-05-21 に ARN 制限可能な ACM certificate、Route53 hostedzone/change、CloudFront distribution/OAC/response headers policy、CloudFormation stack action を ARN へ縮小。
- 2026-05-21 に `aws cloudformation validate-template --template-body file://pipeline.yaml --profile aws_portfolio_profile` が成功。
- 2026-05-21 に未コミットの `pipeline.yaml` を `sam deploy --template-file pipeline.yaml --config-env staging --no-confirm-changeset` で staging pipeline stack へ直接適用したが、正規の source revision 検証ではないため完了根拠から除外。
- 2026-05-21 に上記の直接適用を rollback し、staging pipeline stack `cobaemon-serverless-portfolio-staging-pipeline` は `origin/dev` revision `a1f6a4ae0e505ead4a0606dd50607431b730a467` の `pipeline.yaml` 相当へ戻した。
- 2026-05-21 に `branch-finalize-next` で `dev` へ統合し、`git push origin dev` で staging pipeline execution `0bfa1ee6-b65c-4a8b-bb3e-a1cfe1d80ce9` を起動した。
- 2026-05-21 に staging pipeline source revision が push した `dev` commit `053190bb09a94a363c8e62181bb174c7eb0831cc` と一致し、全 stage が `Succeeded` であることを確認。
- 2026-05-21 に staging IAM inline policy の `Resource: "*"` が 6 statement に限定され、ARN 制限可能 action が分離されていることを確認。
- 2026-05-21 に staging site `/` が `301` 後 `/portfolio/top/` で `200 OK` になることを確認。

### P2: buildspec が翻訳生成とコンパイル失敗を継続する

`makemessages` と `compilemessages` が失敗しても処理を継続する実装がある。プロジェクト規則ではフォールバック禁止が定義されている。

根拠:

- `buildspec.yml`: 各 `makemessages` に `|| echo "...処理を継続します..."` がある。
- `buildspec.yml`: `compilemessages` に `|| echo "...処理を継続します..."` がある。
- `AGENTS.md`: フォールバック禁止を定義。

TODO:

- [x] 翻訳生成を必須工程にするか、生成工程をデプロイから分離するかを決定する。
- [x] 失敗時に build を停止する。
- [x] 翻訳ファイル更新を CI で検出する。

対応状況:

- 2026-05-22 に `buildspec.yml` の翻訳工程から失敗継続用の `|| echo "...処理を継続します..."` を削除。
- 2026-05-22 に CodeBuild install phase で GNU gettext の `msgfmt` を利用可能にする処理を追加したが、外部ツール追加の明示許可がなかったため同日に削除。
- 2026-05-22 に `makemessages -a` を翻訳カタログ更新漏れ検出として実行し、`PO` の source location と `POT-Creation-Date` を除外して意味内容を比較する処理を追加。
- 2026-05-22 に比較後の `locale` を元に戻してから `compilemessages` を必須実行する処理へ変更。
- 2026-05-22 に staging pipeline execution `4702f9c7-cdd0-4d49-ab97-4aac44ff5756` が source revision `395533f3a4d0a1af4066cce28328addaee9183fa` で `PRE_BUILD` 失敗となり、翻訳カタログ更新漏れ検出が build 停止として機能することを確認。
- 2026-05-22 に staging pipeline execution `ea6b7ffe-3bb0-42d6-8abe-68d2981280fa` が source revision `003c26f797e1896cf085f4f45dcb450f096f3457` で `Succeeded` となることを確認。
- 2026-05-22 に Build action `cobaemon-serverless-portfolio-staging-pipeline-Build:43a688b5-4890-43a1-96c6-13e7d80fe8fc` の `PRE_BUILD`、`BUILD`、`POST_BUILD` が `SUCCEEDED` になることを確認。
- 2026-05-22 に staging site `/` が `301` 後 `/portfolio/top/` で `200 OK`、`/portfolio/top/` が `200 OK` になることを確認。
- 2026-05-22 に未承認外部ツール追加の復旧として GNU gettext 導入行を削除し、staging pipeline execution `35c428d5-4f6d-467c-a059-b3e2a447f932` が source revision `9d6f3dca8622de5bff0451c2bb897c9c97995617` で `Succeeded`、staging site `/` が `/portfolio/top/` への redirect 後 `200`、`/portfolio/top/` が `200` になることを確認。

### P2: 静的ファイル配信設計と `public-read` ACL 設定が不整合

記録時点では、ドキュメントが静的ファイルを CloudFront と S3 で配信すると説明している一方で、本番設定に `AWS_DEFAULT_ACL = 'public-read'` が残っていた。

根拠:

- `docs/architecture.md`: 静的ファイルは Django から直接配信せず、S3 と CloudFront で配信すると記載。
- 変更前の `config/settings/prod.py`: `AWS_DEFAULT_ACL = 'public-read'`。

TODO:

- [x] `AWS_DEFAULT_ACL` の必要性を確認する。
- [x] 不要であれば private 前提の設定に変更する。
- [x] S3 bucket policy と OAC 前提の配信確認を staging で行う。

対応状況:

- 2026-05-23 に django-storages 公式ドキュメントで `AWS_DEFAULT_ACL` の default が `None` であり、未設定時は S3 の default により private になることを確認。
- 2026-05-23 に AWS CloudFront 公式ドキュメントで、OAC では CloudFront distribution に S3 bucket policy で権限を付与する構成であることを確認。
- 2026-05-23 に `config/settings/prod.py` の `AWS_DEFAULT_ACL` を `None` に変更。
- 2026-05-23 に `portfolio.tests.ProductionStaticStorageSettingsTests` を追加し、production settings が public ACL を設定しないことを確認対象に追加。
- 2026-05-25 に `aws_portfolio_profile` で staging pipeline execution `ef1c320f-8dd7-41cb-9114-ca74fc665593` が source revision `2daad62dbc99c56167b3ce7d55ae4304e1927198` で `Succeeded` であることを確認。
- 2026-05-25 に staging app stack `cobaemon-serverless-portfolio-staging-stack` が `UPDATE_COMPLETE`、CloudFront distribution が `E18LO9XBUTT6Y9` であることを確認。
- 2026-05-25 に staging dependencies stack `cobaemon-portfolio-dependencies-staging` が `UPDATE_COMPLETE`、OAC ID が `EC2163L29TXKD`、static bucket が `cobaemon-serverless-portfolio-staging-static` であることを確認。
- 2026-05-25 に staging bucket policy stack `cobaemon-serverless-portfolio-bucketpolicy-staging` が `CREATE_COMPLETE` であることを確認。
- 2026-05-25 に static bucket policy が CloudFront service principal の `s3:GetObject` を `arn:aws:s3:::cobaemon-serverless-portfolio-staging-static/*` に許可し、`AWS:SourceArn` を `arn:aws:cloudfront::864454139429:distribution/E18LO9XBUTT6Y9` に限定していることを確認。
- 2026-05-25 に CloudFront distribution `E18LO9XBUTT6Y9` の S3 origin `cobaemon-serverless-portfolio-staging-static.s3.ap-northeast-1.amazonaws.com` が Origin Access Control `EC2163L29TXKD` に紐付いていることを確認。
- 2026-05-25 に static bucket の PublicAccessBlock が `BlockPublicAcls: true`、`IgnorePublicAcls: true`、`BlockPublicPolicy: true`、`RestrictPublicBuckets: true` であることを確認。
- 2026-05-25 に CloudFront 経由の `https://d2t5vawf3svyin.cloudfront.net/css/styles.min.e55cb46da026.css` が `200 OK`、S3 直接アクセスの `https://cobaemon-serverless-portfolio-staging-static.s3.ap-northeast-1.amazonaws.com/css/styles.min.e55cb46da026.css` が `403 Forbidden` であることを確認。

### P3: 自動テストが実質存在しない

`portfolio/tests.py` は雛形のみで、Django test は 0 件だった。

根拠:

- `portfolio/tests.py`: `from django.test import TestCase` と雛形コメントのみ。
- `docs/current-state.md`: テストケース未定義と記載。
- `.venv\Scripts\python.exe manage.py test`: `Found 0 test(s).`、`NO TESTS RAN`。

TODO:

- [x] 問い合わせフォームの validation test を追加する。
- [x] CSRF 有効時の POST test を追加する。
- [x] URL routing test を追加する。
- [x] settings check を CI に追加する。

対応状況:

- 2026-05-21 に `portfolio.tests.ContactFormSecurityTests` を追加。
- 2026-05-21 に CSRF token 付き invalid payload が view まで到達し `400` になることをテストで確認。
- 2026-05-21 に CSRF token なし POST が `403` になることをテストで確認。
- 2026-05-21 に旧 `/contact` が `404` で、問い合わせフォーム action が `/portfolio/contact` になることをテストで確認。
- 2026-05-25 に `buildspec.yml` へ `python manage.py check --fail-level WARNING` を追加し、staging と prod の `ENV` に応じた `DJANGO_SETTINGS_MODULE` で settings check を実行する構成にした。
- 2026-05-25 に Docker ローカル環境の `verify` service へ `python manage.py check --fail-level WARNING`、Django test、`collectstatic --dry-run`、静的ファイル manifest 参照検査を追加した。

### P3: `STATICFILES_DIRS` が存在しない `static` ディレクトリを参照

`STATICFILES_DIRS` が `BASE_DIR / "static"` を参照しているが、リポジトリ直下の `static` ディレクトリは存在しない。

根拠:

- `config/settings/base.py`: `STATICFILES_DIRS = [BASE_DIR / "static"]`。
- `Test-Path static`: `False`。
- `manage.py check`: `staticfiles.W004`。

TODO:

- [x] `STATICFILES_DIRS` の参照先が不要であることを確認する。
- [x] 不要であれば `STATICFILES_DIRS` から削除する。
- [x] `manage.py check` の warning を 0 件にする。

対応状況:

- 2026-05-25 に `python manage.py findstatic css/styles.css --verbosity 2` と `python manage.py findstatic js/scripts.js --verbosity 2` を実行し、`portfolio/static` 配下の CSS と JS が Django app static として検出されることを確認。
- 2026-05-25 に `config/settings/base.py` から存在しない `BASE_DIR / "static"` を参照する `STATICFILES_DIRS` を削除。
- 2026-05-25 に `config/settings/dev.py` が project root の `BASE_DIR` を維持して `.env` と SQLite DB を参照するように修正。

## 外部資産と依存関係の確認事項

`buildspec.yml` は Google Fonts から `Montserrat.ttf` と `Lato.ttf` を取得し、`requirements.txt` と追加 pip install によって外部パッケージを取得する。ライセンスとバージョン固定の確認が必要である。

根拠:

- `buildspec.yml`: `pip install -r requirements.txt`。
- 変更前の `buildspec.yml`: `pip install aws-sam-cli`。
- 変更前の `buildspec.yml`: `pip install csscompressor`。
- `buildspec.yml`: Google Fonts の raw URL から `Montserrat.ttf` と `Lato.ttf` を取得。
- 変更前の `requirements.txt`: バージョン未固定の依存が列挙されている。
- `.gitignore`: `portfolio/static/assets/fonts/` と `staticfiles/assets/fonts/` は Git 管理外。

TODO:

- [x] 依存パッケージのバージョン固定方針を決める。
- [x] `aws-sam-cli` と `csscompressor` のバージョンを固定する。
- [x] Google Fonts のライセンス記載と取得元の固定方針を決める。
- [x] 外部資産のライセンス一覧を追加する。

対応状況:

- 2026-05-25 に Docker build で未固定の `requirements.txt` が `django-6.0.5` を取得することを確認し、再現可能なローカル環境にはバージョン固定が必要であることを確認。
- 2026-05-25 に `requirements.txt` の direct dependency と transitive dependency を、ローカル `.venv`、Docker build の解決結果、Linux/Docker 専用 `awsgi==0.0.5` の package metadata に基づいて固定。
- 2026-05-25 に `sam --version` で `SAM CLI, version 1.160.1`、`pip show csscompressor` で `csscompressor 0.9.5` を確認し、`buildspec.yml` の追加 pip install を `aws-sam-cli==1.160.1` と `csscompressor==0.9.5` に固定。
- 2026-05-25 に Google Fonts の `ofl/montserrat/OFL.txt` と `ofl/lato/OFL.txt` で SIL Open Font License Version 1.1 を確認。
- 2026-05-25 に `docs/external-assets.md` を追加し、Docker image、Python dependencies、build tools、Google Fonts の取得元とライセンス確認結果を記録。
- 2026-05-26 に `aws cloudformation validate-template --template-body file://pipeline.yaml --region ap-northeast-1 --profile aws_portfolio_profile` が成功。
- 2026-05-26 に `aws cloudformation validate-template --template-body file://bucketpolicy.yaml --region ap-northeast-1 --profile aws_portfolio_profile` が成功。
- 2026-05-26 に `AWS_CLI_FILE_ENCODING=UTF-8` を指定したうえで `aws cloudformation validate-template --template-body file://dependencies.yaml --region ap-northeast-1 --profile aws_portfolio_profile` が成功。
- 2026-05-26 に `AWS_CLI_FILE_ENCODING=UTF-8` を指定したうえで `aws cloudformation validate-template --template-body file://template.yaml --region ap-northeast-1 --profile aws_portfolio_profile` が成功。

## 対応済み優先順

1. 問い合わせフォーム URL と CSRF の不整合を修正する。
2. `dependencies.yaml` の S3 bucket policy を CloudFront distribution に限定する。
3. buildspec の継続処理を停止条件へ変更する。
4. `public-read` ACL 設定の必要性を確認し、OAC 前提へ整理する。
5. `Resource: "*"` の必要性を分類し、限定可能な権限を縮小する。
6. 自動テストを追加する。
7. `STATICFILES_DIRS` warning を解消する。
8. 外部資産と依存関係のライセンス、バージョン固定方針を文書化する。

## 未確認事項

- 本番環境で問い合わせフォーム送信が実際に失敗しているかどうか。

## 次回作業候補

- チェックボックス形式の TODO は全件対応済み。
- 新規 TODO は未設定。
- 先にテストを追加し、現状の失敗を確認してから修正する。
- 修正後に `.venv\Scripts\python.exe manage.py check` と `.venv\Scripts\python.exe manage.py test` を実行する。
- AWS 反映が必要な TODO は、staging pipeline の source revision と実行状態を確認してから完了扱いにする。
