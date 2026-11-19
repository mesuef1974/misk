#!/bin/sh
# أمر بدء خدمة العامل (Celery) على Railway: خدمة ثانية من المستودع نفسه، بلا healthcheck HTTP.
set -eu
[ -n "${REDIS_URL:-}" ] || { echo "::error:: REDIS_URL مطلوب للعامل" >&2; exit 1; }
[ -n "${DATABASE_URL:-}" ] || { echo "::error:: DATABASE_URL مطلوب للعامل" >&2; exit 1; }
export DJANGO_SETTINGS_MODULE=config.settings.production
# الهجرات في preDeploy الويب، والعامل يبدأ بالتوازي معه: لا يأخذ مهمة بشيفرة تسبق مخطط القاعدة.
# `migrate --check` يخرج بغير الصفر ما بقيت هجرة غير مطبَّقة؛ بعد المهلة يخرج العامل فتعيده سياسة الإعادة.
waited=0
until python manage.py migrate --check >/dev/null 2>&1; do
  if [ "$waited" -ge "${WORKER_MIGRATION_WAIT_S:-600}" ]; then
    echo "::error:: هجرات غير مطبَّقة بعد ${waited} ث — العامل لا يبدأ" >&2
    exit 1
  fi
  sleep 10
  waited=$((waited + 10))
done
# قوالب تُصيَّر داخل العامل (PDF مثلًا) تحتاج manifest الثابت في قرصها هي.
python manage.py collectstatic --noinput --clear
exec celery -A config worker \
  --loglevel="${CELERY_LOG_LEVEL:-info}" \
  --concurrency="${CELERY_WORKER_CONCURRENCY:-2}" \
  --max-tasks-per-child="${CELERY_WORKER_MAX_TASKS_PER_CHILD:-100}"
