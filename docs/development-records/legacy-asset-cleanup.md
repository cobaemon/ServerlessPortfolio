# 旧資産クリーンアップ（legacy-asset-cleanup）実施記録

## 目的

先行 spec `cost-performance-optimization` による表示経路の静的化および脱 Django の結果として参照されなくなった旧資産を、系統 A（リポジトリ内除去）／系統 B（設定整合除去）／系統 C（ビルド時依存の保全）／系統 D（未使用 dependency 除去）の 4 系統で処理した実施内容、実行コマンド、確認結果、非退行確認結果、および残存する `undetermined` 項目を記録する（R10-5: `.kiro/specs/legacy-asset-cleanup/requirements.md:326`）。

## 対象と前提

| 項目 | 内容 | 出典 |
| --- | --- | --- |
| 作業ブランチ | `v3.7.2` | `git rev-parse --abbrev-ref HEAD` の出力 `v3.7.2` |
| source revision | `5f4ad0d`（`docs(records): record the staging and prod stack updates for the Django retirement`） | `git log --oneline -1` |
| 本 spec による commit | 0 件（全変更が作業ツリー上の未コミット差分） | `git log --oneline -1` の HEAD が `5f4ad0d` のまま |
| Legacy_Asset_Inventory（正本） | `docs/legacy-asset-inventory.json`（`revision: 5f4ad0d`、`items` 41 件 / `preserved` 6 件 / `undetermined_notes` 7 件） | `python -m scripts.cleanup.cli --validate-inventory` の出力 |
| 非退行レコード・AWS 側状態（正本） | `docs/development-records/legacy-asset-cleanup-records.json` | `python -m scripts.cleanup.cli --evaluate` の入力 |

本記録は事実の二重管理を避けるため、項目単位の出典・判定根拠・確定手段を `docs/legacy-asset-inventory.json` に、非退行の実測値と AWS 照会結果を `docs/development-records/legacy-asset-cleanup-records.json` に置き、本記録はそれらを参照する（R10-4: `requirements.md:326`）。

## 確認対象

- 作業ツリーの実体および `git diff HEAD` の差分（系統 A / B / D の適用結果）。
- `docs/legacy-asset-inventory.json`（Inventory の 41 items / 6 preserved / 7 undetermined_notes）。
- `docs/development-records/legacy-asset-cleanup-records.json`（`NonRegressionRecord` 3 件、`AwsSmtpState`、`applied_stream_b_segments` 8 件）。
- 判定層 CLI（`python -m scripts.cleanup.cli` の `--validate-inventory` / `--verify-lines` / `--check-residual` / `--audit-dependencies` / `--evaluate`）。
- `docs/development.md:5` の direct / transitive 併記方針（R10-7: `requirements.md:329`）。

## 実施内容と実行コマンド

差分行数はいずれも `git diff --numstat HEAD -- <path>` の実測値（追加行 / 削除行）。

### 系統 A-1: Django on Lambda 残骸のリポジトリ内除去（tasks.md 7.1）

| 対象 | 実施内容 | 差分 |
| --- | --- | ---: |
| `asgi_lambda.py` | `git rm` により git 追跡下から除去 | 0 / 12 |
| `.aws-sam/build.toml` | `git rm --cached` により git 追跡解除 | 0 / 12 |
| `.gitignore` | `# SAM build artifacts` と `.aws-sam/` を追記（`staticfiles/` と同じ生成物除外の位置づけ） | 3 / 0 |

実行コマンド:

```powershell
git rm asgi_lambda.py
git rm --cached .aws-sam/build.toml
git ls-files -- asgi_lambda.py
git ls-files -- .aws-sam/
git check-ignore -v .aws-sam/build.toml
```

確認結果: `git ls-files -- asgi_lambda.py` / `git ls-files -- .aws-sam/` はいずれも一致 0 件（R3-1 / R3-2）、`git check-ignore -v .aws-sam/build.toml` は `.gitignore:173` の `.aws-sam/` 規則を報告（R3-3）。出典は `--check-residual` の出力 `[R3-1] asgi_lambda: 適合（一致 0 件）` / `[R3-2] aws_sam_build_toml: 適合（一致 0 件）` / `[R3-3] gitignore_aws_sam: 適合（一致 1 件）`。

