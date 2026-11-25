from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from crm_api.access import issue_key
from crm_api.models import AccessKey


class Command(BaseCommand):
    help = "Issue, revoke or rotate a CRM API credential from a private console."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--label", default="CRM integration")
        parser.add_argument("--write", action="store_true")
        parser.add_argument("--identifiers", action="store_true", help="Permit access to listing identifiers.")
        operation = parser.add_mutually_exclusive_group()
        operation.add_argument("--revoke", type=int)
        operation.add_argument("--rotate", type=int)

    @transaction.atomic
    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options["username"], is_active=True, is_staff=True).first()
        if user is None:
            raise CommandError("An active staff account is required.")
        old_id = options["revoke"] or options["rotate"]
        can_write = options["write"]
        can_identify = options["identifiers"]
        if old_id:
            old = AccessKey.objects.filter(pk=old_id, user=user, revoked_at__isnull=True).first()
            if old is None:
                raise CommandError("Active key not found.")
            if AccessKey.objects.filter(pk=old.pk, revoked_at__isnull=True).update(revoked_at=timezone.now()) != 1:
                raise CommandError("Key already revoked.")
            can_write = old.can_write
            can_identify = old.can_identify
            if options["revoke"]:
                return "Key revoked."
        key, secret = issue_key(user, options["label"], can_write, can_identify)
        return f"Key #{key.pk}\n{secret}"
