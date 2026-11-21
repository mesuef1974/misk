import math
import zipfile
from datetime import date
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from apps.catalog import services as catalog_services
from apps.catalog.models import ProductTemplate
from apps.core.models import AuditLog
from apps.designs import estimate, scan, services, svg
from apps.designs.models import Design, DesignFile, DesignSource, VariantEstimate

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
    assert panels.analysis["assumed"] == {"#ff0000": "cut:wood"}
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
