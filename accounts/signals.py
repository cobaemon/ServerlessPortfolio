from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from allauth.account.signals import email_confirmed
from .models import CustomUser, EncryptionKey
from .utils import generate_aes_key, encrypt_secret_key
import datetime

@receiver(post_save, sender=CustomUser)
def create_user_secret_key(sender, instance, created, **kwargs):
    if created and not instance.secret_key:
        # ユーザごとの共通鍵を生成
        user_secret_key = generate_aes_key()
        # 共通鍵をDjangoの秘密鍵で暗号化
        encrypted_key = encrypt_secret_key(user_secret_key)
        # 有効期限を1年後に設定
        # expires_at = timezone.now() + datetime.timedelta(days=365)
        # 暗号化された鍵を保存
        encryption_key = EncryptionKey.objects.create(user=instance, key=encrypted_key)
        instance.secret_key = encryption_key
        instance.save()
