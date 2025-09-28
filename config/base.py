import os
from datetime import timedelta
from pathlib import Path

import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load Env
env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

SECRET_KEY = env("SECRET_KEY")

DEBUG = env("DEBUG")

BASE_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ========================
# THIRD_PARTY_APPS
# ========================
THIRD_PARTY_APPS = [
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "drf_spectacular",
    "django_filters",
    "django_redis",
]


# ========================
# DEBUG
# ========================
if DEBUG:
    THIRD_PARTY_APPS += [
        "django_extensions",
        "silk",
    ]
    MIDDLEWARE += ["silk.middleware.SilkyMiddleware"]


# ========================
# LOCAL_APPS
# ========================
LOCAL_APPS = [
    "apps.products",
]


# ========================
# INSTALLED_APPS
# ========================
INSTALLED_APPS = BASE_APPS + THIRD_PARTY_APPS + LOCAL_APPS


ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.request",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# REST Framework
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",  # 브라우저에서 기본 DRF 페이지 비활성화
    ),
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    # JWT 성능 최적화
    "JWT_AUTH_COOKIE": None,  # 쿠키 처리 비활성화
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 100,
    "DEFAULT_VERSION": "v1",
    "ALLOWED_VERSIONS": ["v1"],
}


# ========================
# CORS
# ========================
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = [
    "DELETE",
    "GET",
    "OPTIONS",
    "PATCH",
    "POST",
    "PUT",
]

# ========================
# SPECTACULAR
# ========================
SPECTACULAR_SETTINGS = {
    "TITLE": "API",
    "DESCRIPTION": "API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayOperationId": True,
        "displayRequestDuration": True,
        "filter": True,
        "showExtensions": True,
        "showCommonExtensions": True,
    },
    "SWAGGER_UI_DIST": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.9.0",
    "COMPONENT_SPLIT_REQUEST": True,
    "COMPONENT_NO_READ_ONLY_REQUIRED": False,
    "COMPONENT_SPLIT_PATCH": True,
    "ENUM_ADD_EXPLICIT_BLANK_NULL_CHOICE": True,
    "GENERIC_ADDITIONAL_PROPERTIES": "dict",
    "SCHEMA_PATH_PREFIX": "/api/",
    "SCHEMA_COERCE_PATH_PK_SUFFIX": True,
    "SCHEMA_PATH_PREFIX_TRIM": False,
    "SORT_OPERATIONS": False,
    "ENABLE_DUPLICATE_LABELS": False,
    "DISABLE_COMPONENTS": False,
    "PREPROCESSING_HOOKS": [],
    "POSTPROCESSING_HOOKS": [],
    "SERVE_AUTHENTICATION": None,
}


# ========================
# SIMPLE_JWT
# ========================
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
}


# ========================
# LOGGING
# ========================
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "logs/django.log",
            "maxBytes": 15728640,  # 15MB
            "backupCount": 10,
            "formatter": "json",
        },
        "performance": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "logs/performance.log",
            "maxBytes": 15728640,  # 15MB
            "backupCount": 10,
            "formatter": "json",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": "INFO",
        },
        "django.db.backends": {
            "handlers": ["console"],
            "level": "INFO" if not DEBUG else "DEBUG",
        },
        "apps.products": {
            "handlers": ["console", "file"],
            "level": "INFO" if not DEBUG else "DEBUG",
        },
        "apps.products.metrics": {
            "handlers": ["console", "performance"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# ========================
# SILKY
# ========================
SILKY_PYTHON_PROFILER = False  # 프로파일링 충돌 방지
SILKY_PYTHON_PROFILER_BINARY = False
SILKY_AUTHENTICATION = True
SILKY_AUTHORISATION = True
