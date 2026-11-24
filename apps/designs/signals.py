"""رفع صورة عرض أو استبدالها يجدول بناء مصغّراتها في العامل بعد اكتمال المعاملة."""

from __future__ import annotations

from functools import partial

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from . import tasks, thumbnails
from .models import DesignImage


@receiver(post_save, sender=DesignImage, dispatch_uid="designs.build_thumbs_on_save")
def schedule_thumbs(sender, instance: DesignImage, raw: bool = False, **kwargs) -> None:
    if not raw and instance.file and not thumbnails.is_current(instance):
        transaction.on_commit(partial(tasks.build_thumbs_async.delay, instance.pk))
