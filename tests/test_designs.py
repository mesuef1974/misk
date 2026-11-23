import json
import math
import zipfile
from datetime import date
from decimal import Decimal
from io import StringIO

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db.models import ProtectedError
from django.test import Client

from apps.capacity import selectors as capacity_selectors
from apps.catalog import services as catalog_services
from apps.catalog.models import ProductTemplate
from apps.checkout import providers
from apps.checkout.models import Payment
from apps.core.models import AuditLog
from apps.designs import estimate, pricing, scan, selectors, services, svg, tasks, validators
from apps.designs.models import (
    Design,
    DesignFile,
    DesignImage,
    DesignPricing,
    DesignSource,
    VariantEstimate,
)
from apps.orders import services as order_services
from apps.orders.models import Order
from apps.production import services as production_services
from apps.production.models import Placement
from tests.test_checkout import SECRET, _checkout, _json, _notify

KEY = {
    "#e30613": {"operation": "cut", "material": "wood"},
    "#009640": {"operation": "score", "material": "wood"},
    "#000": {"operation": "engrave", "material": "wood"},
    "#36a9e1": {"operation": "cut", "material": "acrylic"},
}
U = 25.4 / 72  # مليمتر لكل وحدة في ملف Illustrator بـ 72 نقطة في البوصة

# 720×360 وحدة بعرض 254 مم: ملف Illustrator؛ قراءته بـ 96 نقطة في البوصة كانت ستعطي 190.5 مم.
SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="25.4cm" height="12.7cm" viewBox="0 0 720 360">
  <rect x="0" y="0" width="72" height="72" fill="#e94e1b"/>
  <rect x="72" y="72" width="288" height="144" fill="none" stroke="#e30613"/>
  <circle cx="216" cy="144" r="36" fill="none" stroke="#E30613"/>
  <g transform="translate(10,0)"><line x1="100" y1="300" x2="200" y2="300" stroke="#009640"/></g>
  <path d="M400,72h144v72h-144z" fill="none" style="stroke:#000000"/>
  <rect x="400" y="200" width="72" height="72" fill="none" stroke="#36a9e1"/>
  <line x1="0" y1="350" x2="72" y2="350" stroke="#ff00ff"/>
