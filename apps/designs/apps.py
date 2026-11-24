from django.apps import AppConfig


class DesignsConfig(AppConfig):
    name = "apps.designs"
    verbose_name = "التصاميم الجاهزة"

    def ready(self) -> None:
        from . import signals  # noqa: F401, PLC0415 — تسجيل المستقبِلات
