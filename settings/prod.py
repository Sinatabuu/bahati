# bahati_service/settings/prod.py
import os
from .base import *

DEBUG = False
ALLOWED_HOSTS = ["api.bahatitransport.com"]
CSRF_TRUSTED_ORIGINS = ["https://api.bahatitransport.com", "https://bahati.bahatitransport.com"]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.getenv("PG_HOST"),
        "PORT": os.getenv("PG_PORT", "5432"),
        "NAME": os.getenv("PG_DB"),
        "USER": os.getenv("PG_USER"),
        "PASSWORD": os.getenv("PG_PASSWORD"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"sslmode": "require"},
    }
}