### 系統 A-2: 無効化済み認証のデッドコードと未使用 import の除去（tasks.md 9.1 / 9.2）

| 対象 | 実施内容 | 差分 |
| --- | --- | ---: |
| `config/settings/base.py` | 未使用 import 2 件（`from django.contrib import messages` / `from django.urls import reverse_lazy`）と、`INSTALLED_APPS`（allauth 5 行 / django_otp 2 行 / `# 'accounts',`）、`MIDDLEWARE` 2 行、`TEMPLATES.DIRS` 1 行、および無効化済み認証設定のコメントブロック（`SITE_ID` / `AUTH_USER_MODEL` / `AUTHENTICATION_BACKENDS` / `ACCOUNT_*` / `SITE_NAME` / `APPEND_SLASH` / `MESSAGE_TAGS` / `SOCIALACCOUNT_ADAPTER`）を除去 | 0 / 66 |
| `config/urls.py` | allauth ログインリダイレクトのコメント 2 行と `# path('accounts/', include('accounts.urls')),` を除去。`RedirectView` の import は `favicon.ico` リダイレクトで有効利用中のため保持 | 0 / 3 |

実行コマンド（確認）:

```powershell
git grep -n -E "allauth|django_otp" -- config/
git grep -n "accounts" -- config/
git grep -n -E "from django.contrib import messages|from django.urls import reverse_lazy" -- config/settings/base.py
```

確認結果: 3 コマンドいずれも一致 0 件 / 終了コード 1（R6-1 / R6-2 / R6-3）。有効設定（`INSTALLED_APPS` / `MIDDLEWARE` / `TEMPLATES` / `CONTENT_SECURITY_POLICY` / `LANGUAGES` / `LOGGING`）は保持（R6-4）。出典は `--check-residual` の該当行。

### 系統 B: SMTP 経路の同時整合除去（tasks.md 12.1〜12.6。8 区分を単一変更単位で適用）

`docs/development-records/legacy-asset-cleanup-records.json` の `applied_stream_b_segments` は 8 件（`B-1_prod_settings` / `B-2_prod_comment` / `B-3_dev_settings` / `B-4_forms_log` / `B-5_forms_exception` / `B-6_views_callsite` / `B-7_buildspec` / `B-8_tests_and_docs`）。

| 区分 | 対象 | 実施内容 | 差分 |
| --- | --- | --- | ---: |
| B-1 / B-2 | `config/settings/prod.py` | `EMAIL_HOST` / `EMAIL_PORT` の必須チェックと `EMAIL_USE_TLS` / `EMAIL_USE_SSL` の読み込み・排他チェックを除去し、同一箇所へ `EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"` を明示設定（R4-17）。SMTP に関するコメント記述を除去後の実体と一致する内容へ更新（R4-2） | 14 / 19 |
| B-3 | `config/settings/dev.py` | SMTP 値読み込み・排他チェック・バックエンド分岐を除去し `EMAIL_BACKEND` を console の単一値へ置換（R4-3）。分岐除去により未使用となる `from django.core.exceptions import ImproperlyConfigured` を除去 | 7 / 18 |
| B-4 / B-5 | `portfolio/forms.py` | `settings.EMAIL_BACKEND` / `EMAIL_HOST` / `EMAIL_PORT` / `EMAIL_USE_TLS` / `EMAIL_USE_SSL` を参照する `logger.info` 2 件を除去。`except Exception` で `False` を返すフォールバックを除去し、`email.send()` の例外を呼び出し元へ伝播させる形へ変更（成功時は真偽値を返さない。R4-7） | 12 / 17 |
| B-6 | `portfolio/views.py` | `Top.form_valid` と `contact` の `if form.send_email():` による真偽分岐を除去し、送信呼び出し後に成功応答を返す形へ変更（R4-7）。`contact` に日本語 docstring を追加 | 27 / 7 |
| B-7 | `buildspec.yml` | Parameter Store から `email_host` / `email_port` / `email_use_tls` / `email_use_ssl` を `export` する 4 行を除去し、SMTP に関するコメント記述を実体と一致する内容へ更新（R4-4） | 7 / 8 |
| B-8 | `portfolio/tests/test_regression.py` | `ProductionStaticStorageSettingsTests` の `required_env` から `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` / `EMAIL_HOST` / `EMAIL_PORT` を除去（`ContactFormSecurityTests` は保持） | 0 / 34 |
| B-8 | `docs/configuration.md` | SMTP 関連キーの記載を除去（R4-8） | 5 / 13 |
| B-8 | `docs/staging-values-policy.md` | SMTP 関連キーの記載を除去（R4-8） | 1 / 7 |

