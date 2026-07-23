from django.urls import path
from . import views

app_name = "catalog"
urlpatterns = [
    path("", views.service_list, name="service_list"),
    path("services/<int:pk>/", views.service_detail, name="service_detail"),
    path("instances/", views.instance_list, name="instance_list"),
    path("instances/<int:pk>/", views.instance_detail, name="instance_detail"),
    path("instances/<int:pk>/sync-glpi/", views.sync_glpi_instance, name="sync_glpi_instance"),
]
