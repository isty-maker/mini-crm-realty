from django.urls import path

from . import views


urlpatterns = [
    path("objects/", views.objects),
    path("objects/<int:pk>/", views.object_detail),
    path("objects/<int:pk>/changes/", views.changes),
    path("objects/<int:pk>/<slug:scope>/", views.records),
    path("objects/<int:pk>/<slug:scope>/<int:record_id>/", views.records),
    path("document-types/", views.catalog),
]