実行コマンド（確認）:

```powershell
git grep -n -E "EMAIL_HOST|EMAIL_PORT|EMAIL_USE_TLS|EMAIL_USE_SSL" -- config/
git grep -n -E "EMAIL_HOST|EMAIL_PORT|EMAIL_USE_TLS|EMAIL_USE_SSL|EMAIL_BACKEND" -- portfolio/
git grep -n "except Exception" -- portfolio/forms.py
git grep -n -E "email_host|email_port|email_use_tls|email_use_ssl" -- buildspec.yml
git grep -n -E "EMAIL_HOST_USER|EMAIL_HOST_PASSWORD|EMAIL_HOST|EMAIL_PORT|email_host|email_port|email_use_tls|email_use_ssl" -- docs/configuration.md docs/staging-values-policy.md
git grep -n "EMAIL_BACKEND" -- config/settings/prod.py
```

確認結果: 前 5 コマンドはいずれも一致 0 件 / 終了コード 1（R4-1 / R4-5 / R4-7 / R4-4 / R4-8）。`git grep -n "EMAIL_BACKEND" -- config/settings/prod.py` は一致 2 件（コメントおよび `EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"`）で R4-17 に適合。`config/settings/staging.py:8` の `from .prod import *` を保持しているため staging も同値を継承する（R4-11）。出典は `--check-residual` の該当行。

**系統 B は未完了**である。詳細は本記録「未完了事項」節に記載する。

### 系統 C: ビルド時依存の保全確定（tasks.md 11.1）

`docs/legacy-asset-inventory.json` の `preserved` 6 件（`views_top` / `views_contact` / `urls_portfolio` / `contactform_fields` / `templates_base` / `templates_index`）の扱いを「保全対象」で確定し、各項目の `detection_command` と `build_time_dependency` へ確定に用いた実行コマンドと確認結果を記録した（R5-5 / R5-8）。スキーマ拡張は行っていない（`PreservedAssetItem` は `confirmation` フィールドを持たない）。

確定に用いた実行コマンド（`DJANGO_SETTINGS_MODULE=config.settings.prod`）:

```powershell
python manage.py collectstatic --noinput
python manage.py render_static
```

確認結果: 両コマンドの終了コード 0。7 言語（`ja, en, fr, es, ru, zh-hans, ar`）の `staticfiles/<lang>/portfolio/top/index.html`、ルート `staticfiles/index.html`、`staticfiles/prerender_manifest.json` 1 件（`content_security_policy` 919 文字、`pages` 8 件）の生成成功を確認した。

ビルド時依存の**最小集合**は未確定であり、`undetermined_notes` の `prerender_minimal_set`（U-2）として保持している（R5-7）。R5-6 が求める「除去候補ごとの一時除去 → `render_static` 実行」の確認は 1 件も実施していない（未実施）。

### 系統 D: 未使用 dependency の除去と台帳整合（tasks.md 13.1 / 13.2）

判定対象 12 件（R7-11: `awsgi` / `django-allauth` / `django-otp` / `gunicorn` / `httptools` / `mangum` / `psycopg2-binary` / `pyjwt` / `qrcode` / `uvloop` / `websockets` / `werkzeug`）の全件を `除去対象` と判定し、`requirements.txt` と `docs/external-assets.md` の該当行を除去した（差分: `requirements.txt` 0 / 12、`docs/external-assets.md` 0 / 12）。

