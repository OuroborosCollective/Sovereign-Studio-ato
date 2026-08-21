FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml /app/
RUN pip install --no-cache-dir "mcp[cli]>=1.13.0" "fastapi>=0.115.0" "uvicorn[standard]>=0.30.0" "httpx>=0.27.0" "pydantic>=2.7.0"

COPY server.py /app/server.py

ENV HOST=0.0.0.0
ENV PORT=8000
EXPOSE 8000

CMD ["python", "server.py"]
