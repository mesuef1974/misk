"""تبنّي الهوية: ما في brand/misk/identity/ADOPTION.yaml مطبَّق في الواجهة، ونسخ الواجهة مطابقة لأصل الهوية."""

import re
from pathlib import Path

import pytest
from django.conf import settings

ROOT = Path(settings.BASE_DIR)
IDENTITY = ROOT / "brand" / "misk" / "identity"
PLATFORM_FONTS = ROOT / "brand" / "misk" / "fonts"
STATIC_BRAND = ROOT / "frontend" / "src" / "static" / "brand"

# ADOPTION.yaml مولَّد ببنية ثابتة؛ يُقرأ token_map بنمط نصي حتى لا يحتاج الاختبار مكتبة YAML.
_ENTRY = re.compile(
    r"- app_var: (?P<var>--[\w-]+)\s+light:.*?value: '(?P<light>#[0-9a-fA-F]{6})'\s+dark:.*?value: '(?P<dark>#[0-9a-fA-F]{6})'",
    re.S,
)
# المتغيرات التي لا تتبع السمة: طرفها الليلي لون خام آخر المعامِلين.
_TOKEN = re.compile(r"(--[\w-]+):\s*light-dark\((.+),\s*(#[0-9a-fA-F]{6})\);")
_PALETTE_VAR = re.compile(r"--palette-([\w-]+):\s*(#[0-9a-fA-F]{6});")


def _token_map() -> dict[str, tuple[str, str]]:
    text = (IDENTITY / "ADOPTION.yaml").read_text(encoding="utf-8")
    block = text.split("token_map:", 1)[1].split("\nchecks:", 1)[0]
    return {m["var"]: (m["light"].lower(), m["dark"].lower()) for m in _ENTRY.finditer(block)}


def _tokens_text() -> str:
    return (STATIC_BRAND / "tokens.css").read_text(encoding="utf-8")


def _tokens_css() -> dict[str, tuple[str, str]]:
    return {var: (light.strip().lower(), dark.lower()) for var, light, dark in _TOKEN.findall(_tokens_text())}


def _palettes() -> dict[str, str]:
    return {name: value.lower() for name, value in _PALETTE_VAR.findall(_tokens_text())}


def _luminance(color: str) -> float:
    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


# لكل سمة ليلها ونهارها (قرار المالك 2026-11-17): الخلفية والسطح والحد والتمييز تتبع السمة في الوضعين.
# ما لا يتبعها ليلًا (الحبر والخافت والخطر) يبقى على قيمة token_map الليلية حرفيًّا.
NIGHT_INK = "#f1f7f4"
NIGHT_MUTED = "#b5bdb9"


def test_palette_free_night_tokens_match_adoption_token_map():
    expected = _token_map()
    tokens = _tokens_text()
    # الخريطة تُقرأ كاملة: سبعة متغيرات لونية في الإصدار المعتمد، وأقل من ذلك خلل في القراءة لا نجاح.
    assert len(expected) >= 7
    assert expected["--ink"][1] == NIGHT_INK
    assert expected["--muted"][1] == NIGHT_MUTED
    assert f"--ink: light-dark(var(--day-ink), {NIGHT_INK});" in tokens
    assert f"--muted: light-dark(var(--day-muted), {NIGHT_MUTED});" in tokens
    assert _tokens_css()["--risk"][1] == expected["--risk"][1]


PALETTE_ORDER = [
    "navy",
    "royal-blue",
    "teal",
    "emerald",
    "olive",
    "purple",
    "rose",
    "chocolate",
    "black",
    "oud",
]