判定に用いた確認は 2 段階である（詳細と実行コマンドは `docs/legacy-asset-inventory.json` の各 `dep_*` 項目および `undetermined_notes.transitive_dependency_need` を正本とする）。

1. 8 件（`awsgi` / `django-allauth` / `django-otp` / `gunicorn` / `mangum` / `psycopg2-binary` / `pyjwt` / `qrcode`）: Windows venv と Docker（`python:3.12-slim-bookworm`）の 2 環境で直接参照 0 件・要求元 0 件を確認し `除去対象`（R7-1 / R7-2 / R7-5）。
2. 4 件（`httptools` / `uvloop` / `websockets` / `werkzeug`）: 13.1 時点では要求元 `awsgi==0.0.5` が存在したため `undetermined` を保持していたが、13.2 で `awsgi` の行を除去した `requirements.txt` に対して依存グラフ解決を再実行した結果、4 件いずれも要求元 0 件となり `除去対象` へ確定した。

`whitenoise==6.12.0` は保持（R7-6）。台帳整合の確認結果は `python -m scripts.cleanup.cli --audit-dependencies` の出力「Dependency_Manifest 記載 29 件 / License_Ledger 記載 29 件 / 判定対象 12 件のうち残存 0 件 / 判定: 適合」（R7-7）。

### 記録ファイルの作成（tasks.md 14.1）

`docs/development-records/legacy-asset-cleanup-records.json` を作成し、`NonRegressionRecord` 3 件（stream A / B / D）、`AwsSmtpState`、`applied_stream_b_segments` 8 件を記録した。Secrets Manager については平文値・値の一部・長さ・ハッシュのいずれも記録せず、キー名の存在有無と取得コマンドのみを記録している（R8-4 / R8-7、ゼロトラスト・GDPR）。

### Repository_Documents の整合（tasks.md 15.1）

`docs/architecture.md`（46 / 32）、`docs/current-state.md`（20 / 4）、`docs/development-records/deployment-time-optimization.md`（3 / 1）を除去後の実体へ更新した（R10-1 / R10-2 / R10-3 / R10-4）。

確認結果: `git grep -n -E "asgi_lambda|mangum|Mangum"` の一致は 6 件で、すべて `docs/` 配下 Markdown（`docs/architecture.md:64`、`docs/current-state.md:19`、`docs/development-records/deployment-time-optimization.md:131`、`docs/development-records/unused-resource-removal-django-retirement.md:144`、`docs/development-records/unused-resource-scan-django-retirement.md:197`、`docs/incidents/20260607_202416_Incident.md:21`）である（R3-5）。`.kiro` は `.gitignore` により git 追跡外のため `git grep` の対象に含まれない。

## 非退行確認結果（R10-6）

正本は `docs/development-records/legacy-asset-cleanup-records.json` の `non_regression_records`（3 件）。

**実測条件（重要）**: 3 レコード（stream A / B / D）は、**系統 A・系統 B・系統 D の 3 系統すべてを適用済みの同一作業ツリーに対して 1 回だけ計測した結果**であり、系統ごとの中間状態での再計測は実施していない（未実施）。したがって 3 レコードの実測値は同一であり、系統ごとに異なる値ではない（出典: 同ファイル各レコードの `commands` 先頭の注記）。

| 項目 | 実測値（stream A / B / D 共通） | 判定 |
| --- | --- | --- |
| `python manage.py test` | pass 174 / failure 0 / error 0 | R2-1 適合（Baseline 133 件以上） |
| `python manage.py check --fail-level WARNING` | 終了コード 0 | R2-2 適合 |
| `python -m scripts.control_platform.cli --self-test` | 終了コード 0 | R2-3 適合 |
| `python tests/self_test.py` | 終了コード 0 | R2-3 適合 |
| `python -m scripts.measurement.non_regression_check` | 終了コード 0 | R2-4 適合 |
| `python manage.py render_static` | Prerendered_Page 7 件 / `prerender_manifest.json` 1 件 | R2-5 適合 |
| `prerender_manifest.json` の `content_security_policy` | 919 文字（非空） | R2-6 適合 |

