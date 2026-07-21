FROM node:22-bookworm-slim AS admin-web

ARG SOVEREIGN_SOURCE_REVISION=unverified
ENV VITE_BASE_PATH=/admin/ \
    VITE_ADMIN_API_BASE= \
    VITE_SOVEREIGN_SOURCE_REVISION=${SOVEREIGN_SOURCE_REVISION}

WORKDIR /workspace
RUN corepack enable && corepack prepare pnpm@9.12.2 --activate

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile --ignore-scripts

COPY . .
RUN pnpm run build:web \
    && test -f /workspace/dist/index.html \
    && grep -Eq 'src="/admin/assets/[^"]+\.js"' /workspace/dist/index.html \
    && find /workspace/dist/assets -type f -name '*.js' -size +0c -print -quit | grep -q .

FROM python:3.11-slim

ARG SOVEREIGN_SOURCE_REVISION=unverified
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SOVEREIGN_SOURCE_REVISION=${SOVEREIGN_SOURCE_REVISION} \
    SOVEREIGN_RUNTIME_ENVIRONMENT=production \
    SOVEREIGN_ADMIN_DIST_ROOT=/app/admin-dist

WORKDIR /app

# Install system dependencies
# - postgresql-client: for database migrations
# - git: for workspace repository cloning by sovereign-local-runner
# No external agent runtime is installed; sovereign-local-runner is the only live executor.
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching.
COPY scripts/sovereign-backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code from the canonical repository-root build context.
COPY scripts/sovereign-backend/*.py ./
COPY scripts/sovereign-backend/enterprise_platform/ ./enterprise_platform/
COPY scripts/sovereign-backend/agent_runtime/ ./agent_runtime/
COPY scripts/sovereign-backend/migrations ./migrations
COPY scripts/sovereign-backend/auto-migrate.sh /docker-entrypoint.d/auto-migrate.sh
COPY --from=admin-web /workspace/dist /app/admin-dist
RUN chmod +x /docker-entrypoint.d/auto-migrate.sh \
    && test -f /app/admin-dist/index.html \
    && rm -f /app/enterprise_admin_ui.py

# Expose only the container port. Compose owns the loopback-only host binding.
EXPOSE 8787
STOPSIGNAL SIGTERM

# Run migrations on startup, then start bounded threaded gunicorn workers.
# Agents SDK requests may hold one request slot for a complete double loop, so
# status and health routes need independent capacity instead of two sync slots.
CMD ["/bin/sh", "-c", "/docker-entrypoint.d/auto-migrate.sh && exec gunicorn --bind 0.0.0.0:8787 --worker-class gthread --workers \"${SOVEREIGN_WEB_WORKERS:-2}\" --threads \"${SOVEREIGN_WEB_THREADS:-4}\" --timeout 120 app:app"]