"""
재고 시스템 최적화된 Django 설정
"""

from .base import *

# ===============================
# 데이터베이스 연결 최적화
# ===============================

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST"),
        "PORT": env("DB_PORT"),
        "OPTIONS": {
            # 격리 수준 설정 - REPEATABLE READ
            "isolation_level": 2,  # ISOLATION_LEVEL_REPEATABLE_READ
            "options": " ".join(
                [
                    "-c default_transaction_isolation=repeatable\\ read",
                    "-c statement_timeout=30000",  # 30초 타임아웃
                    "-c idle_in_transaction_session_timeout=300000",  # 5분
                    "-c lock_timeout=5000",  # 5초 락 타임아웃
                ]
            ),
        },
        "CONN_MAX_AGE": 600,  # 10분 연결 유지
        "CONN_HEALTH_CHECKS": True,
    }
}

# ===============================
# 캐시 설정 - 재고 최적화
# ===============================

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "CONNECTION_POOL_KWARGS": {
                "max_connections": 100,
                "socket_timeout": 30,
                "socket_connect_timeout": 30,
                "retry_on_timeout": True,
            },
        },
        "KEY_PREFIX": "stock_system",
        "TIMEOUT": 300,  # 5분 기본 캐시
    },
    # 재고 전용 캐시 (짧은 TTL)
    "stock_cache": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL"),
        "OPTIONS": {
            "db": 1,  # 별도 DB 사용
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "KEY_PREFIX": "stock_fast",
        "TIMEOUT": 30,  # 30초 짧은 캐시
    },
}

# ===============================
# 로깅 설정 - 성능 모니터링
# ===============================

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
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s %(pathname)s %(lineno)d",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "stock_file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "logs/stock_operations.log",
            "maxBytes": 1024 * 1024 * 50,  # 50MB
            "backupCount": 5,
            "formatter": "json",
        },
        "performance_file": {
            "level": "WARNING",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "logs/performance.log",
            "maxBytes": 1024 * 1024 * 50,
            "backupCount": 5,
            "formatter": "json",
        },
    },
    "loggers": {
        "django.db.backends": {
            "handlers": ["performance_file"],
            "level": "DEBUG" if DEBUG else "WARNING",
            "propagate": False,
        },
        "apps.products.services": {
            "handlers": ["stock_file", "console"],
            "level": "INFO",
            "propagate": False,
        },
        # 성능 크리티컬 로거
        "stock.performance": {
            "handlers": ["performance_file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# ===============================
# 재고 시스템 전용 설정
# ===============================

# 재고 예약 설정
STOCK_RESERVATION_SETTINGS = {
    "DEFAULT_DURATION_MINUTES": 30,
    "MAX_RETRY_COUNT": 3,
    "BASE_RETRY_DELAY": 0.1,
    "HIGH_CONTENTION_THRESHOLD": 5,
    "CRITICAL_STOCK_THRESHOLD": 10,
    "ENABLE_ADAPTIVE_STRATEGY": True,
    "ENABLE_PERFORMANCE_MONITORING": True,
}

# 격리 수준 전략 매핑
ISOLATION_STRATEGY_MAP = {
    "low_contention": "READ_COMMITTED",
    "medium_contention": "REPEATABLE_READ",
    "high_contention": "SERIALIZABLE",
}

# 성능 모니터링 설정
PERFORMANCE_MONITORING = {
    "ENABLE_QUERY_LOGGING": DEBUG,
    "SLOW_QUERY_THRESHOLD_MS": 1000,
    "ENABLE_LOCK_MONITORING": True,
    "ALERT_EMAIL_RECIPIENTS": [
        "admin@company.com",
    ],
    "METRICS_COLLECTION_INTERVAL": 60,  # 초
}

# ===============================
# 미들웨어 최적화
# ===============================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # 성능 모니터링 제거됨 (silk 데드락 방지)
    # 커스텀 성능 모니터링 미들웨어
    "apps.products.middleware.StockPerformanceMiddleware",
]

# ===============================
# DRF 최적화 설정
# ===============================

REST_FRAMEWORK.update(
    {
        "DEFAULT_THROTTLE_CLASSES": [
            "rest_framework.throttling.AnonRateThrottle",
            "rest_framework.throttling.UserRateThrottle",
            # 재고 예약 전용 쓰로틀링
            "apps.products.throttling.StockReservationThrottle",
        ],
        "DEFAULT_THROTTLE_RATES": {
            "anon": "100/hour",
            "user": "1000/hour",
            "stock_reservation": "60/minute",  # 재고 예약은 분당 60회 제한
        },
        # 응답 시간 최적화
        "DEFAULT_RENDERER_CLASSES": [
            "rest_framework.renderers.JSONRenderer",
            # 개발 환경에서만 BrowsableAPIRenderer
            *(["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else []),
        ],
    }
)

# ===============================
# Celery 설정 - 비동기 처리
# ===============================

CELERY_BEAT_SCHEDULE = {
    # 만료된 예약 정리 (5분마다)
    "cleanup-expired-reservations": {
        "task": "apps.products.tasks.cleanup_expired_reservations",
        "schedule": 300.0,  # 5분
    },
    # 재고 통계 업데이트 (1시간마다)
    "update-stock-statistics": {
        "task": "apps.products.tasks.update_stock_statistics",
        "schedule": 3600.0,  # 1시간
    },
    # 성능 메트릭 수집 (10분마다)
    "collect-performance-metrics": {
        "task": "apps.products.tasks.collect_performance_metrics",
        "schedule": 600.0,  # 10분
    },
}

# ===============================
# 보안 설정
# ===============================

# CSRF 보호 강화
CSRF_USE_SESSIONS = True
CSRF_COOKIE_HTTPONLY = True

# 세션 보안
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 3600  # 1시간

# ===============================
# 개발/프로덕션 분기 설정
# ===============================

if DEBUG:
    # 개발 환경 전용 설정
    INSTALLED_APPS += [
        "django_extensions",
    ]

    # Silk 프로파일링 설정 제거됨 (데드락 방지)

else:
    # 프로덕션 환경 전용 설정

    # 보안 강화
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    # 정적 파일 압축
    STATICFILES_STORAGE = "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"

    # 에러 리포팅 (예: Sentry)
    # import sentry_sdk
    # sentry_sdk.init(dsn="YOUR_SENTRY_DSN")
