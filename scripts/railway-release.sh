#!/bin/bash
# startCommand: لكل نسخة في حاويتها. collectstatic هنا لأن STATIC_ROOT قرص محلي للحاوية،
# وحاوية preDeploy حاوية عابرة منفصلة — ما يُجمَّع هناك لا يصل هنا (درس حادثة 2026-09-17).
set -euo pipefail

python manage.py collectstatic --noinput --clear
exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --threads "${GUNICORN_THREADS:-4}" \
  --timeout 60 \
  --access-logfile - --error-logfile -
