"""
Django settings for the My-Money personal finance application.

All environment-specific values are read from environment variables, loaded from
`data/.env` at the repository root. That folder is also where every persistent
artefact lives — the database, uploads, collected static files — so a deployment
has exactly one thing to mount, back up and set permissions on. See
`data/README.md`.

Database
--------
This build ships SQLite-only, per the project decision. The connection is
nevertheless configured through the small `DATABASES` mapping below so that a
future PostgreSQL deployment is a configuration change, not a code change.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------
# The data folder and the configuration file
# --------------------------------------------------------------------------


def resolve_data_dir() -> Path:
    """Locate the folder holding persistent, non-image data.

    One folder holds the database, uploads, collected static files and the
    configuration file. In Docker this resolves to `/data`; locally it is
    `<repo>/data`.

    The value may be absolute or relative to the repository root, because the
    two environments want different answers and neither should be a special
    case elsewhere in the code.
    """
    raw = os.environ.get("MY_MONEY_DATA_DIR", "data").strip() or "data"
    candidate = Path(raw).expanduser()
    return candidate if candidate.is_absolute() else (REPO_ROOT / candidate).resolve()


def load_env_file(data_dir: Path) -> Path | None:
    """Load configuration from the first candidate file that exists.

    `data/.env` is the documented location. `backend/.env` is honoured as a
    fallback so an older checkout keeps working after the move — it is read if
    present, not required. An explicit `MY_MONEY_ENV_FILE` wins over both, which
    is what a platform that injects a mounted secret file wants.

    `load_dotenv` does not overwrite variables already present in the process
    environment, which is deliberate: it lets `docker compose` set
    `DJANGO_DEBUG=False` and have it beat the file without editing it.
    """
    explicit = os.environ.get("MY_MONEY_ENV_FILE", "").strip()
    candidates = ([Path(explicit).expanduser()] if explicit else []) + [
        data_dir / ".env",
        BASE_DIR / ".env",
    ]
    for candidate in candidates:
        if candidate.is_file():
            load_dotenv(candidate)
            return candidate
    return None


# Two passes, because the configuration file lives *inside* the data folder and
# is itself allowed to move that folder. The first locates the folder using the
# process environment; the second re-reads it once the file has been loaded.
DATA_DIR = resolve_data_dir()
ENV_FILE = load_env_file(DATA_DIR)
DATA_DIR = resolve_data_dir()


# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------

# In production DJANGO_SECRET_KEY MUST be set. The fallback exists only so a
# fresh checkout runs locally; it is intentionally obvious that it is insecure.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-key-change-me")

DEBUG = env_bool("DJANGO_DEBUG", default=True)

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")

# Vite's dev server runs on a different origin than Django, so the API is
# cross-origin in development. Listed explicitly rather than using a wildcard.
CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)

CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    # Local
    "apps.core",
    "apps.users",
    "apps.accounts",
    "apps.categories",
    "apps.transactions",
    "apps.budgets",
    "apps.debts",
    "apps.assets",
    "apps.reports",
    "apps.insights",
    "apps.sms",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Custom runner: this project keeps one `tests` subpackage per app, and Django's
# stock discovery cannot handle the repeated basename. See config/test_runner.py
# for the full explanation. `python manage.py test` works as a single command
# because of this.
TEST_RUNNER = "config.test_runner.AppAwareDiscoverRunner"


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------

DB_ENGINE = os.environ.get("DB_ENGINE", "sqlite").strip().lower()


def sqlite_path() -> Path:
    """Resolve the SQLite file.

    `DB_NAME` is normally a bare filename and always lands in `<DATA_DIR>/db/`,
    so the database cannot drift outside the one folder that gets mounted and
    backed up. An absolute path is honoured for the case where the file is
    mounted from somewhere else entirely.

    Resolved to an absolute string rather than a `Path` because Django passes it
    straight to `sqlite3.connect`, and because a relative name would otherwise
    be interpreted against the process working directory — which differs between
    `manage.py` run from `backend/` and gunicorn run from `/app`.
    """
    raw = os.environ.get("DB_NAME", "db.sqlite3").strip() or "db.sqlite3"
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return candidate
    return DATA_DIR / "db" / candidate


def sqlite_pragmas() -> str:
    """PRAGMAs applied to every SQLite connection.

    Foreign keys are OFF by default in SQLite, so without this the cascade rules
    in the models are never exercised and a delete can silently orphan rows.

    WAL is opt-in via `SQLITE_JOURNAL_MODE`. It lets readers proceed while a
    writer is active, which is what stops "database is locked" once gunicorn
    runs more than one worker — but it changes on-disk behaviour (it creates
    `-wal` and `-shm` files beside the database), so it is a decision the
    operator makes knowingly rather than something enabled behind their back.
    Django splits this string on `;` and runs each statement.
    """
    pragmas = ["PRAGMA foreign_keys = ON;"]
    mode = os.environ.get("SQLITE_JOURNAL_MODE", "").strip().upper()
    if mode in {"WAL", "DELETE", "TRUNCATE", "PERSIST", "MEMORY", "OFF"}:
        pragmas.append(f"PRAGMA journal_mode = {mode};")
    return " ".join(pragmas)


DB_PATH = sqlite_path()

if DB_ENGINE in {"postgres", "postgresql"}:
    # Documented seam: this branch is not exercised by the shipped build, but
    # it is why no application code contains SQLite-specific assumptions.
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "my_money"),
            "USER": os.environ.get("DB_USER", ""),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
            "PORT": os.environ.get("DB_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    # The directory may not exist on a fresh clone; SQLite will not create it.
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(DB_PATH),
            "OPTIONS": {
                # IMMEDIATE takes the write lock at the start of a transaction
                # rather than upgrading mid-way, which turns a class of
                # deadlocks into a clean wait.
                "transaction_mode": "IMMEDIATE",
                "init_command": sqlite_pragmas(),
            },
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --------------------------------------------------------------------------
# Internationalization
# --------------------------------------------------------------------------

LANGUAGE_CODE = "fa-ir"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True


# --------------------------------------------------------------------------
# Static / media
# --------------------------------------------------------------------------

# Both live under DATA_DIR, not under BASE_DIR. Collected static files are
# written by the container on every start and served directly by nginx, so they
# belong somewhere the image can write to and the web server can read — which a
# read-only image layer is not. Media is user content and must outlive the
# container. An absolute override is accepted for the case where they are
# mounted separately.
def _data_subdir(name: str, env_var: str) -> Path:
    raw = os.environ.get(env_var, "").strip()
    if raw:
        candidate = Path(raw).expanduser()
        return candidate if candidate.is_absolute() else DATA_DIR / candidate
    return DATA_DIR / name


STATIC_ROOT = _data_subdir("static", "STATIC_ROOT")
MEDIA_ROOT = _data_subdir("media", "MEDIA_ROOT")

STATIC_URL = "static/"
MEDIA_URL = "media/"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


# --------------------------------------------------------------------------
# Django REST Framework
# --------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    # Deny by default: a new endpoint is private until someone opts it out.
    # This is the safe direction for an app full of financial data.
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "apps.core.permissions.StandardPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "EXCEPTION_HANDLER": "apps.core.permissions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        # Generous for normal use, tight enough to blunt credential stuffing.
        "anon": "120/min",
        "user": "6000/hour",
        "auth": "20/min",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": dt.timedelta(
        minutes=env_int("ACCESS_TOKEN_LIFETIME_MINUTES", 60)
    ),
    "REFRESH_TOKEN_LIFETIME": dt.timedelta(
        days=env_int("REFRESH_TOKEN_LIFETIME_DAYS", 14)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    # Without blacklisting, a rotated refresh token stays valid until it
    # expires, so a stolen token keeps working. Blacklisting closes that.
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}


# --------------------------------------------------------------------------
# Security hardening
# --------------------------------------------------------------------------

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# Always on, DEBUG or not — these cost nothing and prevent MIME sniffing and
# clickjacking in every environment.
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # must be readable by the SPA to echo the token
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"


# --------------------------------------------------------------------------
# Logging — technical detail stays server-side, users get friendly messages
# --------------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
