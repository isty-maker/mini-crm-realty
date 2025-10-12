from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from core import views as core_views

urlpatterns = [
    path("healthz/", core_views.healthz, name="healthz"),
    path("healthz/mediainfo/", core_views.healthz_mediainfo, name="healthz_mediainfo"),
    path("healthz/dbinfo/", core_views.dbinfo, name="dbinfo"),
    path("healthz/logtail/", core_views.logtail, name="logtail"),
    path("panel/", core_views.panel_list, name="panel_list"),
    path("panel/new/", core_views.panel_new, name="panel_new"),
    path("panel/create/", core_views.panel_create, name="panel_create"),
    path("panel/edit/<int:pk>/", core_views.panel_edit, name="panel_edit"),
    path("panel/edit/<int:pk>/add-photo/", core_views.panel_add_photo, name="panel_add_photo"),
    path("panel/photo/<int:pk>/delete/", core_views.panel_photo_delete, name="panel_photo_delete"),
    path("panel/photo/<int:pk>/rotate/", core_views.panel_photo_rotate, name="panel_photo_rotate"),
    path(
        "panel/<int:prop_id>/photos/reorder/",
        core_views.panel_photos_reorder,
        name="panel_photos_reorder",
    ),
    path(
        "panel/photo/<int:pk>/set-default/",
        core_views.panel_photo_set_default,
        name="panel_photo_set_default",
    ),
    path(
        "panel/photos/bulk-delete/",
        core_views.panel_photos_bulk_delete,
        name="panel_photos_bulk_delete",
    ),
    path("panel/export/cian/", core_views.export_cian, name="export_cian"),
    path("panel/export/domklik/", core_views.export_domklik, name="export_domklik"),
    path("panel/export/cian/check/", core_views.export_cian_check, name="export_cian_check"),
    path("panel/<int:pk>/price/", core_views.panel_update_price, name="panel_update_price"),
    path(
        "panel/<int:pk>/toggle-archive/",
        core_views.panel_toggle_archive,
        name="panel_toggle_archive",
    ),
    path("panel/<int:pk>/delete/", core_views.panel_delete, name="panel_delete"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
