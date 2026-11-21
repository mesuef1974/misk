"""الكتالوج العام والمصمِّم: تحويل النص إلى مسارات، والمولّدات، وكشف النص، وحدود الحروف، والمسارات العامة."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from apps.catalog import designer, generators, services, text_policy, typeset
from apps.catalog.models import Calibration

SEED = Path(__file__).resolve().parents[1] / "apps" / "catalog" / "seed" / "catalog.json"
CASE_SCHEMA = [
    {"name": "النمط", "type": "choice", "choices": ["اسم", "حرفان"]},
    {"name": "النص", "type": "text", "max_length": 20},
]
CARD_SCHEMA = [
    {"name": "الاسم", "type": "text", "max_length": 30},
    {"name": "العبارة", "type": "text", "max_length": 60, "required": False},
    {"name": "الخط", "type": "choice", "choices": ["كايرو", "المراي"]},
]


@pytest.fixture
def case(db):
    return services.upsert_template(
        slug="case",
        name="كفر جلد",
        name_en="Leather case",
        generator="case_name",
        width_mm=Decimal("72"),
        height_mm=Decimal("150"),
        base_price=Decimal("85.00"),
        param_schema=CASE_SCHEMA,
        material_kinds=["leather"],
    )


@pytest.fixture
def plaque(db):
    return services.upsert_template(
        slug="plaque",
        name="لوحة معلّقة",
        generator="arched_card",
        width_mm=Decimal("90"),
        height_mm=Decimal("130"),
        param_schema=CARD_SCHEMA,
        allows_religious_text=True,
    )


def _calibrate(material, min_line: str, day: int = 17) -> Calibration:
    return services.record_calibration(
        material=material,
        operation="engrave",
        power_pct=31,
        speed_mm_s=Decimal("200"),
        min_line_mm=Decimal(min_line),
        measured_on=date(2026, 11, day),
    )


NAME = {"النمط": "اسم", "النص": "نورة"}


# ---------- تحويل النص إلى مسارات ----------


@pytest.mark.parametrize("font", sorted(typeset.FONTS))
def test_outline_shapes_arabic_latin_and_marks(font):
    shape = typeset.outline("مُحَمَّد Noora ٢٠٢٧", font)
    minx, miny, maxx, maxy = shape.bounds
    assert maxx - minx > 3 and miny < 0 < maxy  # فوق خط القاعدة وتحته، بوحدة الإم
    assert 0.03 < typeset.stroke_em(font) < 0.2


def test_arabic_is_joined_not_isolated_letters():
    # الوصل يقصّر الكلمة: مجموع عرض الحروف مفردة أكبر من عرضها موصولة.
    assert typeset.measure("نورة") < sum(typeset.measure(ch) for ch in "نورة")


def test_visual_runs_keep_latin_left_to_right_inside_arabic_line():
    # ترتيب العرض من اليسار: اللاتيني كما كُتب، ثم العربي مقطعًا واحدًا يُشكَّل بترتيبه المنطقي.
    assert typeset._visual_runs("نورة Noora") == [("Noora ", "ltr"), ("نورة", "rtl")]


def test_missing_glyph_is_an_error_not_a_box():
    with pytest.raises(typeset.TypesetError):
        typeset.outline("نور 😀")


# ---------- كشف النص ----------


@pytest.mark.parametrize(
    "text",
    ["بسم الله", "بِسْمِ اللَّهِ الرَّحْمَنِ", "ﷲ", "﷽", "الله", "والله", "ا ل ل ه", "ما شاء الله", "ماشاءالله"]
    + ["Allah", "Bismillah", "SubhanAllah", "لا إله إلا الله", "الحمد لله", "آية الكرسي"],
)
def test_religious_text_is_detected(text):
    verdict = text_policy.inspect(text)
    assert verdict.religious and verdict.needs_review and not verdict.divine_name


@pytest.mark.parametrize("text", ["عبدالله", "عبد الله", "سيف الله", "نصرالله", "Abdullah", "Abdallah"])
def test_divine_name_inside_personal_name_goes_to_review_only(text):
    verdict = text_policy.inspect(text)
    assert verdict.divine_name and verdict.needs_review and not verdict.religious


@pytest.mark.parametrize("text", ["نورة", "آية", "Noora", "عبدالعزيز", "مريم ٢٠٢٧", "سلطان", ""])
def test_ordinary_names_pass(text):
    assert text_policy.inspect(text) == text_policy.Verdict()


@pytest.mark.parametrize("text", ["يا كلب", "الحمار", "FUCK", "حـمـار"])
def test_offensive_words_are_detected(text):
    assert text_policy.inspect(text).offensive


def test_offensive_matches_whole_words_only():
    assert not text_policy.inspect("كلبشة Scunthorpe").offensive


# ---------- المولّدات ----------


def test_every_seed_template_has_a_generator_and_known_fonts():
    for row in json.loads(SEED.read_text(encoding="utf-8"))["templates"]:
        assert row["generator"] in generators.GENERATORS, row["slug"]
        for field in row["param_schema"]:
            if field["name"] == generators.FONT_FIELD:
                assert set(field["choices"]) == set(generators.FONT_CHOICES)
    assert set(generators.FONT_CHOICES.values()) <= set(typeset.FONTS)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("generator", "schema", "params"),
    [
        (
            "arched_card",
            CARD_SCHEMA,
            {"الاسم": "عبدالعزيز ونورة", "العبارة": "٢٠ . ٣ . ٢٠٢٧", "الخط": "المراي"},
        ),
        ("letter_keychain", [{"name": "الحرف", "type": "text", "max_length": 1}], {"الحرف": "ن"}),
        (
            "jar_lid",
            [
                {"name": "الاسم", "type": "text", "max_length": 24},
                {"name": "القطر مم", "type": "int", "min": 50, "max": 100},
            ],
            {"الاسم": "Noora نورة", "القطر مم": 80},
        ),
        ("case_name", CASE_SCHEMA, {"النمط": "حرفان", "النص": "ن ع"}),
    ],
)
def test_generators_render_paths_only(material, calibration, generator, schema, params):
    template = services.upsert_template(
        slug=generator, name=generator, generator=generator, width_mm=Decimal("72"), height_mm=Decimal("110"),
        param_schema=schema,
    )  # fmt: skip
    rendered = designer.render(template, material, params)
    assert rendered.svg.startswith("<svg") and 'id="engrave"' in rendered.svg
    assert "<text" not in rendered.svg and "<script" not in rendered.svg
    assert not any(str(value) in rendered.svg for value in params.values() if isinstance(value, str))
    assert rendered.width_mm > 0 and rendered.height_mm > 0
    if generator == "jar_lid":
        assert rendered.width_mm == 80.0  # القطر من الحقل لا من القالب


@pytest.mark.django_db
def test_render_is_deterministic_and_fingerprinted(case, material, calibration):
    first = designer.render(case, material, NAME)
    from django.core.cache import cache

    cache.clear()
    second = designer.render(case, material, {"النص": " نورة ", "النمط": "اسم"})
    assert first.sha256 == second.sha256 and len(first.sha256) == 64
    assert designer.render(case, material, {**NAME, "النص": "نور"}).sha256 != first.sha256


# ---------- قواعد المصمِّم ----------


@pytest.mark.django_db
def test_religious_text_rejected_with_suggestion_on_plain_template(case, plaque, material, calibration):
    with pytest.raises(designer.DesignRejectedError) as info:
        designer.render(case, material, {**NAME, "النص": "بسم الله"})
    assert info.value.errors == {"النص": "religious_not_allowed"}
    assert info.value.suggestions == ["plaque"]


@pytest.mark.django_db
def test_religious_text_allowed_template_needs_review(plaque, material, calibration):
    rendered = designer.render(plaque, material, {"الاسم": "ما شاء الله", "الخط": "كايرو"})
    assert rendered.needs_review and rendered.review_reasons == ["religious_text"]


@pytest.mark.django_db
def test_personal_name_with_divine_name_is_allowed_but_reviewed(case, material, calibration):
    rendered = designer.render(case, material, {**NAME, "النص": "عبدالله"})
    assert rendered.needs_review and rendered.review_reasons == ["divine_name"]
    assert not designer.render(case, material, NAME).needs_review


@pytest.mark.django_db
def test_offensive_text_rejected_even_where_religious_allowed(plaque, material, calibration):
    with pytest.raises(designer.DesignRejectedError) as info:
        designer.render(plaque, material, {"الاسم": "حمار", "الخط": "كايرو"})
    assert info.value.errors == {"الاسم": "offensive"}


@pytest.mark.django_db
def test_text_thinner_than_calibration_is_rejected(case, material, calibration):
    long_name = {**NAME, "النص": "عبدالرحمن بن سلطان"}
    assert designer.render(case, material, long_name).text_sizes["النص"] > 0
    _calibrate(material, "0.90")  # أحدث معايرة تحكم: خامة لا تحفر خطًّا أرفع من 0.9 مم
    with pytest.raises(designer.DesignRejectedError) as info:
        designer.render(case, material, long_name)
    assert info.value.errors == {"النص": "too_small"}
    assert designer.render(case, material, NAME).text_sizes["النص"] > 0  # الاسم القصير ما زال يُحفر


@pytest.mark.django_db
def test_monogram_takes_two_letters_and_unsupported_chars_are_named(case, material, calibration):
    with pytest.raises(designer.DesignRejectedError) as info:
        designer.render(case, material, {"النمط": "حرفان", "النص": "نور"})
    assert info.value.errors == {"النص": "two_letters"}
    with pytest.raises(designer.DesignRejectedError) as info:
        designer.render(case, material, {**NAME, "النص": "نور 😀"})
    assert info.value.errors == {"النص": "unsupported_char"}


@pytest.mark.django_db
def test_material_must_match_kind_and_have_engrave_calibration(case, material, name_tag):
    with pytest.raises(designer.DesignUnavailableError) as info:
        designer.render(case, material, NAME)  # جلد بلا معايرة
    assert info.value.code == "material_not_offered"
    _calibrate(material, "0.40")
    assert designer.render(case, material, NAME).svg
    wood = services.upsert_material(name="خشب", kind="wood", thickness_mm=Decimal("3"))
    _calibrate(wood, "0.40")
    with pytest.raises(designer.DesignUnavailableError):
        designer.render(case, wood, NAME)  # الكفر جلد فقط
    with pytest.raises(designer.DesignUnavailableError) as info:
        designer.render(name_tag, material, {"text": "نور"})
    assert info.value.code == "no_generator"


@pytest.mark.django_db
def test_limits_shrink_with_coarser_calibration(case, plaque, material, calibration):
    fine = {(row.when["النمط"]): row for row in designer.limits(case, material)}
    assert fine["حرفان"].max_chars == 2 and 2 < fine["اسم"].max_chars <= 20
    by_font = {row.when["الخط"]: row for row in designer.limits(plaque, material) if row.field == "الاسم"}
    assert set(by_font) == {"كايرو", "المراي"}
    _calibrate(material, "0.80")
    coarse = {(row.when["النمط"]): row for row in designer.limits(case, material)}
    assert coarse["اسم"].max_chars < fine["اسم"].max_chars
    assert coarse["اسم"].min_text_height_mm > fine["اسم"].min_text_height_mm


def test_material_kinds_are_validated(db):
    from apps.catalog import domain

    with pytest.raises(domain.ParamError):
        services.upsert_template(
            slug="x", name="x", generator="case_name", width_mm=Decimal("10"), height_mm=Decimal("10"),
            param_schema=[], material_kinds=["stone"],
        )  # fmt: skip


# ---------- المسارات العامة ----------


def _post(client, slug, body, **extra):
    return client.post(
        f"/api/store/templates/{slug}/preview",
        data=json.dumps(body),
        content_type="application/json",
        **extra,
    )


@pytest.mark.django_db
def test_store_catalog_is_public_and_hides_internals(client, case, material, calibration):
    rows = client.get("/api/store/templates").json()
    assert [row["slug"] for row in rows] == ["case"]
    assert "generator" not in rows[0] and rows[0]["name_en"] == "Leather case"
    detail = client.get("/api/store/templates/case").json()
    assert [m["id"] for m in detail["materials"]] == [material.pk]
    assert "sheet_cost" not in detail["materials"][0]
    res = client.get("/api/store/templates/none?lang=en")
    assert res.status_code == 404 and res.json()["detail"] == "Product not found"


@pytest.mark.django_db
def test_store_limits_endpoint(client, case, material, calibration):
    res = client.get(f"/api/store/templates/case/limits?material_id={material.pk}")
    assert res.status_code == 200 and {row["field"] for row in res.json()} == {"النص"}
    assert client.get("/api/store/templates/case/limits?material_id=999999").status_code == 422
    assert client.get("/api/store/templates/case/limits").status_code == 422


@pytest.mark.django_db
def test_store_preview_roundtrip_and_bilingual_errors(client, case, plaque, material, calibration):
    res = _post(client, "case", {"material_id": material.pk, "params": NAME})
    assert res.status_code == 200
    body = res.json()
    assert body["svg"].startswith("<svg") and body["needs_review"] is False and len(body["sha256"]) == 64

    res = _post(
        client, "case", {"material_id": material.pk, "params": {**NAME, "النص": "بسم الله"}, "lang": "en"}
    )
    assert res.status_code == 422
    body = res.json()
    assert body["fields"]["النص"]["code"] == "religious_not_allowed"
    assert body["fields"]["النص"]["message"].startswith("Out of respect") and body["suggestions"] == [
        "plaque"
    ]

    res = _post(client, "case", {"material_id": material.pk, "params": {"النمط": "اسم", "x": 1}})
    fields = res.json()["fields"]
    assert (
        res.status_code == 422
        and fields["النص"]["code"] == "required"
        and fields["x"]["code"] == "unknown_field"
    )
    assert fields["النص"]["message"] == "مطلوب"

    res = _post(
        client, "case", {"material_id": material.pk, "params": {**NAME, "النص": "ن" * 21}, "lang": "en"}
    )
    assert res.json()["fields"]["النص"] == {"code": "too_long", "message": "Text is longer than allowed"}
    assert _post(client, "case", {"material_id": 999999, "params": NAME}).status_code == 422
    assert _post(client, "nope", {"material_id": material.pk, "params": NAME}).status_code == 404
    assert (
        _post(client, "case", {"material_id": material.pk, "params": NAME, "lang": "fr"}).status_code == 422
    )


@pytest.mark.django_db
def test_store_preview_is_rate_limited_per_client_address(client, case, material, calibration, settings):
    settings.TRUSTED_PROXY_COUNT = 1
    body = {"material_id": material.pk, "params": NAME}
    codes = [_post(client, "case", body, HTTP_X_FORWARDED_FOR="203.0.113.7").status_code for _ in range(31)]
    assert codes[:30] == [200] * 30 and codes[30] == 429
    # ترويسة يكتبها العميل قبل خانة الوكيل الموثوق لا تفتح عدّادًا جديدًا.
    assert _post(client, "case", body, HTTP_X_FORWARDED_FOR="198.51.100.1, 203.0.113.7").status_code == 429
    assert _post(client, "case", body, HTTP_X_FORWARDED_FOR="203.0.113.8").status_code == 200
    # التصفح له عدّاده، فلا يحجبه استنفاد المعاينة.
    assert client.get("/api/store/templates", HTTP_X_FORWARDED_FOR="203.0.113.7").status_code == 200
