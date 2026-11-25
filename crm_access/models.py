from django.conf import settings
from django.db import models


class StaffInvitation(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    digest = models.CharField(max_length=64, unique=True, editable=False)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True)
    revoked_at = models.DateTimeField(null=True)


class InvitationThrottle(models.Model):
    window = models.PositiveBigIntegerField(primary_key=True)
    attempts = models.PositiveIntegerField(default=0)
