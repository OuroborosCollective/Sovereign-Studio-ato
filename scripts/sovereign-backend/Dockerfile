FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
# - postgresql-client: for database migrations
# - git: for workspace repository cloning (sovereign-local-runner)
# Note: OpenHands is NOT installed - sovereign-local-runner is the primary executor
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .
COPY security_oauth.py .
COPY agent_runtime/ ./agent_runtime/
COPY migrations ./migrations
COPY auto-migrate.sh /docker-entrypoint.d/auto-migrate.sh
RUN chmod +x /docker-entrypoint.d/auto-migrate.sh

# Expose port
EXPOSE 8787

# Run migrations on startup, then start gunicorn
CMD ["/bin/sh", "-c", "/docker-entrypoint.d/auto-migrate.sh && exec gunicorn --bind 0.0.0.0:8787 --workers 2 --timeout 120 app:app"]
