"""هل بقيت هجرات غير مطبَّقة؟ رمز الخروج يميّز الانتظار من العطل (د8).

`migrate --check` يخرج بـ1 للهجرات المعلّقة ولانقطاع القاعدة وخطأ الإعداد معًا، فلا يعرف
العامل أيّها ينتظر. هنا: 0 لا شيء معلّق، 3 هجرات معلّقة، وأي عطل استثناء يطبعه Django
ويخرج بـ1 (كما في فحص superuser في railway-predeploy.sh).
"""

from __future__ import annotations

import sys

from django.core.management.base import BaseCommand
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.executor import MigrationExecutor

PENDING_EXIT = 3


class Command(BaseCommand):
    help = "يخرج بـ0 إن طُبّقت الهجرات كلها، وبـ3 إن بقي منها شيء؛ وأي عطل يخرج بـ1 ومعه سببه."

    def handle(self, *args, **options):
        connection = connections[DEFAULT_DB_ALIAS]
        connection.prepare_database()
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if plan:
            names = ", ".join(f"{migration.app_label}.{migration.name}" for migration, _ in plan)
            self.stdout.write(f"{len(plan)} هجرة غير مطبَّقة: {names}")
            sys.exit(PENDING_EXIT)
        self.stdout.write("الهجرات كلها مطبَّقة")
