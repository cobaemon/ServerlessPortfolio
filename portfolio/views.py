from django.http import HttpResponse
from django.views.generic import FormView
from django.views.decorators.http import require_POST
import logging

from .forms import ContactForm

logger = logging.getLogger(__name__)


class Top(FormView):
    """
    ポートフォリオサイトのトップページビュー
    お問い合わせフォームを表示し、送信処理を行う
    """
    template_name = 'index.html'
    form_class = ContactForm

    def form_valid(self, form):
        """
        フォームが有効な場合の処理

        お問い合わせ内容をメール送信し、成功メッセージを返す。

        戻り値:
            HttpResponse: 送信成功時の応答
        例外:
            ContactForm.send_email() は成否を戻り値で通知せず、送信失敗時は例外を
            送出する。本メソッドは当該例外を捕捉せず伝播させる
            （出典: portfolio/forms.py send_email、requirements.md R4-7、
            design.md C8 区分 B-6）。
        """
        form.send_email()
        return HttpResponse("Form submission successful")

    def form_invalid(self, form):
        """
        フォームが無効な場合の処理
        バリデーションエラーをログに出力
        """
        logger.warning("Invalid contact form submission: %s", form.errors)
        return super().form_invalid(form)
        
    def get_context_data(self, **kwargs):
        """
        テンプレートに渡すコンテキストデータを取得
        フォームインスタンスをコンテキストに追加
        """
        context = super().get_context_data(**kwargs)
        context['form'] = self.form_class()
        return context


@require_POST
def contact(request):
    """
    お問い合わせ送信を受け付ける POST 専用ビュー

    引数:
        request (HttpRequest): POST リクエスト
    戻り値:
        HttpResponse: 送信成功時は 200、バリデーション失敗時は 400
    例外:
        ContactForm.send_email() は成否を戻り値で通知せず、送信失敗時は例外を
        送出する。本ビューは当該例外を捕捉せず伝播させる
        （出典: portfolio/forms.py send_email、requirements.md R4-7、
        design.md C8 区分 B-6）。
    """
    form = ContactForm(request.POST)
    if form.is_valid():
        form.send_email()
        return HttpResponse("Form submission successful")
    logger.warning("Invalid contact form submission: %s", form.errors)
    return HttpResponse("Invalid", status=400)
