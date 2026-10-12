# Two images are built from this file (see docker-compose.yml):
#   web – Caddy, serving the built frontend and forwarding /api
#   api – the Flask backend under gunicorn

FROM node:22-slim AS frontend
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM caddy:2 AS web
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=frontend /app/dist /srv

FROM python:3.13-slim AS api
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/server.py ./
# The database and its backups live on a volume mounted at /data
ENV LAUNDRY_DATABASE=/data/laundry.db \
    LAUNDRY_BACKUP_DIR=/data/backups
EXPOSE 8000
# --preload creates the app, and with it the database tables, once rather
# than in every worker at the same time
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--preload", "server:create_app()"]
