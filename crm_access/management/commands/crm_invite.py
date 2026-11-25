from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from crm_access.invitations import issue
from crm_access.models import StaffInvitation


class Command(BaseCommand):
    help = "Issue or revoke an employee invitation from a private operator console."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--origin")
        parser.add_argument("--hours", type=int, default=24)
        parser.add_argument("--revoke", type=int, help="Revoke a pending invitation by ID.")
        parser.add_argument("--disable", action="store_true", help="Revoke this employee's browser access.")

    @transaction.atomic
    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options["username"], is_staff=True).first()
        if not user:
            raise CommandError("Create a staff account before issuing access.")
        pending = StaffInvitation.objects.filter(user=user, used_at__isnull=True, revoked_at__isnull=True)
        if options["disable"]:
            user.is_active = False
            user.set_unusable_password()
            user.save(update_fields=["is_active", "password"])
            pending.update(revoked_at=timezone.now())
            return "Access disabled and pending invitations revoked."
        if options["revoke"] is not None:
            if not pending.filter(pk=options["revoke"]).update(revoked_at=timezone.now()):
                raise CommandError("Pending invitation not found.")
            return "Invitation revoked."
        origin = urlsplit(options["origin"] or "")
        if (origin.scheme != "https" or not origin.hostname or origin.username or origin.path not in {"", "/"}
                or origin.query or origin.fragment or not user.is_active or not 1 <= options["hours"] <= 168):
            raise CommandError("Use an HTTPS origin, an active employee and an expiry of 1–168 hours.")
        invitation, secret = issue(user, options["hours"])
        return f"Invitation #{invitation.pk}\nhttps://{origin.netloc}/crm/login/#{secret}"
