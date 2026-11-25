import hashlib
import re
import secrets
from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import InvitationThrottle, StaffInvitation


def digest(secret):
    return hashlib.sha256(secret.encode("ascii")).hexdigest()


def issue(user, hours):
    secret = secrets.token_urlsafe(32)
    invitation = StaffInvitation.objects.create(
        user=user, digest=digest(secret), expires_at=timezone.now() + timedelta(hours=hours)
    )
    return invitation, secret


@transaction.atomic
def consume(secret):
    now = timezone.now()
    window = int(now.timestamp()) // 60
    # Write first so SQLite serializes this counter and token consumption.
    InvitationThrottle.objects.bulk_create([InvitationThrottle(window=window)], ignore_conflicts=True)
    if not InvitationThrottle.objects.filter(window=window, attempts__lt=60).update(attempts=F("attempts") + 1):
        return None, 429
    InvitationThrottle.objects.filter(window__lt=window - 2).delete()
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", secret):
        return None, 403
    pending = StaffInvitation.objects.filter(
        digest=digest(secret), expires_at__gt=now, used_at__isnull=True, revoked_at__isnull=True,
        user__is_active=True, user__is_staff=True,
    )
    invitation = pending.select_related("user").first()
    if invitation and pending.update(used_at=now) == 1:
        return invitation.user, 200
    return None, 403