def test_ten_day_palettes_are_declared_once_and_named_alike():
    # عشر سمات نهارية بترتيب جدول الهوية؛ الأسماء واحدة في الألوان والواجهة وسكربت ما قبل الرسم.
    tokens = _tokens_text()
    assert list(_palettes()) == PALETTE_ORDER
    for name in PALETTE_ORDER:
        assert re.search(
            rf'\[data-palette="{name}"\]\s*{{\s*--day-color:\s*var\(--palette-{name}\);', tokens
        ), name
    domain = (ROOT / "frontend" / "src" / "domain" / "theme.ts").read_text(encoding="utf-8")
    assert re.findall(r'{ id: "([\w-]+)", label: "[^"]+" }', domain) == PALETTE_ORDER
    init = (ROOT / "apps" / "core" / "static" / "core" / "theme-init.js").read_text(encoding="utf-8")
    listed = re.search(r"var palettes = \[([^\]]+)\];", init)
    assert listed and re.findall(r'"([\w-]+)"', listed.group(1)) == PALETTE_ORDER
    # العودي افتراضي في المواضع الثلاثة.
    assert "--day-color: var(--palette-oud);" in tokens.split("[data-palette=", 1)[0]
    assert 'DEFAULT_PALETTE: Palette = "oud"' in domain
    assert 'var palette = "oud";' in init


def _mix(a: str, share: float, b: str) -> str:
    """color-mix(in srgb, a share%, b) كما يحسبه المتصفح."""
    pairs = zip(
        (int(a[i : i + 2], 16) for i in (1, 3, 5)), (int(b[i : i + 2], 16) for i in (1, 3, 5)), strict=True
    )
    return "#" + "".join(f"{round(x * share + y * (1 - share)):02x}" for x, y in pairs)


def _rule_values(selector: str) -> dict[str, str]:
    """القيم الخام (#rrggbb) في قاعدة واحدة من tokens.css."""
    rule = re.search(rf"(?m)^{re.escape(selector)}\s*{{([^}}]*)}}", _tokens_text())
    assert rule, selector
    return {
        var: value.lower() for var, value in re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6});", rule.group(1))
    }


def _day(name: str) -> dict[str, str]:
    """ألوان نهار السمة كما يحسبها المتصفح: قاعدة السمة، وما لم تذكره فمن الاشتقاق العام [data-palette]."""
    color = _palettes()[name]
    own = _rule_values(f'[data-palette="{name}"]')
    generic = _rule_values("[data-palette]")
    bg = own["--day-bg"]
    derived = {
        "--day-surface": _mix("#ffffff", 0.60, bg),
        "--day-raised": _mix(color, 0.06, bg),
        "--day-line": _mix(generic["--day-ink"], 0.14, bg),
        "--day-soft": _mix(color, 0.10, bg),
    }
    return {"--day-color": color, "--day-accent": color, **generic, **derived, **own}


def test_generic_day_derivation_is_the_one_computed_here():
    # الاشتقاق في _day هو ما في tokens.css حرفيًّا: إن تغيّرت نسبة هناك فشل هذا الاختبار حتى تُحدَّث هنا.
    tokens = _tokens_text()
    for line in (
        "--day-surface: color-mix(in srgb, #ffffff 60%, var(--day-bg));",
        "--day-raised: color-mix(in srgb, var(--day-color) 6%, var(--day-bg));",
        "--day-line: color-mix(in srgb, #17201d 14%, var(--day-bg));",
        "--day-soft: color-mix(in srgb, var(--day-color) 10%, var(--day-bg));",
        "--bg: light-dark(var(--day-bg), var(--night-bg));",
        "--surface: light-dark(var(--day-surface), color-mix(in srgb, #ffffff 7%, var(--night-bg)));",
        "--ink: light-dark(var(--day-ink), #f1f7f4);",
        "--muted: light-dark(var(--day-muted), #b5bdb9);",
        "--line: light-dark(var(--day-line), color-mix(in srgb, #ffffff 24%, var(--night-bg)));",
        "--accent: light-dark(var(--day-accent), var(--night-accent));",
        "--raised: light-dark(var(--day-raised), color-mix(in srgb, #ffffff 13%, var(--night-bg)));",
        "--brand-soft: light-dark(var(--day-soft), color-mix(in srgb, var(--night-accent) 12%, var(--night-bg)));",
        "--on-accent: light-dark(#ffffff, var(--night-bg));",
    ):
        assert line in tokens, line
    # القاعدة العامة تسبق قواعد السمات: التخصيص نفسه، فالأخيرة تغلب.
    assert tokens.index("[data-palette] {") < tokens.index('[data-palette="navy"]')


