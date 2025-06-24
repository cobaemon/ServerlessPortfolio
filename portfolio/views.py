from django.http import HttpResponse
from django.views.generic import FormView

from .forms import ContactForm


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
        お問い合わせ内容をメール送信し、成功メッセージを返す
        """
        form.send_email()
        return HttpResponse("Form submission successful")
        
    def get_context_data(self, **kwargs):
        """
        テンプレートに渡すコンテキストデータを取得
        フォームインスタンスをコンテキストに追加
        """
        context = super().get_context_data(**kwargs)
        context['form'] = self.form_class()
        return context
