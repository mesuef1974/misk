"""يسخّن مصغّرات صور التصاميم المنشورة في الذاكرة المؤقتة (بعد مسح Redis أو استيراد صور)."""

from django.core.management.base import BaseCommand

from apps.designs import tasks


class Command(BaseCommand):
    help = "تسخين مصغّرات صور التصاميم المنشورة"

    def handle(self, *args, **options):
        made = tasks.warm_images_async()
        self.stdout.write(f"وُلِّد {made} مصغّرًا")
