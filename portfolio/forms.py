from django import forms
from django.core.mail import EmailMessage
from django.conf import settings

class ContactForm(forms.Form):
    full_name = forms.CharField(
        label='Full Name', 
        max_length=100,
        widget=forms.TextInput(attrs={
            'name': 'full_name',
            'class': 'form-control',
            'placeholder': 'Enter your name...',
            'autocomplete': 'name'  # autocomplete属性を追加
        })
    )
    email = forms.EmailField(
        label='Email Address',
        widget=forms.TextInput(attrs={
            'name': 'email',
            'class': 'form-control',
            'placeholder': 'name@example.com',
            'data-sb-validations': 'required,email',
            'autocomplete': 'email'  # autocomplete属性を追加
        })
    )
    phone_number = forms.CharField(
        label='Phone Number',
        max_length=20,
        widget=forms.TextInput(attrs={
            'name': 'phone_number',
            'class': 'form-control',
            'placeholder': '(123) 456-7890',
            'autocomplete': 'tel'  # autocomplete属性を追加
        })
    )
    message = forms.CharField(
        label='Message',
        widget=forms.Textarea(attrs={
            'name': 'message',
            'class': 'form-control',
            'placeholder': 'Enter your message here...',
            'autocomplete': 'off'  # メッセージフィールドにはautocompleteをオフに設定
        })
    )

    def clean_phone_number(self):
        phone_number = self.cleaned_data.get('phone_number')
        if not phone_number.isdigit():
            raise forms.ValidationError('Phone number should only contain digits')
        return phone_number
    
    def send_email(self):
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
            to=[settings.DEFAULT_TO_EMAIL]
        )
        email.send()
