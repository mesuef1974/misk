"""أطوال الأعمدة من النماذج نفسها، فلا يُكرَّر الرقم في الخدمات والمخططات."""

from __future__ import annotations

from django.db import models


def column_length(model: type[models.Model], field: str) -> int:
    length = getattr(model._meta.get_field(field), "max_length", None)
    if length is None:
        raise ValueError(f"{model.__name__}.{field} بلا max_length")
    return length
