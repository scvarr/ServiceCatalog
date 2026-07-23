import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "unsafe-development-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = [host.strip() for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if host.strip()]
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "catalog",
    "contracts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": os.environ.get("POSTGRES_DB", "servicecatalog"),
    "USER": os.environ.get("POSTGRES_USER", "servicecatalog"),
    "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "servicecatalog"),
    "HOST": os.environ.get("POSTGRES_HOST", "172.30.0.11"),
    "PORT": os.environ.get("POSTGRES_PORT", "5432"),
}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "catalog:service_list"
LOGOUT_REDIRECT_URL = "login"

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

GLPI_ENABLED = os.environ.get("GLPI_ENABLED", "false").lower() == "true"
GLPI_BASE_URL = os.environ.get("GLPI_BASE_URL", "").rstrip("/")
GLPI_API_VERSION = os.environ.get("GLPI_API_VERSION", "v2.3")
GLPI_CLIENT_ID = os.environ.get("GLPI_CLIENT_ID", "")
GLPI_CLIENT_SECRET = os.environ.get("GLPI_CLIENT_SECRET", "")
GLPI_USERNAME = os.environ.get("GLPI_USERNAME", "")
GLPI_PASSWORD = os.environ.get("GLPI_PASSWORD", "")
# Optional GLPI web-authentication source used only to read API documentation.
# Leave empty to use the source preselected by the GLPI login page.
GLPI_WEB_AUTH_SOURCE = os.environ.get("GLPI_WEB_AUTH_SOURCE", "")
GLPI_CA_BUNDLE = os.environ.get("GLPI_CA_BUNDLE", "")
GLPI_TIMEOUT_SECONDS = int(os.environ.get("GLPI_TIMEOUT_SECONDS", "15"))
GLPI_TLS_VERIFY = os.environ.get("GLPI_TLS_VERIFY", "true").lower() == "true"
