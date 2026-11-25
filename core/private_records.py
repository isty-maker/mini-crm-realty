"""Explicit private write scopes used by HTML and API."""

from dataclasses import dataclass

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.forms import modelform_factory
from django.utils import timezone

from .models import Property
from .property_writes import property_version, version_matches
from .workspace_models import (
    DriveFile, OwnershipBasis, PropertyChange, PropertyDocument, PropertyNote,
    PropertyOwner, PropertyWorkspace,
)


@dataclass(frozen=True)
class RecordScope:
    model: type
    title: str
    fields: tuple[str, ...]


SCOPES = {
    "status": RecordScope(PropertyWorkspace, "Рабочий статус", (
        "work_status", "status_reason", "status_date", "status_comment",
    )),
    "terms": RecordScope(PropertyWorkspace, "Рабочие условия сделки", (
        "occupancy", "registered_people", "release_date", "release_terms", "keys_available",
        "keys_location", "furnishing", "furnishing_comment", "payment_methods", "assignee", "facts_current_on",
    )),
    "legal": RecordScope(PropertyWorkspace, "Юридическое состояние", (
        "documented_area", "documented_area_source", "documented_area_checked_on",
        "ownership", "owner_count", "encumbrances", "encumbrance_source", "encumbrance_checked_on",
        "encumbrance_comment", "minor_owners", "registered_minors", "alterations", "legal_comments", "drive_folder_id",
    )),
    "bases": RecordScope(OwnershipBasis, "Основания права", ("kind", "document_date", "source")),
    "owners": RecordScope(PropertyOwner, "Собственники и доли", ("name", "share_numerator", "share_denominator")),
    "documents": RecordScope(PropertyDocument, "Готовность документов", (
        "document_type", "applicability", "availability", "verification", "document_date",
        "checked_on", "source", "comment", "original",
    )),
    "files": RecordScope(DriveFile, "Файлы Google Drive", ("file_id", "name", "url", "modified_at")),
    "notes": RecordScope(PropertyNote, "Рабочие заметки", ("text",)),
}


class RecordConflict(Exception):
    pass


def get_record(prop, key, pk=None):
    scope = SCOPES[key]
    workspace = PropertyWorkspace.objects.filter(property=prop).first()
    if scope.model is PropertyWorkspace:
        return workspace or PropertyWorkspace(property=prop)
    if pk is None:
        return scope.model(workspace=workspace)
    return scope.model.objects.filter(workspace=workspace, pk=pk).first() if workspace else None


def model_values(record, fields):
    return {name: getattr(record, record._meta.get_field(name).attname) for name in fields}


def record_version(prop, key, record):
    identifier = f"{prop.pk}:{key}:{record.pk or 'new'}"
    fields = tuple(record._meta.get_field(name).attname for name in SCOPES[key].fields)
    return property_version(record, identifier, fields)


def record_form(prop, key, record, data=None):
    scope = SCOPES[key]
    widgets = {}
    for name in scope.fields:
        field = scope.model._meta.get_field(name)
        if field.get_internal_type() == "DateField":
            widgets[name] = forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})
        elif field.get_internal_type() == "DateTimeField":
            widgets[name] = forms.DateTimeInput(format="%Y-%m-%dT%H:%M:%S", attrs={"type": "datetime-local"})
        elif field.get_internal_type() == "TextField":
            widgets[name] = forms.Textarea(attrs={"rows": 2})
    form = modelform_factory(scope.model, fields=scope.fields, widgets=widgets)(data, instance=record)
    if key == "documents":
        form.fields["original"].queryset = DriveFile.objects.filter(workspace__property=prop)
    return form


def prepare_record(prop, key, record, data):
    fields = SCOPES[key].fields
    if set(data) - set(fields):
        raise ValidationError("Поле вне разрешённого набора.")
    values = model_values(record, fields)
    version = record_version(prop, key, record)
    form = record_form(prop, key, record, {**values, **data})
    if not form.is_valid():
        return form, version, {}
    changes = {name: getattr(form.instance, form.instance._meta.get_field(name).attname)
               for name in data}
    changes = {name: value for name, value in changes.items() if value != values[name]}
    return form, version, changes


def record_audit(prop, actor, source, key, record_id, fields):
    if fields:
        PropertyChange.objects.create(property=prop, actor=actor, source=source, scope=key,
                                      record_id=record_id, fields=sorted(fields))


@transaction.atomic
def save_record(prop, key, pk, version, changes, *, actor, source):
    if set(changes) - set(SCOPES[key].fields):
        raise ValidationError("Поле вне разрешённого набора.")
    # The property is the aggregate lock, including creation of missing private rows.
    if Property.objects.filter(pk=prop.pk).update(id=F("id")) != 1:
        raise RecordConflict
    current = get_record(prop, key, pk)
    if current is None or version != record_version(prop, key, current):
        raise RecordConflict
    if not changes:
        return current
    if isinstance(current, PropertyWorkspace):
        if "work_status" in changes:
            current.status_changed_at = timezone.now()
            current.status_changed_by = actor
    elif not current.pk:
        current.workspace, _ = PropertyWorkspace.objects.get_or_create(property=prop)
        if isinstance(current, PropertyNote):
            current.author = actor
    save_fields = []
    for name, value in changes.items():
        setattr(current, current._meta.get_field(name).attname, value)
        save_fields.append(name)
    current.full_clean()
    if not current.pk:
        current.save()
    else:
        if isinstance(current, PropertyNote):
            save_fields.append("updated_at")
        if isinstance(current, PropertyWorkspace) and "work_status" in changes:
            save_fields += ["status_changed_at", "status_changed_by"]
        current.save(update_fields=save_fields)
    record_audit(prop, actor, source, key, current.pk, changes)
    return current


def display_record(record, scope):
    result = []
    for name in scope.fields:
        field = record._meta.get_field(name)
        value = getattr(record, name)
        if value is None or value == "":
            continue
        if field.choices:
            value = getattr(record, f"get_{name}_display")()
        result.append((field.verbose_name, value))
    if isinstance(record, PropertyNote) and record.pk:
        result.extend([("Автор", record.author or "—"), ("Создано", record.created_at), ("Изменено", record.updated_at)])
    if isinstance(record, PropertyDocument) and record.original_id and record.original.url.startswith("https://"):
        result.append(("Оригинал Drive", record.original.url))
    return result


def private_context(prop):
    workspace = PropertyWorkspace.objects.filter(property=prop).first()
    blocks = {}
    for key, scope in SCOPES.items():
        if scope.model is PropertyWorkspace:
            rows = [workspace] if workspace else []
        else:
            query = scope.model.objects.filter(workspace=workspace).order_by("pk")
            if key == "documents":
                query = query.select_related("document_type", "original")
            if key == "notes":
                query = query.select_related("author")
            rows = query if workspace else []
        blocks[key] = {"key": key, "title": scope.title, "collection": scope.model is not PropertyWorkspace,
                       "items": [{"id": row.pk, "rows": display_record(row, scope)} for row in rows]}
    warning = workspace and workspace.work_status in {
        workspace.WorkStatus.SOLD, workspace.WorkStatus.LET, workspace.WorkStatus.PAUSED,
        workspace.WorkStatus.EXPIRED, workspace.WorkStatus.TERMINATED,
    } and (prop.export_to_cian or prop.export_to_domklik)
    return {"workspace": workspace, "private_blocks": blocks, "publication_warning": warning}