`python -m scripts.cleanup.cli --evaluate` による判定結果: `[R2] stream=A / B / D: 適合（pass 174 / failure 0 / error 0）`。

`render_static` の実行前提（tasks.md 10 の実行前提 (1)〜(5)）:

- `DJANGO_SETTINGS_MODULE=config.settings.prod` を供給（`render_static` は `settings.AWS_S3_CUSTOM_DOMAIN` を必須とし、当該設定の定義は `config/settings/prod.py` のみ）。
- `CLOUDFRONT_DOMAIN_NAME` / `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` は Parameter Store の実値を `aws ssm get-parameter`（プロファイル `aws_portfolio_profile`、リージョン `ap-northeast-1`）で取得して供給。
- OAuth 4 件（`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET`）と `DJANGO_SECRET_KEY` はプレースホルダ値を供給した。根拠は当該 4 件が `config/settings/prod.py:42-56` の非空チェックにのみ用いられ、`render_static` の成果物内容に影響しないことである（tasks.md 10 実行前提 (4)）。
- 環境変数は当該プロセス限りで供給し、`.env` / `env_dev.json` へ書き込まず実行後に削除した。
- `python manage.py collectstatic --noinput` を `render_static` より先に実行した。

## 検証コマンドと終了コード（本記録作成時点の実測）

| コマンド | 終了コード | 出力の要点 |
| --- | ---: | --- |
| `python -m scripts.cleanup.cli --validate-inventory` | 0 | `items: 41 件 / preserved: 6 件 / undetermined_notes: 7 件`、判定: 適合（R1-1〜R1-8、R7-11、R9-1〜R9-3） |
| `python -m scripts.cleanup.cli --verify-lines` | 0 | 照合先 revision `5f4ad0d`、照合対象 46 件 / 対象外 1 件（`steering_inconsistency` は Repository 外）、判定: 適合（R1-5） |
| `python -m scripts.cleanup.cli --check-residual` | 0 | 除去確認 33 件と R3-5 の範囲限定がすべて成立。除去保留（`undetermined`）8 件を列挙 |
| `python -m scripts.cleanup.cli --audit-dependencies` | 0 | Dependency_Manifest 29 件 / License_Ledger 29 件が一致、判定対象 12 件の残存 0 件（R7-7） |
| `python -m scripts.cleanup.cli --evaluate` | **1** | 判定: 不適合（違反 3 件）。内容は下記 |
| `$env:DJANGO_SETTINGS_MODULE="config.settings.dev"; python manage.py test` | 0 | `Ran 174 tests` / `OK`（failure 0 / error 0）、`System check identified no issues (0 silenced).` |
| `git grep -n -E "asgi_lambda|mangum|Mangum"` | 0 | 一致 6 件。すべて `docs/` 配下 Markdown（R3-5 の許容範囲内） |

`--evaluate` の不適合条項（実測 3 件）:

1. `R9-5: gitignore_aws_sam: 除去済みとして計上できない（残存一致 1 件、非退行判定 適合）`
2. `R9-5: prod_email_backend_policy: 除去済みとして計上できない（残存一致 2 件、非退行判定 適合）`
3. `R4-14: 系統 B が未完了（8 区分の適用と AWS 側の削除完了・不在確認の双方成立が必要）`

上記 1 と 2 は、当該 2 項目の変更が「行の除去」ではなく「追記」であることに起因する。`gitignore_aws_sam` の `removal_check_command` は `git check-ignore -v .aws-sam/build.toml`、`prod_email_backend_policy` の `removal_check_command` は `git grep -n "EMAIL_BACKEND" -- config/settings/prod.py` であり、いずれも**適用が成功しているときに一致が 1 件以上になる**。R9-5（`requirements.md:315`）は除去済み計上の条件に「除去確認コマンドで一致 0 件」を含むため、追記系の 2 項目は構造上「除去済み」として計上されない（`--check-residual` では同じ 2 項目が `[R3-3] 適合（一致 1 件）` / `[R4-17] 適合（一致 2 件）` と判定されており、変更自体は成立している）。`--evaluate` の `[R9-5] 除去済み計上: 31 件 / 除去対象 33 件` の差 2 件はこの 2 項目である。

