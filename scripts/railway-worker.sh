#!/bin/sh
# أمر بدء خدمة العامل (Celery) على Railway: خدمة ثانية من المستودع نفسه، بلا healthcheck HTTP.
set -eu
[ -n "${REDIS_URL:-}" ] || { echo "::error:: REDIS_URL مطلوب للعامل" >&2; exit 1; }
[ -n "${DATABASE_URL:-}" ] || { echo "::error:: DATABASE_URL مطلوب للعامل" >&2; exit 1; }
export DJANGO_SETTINGS_MODULE=config.settings.production
# الهجرات في preDeploy الويب، والعامل يبدأ بالتوازي معه: لا يأخذ مهمة بشيفرة تسبق مخطط القاعدة.
# pending_migrations: 0 مطبَّقة، 3 معلّقة (ينتظر)، وغيرهما عطل (قاعدة أو إعداد) يُطبع سببه ولا يُسمّى «هجرات معلّقة» (د8).
# بعد المهلة يخرج العامل فتعيده سياسة الإعادة، ومعه آخر سبب.
waited=0
while :; do
  rc=0
  out=$(python manage.py pending_migrations 2>&1) || rc=$?
  [ "$rc" -eq 0 ] && break
  if [ "$rc" -eq 3 ]; then
    reason="هجرات غير مطبَّقة: $out"
  else
    reason="تعذّر فحص الهجرات (رمز $rc): $(printf '%s\n' "$out" | tail -n 5)"
  fi
  if [ "$waited" -ge "${WORKER_MIGRATION_WAIT_S:-600}" ]; then
    echo "::error:: العامل لا يبدأ بعد ${waited} ث — $reason" >&2
    exit 1
  fi
  echo "انتظار ${waited} ث — $reason" >&2
  sleep 10
  waited=$((waited + 10))
done
# قوالب تُصيَّر داخل العامل (PDF مثلًا) تحتاج manifest الثابت في قرصها هي.
python manage.py collectstatic --noinput --clear
exec celery -A config worker \
  --loglevel="${CELERY_LOG_LEVEL:-info}" \
  --concurrency="${CELERY_WORKER_CONCURRENCY:-2}" \
  --max-tasks-per-child="${CELERY_WORKER_MAX_TASKS_PER_CHILD:-100}"
