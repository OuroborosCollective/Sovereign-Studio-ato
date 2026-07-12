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
COPY app.py .
COPY runner.py .
COPY security_oauth.py .
COPY security_runtime.py .
COPY vector_embedding.py .
COPY r2_storage.py .
COPY knowledge_library.py .
COPY are_inference.py .
COPY agent_runtime/ ./agent_runtime/
COPY migrations ./migrations
COPY migration_ledger_adapter.py ./migration_ledger_adapter.py
COPY auto-migrate.sh /docker-entrypoint.d/auto-migrate.sh
RUN chmod +x /docker-entrypoint.d/auto-migrate.sh

# Expose port
EXPOSE 8787

# Run migrations on startup, then start gunicorn
CMD ["/bin/sh", "-c", "/docker-entrypoint.d/auto-migrate.sh && exec gunicorn --bind 0.0.0.0:8787 --workers 2 --timeout 120 app:app"]
