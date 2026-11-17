#!/bin/bash
# preDeployCommand: مرة واحدة لكل نشر قبل أن تستقبل أي نسخة حركة.
# الهجرات هنا (تكتب في القاعدة المشتركة) لا في start (يُنفَّذ لكل نسخة → سباق DDL).
# فشل أي خطوة يمنع النشر قبل أن يمسّ الحركة الحية.
set -euo pipefail

echo "== Pre-Deploy =="
python manage.py migrate --noinput
python manage.py check --deploy --fail-level ERROR

if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
  # الوجود يُفحص صراحةً (0 موجود، 3 غائب): أي فشل آخر، هنا أو في الإنشاء، يوقف النشر ولا يُبتلع.
  found=0
  python manage.py shell -c "
import os, sys
from django.contrib.auth import get_user_model
User = get_user_model()
name = os.environ['DJANGO_SUPERUSER_USERNAME']
sys.exit(0 if User.objects.filter(**{User.USERNAME_FIELD: name}).exists() else 3)
" || found=$?
  if [ "$found" -eq 0 ]; then
    echo "superuser موجود: تخطٍّ"
  elif [ "$found" -eq 3 ]; then
    python manage.py createsuperuser --noinput --username "$DJANGO_SUPERUSER_USERNAME" \
      --email "${DJANGO_SUPERUSER_EMAIL:-admin@example.com}"
  else
    echo "تعذّر فحص وجود superuser (رمز $found)" >&2
    exit "$found"
  fi
fi

# RLS (اختياري): إن أردت دورًا غير superuser للتطبيق، وفّره هنا بأمر إداري ثم شغّل gunicorn به في release.
echo "== Pre-Deploy complete =="
