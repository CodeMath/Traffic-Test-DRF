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
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("REDIS_URL"),  # noqa
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            # COMPRESSOR는 django-redis 6.0+에서 제거됨
            # 압축이 필요한 경우 SERIALIZER 사용
            "CONNECTION_POOL_KWARGS": {
                "max_connections": 50,
                "retry_on_timeout": True,
            },
            "SOCKET_CONNECT_TIMEOUT": 5,
            "SOCKET_TIMEOUT": 5,
        },
        "TIMEOUT": 300,
    }
}
