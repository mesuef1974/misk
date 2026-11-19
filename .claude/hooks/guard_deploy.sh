#!/usr/bin/env bash
# PreToolUse (Bash|PowerShell): يشغّل guard_deploy.py ببايثون يعمل فعلًا، كما يفعل guard_git.sh.
# رمز 2 من الحارس يمنع الأمر؛ وإن لم يوجد بايثون يعمل فرمز 2 أيضًا: حارس الدمج والنشر لا يُفتح بغيابه.
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for py in python3 python "py -3"; do
  # shellcheck disable=SC2086
  if $py -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
    # shellcheck disable=SC2086
    exec $py "$here/guard_deploy.py"
  fi
done
echo "guard_deploy: لا بايثون 3.9+ يعمل — يُمنع الأمر احتياطًا" >&2
exit 2
