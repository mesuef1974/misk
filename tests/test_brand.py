"""تبنّي الهوية: ما في brand/misk/identity/ADOPTION.yaml مطبَّق في الواجهة، ونسخ الواجهة مطابقة لأصل الهوية."""

import re
from pathlib import Path

import pytest
from django.conf import settings

ROOT = Path(settings.BASE_DIR)
IDENTITY = ROOT / "brand" / "misk" / "identity"
STATIC_BRAND = ROOT / "frontend" / "src" / "static" / "brand"

# ADOPTION.yaml مولَّد ببنية ثابتة؛ يُقرأ token_map بنمط نصي حتى لا يحتاج الاختبار مكتبة YAML.
_ENTRY = re.compile(
    r"- app_var: (?P<var>--[\w-]+)\s+light:.*?value: '(?P<light>#[0-9a-fA-F]{6})'\s+dark:.*?value: '(?P<dark>#[0-9a-fA-F]{6})'",
    re.S,
)
_TOKEN = re.compile(r"(--[\w-]+):\s*light-dark\((#[0-9a-fA-F]{6}),\s*(#[0-9a-fA-F]{6})\)")


def _token_map() -> dict[str, tuple[str, str]]:
    text = (IDENTITY / "ADOPTION.yaml").read_text(encoding="utf-8")
    block = text.split("token_map:", 1)[1].split("\nchecks:", 1)[0]
    return {m["var"]: (m["light"].lower(), m["dark"].lower()) for m in _ENTRY.finditer(block)}


def _tokens_css() -> dict[str, tuple[str, str]]:
    text = (STATIC_BRAND / "tokens.css").read_text(encoding="utf-8")
    return {var: (light.lower(), dark.lower()) for var, light, dark in _TOKEN.findall(text)}


def test_tokens_match_adoption_token_map():
    expected = _token_map()
    actual = _tokens_css()
    # الخريطة تُقرأ كاملة: سبعة متغيرات لونية في الإصدار المعتمد، وأقل من ذلك خلل في القراءة لا نجاح.
    assert len(expected) >= 7
    assert {var: actual.get(var) for var in expected} == expected


@pytest.mark.parametrize(
    ("copy", "source"),
    [
        ("motion.css", IDENTITY / "motion.css"),
        ("motif.svg", IDENTITY / "patterns" / "motif-mono.svg"),
        ("mark.svg", ROOT / "brand" / "misk" / "misk-mark.svg"),
        ("fonts/Cairo-Variable.ttf", IDENTITY / "fonts" / "Cairo[slnt,wght].ttf"),
        ("fonts/Almarai-Regular.ttf", IDENTITY / "fonts" / "Almarai-Regular.ttf"),
        ("fonts/OFL-Cairo.txt", IDENTITY / "fonts" / "OFL-Cairo.txt"),
        ("fonts/OFL-Almarai.txt", IDENTITY / "fonts" / "OFL-Almarai.txt"),
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
    assert "font-family: var(--font-heading)" in base
    assert "font-family: var(--font-ui)" in base


def test_mark_intro_motion_is_applied():
    base = (ROOT / "frontend" / "src" / "styles" / "base.css").read_text(encoding="utf-8")
    app = (ROOT / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")
    assert '@import "../static/brand/motion.css"' in base
    assert re.search(r'<BrandLockup[^>]*class="sima-mark-intro"', app)


def test_spa_shows_splash_until_app_boots(client):
    from django.contrib.staticfiles import finders

    page = client.get("/").content.decode()
    # الشاشة داخل #app فيستبدلها Vue عند الإقلاع، وأنماطها ملفات ثابتة تسبق حزمة الواجهة.
    app = page.index('<div id="app"')
    assert app < page.index('class="splash"') < page.index("</div>\n  </div>", app)
    assert page.index("/static/brand/splash.css") < page.index("src/main.ts")
    for name in ("brand/splash.css", "brand/mark.svg", "brand/motif.svg", "brand/fonts/Cairo-Variable.ttf"):
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
    assert re.search(r'\.empty::before\s*{[^}]*url\("\.\./static/brand/motif\.svg"\)', base)


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
