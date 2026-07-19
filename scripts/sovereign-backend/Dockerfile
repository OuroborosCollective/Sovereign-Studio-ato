FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
# - postgresql-client: for database migrations
# - git: for workspace repository cloning by sovereign-local-runner
# No external agent runtime is installed; sovereign-local-runner is the only live executor.
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY *.py ./
COPY agent_runtime/ ./agent_runtime/
COPY migrations ./migrations
COPY auto-migrate.sh /docker-entrypoint.d/auto-migrate.sh
RUN chmod +x /docker-entrypoint.d/auto-migrate.sh

# Expose port
EXPOSE 8787

# Run migrations on startup, then start bounded threaded gunicorn workers.
# Agents SDK requests may hold one request slot for a complete double loop, so
# status and health routes need independent capacity instead of two sync slots.
CMD ["/bin/sh", "-c", "/docker-entrypoint.d/auto-migrate.sh && exec gunicorn --bind 0.0.0.0:8787 --worker-class gthread --workers \"${SOVEREIGN_WEB_WORKERS:-2}\" --threads \"${SOVEREIGN_WEB_THREADS:-4}\" --timeout 120 app:app"]