@pytest.mark.parametrize("name", PALETTE_ORDER)
def test_each_palette_reaches_contrast_in_day_and_night(name):
    day = _day(name)
    night = _rule_values(f'[data-palette="{name}"]')
    night_bg, night_accent = night["--night-bg"], night["--night-accent"]
    # الدرجة الأغمق للوردي وحده؛ بقية السمات نصّها بلونها.
    assert (day["--day-accent"] != day["--day-color"]) == (name == "rose")

    for ground in (day["--day-bg"], day["--day-surface"], day["--day-raised"], day["--day-soft"]):
        assert _contrast(day["--day-accent"], ground) >= 4.5
        assert _contrast(day["--day-muted"], ground) >= 4.5
        assert _contrast(day["--day-ink"], ground) >= 7
    assert _contrast("#ffffff", day["--day-accent"]) >= 4.5
    # لون الشعار معلوماتي: 3:1 على خلفية سمته.
    assert _contrast(day["--day-color"], day["--day-bg"]) >= 3

    night_grounds = [
        night_bg,
        _mix("#ffffff", 0.07, night_bg),
        _mix("#ffffff", 0.13, night_bg),
        _mix(night_accent, 0.12, night_bg),
    ]
    for ground in night_grounds:
        assert _contrast(night_accent, ground) >= 4.5
        assert _contrast(NIGHT_MUTED, ground) >= 4.5
        assert _contrast(NIGHT_INK, ground) >= 7
    assert _contrast(night_bg, night_accent) >= 4.5


def test_oud_day_is_the_guide_token_map():
    # نهار العودي قيم دليل الهوية حرفيًّا (token_map)، لا اشتقاقًا. بقية السمات تشتق من ألوانها.
    expected = {var: light for var, (light, _) in _token_map().items()}
    oud = _day("oud")
    actual = {
        "--bg": oud["--day-bg"],
        "--surface": oud["--day-surface"],
        "--ink": oud["--day-ink"],
        "--muted": oud["--day-muted"],
        "--line": oud["--day-line"],
        "--accent": oud["--day-accent"],
        "--risk": _tokens_css()["--risk"][0],
    }
    assert actual == expected


def test_default_palette_values_are_oud():
    # بلا data-palette (قبل السكربت أو بتخزين محجوب) الصفحة عودية في الوضعين.
    tokens = _tokens_text()
    root = tokens.split("[data-palette", 1)[0]
    ivory = re.search(r"--ivory:\s*(#[0-9a-fA-F]{6});", tokens)
    champagne = re.search(r"--champagne:\s*(#[0-9a-fA-F]{6});", tokens)
    assert ivory and champagne
    oud = _rule_values('[data-palette="oud"]')
    assert oud["--day-bg"] == ivory.group(1).lower()
    assert oud["--night-accent"] == champagne.group(1).lower()
    assert "--day-bg: var(--ivory);" in root
    assert "--night-accent: var(--champagne);" in root
    for var in (
        "--night-bg",
        "--day-ink",
        "--day-muted",
        "--day-surface",
        "--day-raised",
        "--day-line",
        "--day-soft",
    ):
        assert re.search(rf"{var}:\s*{oud[var]};", root, re.I), var


def test_colored_logo_component_keeps_source_paths():
    # مكوّن الشعار الملوَّن ينسخ مسارات أصل سِمة حرفيًّا ويأخذ اللون وحده من السمة.
    source = (ROOT / "brand" / "misk" / "misk-logo-color.svg").read_text(encoding="utf-8")
    component = (ROOT / "frontend" / "src" / "components" / "BrandLogo.vue").read_text(encoding="utf-8")
    parts = dict(re.findall(r'<path id="(\w+)"[^>]*? d="([^"]+)"', source))
    assert list(parts) == ["ribbon", "folds", "design"]
    fills = {
        "ribbon": "var(--color-mark-ink)",
        "folds": "var(--color-mark-fold)",
        "design": "var(--color-mark-ink)",
    }
    for part, d in parts.items():
        assert f'<path class="logo-{part}" fill="{fills[part]}" fill-rule="nonzero" d="{d}" />' in component
    assert not re.search(r"#[0-9a-fA-F]{6}", component)