## Dependency_Manifest と direct / transitive 併記方針の整合（R10-7）

確認対象: `docs/development.md:5`。記述内容は「`requirements.txt` には direct dependency と transitive dependency のバージョンを記載しています。Windows ローカルだけで必要な依存は `sys_platform == 'win32'`、Linux/Docker だけで必要な依存は `sys_platform != 'win32'` の marker を付けています。」（実ファイル読み取りで確認）。

確認結果: **整合しており、方針記述の更新は不要**と判断した。根拠は次の 3 点。

1. 13.2 で除去した 12 件は、いずれも direct 参照 0 件（R7-1）かつ要求元 0 件（R7-2）が確認された項目であり、direct dependency でも transitive dependency でもない記載であった（出典: `docs/legacy-asset-inventory.json` の各 `dep_*` 項目の `confirmation`）。したがって「direct と transitive を併記する」という方針の対象から外れる行の除去であり、方針に反しない。
2. 除去後も transitive dependency の記載は残存している（例: `asgiref==3.11.1`（`requirements.txt:1`）、`markupsafe==3.0.3`（`:15`）、`sqlparse==0.5.5`（`:25`）、`six==1.17.0`（`:24`））。併記方針の記述と実体は一致する。
3. marker に関する記述も実体と一致する。`sys_platform == 'win32'` は `requirements.txt:7`（`colorama==0.4.6`）と `:27`（`tzdata==2025.3`）、`sys_platform != 'win32'` は `:15`（`markupsafe==3.0.3`）に残存する（出典: `git grep -n -E "sys_platform" -- requirements.txt` の一致 3 件）。marker を持つ 5 件（`awsgi` / `httptools` / `uvloop` / `websockets` / `werkzeug`）を除去した後も、双方の marker が実体として存在するため記述は成立している。

したがって本タスクでは `docs/development.md` を編集していない（`git diff HEAD -- docs/development.md` の差分は本 spec 以前の未コミット変更のみで、内容はテストパッケージ移行と `render_static` の説明更新であり、dependency 方針とは無関係）。

## 未完了事項

### 系統 B は未完了（R4-15）

8 区分の適用（`applied_stream_b_segments` 8 件）と AWS 照会（R4-13）は完了しているが、**AWS 側 6 対象が現存し、削除も不在確認も成立していない**。したがって R4-14 の完了判定は未成立であり、系統 B を未完了として記録する（R4-10 / R4-15）。

対象環境は prod。照会結果（読み取り専用。削除は未実施）:

| 対象 | 照会結果 |
| --- | --- |
| `/prod/portfolio/parameter/email_host` | 現存（終了コード 0 / 取得値 `email-smtp.ap-northeast-1.amazonaws.com`） |
| `/prod/portfolio/parameter/email_port` | 現存（終了コード 0 / 取得値 `587`） |
| `/prod/portfolio/parameter/email_use_tls` | 現存（終了コード 0 / 取得値 `True`） |
| `/prod/portfolio/parameter/email_use_ssl` | 現存（終了コード 0 / 取得値 `False`） |
| `prod/portfolio/secret` の `EMAIL_HOST_USER` | キー名として存在（`PRESENT`。平文値は取得・記録していない） |
| `prod/portfolio/secret` の `EMAIL_HOST_PASSWORD` | キー名として存在（`PRESENT`。平文値は取得・記録していない） |

`AwsSmtpState` は `queried: true` / `absent_targets: []` / `deleted_targets: []` / `expected_targets` 6 件（出典: `docs/development-records/legacy-asset-cleanup-records.json`）。

削除は Approver 承認と `scripts/cleanup/approval.py` の `is_executable` の許可を前提とする運用手順であり、本 spec のコーディングタスクの範囲外である（出典: `.kiro/specs/legacy-asset-cleanup/tasks.md` の Notes、R8-1）。承認取得後は R8-4（実行前の現在値取得と記録）→ 実行 → R8-5（不在確認と記録）の順で実施する。

