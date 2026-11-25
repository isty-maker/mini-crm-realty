"""Versioned JSON transport for the existing listing and staff write services."""

import hashlib
import json
import re

from django.core.exceptions import RequestDataTooBig, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.http import JsonResponse

from core.models import Property
from core.private_records import (
    SCOPES, RecordConflict, check_retirement, get_record, record_audit, record_version, retire_record, save_record,
)
from core.property_writes import update_property
from core.workspace_models import PropertyWorkspace

from .access import APIError, api_view
from .models import AccessKey, IdempotentWrite
from .records import (
    COLLECTIONS, READ_FIELDS, WORKSPACE, aggregate, checked_listing, checked_record, create_listing,
    document_types, serialize_record, visible_listing_fields,
)


def unique_object(pairs):
    data = dict(pairs)
    if len(data) != len(pairs):
        raise ValueError("Duplicate JSON key")
    return data


def read_body(request, keys):
    if request.content_type != "application/json":
        raise APIError(415, "content_type", "Send application/json.")
    try:
        if int(request.headers.get("Content-Length", "0")) > 65536 or len(request.body) > 65536:
            raise RequestDataTooBig
        data = json.loads(request.body, object_pairs_hook=unique_object)
    except RequestDataTooBig:
        raise APIError(413, "too_large", "Maximum request size is 64 KiB.") from None
    except (ValueError, UnicodeError, RecursionError):
        raise APIError(400, "invalid_json", "Malformed JSON.") from None
    if not isinstance(data, dict) or set(data) - set(keys):
        raise APIError(422, "invalid_fields", "Unexpected request fields.")
    return data


def mode(request):
    value = request.GET.get("dry_run", "0")
    if value not in {"0", "1"}:
        raise APIError(400, "dry_run", "Use dry_run=0 or dry_run=1.")
    return value == "1"


def expected_version(request, dry_run):
    value = request.headers.get("If-Match")
    if value is None and dry_run:
        return None
    if value is None:
        raise APIError(428, "version_required", "Supply an If-Match version.")
    if not re.fullmatch(r'"[0-9a-f]{64}"', value):
        raise APIError(400, "invalid_version", "Send a quoted version in If-Match.")
    return value[1:-1]


def object_for(pk):
    prop = Property.objects.filter(pk=pk).first()
    if prop is None:
        raise APIError(404, "not_found", "Object not found.")
    return prop


def lock_writes(key):
    # Acquire SQLite's write lock before reads, including replay lookup.
    if AccessKey.objects.filter(pk=key.pk, revoked_at__isnull=True, can_write=True,
                                user__is_staff=True, user__is_active=True, user__password=key.user.password).update(id=F("id")) != 1:
        raise APIError(403, "key_revoked", "The key no longer permits modifications.")


def with_version(data, *, status=200, replay=False):
    response = JsonResponse(data, status=status)
    if "version" in data:
        response["ETag"] = '"' + data["version"] + '"'
    if replay:
        response["Idempotency-Replayed"] = "true"
    return response


def normal_address(address):
    return " ".join(address.split()).casefold()


def duplicate_check(prop):
    address = normal_address(prop.address)
    number = normal_address(prop.flat_number)
    cadastral = normal_address(prop.cadastral_number)
    exact, possible = [], []
    candidates = Property.objects.exclude(pk=prop.pk).order_by("pk")
    for pk, other_address, flat, cad, operation in candidates.values_list(
            "pk", "address", "flat_number", "cadastral_number", "operation").iterator():
        same_cad = bool(cadastral and cadastral == normal_address(cad))
        same_address = address == normal_address(other_address)
        other_number = normal_address(flat)
        if same_cad or (same_address and number and number == other_number):
            (exact if operation == prop.operation else possible).append(pk)
        elif same_address and not (number and other_number and number != other_number) and not (
                cadastral and cad and cadastral != normal_address(cad)):
            possible.append(pk)
    warnings = []
    if possible:
        warnings.append({"code": "possible_duplicate", "ids": possible[:20]})
    if not number and not cadastral:
        warnings.append({"code": "incomplete_identity"})
    if exact:
        raise APIError(409, "duplicate_identity", "An object with that identity and operation exists.", ids=exact[:20])
    return warnings


def duplicate_confirmation(data):
    confirmed = data.get("confirm_possible_duplicate", False)
    if type(confirmed) is not bool:
        raise APIError(422, "invalid_fields", "confirm_possible_duplicate must be a boolean.")
    return confirmed


