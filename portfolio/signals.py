# portfolio/signals.py

from django.conf import settings
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.contrib.sites.models import Site
from django.db.utils import OperationalError

@receiver(post_migrate)
def create_or_update_default_site(sender, **kwargs):
    try:
        site, created = Site.objects.get_or_create(pk=settings.SITE_ID, defaults={
            'domain': settings.ALLOWED_HOSTS[0],
            'name': settings.SITE_NAME,
        })
        if not created:
            site.domain = settings.ALLOWED_HOSTS[0]
            site.name = settings.SITE_NAME
            site.save()
    except OperationalError:
        # 初期マイグレーションがまだ適用されていない場合は、エラーを無視します
        pass
