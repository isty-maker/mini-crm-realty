from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from core import views as core_views

urlpatterns = [
    path("healthz/", core_views.healthz, name="healthz"),
    path("panel/", core_views.panel_list, name="panel_list"),
    path("panel/new/", core_views.panel_new, name="panel_new"),
    path("panel/create/", core_views.panel_create, name="panel_create"),
    path("panel/edit/<int:pk>/", core_views.panel_edit, name="panel_edit"),
    path("panel/edit/<int:pk>/add-photo/", core_views.panel_add_photo, name="panel_add_photo"),
    path("panel/photo/<int:photo_id>/delete/", core_views.panel_delete_photo, name="panel_delete_photo"),
    path("panel/photo/<int:photo_id>/make-main/", core_views.panel_toggle_main, name="panel_toggle_main"),
    path("panel/export/cian/", core_views.export_cian, name="export_cian"),
    path("panel/export/cian/check/", core_views.export_cian_check, name="export_cian_check"),
    path("panel/archive/<int:pk>/", core_views.panel_archive, name="panel_archive"),
    path("panel/restore/<int:pk>/", core_views.panel_restore, name="panel_restore"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
