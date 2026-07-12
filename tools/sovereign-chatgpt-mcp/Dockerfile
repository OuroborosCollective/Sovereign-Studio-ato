FROM node:22-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       git \
       python3 \
       python3-pip \
       python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv \
    && corepack enable

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY policy.py runtime.py database.py broker_client.py self_heal.py server.py /app/

RUN useradd --create-home --uid 10001 sovereign \
    && mkdir -p /opt/sovereign-chatgpt-tools/workspaces \
    && chown -R sovereign:sovereign /app /opt/sovereign-chatgpt-tools

USER sovereign
EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import socket; s=socket.create_connection(('127.0.0.1',8090),3); s.close()" || exit 1

CMD ["python", "server.py"]
