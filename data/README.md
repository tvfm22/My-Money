# `data/` — everything that must survive a redeploy

This folder holds every file the application needs to **read, write, or keep
secret**. Nothing here belongs in a Docker image, and nothing here should be
committed to version control (except the two templates and the `.gitkeep` files
that hold the folder structure).

The rule is simple: **if losing it would lose user data, or if reading it would
leak a secret, it lives here.**

## Layout

```
data/
├── .env              ← the configuration file. Edit this one.
├── .env.example      ← template, safe to commit
├── db/
│   └── db.sqlite3    ← the entire database
├── media/            ← files uploaded by users
├── static/           ← collected Django static files (admin CSS/JS)
└── backups/          ← your database dumps go here
```

### `.env`

The single configuration file. Every environment-specific value is read from
it — the secret key, the debug flag, allowed hostnames, token lifetimes. The
backend loads it at startup; `docker-compose.yml` reads the same file, so local
development and the container are configured identically.

`DJANGO_SECRET_KEY` is the one value you **must** change before deploying. A
leaked key lets an attacker forge session cookies and password-reset tokens.
Generate one with:

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

### `db/`

The SQLite database file. This is the whole application state: every account,
transaction, budget, debt and asset.

`DB_NAME` in `.env` is a **filename**, and it always resolves inside this
folder. An absolute path is also honoured, which is the escape hatch if you ever
want to mount the file from elsewhere.

SQLite writes a `-wal` and a `-shm` file next to the database while running.
That is normal. **Copy all three together when backing up while the server is
running**, or stop the container first — a copy of just `db.sqlite3` taken
mid-write can be inconsistent.

### `media/`

Files uploaded by users. Currently nothing in the product uploads a file, so
this folder stays empty; it exists because `MEDIA_ROOT` points here and Django
creates it on demand. If a future feature adds an avatar or a receipt image, it
lands here and is served by nginx.

### `static/`

Django's collected static files — the admin site's CSS and JavaScript. This is
**generated**, not authored: the container runs `collectstatic` on every start
and rewrites this folder. Safe to delete; it comes back. It is outside the image
so nginx can serve it directly without asking Django for every file.

### `backups/`

Not used by the application. It exists so there is an obvious place to put
database dumps, and so a backup script has a target that is already excluded
from version control and from the Docker build context.

## Backing up

The database is one file, which is the main advantage of SQLite here.

```bash
# Safe while running: dump through SQLite itself, which takes a consistent
# snapshot and waits for writers instead of copying a half-written file.
docker compose exec api python -c "
import sqlite3, os
src = sqlite3.connect(os.environ['DB_PATH'])
dst = sqlite3.connect('/data/backups/backup.db')
src.backup(dst); dst.close(); src.close()
print('backup written')
"

# Or stop first, then copy — including the -wal and -shm files if present.
docker compose stop api
cp -a data/db/ data/backups/$(date +%Y%m%d-%H%M%S)/
docker compose start api
```

To restore, stop the stack, put the backup file back as `data/db/db.sqlite3`,
and start again. Delete any stale `-wal`/`-shm` files first — a leftover
write-ahead log from a different database file is a corruption risk.

## Permissions

The container runs as a non-root user (UID **1000**). The bind mount means the
host's ownership applies, so on a Linux server this folder must be readable and
writable by that UID:

```bash
sudo chown -R 1000:1000 data/
```

On Docker Desktop for Windows and macOS this is handled by the VM and can be
ignored. If the container exits immediately complaining about permissions, this
is the cause.

## What is deliberately *not* here

- **Application code.** It is baked into the images. A redeploy replaces it.
- **Dependencies.** Same — `node_modules` and the Python packages live in the
  image, not in the volume.
- **The Vite build output.** Compiled into the nginx image at build time.
- **Logs.** The containers log to stdout, which is what `docker compose logs`
  reads. There is no log file to rotate here.
