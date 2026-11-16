#!/bin/bash
# preDeployCommand: مرة واحدة لكل نشر قبل أن تستقبل أي نسخة حركة.
# الهجرات هنا (تكتب في القاعدة المشتركة) لا في start (يُنفَّذ لكل نسخة → سباق DDL).
# فشل أي خطوة يمنع النشر قبل أن يمسّ الحركة الحية.
set -euo pipefail

echo "== Pre-Deploy =="
python manage.py migrate --noinput
python manage.py check --deploy --fail-level ERROR

if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
  python manage.py createsuperuser --noinput --username "$DJANGO_SUPERUSER_USERNAME" \
    --email "${DJANGO_SUPERUSER_EMAIL:-admin@example.com}" 2>/dev/null || echo "superuser موجود — تخطٍّ"
fi

# RLS (اختياري): إن أردت دورًا غير superuser للتطبيق، وفّره هنا بأمر إداري ثم شغّل gunicorn به في release.
echo "== Pre-Deploy complete =="
