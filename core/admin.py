from django.conf import settings
from django.contrib import admin

from .property_writes import can_use_staff_card
from .workspace_models import (
    DriveFile, MarketplaceListing, OwnershipBasis, PropertyDocument, PropertyDocumentType,
    PropertyNote, PropertyOwner, PropertyWorkspace,
)


class PrivateWorkspaceAdminSite(admin.AdminSite):
    site_header = "Закрытые сведения CRM"
    index_title = "Рабочие паспорта и документы"
    site_url = "/panel/"

    def has_permission(self, request):
        return settings.CRM_REQUIRE_STAFF_LOGIN and can_use_staff_card(request.user)


workspace_admin = PrivateWorkspaceAdminSite(name="crm_workspace_admin")


class ReadOnlyPrivateAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class WorkspaceAdmin(ReadOnlyPrivateAdmin):
    list_display = ("property", "work_status", "assignee", "facts_current_on", "publication_warning")
    list_select_related = ("property", "assignee")
    list_filter = ("work_status",)
    readonly_fields = ("publication_warning", "status_changed_by", "status_changed_at")
    # Moving a passport to a different object could attach records to the wrong listing.
    def get_readonly_fields(self, request, obj=None):
        return (*self.readonly_fields, "property") if obj else self.readonly_fields

    @admin.display(description="Проверьте настройки выгрузки")
    def publication_warning(self, obj):
        inactive = {obj.WorkStatus.PAUSED, obj.WorkStatus.SOLD, obj.WorkStatus.LET,
                    obj.WorkStatus.EXPIRED, obj.WorkStatus.TERMINATED}
        if obj.property_id and obj.work_status in inactive and (obj.property.export_to_cian or obj.property.export_to_domklik):
            return "Одна из выгрузок включена. Проверьте, нужна ли она."
        return "—"

class NoteAdmin(ReadOnlyPrivateAdmin):
    list_display = ("workspace", "author", "created_at", "updated_at")
    list_select_related = ("workspace__property", "author")


workspace_admin.register(PropertyWorkspace, WorkspaceAdmin)
workspace_admin.register(PropertyNote, NoteAdmin)
workspace_admin.register([DriveFile, MarketplaceListing, OwnershipBasis, PropertyDocument, PropertyOwner],
                         ReadOnlyPrivateAdmin)
workspace_admin.register(PropertyDocumentType)