### 本 spec の範囲外として未対応の事項

- `.kiro/steering/django-settings.md:33` は「`EMAIL_USE_TLS` と `EMAIL_USE_SSL` は排他。両方 True にならないよう検証ロジックを維持」と記述するが、系統 B（R4-1）により当該検証ロジックを `config/settings/prod.py` および `config/settings/dev.py` から除去した。steering の当該記述の改訂は本 spec の範囲外であり**未対応**である（`.kiro` は git 追跡外であり Repository_Documents に該当しないため R10-1 の更新対象でもない）。
- 本 spec による commit は 0 件である。commit / push は本タスクの範囲外。

## 残存する `undetermined` 項目（R9-6）

正本は `docs/legacy-asset-inventory.json`。本節は実測した一覧と各項目の「なぜ未確定か」「確定手段」の要約のみを記載し、詳細（出典・`reason`・`pending_check` の全文）は正本を参照する。

実測（`python -m scripts.cleanup.cli --validate-inventory` および Inventory の走査）: `items` の `disposition: undetermined` **8 件**、`undetermined_notes` **7 件**、合計 **15 レコード**。

### `items` の `undetermined` 8 件

| キー | U 番号 | 未確定の理由（要約） | 確定手段（要約） |
| --- | --- | --- | --- |
| `aws_smtp_parameters` | U-4 | Parameter Store の SMTP 設定 4 件の扱い（削除可否）が未決定。照会では 4 件すべて現存 | Approver 承認に基づく Destructive_Operation の実施と不在確認（R8-2 / R8-5） |
| `aws_smtp_secret_keys` | U-4 | Secrets Manager `prod/portfolio/secret` の `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` の扱いが未決定。照会ではキー名として存在 | 同上（記録には平文値を含めない） |
| `template_account_modal` | U-7 | `templates/portfolio_base.html:311-394` の `body_account_modal` の除去可否が Approver 判断待ち（R6-5 / R6-6） | Approver 判断 |
| `prod_oauth_required` | U-8 | `config/settings/prod.py:42-56` の OAuth 必須チェック 4 件の除去可否が Approver 判断待ち（R1-7） | Approver 判断 |
| `steering_inconsistency` | U-10 | `.kiro/steering` の記述と実体の不整合の扱いが Approver 判断待ち。`.kiro` は git 追跡外で Repository のスリム化対象外 | Approver 判断 |
| `base_debug_print` | U-9 | `config/settings/base.py:101` のデバッグ用標準出力の除去可否が Approver 判断待ち（R1-7） | Approver 判断 |
| `base_contrib_sites` | U-12 | `config/settings/base.py:48` の `'django.contrib.sites'` の除去可否が Approver 判断待ち。既存受入基準の確認パターンに一致せず対象外 | Approver 判断 |
| `template_two_factor_url` | U-13 | `templates/portfolio_base.html:340` の `two_factor_authentication_settings` が解決不能である扱いが Approver 判断待ち | Approver 判断（U-7 と併せて判断） |

### `undetermined_notes` 7 件

| キー | U 番号 | 未確定の理由（要約） | 確定手段（要約） |
| --- | --- | --- | --- |
| `outputs_apiurl_external_users` | U-3 | `Outputs.ApiUrl` のリポジトリ外利用者の有無が未確認 | Approver による外部利用者有無の判断 |
| `sam_build_toml_dependency` | U-5 | `sam build` が既存 `.aws-sam/build.toml` を読み取ってビルド結果に影響するかが未検証（実行検証未実施） | `build.toml` 有／無の 2 条件で `sam build --use-container` を実行し生成物を比較（Docker 必須） |
| `prerender_minimal_set` | U-2 | ビルド時依存の最小集合が未確定。R5-6 の「候補ごとの一時除去 → `render_static` 実行」を未実施であり、最小性の網羅確認には Approver 判断待ちの `template_account_modal` を含む全候補の確認が必要 | `preserved` 6 件および `除去対象` 各件の一時除去と `render_static` 実行の反復、加えて Approver 判断 |
| `aws_smtp_key_existence` | U-4 | R9-1 が Inventory への記載を義務付けるキー。照会自体は 14.1 で実施済みだが、削除可否の確定は未了 | Approver 承認に基づく削除と不在確認 |
| `transitive_dependency_need` | U-1 | R9-1 が Inventory への記載を義務付けるキーであり、判定対象 12 件が確定しても記載自体は解消しない | 判定対象 12 件については残る未確認事項なし（下記「範囲外の新規検出」を除く） |
| `samconfig_allowed_origin` | U-6 | `samconfig.toml:9` の `AllowedOrigin` に対応する `Parameters` 宣言がリポジトリ内に存在せず、除去可否が未決定 | Approver 判断 |
| `samconfig_allowed_hosts` | U-6 | `samconfig.toml:9` の `AllowedHosts` に対応する `Parameters` 宣言がリポジトリ内に存在せず、除去可否が未決定 | Approver 判断 |

