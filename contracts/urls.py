from django.urls import path
from . import views

app_name = "contracts"
urlpatterns = [
    path("", views.contract_list, name="contract_list"),
    path("<int:pk>/", views.contract_detail, name="contract_detail"),
    path("terms/<int:pk>/comparison/", views.term_comparison, name="term_comparison"),
    path("terms/<int:pk>/import/", views.import_list, name="import_list"),
]

