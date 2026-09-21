# syntax=docker/dockerfile:1
#
# My-Money web — the built SPA, served by nginx alongside the API.
#
# Two stages. The first has Node and the full dependency tree; the second has
# neither, only the compiled output and nginx. That keeps the shipped image
# small and removes the entire build toolchain from the attack surface of
# whatever ends up serving traffic.

# ---------------------------------------------------------------------------
# Stage 1 — build the single-page application
# ---------------------------------------------------------------------------
FROM node:22-alpine AS build

WORKDIR /app

# Dependency manifests first so `npm ci` is cached independently of source
# changes. `ci` rather than `install`: it installs exactly what the lockfile
# pins and fails if the two disagree, which is what makes a build reproducible.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# `npm run build` is `tsc -b && vite build`, so a type error fails the image
# build rather than shipping. That is intentional: a broken bundle should never
# reach a container.
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 — serve
# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine

# The stock configuration only serves a static directory. The application needs
# history fallback for client-side routes and a proxy for /api, /admin and the
# Django static files, so it is replaced wholesale.
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/app.conf

# Only the compiled output crosses the stage boundary.
COPY --from=build /app/dist /usr/share/nginx/html

# The data volume is mounted read-only here: nginx only reads collected static
# files and uploads. Django is the only writer, which is why the API container
# mounts it read-write and this one does not.
VOLUME ["/data"]

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1