def idempotency(request, key, namespace, data):
    value = request.headers.get("Idempotency-Key", "")
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", value):
        raise APIError(400, "idempotency_required", "Supply Idempotency-Key.")
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
    lookup = {"access_key": key, "namespace": namespace, "request_key": value}
    previous = IdempotentWrite.objects.filter(**lookup).first()
    if previous and previous.fingerprint != fingerprint:
        raise APIError(409, "idempotency_conflict", "This key was already used with another payload.")
    return previous, {**lookup, "fingerprint": fingerprint}


@api_view(("GET", "HEAD", "POST"))
def objects(request, key):
    if request.method in {"GET", "HEAD"}:
        try:
            page = int(request.GET.get("page", "1"))
            size = int(request.GET.get("page_size", "30"))
            if not (1 <= page <= 1000000 and 1 <= size <= 100):
                raise ValueError
        except ValueError:
            raise APIError(400, "pagination", "Invalid page or page_size.") from None
        props = Property.objects.select_related("staff_workspace").order_by("pk")
        q = request.GET.get("q", "").strip()
        if len(q) > 255:
            raise APIError(400, "search", "Search query is too long.")
        if q:
            props = props.filter(Q(address__icontains=q) | Q(address__icontains=q.capitalize())
                                 | Q(title__icontains=q))
        status = request.GET.get("status")
        if status == "unknown":
            props = props.filter(Q(staff_workspace__isnull=True) | Q(staff_workspace__work_status=status))
        elif status:
            if status not in PropertyWorkspace.WorkStatus.values:
                raise APIError(400, "status", "Unknown work status.")
            props = props.filter(staff_workspace__work_status=status)
        offset = (page - 1) * size
        return JsonResponse({"page": page, "page_size": size, "total": props.count(), "items": [
            {"id": prop.pk, "address": prop.address,
             "status": getattr(getattr(prop, "staff_workspace", None), "work_status", "unknown")}
            for prop in props[offset:offset + size]
        ]})
    data = read_body(request, {"listing", "confirm_possible_duplicate"})
    confirmed = duplicate_confirmation(data)
    dry_run = mode(request)
    if dry_run:
        prop = create_listing(data.get("listing"), key)
        warnings = duplicate_check(prop)
        return JsonResponse({"old": None, "proposed": {name: getattr(prop, name) for name in visible_listing_fields(key)},
                             "warnings": warnings, "confirmation_required": bool(warnings and not confirmed),
                             "version": None})
    with transaction.atomic():
        lock_writes(key)
        previous, receipt = idempotency(request, key, "objects", data)
        if previous:
            return with_version(aggregate(object_for(previous.result_id), key), status=200, replay=True)
        prop = create_listing(data.get("listing"), key)
        warnings = duplicate_check(prop)
        if warnings and not confirmed:
            raise APIError(409, "identity_confirmation_required", "Check the warnings and confirm distinct creation.",
                           warnings=warnings)
        prop.save()
        record_audit(prop, key.user, "api", "create", prop.pk, data["listing"])
        IdempotentWrite.objects.create(**receipt, result_id=prop.pk)
        return with_version(aggregate(prop, key), status=201)


def conflict(current):
    raise APIError(409, "conflict", "Object changed.", version=current["version"], current=current)


@api_view(("GET", "HEAD", "PATCH"))
def object_detail(request, key, pk):
    if request.method in {"GET", "HEAD"}:
        with transaction.atomic():
            return with_version(aggregate(object_for(pk), key))
    data = read_body(request, {"listing", "workspace"})
    dry_run = mode(request)
    expected = expected_version(request, dry_run)
    workspace = data.get("workspace", {})
    if not isinstance(workspace, dict) or set(workspace) - set(WORKSPACE):
        raise APIError(422, "invalid_fields", "Unknown workspace section.")
    try:
        with transaction.atomic():
            if not dry_run:
                lock_writes(key)
            prop = object_for(pk)
            current = aggregate(prop, key)
            if expected is not None and expected != current["version"]:
                conflict(current)
            listing = checked_listing(prop, data.get("listing", {}), current["version"], key)
            warnings = []
            if listing.keys() & {"address", "cadastral_number", "flat_number"}:
                candidate = Property(pk=prop.pk, address=listing.get("address", prop.address),
                                     flat_number=listing.get("flat_number", prop.flat_number),
                                     cadastral_number=listing.get("cadastral_number", prop.cadastral_number),
                                     operation=prop.operation)
                warnings = duplicate_check(candidate)
            work_changes = {}
            work_diff = {}
            for scope, proposed in workspace.items():
                _, changes, diff = checked_record(prop, scope, get_record(prop, scope), proposed, None)
                work_changes[scope] = changes
                work_diff[scope] = diff
            diff = {"listing": {name: {"old": getattr(prop, name), "new": value} for name, value in listing.items()},
                    "workspace": work_diff}
            if dry_run:
                return with_version({"changes": diff, "version": current["version"], "warnings": warnings})
            if not update_property(prop, READ_FIELDS, listing, actor=key.user, source="api"):
                raise RecordConflict
            for scope, changes in work_changes.items():
                # A previous section in this same transaction may have created the workspace.
                row = get_record(prop, scope)
                save_record(prop, scope, None, record_version(prop, scope, row), changes, actor=key.user, source="api")
            prop.refresh_from_db()
            return with_version(aggregate(prop, key))
    except RecordConflict:
        conflict(aggregate(object_for(pk), key))
    except ValidationError as error:
        raise APIError(422, "validation", "Invalid linked record.", fields=error.messages) from None
    except IntegrityError:
        raise APIError(409, "conflict", "A concurrent write conflicts with this change.") from None


