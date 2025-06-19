# backends.py

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from allauth.account.models import EmailAddress

User = get_user_model()

class CustomBackend(ModelBackend):
    def authenticate(self, request, email=None, password=None, **kwargs):
        if email is None or password is None:
            return None

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return None

        if user.check_password(password):
            email_address = EmailAddress.objects.filter(user=user, email=user.email)
            if email_address.exists() and email_address.first().verified:
                if user.is_active:
                    return user
        return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
