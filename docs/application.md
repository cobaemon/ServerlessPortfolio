# アプリケーション構成

## Django プロジェクト

Django プロジェクトは `config` です。URL ルーティングは `config/urls.py` にあります。

`config/urls.py` のルート構成は次の通りです。

- `/admin/`: Django Admin。
- `/i18n/`: Django 標準の言語切り替え URL。
- `/`: `/portfolio/top/` への恒久リダイレクト。
- `/portfolio/`: `portfolio.urls` を include。
- `/favicon.ico`: `/static/favicon.ico` へのリダイレクト。

## Django アプリ

主要アプリは `portfolio` です。

`portfolio/urls.py` のルート構成は次の通りです。

- `/portfolio/top/`: `portfolio.views.Top`
- `/portfolio/contact`: `portfolio.views.contact`

## ビュー

`portfolio.views.Top` は `FormView` を継承し、`index.html` をテンプレートとして使用します。フォームクラスは `ContactForm` です。

`Top.form_valid()` は `ContactForm.send_email()` が `True` を返した場合に `Form submission successful` を返し、`False` の場合は HTTP 500 で `Email sending failed` を返します。

`portfolio.views.contact` は `csrf_exempt` と `require_POST` が付与された POST 専用ビューです。`ContactForm` が有効でメール送信に成功した場合は `Form submission successful` を返します。フォーム不正の場合は HTTP 400、メール送信失敗の場合は HTTP 500 を返します。

## フォーム

`portfolio.forms.ContactForm` は次の入力を持ちます。

- `full_name`: 最大 100 文字。
- `email`: メールアドレス。
- `phone_number`: 最大 20 文字。`clean_phone_number()` で数字のみを許可。
- `message`: テキストエリア。

`send_email()` は `settings.DEFAULT_FROM_EMAIL` から `settings.DEFAULT_TO_EMAIL` へ `EmailMessage` を送信します。

## モデル

`portfolio/models.py` に独自モデルは定義されていません。

## 国際化

`config/settings/base.py` の `LANGUAGES` には次の言語が定義されています。

- `ja`: Japanese
- `en`: English
- `fr`: French
- `es`: Spanish
- `ru`: Russian
- `zh-hans`: Simplified Chinese
- `ar`: Arabic

翻訳ファイルは `locale` 配下に配置されています。

## 関連ファイル

- [`config/urls.py`](../config/urls.py)
- [`portfolio/urls.py`](../portfolio/urls.py)
- [`portfolio/views.py`](../portfolio/views.py)
- [`portfolio/forms.py`](../portfolio/forms.py)
- [`portfolio/models.py`](../portfolio/models.py)
- [`config/settings/base.py`](../config/settings/base.py)
