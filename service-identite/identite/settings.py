"""Réglages de service-identite. Toute la configuration vient de l'environnement
(Azure : App Service > Configuration ; en local : service-identite/.env)."""
import os
import sys
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

from hospiplan_auth.conf import load_pem
from hospiplan_auth.db import schema_options

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"
KEYGEN = len(sys.argv) > 1 and sys.argv[1] == "generate_jwt_keys"


def env(name, default=None, required=False):
    value = os.environ.get(name, default)
    if required and not value:
        raise ImproperlyConfigured(f"Variable d'environnement manquante : {name}")
    return value


def env_bool(name, default=False):
    return str(os.environ.get(name, default)).strip().lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    return [v.strip() for v in os.environ.get(name, default).split(",") if v.strip()]


SERVICE_NAME = "service-identite"
SECRET_KEY = env("DJANGO_SECRET_KEY", "test-only-secret-key" if TESTING else None, required=True)
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "comptes",
]

MIDDLEWARE = [
    "hospiplan_auth.correlation.CorrelationIdMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "hospiplan_auth.correlation.AccessLogMiddleware",
]

ROOT_URLCONF = "identite.urls"
WSGI_APPLICATION = "identite.wsgi.application"
TEMPLATES = []

# --- Base de données : schéma « identite » (un schéma par service) ---
DB_SCHEMA = env("DB_SCHEMA", "identite")
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", "hospiplan"),
        "USER": env("DB_USER", required=True),
        "PASSWORD": env("DB_PASSWORD", required=True),
        "HOST": env("DB_HOST", "localhost"),
        "PORT": env("DB_PORT", "5432"),
        "OPTIONS": {"sslmode": env("DB_SSLMODE", "prefer"), **schema_options(DB_SCHEMA)},
        "CONN_MAX_AGE": 60,
    }
}

AUTH_USER_MODEL = "comptes.Utilisateur"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Clés JWT (RS256) : privée = signature (identite uniquement), publique = vérification ---
JWT_PRIVATE_KEY = load_pem("JWT_PRIVATE_KEY", BASE_DIR)
JWT_PUBLIC_KEY = load_pem("JWT_PUBLIC_KEY", BASE_DIR)
if TESTING and not (JWT_PRIVATE_KEY and JWT_PUBLIC_KEY):
    # Clés éphémères pour les tests / la CI uniquement
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    _k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    JWT_PRIVATE_KEY = _k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()).decode()
    JWT_PUBLIC_KEY = _k.public_key().public_bytes(serialization.Encoding.PEM,
                                                   serialization.PublicFormat.SubjectPublicKeyInfo).decode()
if not (JWT_PRIVATE_KEY and JWT_PUBLIC_KEY) and not KEYGEN:
    raise ImproperlyConfigured(
        "Clés JWT manquantes : JWT_PRIVATE_KEY(_FILE) et JWT_PUBLIC_KEY(_FILE). "
        "En local : python manage.py generate_jwt_keys"
    )

JWT_ISSUER = "hospiplan-identite"
JWT_AUDIENCE_API = "hospiplan-api"
JWT_AUDIENCE_INTERNAL = "hospiplan-internal"
SERVICE_TOKEN_LIFETIME = timedelta(minutes=15)

SIMPLE_JWT = {
    "ALGORITHM": "RS256",
    "SIGNING_KEY": JWT_PRIVATE_KEY,
    "VERIFYING_KEY": JWT_PUBLIC_KEY,
    "AUDIENCE": JWT_AUDIENCE_API,
    "ISSUER": JWT_ISSUER,
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(env("JWT_ACCESS_MINUTES", "15"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(env("JWT_REFRESH_DAYS", "7"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "sub",
    "TOKEN_TYPE_CLAIM": "type",
    "JTI_CLAIM": "jti",
    "LEEWAY": 10,
}

HOSPIPLAN_AUTH = {
    "PUBLIC_KEY": JWT_PUBLIC_KEY,
    "ISSUER": JWT_ISSUER,
    "AUDIENCE_API": JWT_AUDIENCE_API,
    "AUDIENCE_INTERNAL": JWT_AUDIENCE_INTERNAL,
    "SERVICE_NAME": SERVICE_NAME,
}

# Clients autorisés à obtenir un jeton de service (JSON) :
# {"service-planning": {"secret": "...", "scope": ["personnel:read"]}, ...}
SERVICE_CLIENTS_JSON = env("SERVICE_CLIENTS", "{}")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["hospiplan_auth.authentication.JWTClaimsAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["hospiplan_auth.permissions.IsUserToken"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_PAGINATION_CLASS": "hospiplan_auth.pagination.StandardPagination",
    "EXCEPTION_HANDLER": "hospiplan_auth.errors.exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "login": env("THROTTLE_LOGIN", "5/min"),
        "service_token": "30/min",
    },
    "UNAUTHENTICATED_USER": None,
}

# Cache local (limitation des tentatives de login). En production multi-instances :
# passer à un cache partagé (Azure Cache for Redis).
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
CORS_EXPOSE_HEADERS = ["X-Correlation-ID"]
CORS_ALLOW_HEADERS = ["authorization", "content-type", "x-correlation-id"]

if not DEBUG and not TESTING:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SECURE_REDIRECT_EXEMPT = [r"^health$"]  # sonde interne App Service
    SECURE_HSTS_SECONDS = int(env("DJANGO_HSTS_SECONDS", "3600"))
    SECURE_CONTENT_TYPE_NOSNIFF = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"correlation": {"()": "hospiplan_auth.correlation.CorrelationIdFilter"}},
    "formatters": {
        "standard": {"format": "%(asctime)s %(levelname)s [%(correlation_id)s] %(name)s : %(message)s"}
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard", "filters": ["correlation"]}
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {
        "django.request": {"level": "ERROR"},
        "hospiplan.access": {"level": "WARNING" if TESTING else "INFO"},
    },
}
