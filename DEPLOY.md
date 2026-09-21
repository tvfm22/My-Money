# Deployment

The stack is two containers and one folder.

```
                    ┌──────────────────────────────┐
   browser ──────►  │  web (nginx, port 8080)      │
                    │    /            → the SPA    │
                    │    /api, /admin → api:8000   │
                    │    /static, /media           │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │  api (gunicorn + Django)     │
                    └──────────────┬───────────────┘
                                   │
                          ./data  ──┴──  the only stateful thing
```

One origin serves everything, which is what the application was built for — in
development Vite proxies `/api` to Django for the same reason. Because of that
there is no CORS configuration to get wrong and no second, untested setup.

## Prerequisites

- Docker Engine 24+ with the Compose v2 plugin (`docker compose`, not
  `docker-compose`).

Check with `docker compose version`. Nothing else is needed on the host — no
Python, no Node, no database server.

## First run

**1. Create the configuration file.**

```bash
cp data/.env.example data/.env
```

**2. Generate a secret key and put it in `data/.env`.**

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

Paste the output as `DJANGO_SECRET_KEY`. Do not skip this: the key signs session
cookies and password-reset tokens, and the shipped placeholder is public.

**3. Set the hostname users will type.**

```bash
# in data/.env
DJANGO_ALLOWED_HOSTS=my-money.example.com
```

**4. Start it.**

```bash
docker compose up -d --build
```

The first build takes a few minutes. When it finishes, open
<http://localhost:8080>.

On first start the API container applies migrations and collects static files,
then gunicorn takes traffic. There is **no demo data** — the database starts
empty. Create an account through the UI, or load the demo data deliberately:

```bash
docker compose run --rm seed
```

## What runs on startup

The API entrypoint does four things, in order:

1. Creates `db/`, `media/`, `static/` and `backups/` under the data folder, and
   fails with a clear message if it cannot write there.
2. Refuses to start if `DJANGO_SECRET_KEY` is unset while `DJANGO_DEBUG` is off.
   Serving traffic with a published signing key is worse than not starting.
3. Applies migrations. Additive only.
4. Collects static files.

Then it starts gunicorn.

## Nothing here destroys data

Worth stating plainly, because it is the thing an operator actually cares about:

- **`docker compose down` does not touch `data/`.** There are no named volumes
  in this stack — `data/` is a bind mount to a directory in the repository, so
  even `down -v` has nothing to remove.
- **Rebuilding or replacing either image does not touch `data/`.** Code lives in
  the images; state lives in the folder. That is the whole point of the split.
- **Migrations are additive.** `migrate` creates and alters; it never drops a
  table or deletes a row. There is no `flush`, no `--run-syncdb` and no reset
  path anywhere in the entrypoint or the compose file.
- **The demo seed never runs on its own.** It is behind a Compose profile
  (`docker compose run --rm seed`), because running it against a live database
  would add a second demo user and a pile of fake transactions.
- **`collectstatic` runs without `--clear`.** That flag wipes `STATIC_ROOT`
  first, and `STATIC_ROOT` is a directory inside the operator-controlled data
  volume — one misconfigured variable would turn a deploy into data loss.

## Nothing heavy reaches the server

The repository carries a 260 MB `frontend/node_modules` tree and a 61 MB Python
virtualenv. Neither is in version control, and neither is in either image. The
question comes up often enough to answer it here rather than in a comment.

`frontend/Dockerfile` is two stages. The first has Node and installs the
dependency tree; the second starts from a clean `nginx:alpine` and receives
exactly one thing across the boundary:

```dockerfile
COPY --from=build /app/dist /usr/share/nginx/html
```

So the shipped web image is nginx plus the built bundle — no Node, no toolchain,
no dependency tree. `frontend/.dockerignore` goes a step further and keeps
`node_modules/` out of the build context altogether, so the tree is not even
sent to the daemon. Nothing in `docker-compose.yml` runs `npm` at runtime, and
`backend/Dockerfile` installs from `requirements.txt` into the image rather than
mounting a virtualenv from the host.

This is asserted rather than merely intended.
`frontend/src/test/deploy-hygiene.test.ts` fails if the runtime stage gains a
whole-tree `COPY`, a Node base image or a package-manager command, or if either
ignore file stops excluding `node_modules`:

```bash
cd frontend && npm test
```

Because both directories are rebuilt from their lockfiles — `npm ci` and
`pip install -r requirements.txt` — deleting either one costs a download, never
a deployment.

## Day-to-day operations

