from django.conf import settings
from django.db import models


class AccessKey(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    label = models.CharField(max_length=100)
    digest = models.CharField(max_length=64, unique=True, editable=False)
    can_write = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True)


class IdempotentWrite(models.Model):
    access_key = models.ForeignKey(AccessKey, on_delete=models.CASCADE)
    namespace = models.CharField(max_length=100)
    request_key = models.CharField(max_length=100)
    fingerprint = models.CharField(max_length=64)
    result_id = models.PositiveBigIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("access_key", "namespace", "request_key"),
                                    name="unique_crm_api_write"),
        ]
