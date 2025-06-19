from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.urls import reverse_lazy


class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    def get_signup_redirect_url(self, request):
        # ソーシャルアカウントの新規登録時のリダイレクトURLを設定
        return reverse_lazy('portfolio:top')

    def get_login_redirect_url(self, request):
        # ソーシャルアカウントのログイン後のリダイレクトURLを設定
        return reverse_lazy('portfolio:top')
