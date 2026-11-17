# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow", "numpy"]
# ///
"""يولّد شعار الشريط الحريري (PNG) لكل سمة من العشر من الأصل العودي المعتمد.

الأصل: brand/misk/misk-logo-ribbon.png (شفاف، عودي #68112F وشامبانيا). لكل سمة يُعاد تلوين الشريط وكلمة DESIGN
بلون السمة من tokens.css (--palette-<id>) مع إبقاء الظلال واللمعة، والطيّات الشامبانيا كما هي. العودي نسخة الأصل.

التشغيل (Pillow وnumpy ليستا من اعتماديات المشروع، فيجلبهما uv لهذا السكربت وحده):
    uv run scripts/build_theme_logos.py
"""

from __future__ import annotations

import colorsys
import re
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "brand" / "misk" / "misk-logo-ribbon.png"
TOKENS = ROOT / "frontend" / "src" / "static" / "brand" / "tokens.css"
OUT = ROOT / "frontend" / "src" / "static" / "brand" / "logo"
SOURCE_PALETTE = "oud"
WIDTH = 640
# مسافة الصبغة (بالدرجات) عن العودي: دون الأولى شريط يُلوَّن كله، وفوق الثانية طيّة شامبانيا تبقى.
HUE_INNER, HUE_OUTER = 22.0, 38.0


def palette_colors() -> dict[str, str]:
    return dict(re.findall(r"--palette-([a-z-]+):\s*(#[0-9A-Fa-f]{6})", TOKENS.read_text(encoding="utf-8")))


def hsv_of(hex_color: str) -> tuple[float, float, float]:
    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hsv(r, g, b)


def rgb_to_hsv(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    v = rgb.max(axis=-1)
    c = v - rgb.min(axis=-1)
    s = np.divide(c, v, out=np.zeros_like(v), where=v > 0)
    safe = np.where(c > 0, c, 1.0)
    h = np.select(
        [c == 0, v == r, v == g],
        [np.zeros_like(v), ((g - b) / safe) % 6, (b - r) / safe + 2],
        default=(r - g) / safe + 4,
    )
    return h / 6, s, v


def hsv_to_rgb(h: np.ndarray, s: np.ndarray, v: np.ndarray) -> np.ndarray:
    k = (np.stack([5.0 + h * 6, 3.0 + h * 6, 1.0 + h * 6], axis=-1)) % 6
    return v[..., None] * (1 - s[..., None] * np.clip(np.minimum(k, 4 - k), 0, 1))


def recolor(rgba: np.ndarray, source_hex: str, target_hex: str) -> np.ndarray:
    """ينقل لون الشريط من لون الأصل إلى لون السمة: الصبغة تُستبدل، والتشبّع والإضاءة بمنحنى أُسّي
    يطابق اللون المسطّح بالمسطّح ويبقي الأسود والأبيض في مكانهما فتبقى الظلال واللمعة."""
    rgb = rgba[..., :3].astype(np.float64) / 255
    h, s, v = rgb_to_hsv(rgb)
    sh, ss, sv = hsv_of(source_hex)
    th, ts, tv = hsv_of(target_hex)
    distance = np.abs(((h - sh + 0.5) % 1) - 0.5) * 360
    weight = np.clip((HUE_OUTER - distance) / (HUE_OUTER - HUE_INNER), 0, 1)
    weight = weight * weight * (3 - 2 * weight)
    new_s = np.power(s, np.log(max(ts, 1e-3)) / np.log(ss))
    new_v = np.power(v, np.log(tv) / np.log(sv))
    tinted = hsv_to_rgb(np.full_like(h, th), new_s, new_v)
    out = rgba.copy()
    out[..., :3] = np.rint((rgb + (tinted - rgb) * weight[..., None]) * 255).astype(np.uint8)
    return out


def main() -> None:
    colors = palette_colors()
    source = Image.open(SOURCE).convert("RGBA")
    source = source.crop(source.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox())
    source = source.resize((WIDTH, round(source.height * WIDTH / source.width)), Image.Resampling.LANCZOS)
    pixels = np.array(source)
    OUT.mkdir(parents=True, exist_ok=True)
    for palette, color in colors.items():
        result = pixels if palette == SOURCE_PALETTE else recolor(pixels, colors[SOURCE_PALETTE], color)
        Image.fromarray(result, "RGBA").save(OUT / f"misk-{palette}.png", optimize=True)
        print(palette, color)


if __name__ == "__main__":
    main()
