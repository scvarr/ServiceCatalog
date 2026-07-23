from django.urls import path
from . import views

app_name = "catalog"
urlpatterns = [
    path("", views.service_list, name="service_list"),
    path("services/<int:pk>/", views.service_detail, name="service_detail"),
    path("instances/", views.instance_list, name="instance_list"),
    path("instances/<int:pk>/", views.instance_detail, name="instance_detail"),
    path("instances/<int:pk>/sync-glpi/", views.sync_glpi_instance, name="sync_glpi_instance"),
    path("instances/<int:pk>/import-glpi/", views.import_glpi_instance, name="import_glpi_instance"),
    path("instances/<int:pk>/export-glpi-diagnostics/", views.export_glpi_diagnostics, name="export_glpi_diagnostics"),
    path("instances/<int:pk>/glpi-imports/<int:session_pk>/apply/", views.apply_glpi_import, name="apply_glpi_import"),
]
