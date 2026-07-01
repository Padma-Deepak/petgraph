FROM python:3.13-slim

# curl is needed for the compose health check
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies in a separate layer so they are cached
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Source code is bind-mounted at runtime for live reload.
# This COPY is only used when building the image without a bind-mount (e.g. CI).
COPY . .

# Persistent data directory (SQLite + Cognee system files).
# Mapped to a named Docker volume at runtime via compose.
RUN mkdir -p /data

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