```bash
docker compose logs -f api        # follow API logs
docker compose logs -f web        # follow nginx logs
docker compose ps                 # what is running and healthy
docker compose restart api        # restart one service
docker compose down               # stop (data untouched)
docker compose up -d --build      # rebuild and restart after a code change
```

### Running management commands

The entrypoint runs migrations and collectstatic first, then executes whatever
you give it:

```bash
docker compose run --rm api python manage.py createsuperuser
docker compose run --rm api python manage.py shell
docker compose run --rm api python manage.py migrate --check
```

To skip the startup steps for a one-off command:

```bash
docker compose run --rm -e RUN_MIGRATIONS=false -e RUN_COLLECTSTATIC=false \
  api python manage.py shell
```

### Running the test suites

```bash
docker compose run --rm test          # backend, 315 tests
cd frontend && npm test               # frontend, 180 tests
```

The `test` profile uses a throwaway data directory, so it never reads or writes
`data/`.

## Backing up

The database is a single file, which is the main practical advantage of SQLite.

```bash
# Consistent snapshot while the server keeps running. Uses SQLite's own backup
# API, which waits for writers instead of copying a half-written file.
docker compose exec api python -c "
import sqlite3, os
src = sqlite3.connect(os.environ['DB_PATH'] if 'DB_PATH' in os.environ else '/data/db/db.sqlite3')
dst = sqlite3.connect('/data/backups/backup.db')
src.backup(dst); dst.close(); src.close()
print('written to data/backups/backup.db')
"
```

Or stop first and copy the directory, which also captures uploads:

```bash
docker compose stop api
cp -a data/db/ "data/backups/$(date +%Y%m%d-%H%M%S)/"
docker compose start api
```

To restore: stop the stack, put the backup back as `data/db/db.sqlite3`, delete
any stale `-wal` and `-shm` files, and start again.

## Deploying for real

**Port 80.** The stack publishes on 8080 by default so it can be tried without
colliding with anything already listening. For a real deployment:

```bash
WEB_PORT=80 docker compose up -d
```

**TLS.** Terminate HTTPS in front — a cloud load balancer, Caddy, or Traefik.
Two settings must match that decision:

```bash
# in data/.env
SECURE_SSL_REDIRECT=True          # ONLY once HTTPS actually terminates in front
DJANGO_ALLOWED_HOSTS=your.domain  # the name users type, not the container name
```

Turning `SECURE_SSL_REDIRECT` on without TLS in front produces an infinite
redirect loop. That is why it ships as `False`.

**Workers.** `GUNICORN_WORKERS` defaults to 3. SQLite serialises writes, so
raising it buys read concurrency, not write throughput. `SQLITE_JOURNAL_MODE=WAL`
is on by default, which is what keeps readers from blocking behind a writer.

**Permissions.** The container runs as UID 1000. On a Linux host:

```bash
sudo chown -R 1000:1000 data/
```

Docker Desktop on Windows and macOS handles this in its VM.

## Troubleshooting

**`FATAL: cannot create directories under /data`**
The bind mount is not writable by UID 1000. Run the `chown` above.

**`FATAL: DJANGO_SECRET_KEY is not set while DJANGO_DEBUG is off`**
`data/.env` is missing or has no key. See "First run".

**502 from nginx**
The API is not healthy. `docker compose logs api` — usually migrations failing
or a bad database path.

**`DisallowedHost`**
`DJANGO_ALLOWED_HOSTS` does not contain the name in the address bar. nginx
forwards the original `Host` header, so this must be the public hostname.

**The page loads but every request 404s**
The SPA is served but `/api` is not reaching Django. Confirm with
`docker compose exec web wget -qO- http://api:8000/api/health/`.

**Changed the code but the browser shows the old version**
`index.html` is served with `no-store`, so a plain reload should pick up a new
deploy. If it does not, the image was not rebuilt — `docker compose up -d --build`.

## Files

| File | Purpose |
| --- | --- |
| `docker-compose.yml` | The stack: `api`, `web`, and the opt-in `seed` and `test` profiles |
| `backend/Dockerfile` | Python image, non-root, gunicorn |
| `backend/entrypoint.sh` | Startup: data dir, secret check, migrate, collectstatic, exec |
| `backend/.dockerignore` | Keeps secrets, databases and `__pycache__` out of the image |
| `frontend/Dockerfile` | Two stages: Node build, then nginx runtime |
| `frontend/nginx.conf` | SPA fallback, `/api` and `/admin` proxy, static and media |
| `frontend/.dockerignore` | Keeps `node_modules` and `dist` out of the build context |
| `data/README.md` | What lives in the data folder, and how to back it up |
| `.gitignore` | Excludes `data/`, secrets and databases from version control |
