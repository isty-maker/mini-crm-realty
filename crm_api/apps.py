from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_save
from django.utils import timezone


def revoke_disabled_user_keys(sender, instance, using, raw, **kwargs):
    if raw or (instance.is_active and instance.is_staff):
        return
    from .models import AccessKey

    AccessKey.objects.using(using).filter(user_id=instance.pk, revoked_at__isnull=True).update(revoked_at=timezone.now())


class CRMApiConfig(AppConfig):
    name = "crm_api"

    def ready(self):
        post_save.connect(revoke_disabled_user_keys, sender=settings.AUTH_USER_MODEL,
                          dispatch_uid="crm_api.revoke_disabled_user_keys")
