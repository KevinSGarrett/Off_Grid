# syntax=docker/dockerfile:1.7
FROM node:22-alpine AS web-build
WORKDIR /src/apps/web
COPY apps/web/package*.json ./
# Production builds are deliberately fail-closed until a real npm lockfile exists.
# Wave 17's current sandbox cannot reach the npm registry, so no synthetic lockfile is fabricated.
RUN test -f package-lock.json || (echo 'FATAL: apps/web/package-lock.json is required; generate and verify it with npm install/ci in a network-capable clean environment.' >&2; exit 74)
RUN npm ci --no-audit --no-fund
COPY apps/web ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/apps/api \
    RUNTIME_DB_PATH=/app/data/private/offgrid.db \
    DEMO_SEED_DB=/app/data/demo_seed/offgrid_demo_seed.db \
    DEMO_RESET_ON_START=true
WORKDIR /app
COPY requirements.lock ./requirements.lock
RUN python -m pip install --no-cache-dir -r requirements.lock
COPY apps/api ./apps/api
COPY config ./config
COPY prompts ./prompts
COPY data/demo_seed/offgrid_demo_seed.db ./data/demo_seed/offgrid_demo_seed.db
COPY --from=web-build /src/apps/web/dist ./apps/web/dist
COPY docker/entrypoint.sh /entrypoint.sh
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data/private \
    && chown -R appuser:appuser /app /entrypoint.sh \
    && chmod 0555 /entrypoint.sh
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)" || exit 1
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
