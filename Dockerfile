# --- website
FROM node:24-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# --- app
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    MD_DATA_DIR=/data MD_INBOX_DIR=/data/inbox MD_WEB_DIR=/app/web/build TZ=America/New_York
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils tesseract-ocr tzdata \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY app/ app/
COPY ingest/ ingest/
COPY config/ config/
COPY --from=web /web/build web/build
RUN useradd --uid 1000 --create-home md && mkdir -p /data && chown md /data
USER md
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
# No --proxy-headers: the app never needs the client's IP, and the raw peer
# address is what MD_TRUSTED_PROXIES is checked against.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
