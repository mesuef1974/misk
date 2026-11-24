"""يبني مصغّرات الصور التي ينقصها مصغّر (ملء رجعي بعد النشر الأول أو بعد استيراد صور)."""

from django.core.management.base import BaseCommand

from apps.designs import thumbnails


class Command(BaseCommand):
    help = "بناء مصغّرات صور العرض الناقصة"

    def handle(self, *args, **options):
        self.stdout.write(f"بُنيت مصغّرات {thumbnails.build_missing()} صورة")
