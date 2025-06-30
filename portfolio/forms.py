from django import forms
from django.conf import settings
from django.core.mail import EmailMessage
import logging

logger = logging.getLogger(__name__)


class ContactForm(forms.Form):
    """
    お問い合わせフォームクラス
    ユーザーからの問い合わせを受け付けるためのフォーム
    """
    full_name = forms.CharField(
        label='Full Name', 
        max_length=100,
        widget=forms.TextInput(attrs={
            'name': 'full_name',
            'class': 'form-control',
            'placeholder': 'Enter your name...',
            'autocomplete': 'name'  # ブラウザの自動補完機能を有効化
        })
    )
    email = forms.EmailField(
        label='Email Address',
        widget=forms.TextInput(attrs={
            'name': 'email',
            'class': 'form-control',
            'placeholder': 'name@example.com',
            'data-sb-validations': 'required,email',
            'autocomplete': 'email'  # メールアドレスの自動補完を有効化
        })
    )
    phone_number = forms.CharField(
        label='Phone Number',
        max_length=20,
        widget=forms.TextInput(attrs={
            'name': 'phone_number',
            'class': 'form-control',
            'placeholder': '(123) 456-7890',
            'autocomplete': 'tel'  # 電話番号の自動補完を有効化
        })
    )
    message = forms.CharField(
        label='Message',
        widget=forms.Textarea(attrs={
            'name': 'message',
            'class': 'form-control',
            'placeholder': 'Enter your message here...',
            'autocomplete': 'off'  # メッセージフィールドでは自動補完を無効化（セキュリティ上の理由）
        })
    )

    def clean_phone_number(self):
        """
        電話番号のバリデーション
        数字のみを許可し、不正な文字が含まれている場合はエラーを発生
        """
        phone_number = self.cleaned_data.get('phone_number')
        if not phone_number.isdigit():
            raise forms.ValidationError('Phone number should only contain digits')
        return phone_number
    
    def send_email(self):
        """
        お問い合わせ内容をメールで送信
        フォームの内容を管理者宛にメール送信する
        """
        full_name = self.cleaned_data['full_name']
        email = self.cleaned_data['email']
        phone_number = self.cleaned_data['phone_number']
        message = self.cleaned_data['message']

        subject = f'Contact form submission from {full_name}'
        body = f'Full Name: {full_name}\nEmail: {email}\nPhone Number: {phone_number}\n\nMessage:\n{message}'

        email = EmailMessage(
            subject,
            body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[settings.DEFAULT_TO_EMAIL],
        )

        logger.info("Using email backend %s", settings.EMAIL_BACKEND)
        logger.info(
            "Using SMTP server %s:%s TLS=%s SSL=%s",
            settings.EMAIL_HOST,
            settings.EMAIL_PORT,
            settings.EMAIL_USE_TLS,
            settings.EMAIL_USE_SSL,
        )

        try:
            email.send()
            logger.info("Contact email sent to %s", settings.DEFAULT_TO_EMAIL)
            return True
        except Exception as exc:
            logger.error("Failed to send contact email: %s", exc, exc_info=True)
            return False
