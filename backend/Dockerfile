# syntax=docker/dockerfile:1
#
# My-Money API — Django + DRF behind gunicorn.
#
# The image contains code and dependencies only. Everything that must survive a
# redeploy (the database, uploads, collected static files, the config file)
# lives in the `data/` folder on the host and is bind-mounted at /data. That
# separation is the point: rebuilding or replacing this image can never destroy
# user data.

FROM python:3.13-slim

# - PYTHONDONTWRITEBYTECODE: no .pyc files, so the image layer stays clean and
#   a read-only filesystem would still work.
# - PYTHONUNBUFFERED: logs appear immediately instead of being held in a buffer,
#   which is what makes `docker compose logs` useful during a failed start.
# - PIP_NO_CACHE_DIR: the wheel cache is dead weight in a final image.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MY_MONEY_DATA_DIR=/data \
    DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app

# Dependencies first. Docker caches this layer, so editing application code
# rebuilds in seconds while a dependency change is the only thing that pays for
# a reinstall. SQLite ships with CPython, so no system packages are needed.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user. UID/GID 1000 is the convention documented in
# data/README.md, so the bind-mounted folder can be chowned to match without
# guessing. A process that only needs to read code and write one directory has
# no business being root.
RUN groupadd --gid 1000 app \
 && useradd --uid 1000 --gid 1000 --no-create-home --shell /usr/sbin/nologin app \
 && chmod +x /app/entrypoint.sh \
 && mkdir -p /data/db /data/media /data/static /data/backups \
 && chown -R app:app /data

USER app

EXPOSE 8000

# Liveness only — /api/health/ touches no database and requires no
# authentication, so it answers honestly even while the database is busy.
# Uses the stdlib rather than curl so the image needs no extra package.
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/health/', timeout=4)"

# No CMD: the entrypoint starts gunicorn itself when given no arguments, and
# runs whatever command it is given otherwise. That is what makes
#   docker compose run --rm api python manage.py shell
# work without special casing.
ENTRYPOINT ["/app/entrypoint.sh"]