</svg>
"""


def _length(d: str) -> float:
    return sum(
        math.dist(a, b) for line in svg.path_polylines(d) for a, b in zip(line, line[1:], strict=False)
    )


# ——— قراءة SVG ———


def test_size_follows_declared_units_not_96_dpi():
    result = svg.analyze(SAMPLE, KEY)
    assert result.width_mm == pytest.approx(254)
    assert result.height_mm == pytest.approx(127)
    assert result.mm_per_unit == pytest.approx(U)


def test_operations_lengths_and_counts():
    ops = svg.analyze(SAMPLE, KEY).operations
    assert ops["cut:wood"]["count"] == 2
    assert ops["cut:wood"]["length_mm"] == pytest.approx(304.8 + 2 * math.pi * 12.7, abs=0.1)
    assert ops["score:wood"]["length_mm"] == pytest.approx(100 * U, abs=0.05)
    assert ops["engrave:wood"]["bbox_area_mm2"] == pytest.approx(50.8 * 25.4, abs=0.1)
    assert ops["cut:acrylic"]["length_mm"] == pytest.approx(101.6, abs=0.05)


def test_reference_square_detected_and_unknown_colors_reported():
    result = svg.analyze(SAMPLE, KEY)
    assert result.reference_mm == pytest.approx((25.4, 25.4))
    assert result.unknown_colors == {"#ff00ff": 1}


def test_outer_area_skips_parts_inside_others():
    result = svg.analyze(SAMPLE, KEY)
    assert svg.outer_area_mm2(result, "wood") == pytest.approx(101.6 * 50.8, abs=0.1)


def test_ready_to_cut_drops_reference_and_states_millimetres():
    ready = svg.ready_to_cut(SAMPLE, KEY)
    assert b'width="254.000mm"' in ready
    again = svg.analyze(ready, KEY)
    assert again.reference_mm is None
    assert again.operations == svg.analyze(SAMPLE, KEY).operations


@pytest.mark.parametrize(
    ("d", "expected"),
    [
        ("M0,0H10V10H0Z", 40),
        ("m0,0 10,0 0,10z", 20 + math.sqrt(200)),
        ("M0,0A5,5 0 0 1 10,0", 5 * math.pi),
        ("M0,0a5,5 0 1 0 10,0", 5 * math.pi),
        ("M0 0C0 0 10 0 10 0", 10),
        ("M0,0 1e1,0", 10),
        ("M0-5.5.5.5", math.dist((0, -5.5), (0.5, 0.5))),
    ],
)
def test_path_lengths(d, expected):
    assert _length(d) == pytest.approx(expected, rel=5e-4)


def test_smooth_curves_reflect_previous_control():
    assert _length("M0,0Q5,5 10,0T20,0") == pytest.approx(_length("M0,0Q5,5 10,0Q15,-5 20,0"))
    assert _length("M0,0C0,5 10,5 10,0S20,-5 20,0") == pytest.approx(
        _length("M0,0C0,5 10,5 10,0C10,-5 20,-5 20,0")
    )


def test_transforms_apply_to_lengths():
    data = (
        b'<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" viewBox="0 0 100 100">'
        b'<g transform="scale(2) rotate(90)"><line x1="0" y1="0" x2="10" y2="0" stroke="#e30613"/></g></svg>'
    )
    assert svg.analyze(data, KEY).operations["cut:wood"]["length_mm"] == pytest.approx(20)


@pytest.mark.parametrize(
    "data",
    [
        b'<!DOCTYPE svg [<!ENTITY x "y">]><svg xmlns="http://www.w3.org/2000/svg"/>',
        b"<svg",
        b'<html xmlns="http://www.w3.org/1999/xhtml"/>',
        b'<svg xmlns="http://www.w3.org/2000/svg"/>',
    ],
)
def test_rejects_unsafe_or_unsized_files(data):
    with pytest.raises(svg.SvgError):
        svg.analyze(data, KEY)


# ——— التقدير ———


def test_estimate_marks_missing_calibration_incomplete():
    ops = svg.analyze(SAMPLE, KEY).operations
    result = estimate.estimate(
        operations=ops,
        material_kind="wood",
        settings={
            "cut": estimate.Setting(Decimal("10"), 2, None, 1),
            "engrave": estimate.Setting(Decimal("200"), 1, 100, 2),
        },
        material_area_mm2=5000,
        sheet_area_mm2=Decimal("100000"),
        sheet_cost=Decimal("20"),
    )
    assert result.seconds["cut"] == pytest.approx(ops["cut:wood"]["length_mm"] / 10 * 2, abs=0.1)
    assert result.seconds["engrave"] == pytest.approx(
        ops["engrave:wood"]["bbox_area_mm2"] / 0.1 / 200, abs=0.1
    )
    assert result.seconds["score"] is None
    assert result.complete is False
    assert result.material_cost == Decimal("1.00")
    assert result.calibration_ids == [1, 2]


def test_estimate_none_without_operations_on_material():
    ops = svg.analyze(SAMPLE, KEY).operations
    assert (
        estimate.estimate(
            operations=ops,
            material_kind="leather",
            settings={},
            material_area_mm2=0,
            sheet_area_mm2=Decimal("1"),
            sheet_cost=Decimal("1"),
        )
        is None
    )


# ——— الاستيراد والتحليل ———


@pytest.fixture
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    return settings.MEDIA_ROOT


@pytest.fixture
def source(db):
    return DesignSource.objects.create(name="Test Store", color_key=KEY)


@pytest.fixture
def pack_folder(tmp_path):
    variant = tmp_path / "incoming" / "Baby-Bank-Laser-Cut-1234567" / "Baby Bank-02"
    variant.mkdir(parents=True)
    (variant / "Baby Bank-02.svg").write_bytes(SAMPLE)
    (variant / "Baby Bank-02.png").write_bytes(b"png-layout")
    (variant / "Baby Bank-2.jpg").write_bytes(b"jpg-cover")
    (variant / "Size Preview-2.png").write_bytes(b"png-size")
    (variant / "Size Check & LightBurn Fixes.jpg").write_bytes(b"jpg-help")
    (variant / "Baby Bank-02.dxf").write_bytes(b"dxf")
    (variant / "desktop.ini").write_bytes(b"ini")
    return variant.parent


@pytest.fixture
def wood(db):
    material = catalog_services.upsert_material(
        name="بتولا",
        kind="wood",
        thickness_mm=Decimal("3"),
        sheet_width_mm=Decimal("600"),
        sheet_height_mm=Decimal("400"),
        sheet_cost=Decimal("24.00"),
    )
    for operation, speed, lines in (("cut", "10", None), ("score", "100", None), ("engrave", "300", 100)):
        catalog_services.record_calibration(
            material=material,
            operation=operation,
            power_pct=60,
            speed_mm_s=Decimal(speed),
            min_line_mm=Decimal("0.3"),
            measured_on=date(2026, 11, 20),
            lines_per_cm=lines,
        )
    return material


def test_split_variant_name():
    assert services.split_variant_name("Personalised Baby Milestone Bank-03") == (
        "Personalised Baby Milestone Bank",
        "03",
    )
    assert services.split_variant_name("Stroller") == ("Stroller", "")


def test_import_classifies_files_and_is_idempotent(media, source, pack_folder):
    report = services.import_folder(root=pack_folder, source=source)
    assert len(report.created) == 1 and not report.skipped
    variant = report.created[0]
    design = variant.design
    assert (design.name_original, variant.code) == ("Baby Bank", "02")
    assert design.pack.listing_id == "1234567"
    assert design.status == Design.Status.DRAFT
    roles = {f.name: f.role for f in variant.files.all()}
    assert roles == {
        "Baby Bank-02.svg": DesignFile.Role.ORIGINAL,
        "Baby Bank-02.png": DesignFile.Role.CUT_LAYOUT,
        "Baby Bank-2.jpg": DesignFile.Role.COVER,
        "Size Preview-2.png": DesignFile.Role.SIZE_REFERENCE,
        "Baby Bank-02.dxf": DesignFile.Role.ALTERNATE,
    }
    dxf = variant.files.get(role=DesignFile.Role.ALTERNATE)
    assert not dxf.file and dxf.external_path.endswith("Baby Bank-02.dxf")
    source.refresh_from_db()
    assert source.instructions

    again = services.import_folder(root=pack_folder, source=source)
    assert not again.created and "مستورد من قبل" in again.skipped[0]
    assert AuditLog.objects.filter(action="designs.variant.import").count() == 1


def test_command_imports_analyzes_and_estimates(media, source, pack_folder, wood):
    call_command("import_designs", str(pack_folder), source="Test Store")
    variant = source.designs.get().variants.get()
    assert variant.analysis_error == ""
    assert variant.sheet_width_mm == Decimal("254.0")
    assert variant.analysis["unknown_colors"] == {"#ff00ff": 1}
    ready = variant.files.get(role=DesignFile.Role.READY_CUT)
    with ready.file.open("rb") as handle:
        assert b"e94e1b" not in handle.read()

    est = VariantEstimate.objects.get(variant=variant, material=wood)
    assert est.complete is True
    assert est.seconds["cut"] == pytest.approx(
        variant.analysis["operations"]["cut:wood"]["length_mm"] / 10, abs=0.1
    )
    assert est.material_cost == Decimal("0.52")  # 101.6×50.8 من لوح 600×400 بسعر 24

    services.analyze_variant(variant)  # إعادة التحليل تستبدل ولا تضاعف
    assert variant.files.filter(role=DesignFile.Role.READY_CUT).count() == 1
    assert variant.estimates.count() == 1


def test_broken_svg_records_error(media, source, pack_folder):
    (pack_folder / "Baby Bank-02" / "Baby Bank-02.svg").write_bytes(b"<svg")
    variant = services.import_folder(root=pack_folder, source=source).created[0]
    services.analyze_variant(variant)
    assert variant.analysis_error and variant.analysis == {}


def test_approve_and_license_guard(media, source, pack_folder, staff_user):
    variant = services.import_folder(root=pack_folder, source=source).created[0]
    design = variant.design
    with pytest.raises(services.DesignError, match="الاسم العربي"):
        services.approve(design)
    design.name_ar, design.category = "حصّالة إنجازات الطفل", "مواليد"
    with pytest.raises(services.DesignError, match="محلَّلة"):
        services.approve(design)
    services.analyze_variant(variant)
    design.personalization = [{"name": "child_name", "type": "text", "max_length": 20}]
    services.approve(design, actor=staff_user)
    assert design.status == Design.Status.APPROVED

    template = ProductTemplate.objects.create(
        slug="bank", name="حصّالة", generator="none", width_mm=178, height_mm=250
    )
    with pytest.raises(services.DesignError, match="ليس تجاريًّا"):
        services.link_template(design, template)
    source.license_kind = DesignSource.License.COMMERCIAL
    source.save()
    services.link_template(design, template)
    assert design.product_template == template


def test_admin_pages_render(media, source, pack_folder, admin_client):
    variant = services.import_folder(root=pack_folder, source=source).created[0]
    services.analyze_variant(variant)
    for url in (
        "/admin/designs/design/",
        f"/admin/designs/design/{variant.design.pk}/change/",
        "/admin/designs/designvariant/",
        f"/admin/designs/designvariant/{variant.pk}/change/",
        "/admin/designs/designsource/",
    ):
        assert admin_client.get(url).status_code == 200, url


# ——— التعميم: DOCTYPE والأصناف والمفرد والأجزاء والأرشيفات ———

SINGLE = {"*": {"operation": "cut", "material": "wood"}}


def _box(width: int, color: str = "#ff0000", extra: bytes = b"") -> bytes:
    head = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="50mm" viewBox="0 0 {width} 50">'
        f'<rect x="0" y="0" width="{width}" height="50" fill="none" stroke="{color}"/>'
    )
    return head.encode() + extra + b"</svg>"


def test_public_doctype_and_plain_entities_are_read():
    public = (
        b'<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">'
    )
    assert svg.analyze(public + _box(100), SINGLE).width_mm == pytest.approx(100)
    illustrator = (
        b'<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "x.dtd" [\r\n\t<!ENTITY ns_x "http://ns.example/x">'
        b"<!-- c -->]>"
        b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:x="&ns_x;" width="10mm" height="10mm" viewBox="0 0 10 10">'
        b'<line x1="0" y1="0" x2="10" y2="0" stroke="#e30613"/></svg>'
    )
    assert svg.analyze(illustrator, KEY).operations["cut:wood"]["length_mm"] == pytest.approx(10)


@pytest.mark.parametrize(
    "doctype",
    [
        b'<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]>',
        b'<!DOCTYPE svg [<!ENTITY % p "x">]>',
        b'<!DOCTYPE svg [<!ENTITY a "x"><!ENTITY b "&a;&a;">]>',
        b"<!DOCTYPE svg [<!ELEMENT svg ANY>]>",
        b"<!DOCTYPE svg><!DOCTYPE svg>",
    ],
)
def test_unsafe_doctype_rejected(doctype):
    with pytest.raises(svg.SvgError):
        svg.analyze(doctype + _box(10), KEY)


def test_entity_growth_is_bounded():
    data = (
        b'<!DOCTYPE svg [<!ENTITY e "'
        + b"x" * 512
        + b'">]>'
        + _box(10, extra=b"<desc>" + b"&e;" * 2000 + b"</desc>")
    )
    with pytest.raises(svg.SvgError, match="يضخّم"):
        svg.analyze(data, KEY)


def test_css_class_rules_apply_between_attributes_and_inline_style():
    data = (
        b'<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm" viewBox="0 0 10 10">'
        b"<defs><style><![CDATA[ .str0, .other {stroke:#E30613} /* x */ .fil0 {fill:none} ]]></style></defs>"
        b'<line class="fil0 str0" stroke="#009640" x1="0" y1="0" x2="10" y2="0"/>'
        b'<line class="str0" style="stroke:#009640" x1="0" y1="5" x2="4" y2="5"/></svg>'
    )
    ops = svg.analyze(data, KEY).operations
    assert ops["cut:wood"]["length_mm"] == pytest.approx(10)
    assert ops["score:wood"]["length_mm"] == pytest.approx(4)


def test_single_color_rule_applies_only_to_single_unknown_color():
    single = svg.analyze(_box(100), SINGLE)
    assert single.operations["cut:wood"]["length_mm"] == pytest.approx(300)
    assert single.as_json()["assumed"] == {"#ff0000": "cut:wood"}

    mixed = _box(100, extra=b'<line x1="0" y1="0" x2="5" y2="0" stroke="#000000"/>')
    result = svg.analyze(mixed, SINGLE)
    assert result.operations == {} and result.unknown_colors == {"#ff0000": 1, "#000000": 1}
    assert svg.analyze(_box(100), {}).operations == {}


def test_default_key_reads_multicolor_and_single_color_stays_cut():
    key = services.DEFAULT_COLOR_KEY
    mixed = _box(
        100,
        extra=b'<line x1="0" y1="0" x2="5" y2="0" stroke="#2B3990"/>'
        b'<line x1="0" y1="10" x2="7" y2="10" stroke="#000000"/>',
    )
    result = svg.analyze(mixed, key)
    assert result.unknown_colors == {} and "assumed" not in result.as_json()
    assert result.operations["cut:wood"]["length_mm"] == pytest.approx(300)
    assert result.operations["score:wood"]["length_mm"] == pytest.approx(5)
    assert result.operations["engrave:wood"]["count"] == 1

    # ملف كله بالأسود أو الأزرق قصّ لا حفر ولا علام: قاعدة المفرد تسبق المفتاح.
    for color in ("#000000", "#0000ff"):
        single = svg.analyze(_box(100, color=color), key)
        assert set(single.operations) == {"cut:wood"}
        assert single.as_json()["assumed"] == {color: "cut:wood"}


def test_combine_sums_parts():
    a, b = svg.analyze(_box(100), SINGLE), svg.analyze(_box(40), SINGLE)
    total = svg.combine([a, b])
    assert total.operations["cut:wood"]["count"] == 2
    assert total.operations["cut:wood"]["length_mm"] == pytest.approx(300 + 180)
    assert (total.width_mm, total.height_mm) == (pytest.approx(100), pytest.approx(50))
    assert svg.combine([a]) is a


def _zip(path, members: dict[str, bytes]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return path


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "library"
    _zip(
        root / "Baby" / "Name-Sign-Bundle-153819768.zip",
        {"1/a.svg": _box(100), "1/a.dxf": b"dxf-1", "2/a.svg": _box(120), "__MACOSX/1/._a.svg": b"junk"},
    )
    box = root / "BOXES" / "Gift-Box-119253291" / "Files"
    for thickness, width in (("3mm", 150), ("4mm", 151)):
        folder = box / f"Box 150 70 {thickness}"
        folder.mkdir(parents=True)
        (folder / f"Box {thickness}.svg").write_bytes(_box(width))
        (folder / f"Box {thickness} Glowforge.svg").write_bytes(_box(width, "#e42110"))
    panels = root / "BOXES" / "5M PLYWOOD"
    panels.mkdir(parents=True)
    (panels / "front.svg").write_bytes(_box(80))
    (panels / "back.svg").write_bytes(_box(80).replace(b"<rect", b"<rect id='b'"))
    (panels / "bottom.svg").write_bytes(_box(60))
    (root / "BOXES" / "loose.svg").write_bytes(_box(30))
    sets = root / "Decor" / "Panel-set-36780861" / "SVG"
    sets.mkdir(parents=True)
    (sets / "P (1).svg").write_bytes(_box(20))
    (sets / "P (2).svg").write_bytes(_box(21))
    extracted = root / "Decor" / "Clock-160894418"
    extracted.mkdir()
    (extracted / "Clock.svg").write_bytes(_box(90))
    _zip(root / "Decor" / "Clock-160894418.zip", {"Clock.svg": _box(90)})
    _zip(root / "Decor" / "Only-dxf-123456789.zip", {"a.dxf": b"dxf"})
    return root


def test_plan_names_codes_parts_and_categories(library):
    result = scan.scan(library)
    plans = scan.plan(result, tree=True, each_svg=[library / "Decor" / "Panel-set-36780861"])
    found = {(p.category, p.name, p.code): sorted(e.name for e in p.parts) for p in plans}
    assert found == {
        ("Baby", "Name Sign Bundle", "1"): ["a.svg"],
        ("Baby", "Name Sign Bundle", "2"): ["a.svg"],
        ("BOXES", "Gift Box", "3mm"): ["Box 3mm.svg"],
        ("BOXES", "Gift Box", "4mm"): ["Box 4mm.svg"],
        ("BOXES", "5M PLYWOOD", ""): ["back.svg", "bottom.svg", "front.svg"],
        ("BOXES", "loose", ""): ["loose.svg"],
        ("Decor", "Panel set", "P (1)"): ["P (1).svg"],
        ("Decor", "Panel set", "P (2)"): ["P (2).svg"],
        ("Decor", "Clock", ""): ["Clock.svg"],
    }
    gift = next(p for p in plans if p.code == "3mm")
    assert [e.name for e in gift.files] == ["Box 3mm Glowforge.svg"]
    assert any("Only-dxf" in note and "لا SVG" in note for note in result.notes)


def test_import_tree_from_archives_and_parts(media, library, wood):
    source = services.ensure_source("Creative Fabrica")
    assert source.color_key == services.DEFAULT_COLOR_KEY
    assert services.ensure_source("Creative Fabrica") == source

    report = services.import_folder(root=library, source=source, tree=True)
    assert len(report.created) == 8  # P (1) وP (2) أجزاء نسخة واحدة بلا --each-svg
    sign = source.designs.get(name_original="Name Sign Bundle")
    assert sign.category == "Baby" and sign.pack.listing_id == "153819768"
    dxf = sign.variants.get(code="1").files.get(role=DesignFile.Role.ALTERNATE)
    assert dxf.external_path.endswith("Name-Sign-Bundle-153819768.zip!/1/a.dxf") and not dxf.file

    panels = source.designs.get(name_original="5M PLYWOOD").variants.get()
    services.analyze_variant(panels)
    cut = panels.analysis["operations"]["cut:wood"]
    assert cut["count"] == 3 and cut["length_mm"] == pytest.approx(2 * 260 + 220)
    assert "assumed" not in panels.analysis  # الأحمر في المفتاح الافتراضي قص أصلًا
    assert panels.analysis["outer_area_mm2"]["wood"] == pytest.approx(80 * 50 * 2 + 60 * 50)
    assert panels.analysis["same_geometry"] == [["back.svg", "front.svg"]]
    assert panels.files.filter(role=DesignFile.Role.READY_CUT).count() == 3
    assert panels.estimates.get(material=wood).complete
    services.analyze_variant(panels)
    assert panels.files.filter(role=DesignFile.Role.READY_CUT).count() == 3

    gift = source.designs.get(name_original="Gift Box").variants.get(code="3mm")
    assert gift.files.get(role=DesignFile.Role.ALTERNATE).name == "Box 3mm Glowforge.svg"

    again = services.import_folder(root=library, source=source, tree=True)
    assert not again.created and len(again.skipped) == 8


def test_command_scan_writes_nothing_and_create_source(media, library, db):
    out = StringIO()
    call_command("import_designs", str(library), source="New", tree=True, show_plan=True, stdout=out)
    assert "Name Sign Bundle (1)" in out.getvalue() and not DesignSource.objects.exists()

    archive = library / "Baby" / "Name-Sign-Bundle-153819768.zip"
    call_command("import_designs", str(archive), source="New", create_source=True, stdout=StringIO())
    assert DesignSource.objects.get(name="New").designs.get().variants.count() == 2


# ——— العرض في المتجر: التسعير والنشر والمسارات العامة (docs/ready-designs-plan.md) ———

RATES = pricing.Rates(minute_rate=Decimal("2"), margin_pct=Decimal("100"), round_to=Decimal("5"))
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _price(**overrides):
    values = {
        "rates": RATES,
        "material_cost": Decimal("0.50"),
        "total_seconds": Decimal("30"),
        "complete": True,
        "assembly_fee": Decimal("10"),
    }
    return pricing.price(**{**values, **overrides})


def test_price_rounds_up_and_manual_price_wins():
    assert _price() == Decimal("25.00")  # (0.50 + 1.00 + 10) × 2 = 23 ← 25
    assert _price(assembly_fee=Decimal("11")) == Decimal("25.00")  # 25 تمامًا لا تُرفع
    assert _price(manual_price=Decimal("40")) == Decimal("40.00")
    assert _price(complete=False) is None
    assert _price(complete=False, manual_price=Decimal("40")) == Decimal("40.00")
    assert _price(rates=None, manual_price=Decimal("40")) is None


@pytest.mark.parametrize(
    ("name", "content"),
    [("a.svg", b"<svg/>"), ("a.png", b'<svg xmlns="http://www.w3.org/2000/svg"/>'), ("a.jpg", PNG)],
)
def test_showcase_image_must_be_raster_matching_its_extension(name, content):
    with pytest.raises(ValidationError):
        validators.validate_showcase_image(SimpleUploadedFile(name, content))
    validators.validate_showcase_image(SimpleUploadedFile("a.png", PNG))


@pytest.fixture
def box_design(media, source, wood, tmp_path):
    """تصميم معتمد من مادة واحدة، محلَّل ومقدَّر، بلا ترخيص تجاري ولا صورة ولا سعر بعد."""
    folder = tmp_path / "in" / "Gift Box"
    folder.mkdir(parents=True)
    (folder / "Gift Box.svg").write_bytes(_box(100, "#e30613"))
    variant = services.import_folder(root=folder.parent, source=source).created[0]
    services.analyze_variant(variant)
    design = variant.design
    design.name_ar, design.category = "علبة هدية", "هدايا"
    design.save()
    return services.approve(design)


def _make_listable(design):
    design.source.license_kind = DesignSource.License.COMMERCIAL
    design.source.save()
    design.name_en = "Gift Box"
    design.assembly_fee = Decimal("10")
    design.save()
    DesignImage.objects.create(design=design, file=SimpleUploadedFile("box.png", PNG), alt_en="A gift box")
    services.save_pricing(minute_rate=Decimal("2"), margin_pct=Decimal("100"))
    services.reprice_all()


def test_listing_names_what_is_missing_then_publishes_once(box_design, staff_user):
    with pytest.raises(services.DesignError) as failure:
        services.list_design(box_design)
    for part in ("ترخيص المصدر", "الاسم الإنجليزي", "صورة عرض", "إعداد التسعير"):
        assert part in str(failure.value)

    _make_listable(box_design)
    assert selectors.listing_blockers(box_design) == []
    services.list_design(box_design, actor=staff_user)
    services.list_design(box_design, actor=staff_user)
    assert (box_design.slug, box_design.is_listed) == ("gift-box", True)
    assert AuditLog.objects.filter(action="designs.design.list").count() == 1


def test_multi_material_design_cannot_be_listed(media, source, pack_folder, wood):
    variant = services.import_folder(root=pack_folder, source=source).created[0]
    services.analyze_variant(variant)  # SAMPLE: خشب وأكريليك معًا
    design = variant.design
    design.name_ar, design.category = "حصّالة", "مواليد"
    design.save()
    services.approve(design)
    _make_listable(design)
    assert selectors.listing_blockers(design) == ["نسخة بسعر على مادة واحدة"]


def test_store_designs_show_price_and_image_but_no_design_file(client, box_design, wood):
    assert client.get("/api/store/designs").json() == []
    _make_listable(box_design)
    services.list_design(box_design)

    rows = client.get("/api/store/designs").json()
    assert [(r["slug"], r["name"], r["name_en"], r["price_from"]) for r in rows] == [
        ("gift-box", "علبة هدية", "Gift Box", "25.00")
    ]
    assert client.get("/api/store/designs?category=أخرى").json() == []

    response = client.get("/api/store/designs/gift-box")
    detail = response.json()
    offer = detail["variants"][0]["offers"][0]
    assert (offer["price"], offer["material"]["id"]) == ("25.00", wood.pk)
    assert detail["images"][0]["alt_en"] == "A gift box"
    body = response.content.decode().lower()
    variant = box_design.variants.get()
    for secret in (
        ".svg",
        "sha",
        variant.svg_sha256,
        "test store",
        "folder",
        "cost",
        "seconds",
        "designs/files",
    ):
        assert secret not in body, secret

    image = client.get(detail["images"][0]["url"])
    assert image.status_code == 200 and b"".join(image.streaming_content) == PNG
    assert image["Content-Type"] == "image/png" and image["X-Content-Type-Options"] == "nosniff"
    assert "public" in image["Cache-Control"]
    # ملفات التصميم نفسها تبقى خلف دخول المشرف.
    original = variant.files.get(role=DesignFile.Role.ORIGINAL)
    assert client.get(f"/media/{original.file.name}").status_code == 404


def test_showcase_image_thumbnail_is_webp_cached_and_revalidates(client, box_design):
    from io import BytesIO

    from PIL import Image

    _make_listable(box_design)
    services.list_design(box_design)
    image = box_design.images.get()
    big = BytesIO()
    Image.new("RGB", (1200, 900), "#c8a165").save(big, "PNG")
    image.file.save("big.png", SimpleUploadedFile("big.png", big.getvalue()), save=True)
    url = client.get("/api/store/designs/gift-box").json()["images"][0]["url"]

    thumb = client.get(f"{url}?w=480")
    assert thumb.status_code == 200 and thumb["Content-Type"] == "image/webp"
    assert Image.open(BytesIO(thumb.content)).width == 480 and len(thumb.content) < len(big.getvalue())
    assert client.get(f"{url}?w=480").content == thumb.content  # من الذاكرة المؤقتة
    assert client.get(f"{url}?w=480", HTTP_IF_NONE_MATCH=thumb["ETag"]).status_code == 304
    # عرض خارج القائمة المسموحة يُخدَم أصلًا لا مصغّرًا بمقاس اختياري.
    original = client.get(f"{url}?w=7")
    assert b"".join(original.streaming_content) == big.getvalue() and original["Content-Type"] == "image/png"
    assert Image.open(BytesIO(client.get(f"{url}?w=960").content)).width == 960


def test_heavy_image_is_deferred_to_the_worker_and_served_original_meanwhile(client, box_design, monkeypatch):
    from io import BytesIO

    from django.core.cache import cache
    from PIL import Image

    from apps.designs import thumbnails

    _make_listable(box_design)
    services.list_design(box_design)
    image = box_design.images.get()
    big = BytesIO()
    Image.new("RGB", (1200, 900), "#c8a165").save(big, "PNG")
    image.file.save("big.png", SimpleUploadedFile("big.png", big.getvalue()), save=True)
    cache.clear()
    monkeypatch.setattr(thumbnails, "ON_DEMAND_MAX_PIXELS", 1000)  # كل صورة هنا ثقيلة
    url = client.get("/api/store/designs/gift-box").json()["images"][0]["url"]

    first = client.get(f"{url}?w=480")
    # الأصل الآن بتخزين قصير؛ والمهمة (متزامنة في الاختبار) سخّنت المصغّر بلا قيد.
    assert (
        b"".join(first.streaming_content) == big.getvalue() and first["Cache-Control"] == "public, max-age=60"
    )
    assert "ETag" not in first
    assert thumbnails.cached(image, 480)[0] == "image/webp"
    second = client.get(f"{url}?w=480")
    assert second["Content-Type"] == "image/webp"


def test_warm_images_fills_the_cache_for_listed_designs_only(box_design):
    from io import BytesIO

    from django.core.cache import cache
    from PIL import Image

    from apps.designs import tasks, thumbnails

    _make_listable(box_design)
    image = box_design.images.get()
    big = BytesIO()
    Image.new("RGB", (1200, 900), "#c8a165").save(big, "PNG")
    image.file.save("big.png", SimpleUploadedFile("big.png", big.getvalue()), save=True)
    cache.clear()
    assert tasks.warm_images_async() == 0  # غير منشور: لا يُسخَّن
    services.list_design(box_design)
    assert tasks.warm_images_async() == 2 and tasks.warm_images_async() == 0  # idempotent
    kind, body = thumbnails.cached(image, 480)
    assert kind == "image/webp" and Image.open(BytesIO(body)).width == 480


def test_unlisting_or_losing_the_license_hides_the_design(client, box_design):
    _make_listable(box_design)
    services.list_design(box_design)
    image_url = client.get("/api/store/designs/gift-box").json()["images"][0]["url"]

    box_design.source.license_kind = DesignSource.License.PERSONAL
    box_design.source.save()
    assert client.get("/api/store/designs").json() == []
    assert client.get("/api/store/designs/gift-box").status_code == 404
    assert client.get(image_url).status_code == 404

    box_design.source.license_kind = DesignSource.License.COMMERCIAL
    box_design.source.save()
    assert client.get("/api/store/designs/gift-box").status_code == 200
    services.unlist_design(box_design)
    assert client.get("/api/store/designs/gift-box?lang=en").json()["detail"] == "Design not found"


def test_pricing_change_and_manual_price_reprice(box_design, wood):
    _make_listable(box_design)
    variant = box_design.variants.get()
    assert variant.estimates.get(material=wood).price == Decimal("25.00")

    services.save_pricing(minute_rate=Decimal("2"), margin_pct=Decimal("200"))
    assert tasks.reprice_all_async.delay().get() == 1
    assert variant.estimates.get(material=wood).price == Decimal("35.00")  # 11.5 × 3 = 34.5 ← 35
    assert DesignPricing.objects.count() == 1

    variant.manual_price = Decimal("60")
    variant.save()
    services.refresh_estimates(variant)
    assert variant.estimates.get(material=wood).price == Decimal("60.00")


def test_store_admin_pages_and_actions(box_design, admin_client):
    _make_listable(box_design)
    for url in ("/admin/designs/designpricing/", "/admin/designs/designpricing/1/change/"):
        assert admin_client.get(url).status_code == 200, url
    assert admin_client.get("/admin/designs/design/").status_code == 200
    admin_client.post(
        "/admin/designs/design/", {"action": "list_in_store", "_selected_action": [box_design.pk]}
    )
    box_design.refresh_from_db()
    assert box_design.is_listed


# ——— مقاس البيع ———


def test_scaled_analysis_shrinks_lengths_linearly_and_areas_squared():
    full = svg.analyze(SAMPLE, KEY)
    half = svg.scaled(full, 0.5)
    assert half.width_mm == pytest.approx(full.width_mm / 2)
    for name, group in full.operations.items():
        assert half.operations[name]["count"] == group["count"]
        assert half.operations[name]["length_mm"] == pytest.approx(group["length_mm"] / 2, abs=0.1)
        assert half.operations[name]["bbox_area_mm2"] == pytest.approx(group["bbox_area_mm2"] / 4, abs=0.1)
    assert svg.outer_area_mm2(half, "wood") == pytest.approx(svg.outer_area_mm2(full, "wood") / 4, abs=0.1)
    assert half.reference_mm == full.reference_mm  # المربع المرجعي يُعرَف بمقاس الملف
    assert svg.scaled(full, 1) is full


def test_ready_to_cut_at_sale_scale_reads_back_scaled():
    ready = svg.ready_to_cut(SAMPLE, KEY, 0.5)
    assert b'width="127.000mm"' in ready
    again, full = svg.analyze(ready, KEY), svg.analyze(SAMPLE, KEY)
    assert again.reference_mm is None
    for name, group in full.operations.items():
        assert again.operations[name]["length_mm"] == pytest.approx(group["length_mm"] / 2, abs=0.2)


def test_ready_to_cut_scales_a_file_without_viewbox():
    data = b'<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="50mm"><path d="M0 0H100" stroke="#e30613" fill="none"/></svg>'
    full = svg.analyze(data, KEY).operations["cut:wood"]["length_mm"]
    again = svg.analyze(svg.ready_to_cut(data, KEY, 0.5), KEY)
    assert again.width_mm == pytest.approx(50)
    assert again.operations["cut:wood"]["length_mm"] == pytest.approx(full / 2, abs=0.1)


def test_sale_scale_drives_size_estimate_and_cut_file(media, source, pack_folder, wood):
    call_command("import_designs", str(pack_folder), source="Test Store")
    variant = source.designs.get().variants.get()
    before = VariantEstimate.objects.get(variant=variant, material=wood)

    variant.sale_scale_percent = Decimal("50")
    variant.save()
    services.analyze_variant(variant)
    variant.refresh_from_db()
    assert variant.sheet_width_mm == Decimal("127.0")
    assert variant.analysis["sale_scale_percent"] == 50
    after = VariantEstimate.objects.get(variant=variant, material=wood)
    assert after.seconds["cut"] == pytest.approx(before.seconds["cut"] / 2, abs=0.2)
    assert after.material_cost == Decimal("0.13")  # ربع 0.52
    ready = variant.files.get(role=DesignFile.Role.READY_CUT)
    with ready.file.open("rb") as handle:
        assert b'width="127.000mm"' in handle.read()

    variant.sale_scale_percent = None  # العودة إلى مقاس الملف
    variant.save()
    services.analyze_variant(variant)
    variant.refresh_from_db()
    assert variant.sheet_width_mm == Decimal("254.0")
    assert "sale_scale_percent" not in variant.analysis


def test_fit_to_sheet_picks_largest_whole_percent_and_is_idempotent(media, source, pack_folder, wood):
    call_command("import_designs", str(pack_folder), source="Test Store")
    variant = source.designs.get().variants.get()
    assert services.fit_to_sheet(variant) is None  # 254 مم يسعه لوح 600×400

    wood.sheet_width_mm, wood.sheet_height_mm = Decimal("200"), Decimal("120")
    wood.save()
    short, long = sorted((variant.sheet_width_mm, variant.sheet_height_mm))
    # اللوح بعد هامش الترصيف 5 مم من كل جهة: 190 × 110.
    expected = Decimal(int(min(Decimal("110") / short, Decimal("190") / long) * 100))
    assert services.fit_to_sheet(variant) == expected
    services.analyze_variant(variant)
    variant.refresh_from_db()
    assert max(variant.sheet_width_mm, variant.sheet_height_mm) <= Decimal("190")
    assert min(variant.sheet_width_mm, variant.sheet_height_mm) <= Decimal("110")
    assert selectors.fits_material(variant, wood)
    audits = AuditLog.objects.filter(action="designs.variant.sale_scale").count()
    assert services.fit_to_sheet(variant) == expected  # من مقاس الملف لا من المقاس المصغَّر
    assert AuditLog.objects.filter(action="designs.variant.sale_scale").count() == audits

    wood.sheet_width_mm, wood.sheet_height_mm = Decimal("20"), Decimal("12")
    wood.save()
    with pytest.raises(services.DesignError):
        services.fit_to_sheet(variant)


def test_sale_scale_bounds_and_admin_reanalyzes(media, source, pack_folder, wood, admin_client):
    call_command("import_designs", str(pack_folder), source="Test Store")
    variant = source.designs.get().variants.get()
    variant.sale_scale_percent = Decimal("5")
    with pytest.raises(ValidationError):
        variant.full_clean()

    wood.sheet_width_mm, wood.sheet_height_mm = Decimal("200"), Decimal("120")
    wood.save()
    admin_client.post(
        "/admin/designs/designvariant/", {"action": "fit_to_sheet", "_selected_action": [variant.pk]}
    )
    variant.refresh_from_db()
    assert variant.sale_scale_percent is not None
    assert max(variant.sheet_width_mm, variant.sheet_height_mm) <= Decimal("200")  # المهمة أعادت التحليل


# ——— الطلب 2: السلة والإنتاج ———


@pytest.fixture
def pay(settings):
    settings.PAYMENT_PROVIDER = "test"
    settings.PAYMENT_WEBHOOK_SECRET = SECRET
    return providers.TestProvider(SECRET)


@pytest.fixture
def listed(box_design):
    _make_listable(box_design)
    return services.list_design(box_design)


def _add_design(client, design, material, **extra):
    variant = design.variants.get()
    body = {
        "design_slug": design.slug,
        "variant_code": variant.code,
        "material_id": material.pk,
        "acknowledged": True,
        **extra,
    }
    return _json(client, "post", "/api/store/cart/design-items", body)


def _confirmed_design_order(client, pay, design, material, quantity=1) -> Order:
    assert _add_design(client, design, material, quantity=quantity).status_code == 200
    assert _checkout(client).status_code == 200
    payment = Payment.objects.select_related("order").latest("id")
    assert _notify(client, pay, payment).json()["outcome"] == "confirmed"
    return Order.objects.get(pk=payment.order_id)


def test_listing_creates_sale_template_hidden_from_product_lists(client, listed, staff_user):
    template = listed.product_template
    assert template.slug == f"design-{listed.pk}" and template.generator == "ready_design"
    assert (template.name, template.name_en) == ("علبة هدية", "Gift Box")
    assert (template.width_mm, template.height_mm) == (Decimal("100.0"), Decimal("50.0"))
    assert template.material_kinds == ["wood"] and template.base_price == 0

    assert client.get("/api/store/templates").json() == []
    assert client.get(f"/api/store/templates/{template.slug}").status_code == 404
    client.force_login(staff_user)
    assert client.get("/api/catalog/templates").json() == []

    # إعادة النشر لا تكتب القالب ثانية، وتغيير الاسم يحدّثه على المفتاح نفسه.
    writes = AuditLog.objects.filter(action="catalog.template.upsert").count()
    services.list_design(listed)
    assert AuditLog.objects.filter(action="catalog.template.upsert").count() == writes
    listed.name_ar = "علبة هدايا"
    listed.save()
    assert services.ensure_sale_template(listed).name == "علبة هدايا"
    assert ProductTemplate.objects.count() == 1


def test_variant_larger_than_the_sheet_has_no_price(box_design, wood):
    _make_listable(box_design)
    variant = box_design.variants.get()
    assert VariantEstimate.objects.get(variant=variant, material=wood).price is not None
    wood.sheet_width_mm, wood.sheet_height_mm = Decimal("105"), Decimal("105")  # يسع 95 بعد الهامش
    wood.save()
    variant.manual_price = Decimal("80")  # السعر اليدوي لا يبيع ما لا يُرصَّف
    variant.save()
    services.refresh_estimates(variant)
    assert VariantEstimate.objects.get(variant=variant, material=wood).price is None


def test_cart_takes_a_listed_design_at_the_server_price(client, listed, wood, material):
    variant = listed.variants.get()
    price = VariantEstimate.objects.get(variant=variant, material=wood).price

    refused = _add_design(client, listed, wood, acknowledged=False)
    assert refused.status_code == 422 and refused.json()["code"] == "size_not_acknowledged"
    assert _add_design(client, listed, material).json()["code"] == "not_for_sale"  # خامة بلا سعر
    assert _add_design(client, listed, wood, variant_code="zz").json()["code"] == "not_for_sale"
    assert (
        _json(
            client,
            "post",
            "/api/store/cart/design-items",
            {"design_slug": "nope", "material_id": wood.pk, "acknowledged": True},
        ).json()["code"]
        == "not_for_sale"
    )

    cart = _add_design(client, listed, wood, quantity=2).json()
    (line,) = cart["items"]
    assert line["design_slug"] == listed.slug and line["variant_code"] == variant.code
    assert line["name"] == "علبة هدية" and line["name_en"] == "Gift Box"
    assert Decimal(line["unit_price"]) == price and Decimal(cart["total"]) == 2 * price
    assert not line["needs_review"] and line["params"] == {}
    item = Order.objects.get().items.get()
    assert item.design_variant == variant and item.svg_sha256 == variant.svg_sha256
    assert "svg" not in json.dumps(cart) and variant.svg_sha256 not in json.dumps(cart)

    services.unlist_design(listed)
    assert _add_design(client, listed, wood).json()["code"] == "not_for_sale"


def test_checkout_refuses_design_whose_price_or_listing_changed(client, listed, wood, pay):
    variant = listed.variants.get()
    assert _add_design(client, listed, wood).status_code == 200
    variant.manual_price = Decimal("500")
    variant.save()
    services.refresh_estimates(variant)
    changed = _checkout(client)
    assert changed.status_code == 422 and changed.json()["code"] == "design_changed"

    variant.manual_price = None
    variant.save()
    services.refresh_estimates(variant)
    services.unlist_design(listed)
    assert _checkout(client).json()["code"] == "design_changed"
    services.list_design(listed)
    assert _checkout(client).status_code == 200


def test_design_order_is_paid_planned_cut_and_delivered(client, listed, wood, pay, staff_user):
    variant = listed.variants.get()
    estimate = VariantEstimate.objects.get(variant=variant, material=wood)
    order = _confirmed_design_order(client, pay, listed, wood, quantity=3)
    assert order.status == "confirmed"

    # السعة بزمن النسخة المقدَّر لا بتقدير مساحة القالب.
    expected = math.ceil(3 * float(estimate.total_seconds) * capacity_selectors.correction_factor() / 60)
    assert capacity_selectors.order_minutes(order.pk) == expected
    assert capacity_selectors.backlog_minutes() == [expected]

    (sheet,) = production_services.plan_sheets(material_id=wood.pk)
    placements = list(Placement.objects.filter(sheet=sheet))
    assert sorted(p.copy_index for p in placements) == [0, 1, 2]
    assert {(p.width_mm, p.height_mm) for p in placements} == {(Decimal("100.0"), Decimal("50.0"))}
    assert production_services.plan_sheets(material_id=wood.pk) == []

    client.force_login(staff_user)
    (row,) = client.get("/api/production/sheets").json()["items"]
    ready = variant.files.get(role=DesignFile.Role.READY_CUT)
    for placed in row["placements"]:
        assert placed["name"] == "علبة هدية" and placed["cut_file_url"] == f"/media/{ready.file.name}"
    assert client.get(row["placements"][0]["cut_file_url"]).status_code == 200
    (staff_item,) = client.get(f"/api/orders/{order.pk}").json()["items"]
    assert staff_item["name"] == "علبة هدية" and staff_item["template_slug"] == f"design-{listed.pk}"

    production_services.record_run(sheet_id=sheet.pk, request_id="run-1", duration_s=600, outcome="ok")
    for status in ("ready", "ready_for_pickup", "delivered"):
        order_services.transition(order_id=order.pk, to_status=status, actor=staff_user, system=True)
    order.refresh_from_db()
    assert order.status == "delivered"

    track = Client().get(f"/api/store/track/{order.tracking_token}").json()
    assert track["items"][0]["name"] == "علبة هدية" and track["items"][0]["variant_code"] == variant.code
    # تصميم عليه طلب لا يُحذف ولا تُحذف نسخته.
    with pytest.raises(ProtectedError):
        listed.delete()


def test_multi_part_variant_plans_a_piece_per_part_and_rotates_to_fit(client, listed, wood, pay, staff_user):
    variant = listed.variants.get()
    variant.analysis["parts"] = [
        {"name": "side.svg", "width_mm": 100.0, "height_mm": 50.0},
        {"name": "lid.svg", "width_mm": 60.0, "height_mm": 300.0},  # أطول من اللوح: يُدار
    ]
    variant.save()
    wood.sheet_height_mm = Decimal("200")  # 600 × 200: يسع 590 × 190
    wood.save()
    assert selectors.fits_material(variant, wood)
    order = _confirmed_design_order(client, pay, listed, wood, quantity=2)

    estimate = VariantEstimate.objects.get(variant=variant, material=wood)
    factor = capacity_selectors.correction_factor()
    assert capacity_selectors.order_minutes(order.pk) == math.ceil(
        2 * float(estimate.total_seconds) * factor / 60
    )

    production_services.plan_sheets(material_id=wood.pk)
    sizes = {p.copy_index: (p.width_mm, p.height_mm) for p in Placement.objects.all()}
    assert sizes == {
        0: (Decimal("100.0"), Decimal("50.0")),
        1: (Decimal("300.0"), Decimal("60.0")),
        2: (Decimal("100.0"), Decimal("50.0")),
        3: (Decimal("300.0"), Decimal("60.0")),
    }
    # الجزء بلا ملف قص جاهز رابطه فارغ، ولا يأخذ ملف جزء آخر.
    assert selectors.cut_file_urls(variant) == ["", ""]
    order_services.transition(order_id=order.pk, to_status="in_production", actor=staff_user)
    with pytest.raises(order_services.OrderError, match="4"):  # بقيت أربع قطع لم تُقصّ
        order_services.transition(order_id=order.pk, to_status="ready", actor=staff_user)


# ---- التخصيص: نص تضيفه الورشة يدويًّا قبل القص (الطلب 3) ----

NAME_FIELD = [{"name": "name", "type": "text", "label": "الاسم", "label_en": "Name", "max_length": 12}]


@pytest.fixture
def personal(box_design):
    box_design.personalization = NAME_FIELD
    box_design.save()
    _make_listable(box_design)
    return services.list_design(box_design)


def test_approval_allows_one_text_field_only(box_design):
    for bad in (
        NAME_FIELD + [{"name": "line2", "type": "text", "label": "س", "label_en": "L"}],
        [{"name": "size", "type": "int", "label": "حجم", "label_en": "Size"}],
    ):
        box_design.personalization = bad
        with pytest.raises(services.DesignError, match="حقل نص واحد"):
            services.approve(box_design)


def test_detail_exposes_fields_and_template_carries_the_schema(client, personal, wood):
    assert client.get(f"/api/store/designs/{personal.slug}").json()["fields"] == NAME_FIELD
    assert personal.product_template.param_schema == NAME_FIELD


def test_personalized_design_keeps_text_on_the_item_and_shows_it_to_the_workshop(
    client, personal, wood, pay, staff_user
):
    missing = _add_design(client, personal, wood)
    assert missing.status_code == 422 and missing.json()["fields"]["name"]["code"] == "required"
    long = _add_design(client, personal, wood, params={"name": "ا" * 13})
    assert long.status_code == 422 and long.json()["fields"]["name"]["code"] == "too_long"
    unknown = _add_design(client, personal, wood, params={"name": "سارة", "x": "y"})
    assert unknown.status_code == 422 and unknown.json()["fields"]["x"]["code"] == "unknown_field"
    assert not Order.objects.filter(items__isnull=False).exists()

    cart = _add_design(client, personal, wood, params={"name": "  سارة   علي "}).json()
    (line,) = cart["items"]
    assert line["params"] == {"name": "سارة علي"} and not line["needs_review"]

    assert _checkout(client).status_code == 200
    payment = Payment.objects.latest("id")
    assert _notify(client, pay, payment).json()["outcome"] == "confirmed"
    production_services.plan_sheets(material_id=wood.pk)
    client.force_login(staff_user)
    (row,) = client.get("/api/production/sheets").json()["items"]
    assert row["placements"][0]["personalization"] == [{"label": "الاسم", "value": "سارة علي"}]


def test_design_without_fields_takes_no_text_and_shows_none(client, listed, wood):
    assert client.get(f"/api/store/designs/{listed.slug}").json()["fields"] == []
    refused = _add_design(client, listed, wood, params={"name": "سارة"})
    assert refused.status_code == 422 and refused.json()["fields"]["name"]["code"] == "unknown_field"


def test_offensive_text_is_refused_and_divine_name_waits_in_the_review_queue(client, personal, wood, pay):
    offensive = _add_design(client, personal, wood, params={"name": "كلب"})
    assert offensive.status_code == 422 and offensive.json()["fields"]["name"]["code"] == "offensive"
    religious = _add_design(client, personal, wood, params={"name": "بسم الله"})
    assert (
        religious.status_code == 422 and religious.json()["fields"]["name"]["code"] == "religious_not_allowed"
    )

    cart = _add_design(client, personal, wood, params={"name": "عبدالله"}).json()
    (line,) = cart["items"]
    assert line["needs_review"] and cart["needs_review"]
    assert Order.objects.get().items.get().review_reasons == ["divine_name"]


def test_checkout_refuses_text_the_design_no_longer_accepts(client, personal, wood, pay):
    assert _add_design(client, personal, wood, params={"name": "سارة"}).status_code == 200
    personal.personalization = [{**NAME_FIELD[0], "max_length": 3}]
    personal.save()
    services.ensure_sale_template(personal)
    changed = _checkout(client)
    assert changed.status_code == 422 and changed.json()["code"] == "design_changed"