@pytest.mark.parametrize(
    ("copy", "source"),
    [
        ("motion.css", IDENTITY / "motion.css"),
        ("motif-mono.svg", IDENTITY / "patterns" / "motif-mono.svg"),
        ("mark.svg", ROOT / "brand" / "misk" / "misk-mark.svg"),
        # خطّا المنصة بقرار المالك 2026-11-17 يخالفان دليل v6، فأصلهما brand/misk/fonts لا مجلد الدليل.
        ("fonts/Cairo-Variable.ttf", PLATFORM_FONTS / "Cairo[slnt,wght].ttf"),
        ("fonts/Almarai-Regular.ttf", PLATFORM_FONTS / "Almarai-Regular.ttf"),
        ("fonts/OFL-Cairo.txt", PLATFORM_FONTS / "OFL-Cairo.txt"),
        ("fonts/OFL-Almarai.txt", PLATFORM_FONTS / "OFL-Almarai.txt"),
    ],
)
def test_frontend_copies_match_identity_source(copy, source):
    # الواجهة تُبنى من frontend/ وحده (Dockerfile)، فالموارد منسوخة إليه؛ النسخة لا تحيد عن أصل الهوية.
    def content(path: Path) -> bytes:
        return path.read_bytes().replace(b"\r\n", b"\n")

    assert content(STATIC_BRAND / copy) == content(source)


def test_identity_fonts_are_declared_and_used():
    tokens = (STATIC_BRAND / "tokens.css").read_text(encoding="utf-8")
    base = (ROOT / "frontend" / "src" / "styles" / "base.css").read_text(encoding="utf-8")
    for family, file in (("Cairo", "fonts/Cairo-Variable.ttf"), ("Almarai", "fonts/Almarai-Regular.ttf")):
        assert re.search(
            rf'@font-face\s*{{[^}}]*font-family:\s*"{family}"[^}}]*url\("{re.escape(file)}"\)', tokens
        )
    assert re.search(r'--font-heading:\s*"Cairo"', tokens)
    assert re.search(r'--font-ui:\s*"Almarai"', tokens)
    # خط الدليل v6 لا يُنسخ إلى الواجهة ما دامت لا تستعمله.
    assert sorted(p.name for p in (STATIC_BRAND / "fonts").iterdir()) == [
        "Almarai-Regular.ttf",
        "Cairo-Variable.ttf",
        "OFL-Almarai.txt",
        "OFL-Cairo.txt",
    ]
    assert "font-family: var(--font-heading)" in base
    assert "font-family: var(--font-ui)" in base


