# المرحلة 1: بناء واجهة Vue إلى frontend_dist (لا Node في صورة الإنتاج).
FROM node:22-alpine AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# المرحلة 2: اعتماديات بايثون في venv منفصل.
FROM python:3.12-slim-bookworm AS builder
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /build
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# المرحلة 3: صورة التشغيل، مستخدم غير جذر، بلا مترجمات.
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    PATH="/opt/venv/bin:$PATH"
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 wget && rm -rf /var/lib/apt/lists/*
RUN groupadd -r app && useradd -r -g app -d /app app && mkdir -p /app/staticfiles /app/media && chown -R app:app /app
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
# الشيفرة ملك root ولا يكتبها مستخدم التشغيل؛ staticfiles وmedia وحدهما له (collectstatic في العامل والإصدار).
COPY . .
COPY --from=frontend /build/frontend_dist ./frontend_dist
RUN mkdir -p /app/staticfiles /app/media && chown -R app:app /app/staticfiles /app/media
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD wget -qO- "http://localhost:${PORT:-8000}/health/" || exit 1
CMD ["bash", "scripts/railway-release.sh"]
