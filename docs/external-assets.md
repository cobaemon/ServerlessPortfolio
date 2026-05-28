# 外部資産とライセンス

## Docker image

| 資産 | バージョンまたは参照 | ライセンス確認結果 | 確認元 |
| --- | --- | --- | --- |
| Python Docker Official Image packaging | `python:3.12-slim-bookworm@sha256:93ab4b7fa528b25124c97bcc755415e60eb671a86b4dbe0328df2fe2d1c1193d` | MIT license | `docker-library/python` GitHub repository |

`docker-library/python` は Docker Official Image packaging for Python のリポジトリです。同 repository の GitHub 表示で MIT license を確認しました。

## Python dependencies

`requirements.txt` に記載する dependency は次の通りです。ライセンスは `pip show` または package metadata の `License`、`License-Expression`、`Classifier` 表示で確認しました。

| パッケージ | バージョン | ライセンス確認結果 |
| --- | --- | --- |
| asgiref | 3.11.1 | BSD-3-Clause |
| awsgi | 0.0.5 | BSD License classifier |
| boto3 | 1.42.63 | Apache-2.0 |
| botocore | 1.42.97 | Apache-2.0 |
| certifi | 2026.5.20 | MPL-2.0 |
| cffi | 2.0.0 | MIT |
| charset-normalizer | 3.4.7 | MIT |
| colorama | 0.4.6 | BSD license metadata |
| cryptography | 46.0.5 | Apache-2.0 OR BSD-3-Clause |
| Django | 6.0.3 | BSD-3-Clause |
| django-allauth | 65.14.3 | MIT |
| django-csp | 4.0 | BSD |
| django-environ | 0.13.0 | MIT |
| django-otp | 1.7.0 | Unlicense |
| django-storages | 1.14.6 | BSD-3-Clause |
| gunicorn | 25.1.0 | MIT |
| httptools | 0.7.1 | MIT |
| idna | 3.16 | BSD-3-Clause |
| jmespath | 1.1.0 | MIT |
| mangum | 0.21.0 | MIT License classifier |
| markupsafe | 3.0.3 | BSD-3-Clause |
| packaging | 26.2 | Apache-2.0 OR BSD-2-Clause |
| pillow | 12.1.1 | MIT-CMU |
| pillow-avif-plugin | 1.5.5 | MIT License |
| psycopg2-binary | 2.9.11 | LGPL with exceptions |
| pycparser | 3.0 | BSD-3-Clause |
| PyJWT | 2.11.0 | MIT |
| python-dateutil | 2.9.0.post0 | Dual License |
| python-dotenv | 1.2.2 | BSD-3-Clause |
| qrcode | 8.2 | BSD |
| requests | 2.32.5 | Apache-2.0 |
| s3transfer | 0.16.1 | Apache License 2.0 |
| six | 1.17.0 | MIT |
| sqlparse | 0.5.5 | BSD license metadata |
| typing-extensions | 4.15.0 | PSF-2.0 |
| tzdata | 2025.3 | Apache-2.0 |
| urllib3 | 2.7.0 | MIT |
| uvloop | 0.22.1 | MIT |
| websockets | 16.0 | BSD-3-Clause |
| werkzeug | 3.1.8 | BSD-3-Clause |
| whitenoise | 6.12.0 | MIT |

## Build tools

| 資産 | バージョン | ライセンス確認結果 | 確認元 |
| --- | --- | --- | --- |
| aws-sam-cli | 1.160.1 | Apache-2.0 license | `sam --version` と `aws/aws-sam-cli` GitHub repository |
| csscompressor | 0.9.5 | BSD | `pip show csscompressor` |

## Google Fonts

| 資産 | 取得元 | ライセンス確認結果 |
| --- | --- | --- |
| Montserrat | `https://raw.githubusercontent.com/google/fonts/48133440178622e215912d34d386c5ee1682c677/ofl/montserrat/Montserrat%5Bwght%5D.ttf` | SIL Open Font License 1.1 |
| Lato Regular | `https://raw.githubusercontent.com/google/fonts/48133440178622e215912d34d386c5ee1682c677/ofl/lato/Lato-Regular.ttf` | SIL Open Font License 1.1 |

Google Fonts の `ofl/montserrat/OFL.txt` と `ofl/lato/OFL.txt` で SIL Open Font License Version 1.1 を確認しました。

## 関連ファイル

- [`Dockerfile`](../Dockerfile)
- [`requirements.txt`](../requirements.txt)
- [`buildspec.yml`](../buildspec.yml)