def test_mark_intro_motion_is_applied():
    base = (ROOT / "frontend" / "src" / "styles" / "base.css").read_text(encoding="utf-8")
    app = (ROOT / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")
    assert '@import "../static/brand/motion.css"' in base
    assert re.search(r'<BrandLogo[^>]*class="sima-mark-intro"', app)


def test_spa_shows_splash_until_app_boots(client):
    from django.contrib.staticfiles import finders

    page = client.get("/").content.decode()
    # الشاشة داخل #app فيستبدلها Vue عند الإقلاع، وأنماطها ملفات ثابتة تسبق حزمة الواجهة.
    app = page.index('<div id="app"')
    assert app < page.index('class="splash"') < page.index("</div>\n  </div>", app)
    assert page.index("/static/brand/splash.css") < page.index("src/main.ts")
    for name in (
        "brand/splash.css",
        "brand/mark.svg",
        "brand/motif-mono.svg",
        "brand/fonts/Cairo-Variable.ttf",
    ):
        assert finders.find(name)


def test_slide_template_follows_identity():
    html = (ROOT / "docs" / "slides" / "slides.html").read_text(encoding="utf-8")
    css = (ROOT / "docs" / "slides" / "slides.css").read_text(encoding="utf-8")
    assert 'class="slide slide-title"' in html
    assert 'class="slide slide-content"' in html
    assert "aspect-ratio: 16 / 9" in css
    # القالب يقرأ ألوان المنصة وخطوطها من ملفها، وكل ما يحيل إليه موجود.
    assert '@import "../../frontend/src/static/brand/tokens.css"' in css
    for ref in re.findall(r'(?:src|href)="([^"]+)"', html) + re.findall(r'url\("([^"]+)"\)', css):
        assert (ROOT / "docs" / "slides" / ref).resolve().is_file(), ref


FRONTEND_SRC = ROOT / "frontend" / "src"
IDENTITY_ICONS = sorted((IDENTITY / "icons").glob("*.svg"))


def test_identity_icons_are_copied_unchanged():
    # الأيقونات تُستعمل كما هي: نسخة الواجهة تطابق أصل الهوية ملفًّا بملف، بلا زيادة ولا نقص.
    assert len(IDENTITY_ICONS) >= 10
    copies = sorted((STATIC_BRAND / "icons").glob("*.svg"))
    assert [p.name for p in copies] == [p.name for p in IDENTITY_ICONS]
    for source, copy in zip(IDENTITY_ICONS, copies, strict=True):
        assert copy.read_bytes().replace(b"\r\n", b"\n") == source.read_bytes().replace(b"\r\n", b"\n")


def test_pages_use_identity_icons_and_pattern():
    names = {p.stem for p in IDENTITY_ICONS}
    used = set()
    for path in FRONTEND_SRC.rglob("*.vue"):
        text = path.read_text(encoding="utf-8")
        used |= set(re.findall(r'<BrandIcon name="([\w-]+)"', text))
    catalog = (FRONTEND_SRC / "domain" / "catalog.ts").read_text(encoding="utf-8")
    for table in ("KIND_ICONS", "GENERATOR_ICONS"):
        used |= set(
            re.findall(r': "([\w-]+)"', catalog.split(f"export const {table}", 1)[1].split("};", 1)[0])
        )
    # كل اسم مستعمل أيقونة موجودة في الهوية. الأيقونة الوحيدة بلا موضع هي portrait:
    # لا منتج صور في المنصة بعد، فلا تُحشر (ADOPTION.yaml: icons-used).
    assert used <= names
    assert names - used == {"portrait"}
    base = (FRONTEND_SRC / "styles" / "base.css").read_text(encoding="utf-8")
    assert re.search(r'\.empty::before\s*{[^}]*url\("\.\./static/brand/motif-mono\.svg"\)', base)


def test_pages_take_colors_from_tokens_only():
    # الألوان من متغيرات tokens.css وحدها: لا لون خام في أنماط الصفحات والمكوّنات.
    raw = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")
    offenders = []
    for path in FRONTEND_SRC.rglob("*.vue"):
        for block in re.findall(r"<style[^>]*>(.*?)</style>", path.read_text(encoding="utf-8"), re.S):
            if raw.search(block):
                offenders.append(path.name)
    if raw.search((FRONTEND_SRC / "styles" / "base.css").read_text(encoding="utf-8")):
        offenders.append("base.css")
    assert offenders == []


def test_every_guide_screen_is_compared_with_the_pages():
    # identity/screens: لكل شاشة في الدليل اختبار في frontend/e2e/screens.spec.ts يصيّر الصفحة بمقاسها ويقارنها بها.
    # الاختبار نفسه يحتاج متصفحًا ويُشغَّل بـ `npm --prefix frontend run test:screens`؛ هنا يُضمن ألا تبقى شاشة بلا مقارنة.
    screens = sorted(p.stem for p in (IDENTITY / "screens").glob("*.html"))
    assert screens == ["app-dark", "app-light", "landing", "mobile", "print"]
    spec = (ROOT / "frontend" / "e2e" / "screens.spec.ts").read_text(encoding="utf-8")
    assert "brand/misk/identity/screens" in spec
    compared = set(re.findall(r'(?:openGuide\(\w+, |viewportOf\(|\[)"([a-z-]+)"', spec))
    assert set(screens) <= compared
    package = (ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    assert '"test:screens": "playwright test"' in package
