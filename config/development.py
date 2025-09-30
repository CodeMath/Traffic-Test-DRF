from .base import *

# ========================
# DATABASES | Development and Production are PostgreSQL
# ========================

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME"),  # noqa
        "USER": env("DB_USER"),  # noqa
        "PASSWORD": env("DB_PASSWORD"),  # noqa
        "HOST": env("DB_HOST"),  # noqa
        "PORT": env("DB_PORT"),  # noqa
        "CONN_MAX_AGE": 600,  # 10분 연결 유지
        "CONN_HEALTH_CHECKS": True,
    }
}

# ========================
# Cache
# ========================
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL"),  # noqa
    }
}
