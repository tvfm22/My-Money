#!/bin/sh
# ---------------------------------------------------------------------------
# Container entrypoint for the My-Money API.
#
# Runs the startup steps that must happen against the *live* data volume before
# the server takes traffic, then hands off to gunicorn.
#
# The guiding rule here is that nothing in this script may destroy data. It
# applies migrations (additive), collects static files (a generated directory),
# and never resets, flushes or reseeds the database unless explicitly asked.
# ---------------------------------------------------------------------------
set -e

log() { echo "[entrypoint] $*"; }

DATA_DIR="${MY_MONEY_DATA_DIR:-/data}"
export MY_MONEY_DATA_DIR="$DATA_DIR"

# ---------------------------------------------------------------------------
# 1. Make sure the data tree exists.
#
# On a bind mount the host owns these directories, so this is the first thing
# that fails when permissions are wrong — better a clear message here than a
# confusing "unable to open database file" from deep inside Django.
# ---------------------------------------------------------------------------
if ! mkdir -p "$DATA_DIR/db" "$DATA_DIR/media" "$DATA_DIR/static" "$DATA_DIR/backups" 2>/dev/null; then
    echo "FATAL: cannot create directories under $DATA_DIR." >&2
    echo "       On Linux, grant the container's user (UID 1000) ownership:" >&2
    echo "         sudo chown -R 1000:1000 <host path mounted at $DATA_DIR>" >&2
    exit 1
fi

if [ ! -w "$DATA_DIR/db" ]; then
    echo "FATAL: $DATA_DIR/db is not writable by UID $(id -u)." >&2
    echo "       The database cannot be created or opened." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# 2. Refuse to run insecurely.
#
# A missing secret key with DEBUG off means every session cookie and password
# reset token is signed with a value published in the source. Failing loudly at
# startup is far better than serving traffic with it. The check runs through
# Django so it sees exactly what the application will see, including the env
# file.
# ---------------------------------------------------------------------------
python - <<'PY'
import os, sys
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402

if not settings.DEBUG and settings.SECRET_KEY == "insecure-dev-key-change-me":
    sys.exit(
        "\nFATAL: DJANGO_SECRET_KEY is not set while DJANGO_DEBUG is off.\n"
        "       Set it in data/.env (see data/.env.example).\n"
        "       Generate one with:\n"
        '         python -c "from django.core.management.utils import '
        'get_random_secret_key as k; print(k())"\n'
    )

print(f"[entrypoint] settings ok — data={settings.DATA_DIR} db={settings.DB_PATH} "
      f"debug={settings.DEBUG}")
PY

# ---------------------------------------------------------------------------
# 3. Apply migrations.
#
# Additive by design: `migrate` creates and alters, it never drops a table or
# removes a row. It is safe to run on every start, and running it every start is
# what keeps a redeploy from needing a manual step.
#
# There is deliberately no `flush`, no `--run-syncdb`, and no reset path here.
# ---------------------------------------------------------------------------
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    log "applying migrations"
    python manage.py migrate --noinput
else
    log "RUN_MIGRATIONS=false — skipping migrations"
fi

# ---------------------------------------------------------------------------
# 4. Collect static files.
#
# Deliberately WITHOUT `--clear`. That flag wipes STATIC_ROOT first, and
# STATIC_ROOT is a directory inside the data volume the operator controls — a
# single misconfigured variable would turn a deploy into data loss. Plain
# collection is idempotent and overwrites in place; the only cost is that a file
# from a deleted app may linger, which is cosmetic.
# ---------------------------------------------------------------------------
if [ "${RUN_COLLECTSTATIC:-true}" = "true" ]; then
    log "collecting static files"
    python manage.py collectstatic --noinput
else
    log "RUN_COLLECTSTATIC=false — skipping collectstatic"
fi

# ---------------------------------------------------------------------------
# 5. Optional demo seed — OFF unless explicitly requested.
#
# `seed_demo` creates a demo account and a few months of sample data. It must
# never run on its own: a redeploy of a live instance would otherwise add a
# second demo user and a pile of fake transactions. Opt in with SEED_DEMO=true,
# which is what the compose file's one-shot `seed` profile does.
# ---------------------------------------------------------------------------
if [ "${SEED_DEMO:-false}" = "true" ]; then
    log "SEED_DEMO=true — seeding demo data"
    python manage.py seed_demo
fi

# ---------------------------------------------------------------------------
# 6. Hand off.
#
# With no arguments, start the server. With arguments (a shell, a management
# command, a test run) run exactly that instead, so
#   docker compose run --rm api python manage.py shell
# works without any special casing.
# ---------------------------------------------------------------------------
if [ "$#" -gt 0 ]; then
    log "executing: $*"
    exec "$@"
fi

log "starting gunicorn on 0.0.0.0:${PORT:-8000} with ${GUNICORN_WORKERS:-3} worker(s)"
exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout "${GUNICORN_TIMEOUT:-60}" \
    --access-logfile - \
    --error-logfile - \
    --log-level "${GUNICORN_LOG_LEVEL:-info}"
