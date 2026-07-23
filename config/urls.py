from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.http import HttpResponse
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("healthz/", lambda request: HttpResponse("ok", content_type="text/plain"), name="healthz"),
    path("", include("catalog.urls")),
    path("contracts/", include("contracts.urls")),
]