### tasks.md 15.2 の記述との差異（事実として記録）

`.kiro/specs/legacy-asset-cleanup/tasks.md` の 15.2 は残存項目を「U-1〜U-10、U-12、U-13」と記述する。U 番号の集合としては実測と一致するが、**U-1 の実体は 13.2 の完了により変化している**。

- 13.1 時点では `httptools` / `uvloop` / `websockets` / `werkzeug` の 4 件が要求元 `awsgi==0.0.5` の存在により `undetermined` であったが、13.2 で `awsgi` を除去した後の依存グラフ解決により要求元 0 件が確定し、4 件はいずれも `除去対象` へ確定した。判定対象 12 件に `undetermined` は残っていない（出典: `--audit-dependencies` の「判定対象 12 件のうち Dependency_Manifest に残存: 0 件」、および Inventory の `dep_*` 12 件の `disposition` が全件 `除去対象`）。
- U-1 に対応する `undetermined_notes.transitive_dependency_need` は解消せず保持している。理由は R9-1 が当該キーの Inventory への記載を義務付けており、`scripts/cleanup/inventory.py` の必須ノートキー検証が当該キーの包含を要求するためである。
- したがって U-1 の残存内容は「判定対象 12 件の推移要求の未確認」ではなく、「記載義務によるノートの保持」と「下記の範囲外新規検出 1 件」である。

### 範囲外の新規検出（`undetermined`。R9-6）

`markupsafe==3.0.3`（`requirements.txt:15`、`docs/external-assets.md:31`）は、13.2 の `werkzeug` 除去前は `werkzeug` の要求先であったが、除去後の依存グラフ解決では**要求元 0 件**である。`markupsafe` は R7-11 が定める判定対象 12 件に含まれず、`docs/legacy-asset-inventory.json` の `items` にも項目が存在しないため、**扱いは未判定（`undetermined`）**である。

確定手段: `markupsafe` を判定対象へ含める**要件追補について Approver の判断が必要**であり、判断が得られたうえで `git grep` による direct 参照確認と Docker（`python:3.12-slim-bookworm`）での依存グラフ解決による transitive 要求確認を行い `decide` を適用する（出典: `docs/legacy-asset-inventory.json` の `undetermined_notes.transitive_dependency_need` の `pending_check`）。

## 未確認事項（本記録作成時点）

- 系統ごと（A のみ / B のみ / D のみ）の中間状態での非退行再計測は**未実施**。3 レコードは 3 系統適用後の同一作業ツリーでの 1 回の計測結果である。
- 変更後の `requirements.txt` に対するクリーンな仮想環境での `pip install -r requirements.txt`（R7-8）の再実行は本タスクでは**未実施**（実行結果は tasks.md 13.2 の記録に属する）。
- `collectstatic` が `render_static` の成功に厳密に必須であるかは**未確認**（`buildspec.yml` の実行順序に倣って先行実行しているのみ）。
- AWS 側 6 対象の削除および削除後の不在確認は**未実施**（Approver 承認前）。
- `.kiro/steering/django-settings.md:33` の記述改訂は**未対応**（本 spec の範囲外）。
