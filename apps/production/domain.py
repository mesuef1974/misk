"""ترتيب القطع على الألواح: خوارزمية رفوف (shelf) خالصة بلا Django.

القطع تُرتَّب تنازليًّا بالارتفاع ثم تُصفّ من اليسار إلى اليمين في رفوف، وكل لوح يُفتح حين يمتلئ سابقه.
الخوارزمية حتمية: المدخل نفسه يعطي الترتيب نفسه. الأبعاد بعُشر المليمتر أعدادًا صحيحة لتفادي أخطاء الكسور.
"""

from __future__ import annotations

from dataclasses import dataclass


class PackingError(ValueError):
    """قطعة لا يسعها اللوح."""


@dataclass(frozen=True)
class Piece:
    key: tuple[int, int]  # (معرّف البند، رقم النسخة)
    width: int
    height: int


@dataclass(frozen=True)
class Placed:
    key: tuple[int, int]
    sheet: int
    x: int
    y: int
    width: int
    height: int


def pack(pieces: list[Piece], *, sheet_width: int, sheet_height: int, margin: int, gap: int) -> list[Placed]:
    usable_right = sheet_width - margin
    usable_bottom = sheet_height - margin
    for piece in pieces:
        if piece.width <= 0 or piece.height <= 0:
            raise PackingError(f"القطعة {piece.key} بلا أبعاد")
        if margin + piece.width > usable_right or margin + piece.height > usable_bottom:
            raise PackingError(f"القطعة {piece.key} أكبر من اللوح بعد الهامش")

    ordered = sorted(pieces, key=lambda p: (-p.height, -p.width, p.key))
    placed: list[Placed] = []
    sheet = 0
    x = y = margin
    shelf_height = 0
    for piece in ordered:
        if x + piece.width > usable_right:  # الرف امتلأ
            x = margin
            y += shelf_height + gap
            shelf_height = 0
        if y + piece.height > usable_bottom:  # اللوح امتلأ
            sheet += 1
            x = y = margin
            shelf_height = 0
        placed.append(Placed(piece.key, sheet, x, y, piece.width, piece.height))
        x += piece.width + gap
        shelf_height = max(shelf_height, piece.height)
    return placed