@api_view(("GET", "HEAD", "POST", "PATCH"))
def records(request, key, pk, scope, record_id=None):
    if scope not in COLLECTIONS:
        raise APIError(404, "not_found", "Unknown collection.")
    if request.method in {"GET", "HEAD"}:
        with transaction.atomic():
            prop = object_for(pk)
            if record_id is None:
                response = aggregate(prop, key)
                return with_version({"items": response["collections"][scope], "version": response["version"]})
            row = get_record(prop, scope, record_id)
            if row is None:
                raise APIError(404, "not_found", "Record not found.")
            return with_version(serialize_record(prop, scope, row))
    if (record_id is None) != (request.method == "POST"):
        raise APIError(400, "invalid_route", "POST creates at the collection and PATCH updates an ID.")
    data = read_body(request, (*SCOPES[scope].fields, "retire"))
    retirement = "retire" in data
    if retirement and (record_id is None or data != {"retire": True} or data["retire"] is not True):
        raise APIError(422, "invalid_fields", "Confirm retirement explicitly on an existing record.")
    dry_run = mode(request)
    expected = expected_version(request, dry_run)
    try:
        with transaction.atomic():
            if not dry_run:
                lock_writes(key)
            prop = object_for(pk)
            receipt = None
            if record_id is None and not dry_run:
                previous, receipt = idempotency(request, key, f"{pk}:{scope}", data)
                if previous:
                    row = get_record(prop, scope, previous.result_id)
                    if row is None:
                        raise APIError(404, "not_found", "Record not found.")
                    return with_version(serialize_record(prop, scope, row), replay=True)
            row = get_record(prop, scope, record_id)
            if row is None:
                raise APIError(404, "not_found", "Record not found.")
            if record_id is None and expected is not None:
                current = aggregate(prop, key)
                if current["version"] != expected:
                    conflict(current)
            if retirement:
                version = record_version(prop, scope, row)
                if expected is not None and expected != version:
                    raise APIError(409, "conflict", "Record changed.", version=version)
                check_retirement(row)
                if dry_run:
                    return with_version({"changes": {"is_current": {"old": True, "new": False}},
                                         "warnings": [], "version": version})
                return with_version(serialize_record(prop, scope, retire_record(
                    prop, scope, record_id, version, actor=key.user, source="api"
                )))
            version, changes, diff = checked_record(prop, scope, row, data, expected if record_id else None)
            if record_id is None and not changes:
                raise APIError(422, "validation", "Supply data for the new record.")
            if dry_run:
                return with_version({"changes": diff, "warnings": [],
                                     "version": version if record_id else aggregate(prop, key)["version"]})
            saved = save_record(prop, scope, record_id, version, changes, actor=key.user, source="api")
            if receipt is not None:
                IdempotentWrite.objects.create(**receipt, result_id=saved.pk)
            return with_version(serialize_record(prop, scope, saved), status=201 if receipt else 200)
    except RecordConflict:
        raise APIError(409, "conflict", "Record changed.") from None
    except ValidationError as error:
        raise APIError(422, "validation", "Invalid linked record.", fields=error.messages) from None
    except IntegrityError:
        raise APIError(409, "conflict", "A concurrent write conflicts with this change.") from None


@api_view(("GET", "HEAD"))
def catalog(request, key):
    return JsonResponse({"document_types": document_types()})


@api_view(("GET", "HEAD"))
def changes(request, key, pk):
    prop = object_for(pk)
    return JsonResponse({"items": list(prop.staff_changes.order_by("-pk").values(
        "id", "actor_id", "source", "scope", "record_id", "fields", "diff", "created_at"
    )[:100])})
