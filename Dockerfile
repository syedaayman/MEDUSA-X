# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1: build the React/Vite client into static assets.
# ---------------------------------------------------------------------------
FROM node:26-alpine AS client
RUN apk upgrade --no-cache
WORKDIR /client
COPY frontend/package.json frontend/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: FastAPI runtime. It serves the API *and* the built client, so the
# browser talks to one origin and no VITE_API_BASE_URL is needed.
# ---------------------------------------------------------------------------
FROM python:3.12-alpine

# The date keys the cache so this layer installs today's OS fixes.
RUN echo "os-refresh 2026-11-25" && apk upgrade --no-cache

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt

# Refresh pip past its advisory and drop the stale wheel bundled inside
# ensurepip, which is unused at runtime but still scanned in the image.
RUN python -m pip install --no-cache-dir --upgrade "pip>=26.1.2" \
    && rm -rf /usr/local/lib/python*/ensurepip/_bundled

RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY --from=client /client/dist ./frontend/dist

RUN adduser -D -u 10001 -h /home/appjet appjet \
    && mkdir -p /app/data/documents /app/sample_data/datasets \
    && chown -R 10001:10001 /app /home/appjet

ENV HOME=/home/appjet \
    PORT=8000 \
    DATABASE_PATH=/app/data/medusa_x.db \
    STORAGE_DIR=/app/data/documents \
    DATASET_DIR=/app/sample_data/datasets

EXPOSE 8000
USER 10001:10001

# Single worker: the SQLite file and the in-process analysis runs are per
# process, so extra workers would not share state.
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
