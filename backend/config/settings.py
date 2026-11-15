import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-secret-key")
DEBUG = os.getenv("DJANGO_DEBUG", "0") == "1"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "accounts.apps.AccountsConfig",
    "billing.apps.BillingConfig",
    "nodes.apps.NodesConfig",
    "probes.apps.ProbesConfig",
    "sub_gateway.apps.SubGatewayConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "config.middleware.SubdomainRoutingMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
SUB_GATEWAY_URLCONF = "config.sub_urls"

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
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "linkori"),
        "USER": os.environ.get("POSTGRES_USER", "linkori"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "linkori"),
        "HOST": os.environ.get("POSTGRES_HOST", "postgres"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.getenv("REDIS_URL", "redis://redis:6379/0"),
    }
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
CSRF_TRUSTED_ORIGINS = [
    "https://linkori.org",
    "https://www.linkori.org",
]

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "EXCEPTION_HANDLER": "config.exceptions.custom_exception_handler",
}

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/1")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/2")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULE = {
    "probes-check-nodes-health": {
        "task": "probes.tasks.check_nodes_health",
        "schedule": 60.0,
    },
    "billing-expire-subscriptions": {
        "task": "billing.tasks.expire_overdue_subscriptions",
        "schedule": 120.0,
    },
}

# Шлюз подписок
SUB_GATEWAY_HOST = os.getenv("SUB_GATEWAY_HOST", "sub.linkori.org").lower()
SUB_PROFILE_TITLE = os.getenv("SUB_PROFILE_TITLE", "Linkori Proxy")
SUB_UPDATE_INTERVAL_HOURS = int(os.getenv("SUB_UPDATE_INTERVAL_HOURS", "6"))
SUB_SUPPORT_URL = os.getenv("SUB_SUPPORT_URL", "https://t.me/Linkorisupport")
SUB_WEB_URL = os.getenv("SUB_WEB_URL", "https://linkori.org")

# Токены внутренних интеграций (стенд проверок и Telegram-бот)
PROBE_API_TOKEN = os.getenv("PROBE_API_TOKEN", "")
PROBE_XRAY_UUID = os.getenv("PROBE_XRAY_UUID", "")
BOT_API_TOKEN = os.getenv("BOT_API_TOKEN", "")

# Биллинг, рефералка и платежный шлюз
REFERRAL_BONUS_PERCENT = int(os.getenv("REFERRAL_BONUS_PERCENT", "15"))
PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "stub").lower()
ALLOW_STUB_PAYMENTS = os.getenv("ALLOW_STUB_PAYMENTS", "1") == "1"