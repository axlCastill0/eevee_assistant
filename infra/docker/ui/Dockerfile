# ---------------------------------------------------------------------------
# Stage 1 — build the static bundle
# ---------------------------------------------------------------------------
# Node is a BUILD-time dependency only. Nothing from this stage ships; the
# runtime image is nginx plus a directory of files. That is the whole reason
# for choosing a static build over SSR: no Node process competing with the
# 1.5B model and Chromium for memory on the Pi.
FROM node:22-alpine AS build

WORKDIR /build

# Copy manifests first so `npm ci` is cached independently of source changes.
COPY apps/ui/package.json apps/ui/package-lock.json* ./

# `npm ci` when a lockfile exists (reproducible), otherwise fall back to
# install so a fresh checkout without one still builds.
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY apps/ui/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 — serve
# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine

# The official entrypoint runs envsubst over every *.template in this directory
# and writes the result to /etc/nginx/conf.d/.
COPY infra/docker/ui/nginx.conf.template /etc/nginx/templates/default.conf.template

COPY --from=build /build/dist /usr/share/nginx/html

# Restrict substitution to our own variables. Without this, envsubst would also
# try to expand nginx runtime variables such as $host and $uri and blank them,
# because they are not set in the environment.
ENV NGINX_ENVSUBST_FILTER="^(API_KEY|BACKEND_ORIGIN)$"

# Overridable via compose; host networking means the backend is on loopback.
ENV BACKEND_ORIGIN="http://127.0.0.1:8000"

EXPOSE 8080

# Default CMD from the base image starts nginx after the template pass.
