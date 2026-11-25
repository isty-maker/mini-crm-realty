"""Versioned writes shared by the panel and future authorized callers."""

import json

from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from .models import Property


PROPERTY_FIELDS = tuple(field.name for field in Property._meta.concrete_fields if not field.primary_key)


def current_values(prop, fields):
    return {name: getattr(prop, name) for name in fields}


def property_version(prop, scope, fields):
    serialized = json.dumps([prop.pk, scope, current_values(prop, fields)], default=str, sort_keys=True)
    return salted_hmac("core.property-write.v1", serialized, algorithm="sha256").hexdigest()


def version_matches(prop, scope, fields, version):
    return constant_time_compare(version, property_version(prop, scope, fields))


def update_property(prop, fields, changes, *, actor=None, source=None):
    """Update against the read snapshot. A stale SQLite writer cannot overwrite newer values."""
    if not changes:
        return True
    if set(changes) - set(fields):
        raise ValueError("Fields outside the write scope")
    with transaction.atomic():
        changed = Property.objects.filter(pk=prop.pk, **current_values(prop, fields)).update(
            **changes, updated_at=timezone.now(),
        ) == 1
        if changed and source:
            from .private_records import record_audit

            record_audit(prop, actor if actor and actor.is_authenticated else None, source, "listing", prop.pk, changes)
        return changed


def same_form_text(original, submitted):
    """Browsers normalize line endings when they submit textareas."""
    return isinstance(original, str) and isinstance(submitted, str) and (
        original.replace("\r\n", "\n") == submitted.replace("\r\n", "\n")
    )


def can_use_staff_card(user):
    return user.is_authenticated and user.is_active and user.is_staff
