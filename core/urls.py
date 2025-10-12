# core/urls.py
from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.panel_list, name="panel_list"),
    path("new/", views.panel_edit, name="panel_new"),      # «новый» = panel_edit без pk
    path("<int:pk>/", views.panel_edit, name="panel_edit"),
    path(
        "panel/edit/<int:pk>/add-photo/",
        views.panel_add_photo,
        name="panel_add_photo",
    ),
    path(
        "panel/photo/<int:pk>/delete/",
        views.panel_photo_delete,
        name="panel_photo_delete",
    ),
    path(
        "panel/photo/<int:pk>/rotate/",
        views.panel_photo_rotate,
        name="panel_photo_rotate",
    ),
    path(
        "panel/<int:prop_id>/photos/reorder/",
        views.panel_photos_reorder,
        name="panel_photos_reorder",
    ),
    path(
        "panel/photo/<int:pk>/set-default/",
        views.panel_photo_set_default,
        name="panel_photo_set_default",
    ),
    path(
        "panel/photos/bulk-delete/",
        views.panel_photos_bulk_delete,
        name="panel_photos_bulk_delete",
    ),
    path("panel/<int:pk>/price/", views.panel_update_price, name="panel_update_price"),
    path(
        "panel/<int:pk>/toggle-archive/",
        views.panel_toggle_archive,
        name="panel_toggle_archive",
    ),
    path("panel/<int:pk>/delete/", views.panel_delete, name="panel_delete"),
    path("feed/cian.xml", views.export_cian, name="export_cian"),
    path("feed/domklik.xml", views.export_domklik, name="export_domklik"),
]
