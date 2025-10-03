# core/urls.py
from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.panel_list, name="panel_list"),
    path("new/", views.panel_edit, name="panel_new"),      # «новый» = panel_edit без pk
    path("<int:pk>/", views.panel_edit, name="panel_edit"),
    path("<int:pk>/photo/add/", views.photo_add, name="photo_add"),
    path("<int:pk>/photo/<int:photo_id>/delete/", views.photo_delete, name="photo_delete"),
    path("feed/cian.xml", views.export_cian, name="export_cian"),
]
