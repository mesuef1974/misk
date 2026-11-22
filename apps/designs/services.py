"""كتابة فهرس التصاميم: الاستيراد والتحليل والتقدير والاعتماد. كل عملية idempotent وتُسجَّل في سجل التدقيق."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from decimal import Decimal
from functools import partial
from pathlib import Path, PurePosixPath

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.catalog import domain as catalog_domain
from apps.catalog.models import Calibration, Material, ProductTemplate
from apps.core.services import record_audit

from . import estimate as estimating
from . import pricing, scan, selectors, svg
from .models import (
    Design,
    DesignFile,
    DesignPack,
    DesignPricing,
    DesignSource,
    DesignVariant,
    VariantEstimate,
)

ALTERNATE_FORMATS = {".dxf", ".eps", ".pdf", ".cdr", ".ai", ".dwg"}
IMAGE_FORMATS = {".png", ".jpg", ".jpeg", ".webp"}
IGNORED = {"desktop.ini", "thumbs.db", ".ds_store"}
MIN_SALE_SCALE_PERCENT = Decimal("10")
_INSTRUCTIONS = re.compile(r"size\s*check|lightburn", re.IGNORECASE)
_SIZE_REFERENCE = re.compile(r"size\s*preview", re.IGNORECASE)
# قرار المالك 2026-11-21: مصدر عام لحزم البائعين المتفرقين، والملف أحادي اللون فيه قص على الخشب.
# والمتعدد الألوان بعُرف البائعين: الأحمر قص، والأزرق علام، والأسود حفر، وألوان تعبئة الطبقات قص.
_CUT = ("#ff0000", "#ed1c24", "#fe0002", "#e94e1b")
_LAYER_FILLS = ("#a88671", "#c4a695", "#f0b2ac", "#ffffff", "#cfb69f", "#6a3814", "#fefefe")
_SCORE = ("#0000ff", "#2b3990", "#27aae1", "#00aeef")
_ENGRAVE = ("#000000", "#2b2a29", "#383746")
DEFAULT_COLOR_KEY = {
    svg.SINGLE_COLOR: {"operation": "cut", "material": "wood"},
    **{c: {"operation": "cut", "material": "wood"} for c in _CUT + _LAYER_FILLS},
    **{c: {"operation": "score", "material": "wood"} for c in _SCORE},
    **{c: {"operation": "engrave", "material": "wood"} for c in _ENGRAVE},
}

split_variant_name = scan.split_variant_name


class DesignError(ValueError):
    pass


@dataclass
class ImportReport:
    created: list[DesignVariant] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def classify(name: str, stems: set[str]) -> str | None:
    """دور الملف في النسخة، أو «instructions» لملف تعليمات المصدر، أو None لما يُتجاهل.

    `stems` أسماء أجزاء النسخة واسم مجلدها بأحرف صغيرة: صورة PNG باسم أحدها معاينة قصه.
    """
    path = PurePosixPath(name)
    lower, ext = path.name.lower(), path.suffix.lower()
    if lower in IGNORED:
        return None
    if ext == ".svg":
        return DesignFile.Role.ORIGINAL
    if ext in ALTERNATE_FORMATS:
        return DesignFile.Role.ALTERNATE
    if ext not in IMAGE_FORMATS:
        return None
    if _INSTRUCTIONS.search(path.stem):
        return "instructions"
    if _SIZE_REFERENCE.search(path.stem):
        return DesignFile.Role.SIZE_REFERENCE
    if ext == ".png" and path.stem.lower() in stems:
        return DesignFile.Role.CUT_LAYOUT
    return DesignFile.Role.COVER


@transaction.atomic
def ensure_source(name: str, *, actor=None) -> DesignSource:
    """المصدر بالاسم، أو مصدر جديد بترخيص «غير محدد» ومفتاح المفرد (`DEFAULT_COLOR_KEY`)."""
    source, created = DesignSource.objects.get_or_create(name=name, defaults={"color_key": DEFAULT_COLOR_KEY})
    if created:
        record_audit(action="designs.source.create", actor=actor, target=f"source:{source.pk}")
    return source


def _pack(source: DesignSource, pack: tuple[str, str] | None) -> DesignPack | None:
    if pack is None:
        return None
    listing, title = pack
    obj, _ = DesignPack.objects.get_or_create(source=source, listing_id=listing, defaults={"title": title})
    return obj


def _variant_digest(digests: list[str]) -> str:
    """بصمة النسخة: بصمة SVG الوحيد، أو بصمة بصمات أجزائها مرتّبة فلا يغيّرها ترتيب المسح."""
    return digests[0] if len(digests) == 1 else _sha256("\n".join(sorted(digests)).encode())


def _store(variant: DesignVariant, role: str, entry: scan.Entry, content: bytes, digest: str) -> None:
    row = DesignFile(
        variant=variant,
        role=role,
        fmt=entry.suffix.lstrip(".")[:8],
        name=entry.name[:255],
        size_bytes=len(content),
        sha256=digest,
    )
    if role == DesignFile.Role.ALTERNATE:
        row.external_path = entry.location[:500]  # الصيغ الكبيرة تبقى مكانها (قرار المالك 2026-11-20)
    else:
        row.file.save(f"{digest[:16]}{entry.suffix}", ContentFile(content), save=False)
    row.save()


@transaction.atomic
def _import_variant(source: DesignSource, plan: scan.VariantPlan, actor, report: ImportReport) -> None:
    label = plan.folder.location if len(plan.parts) > 1 else plan.parts[0].location
    try:
        parts = [(entry, entry.read()) for entry in plan.parts]
    except (scan.ScanError, OSError) as exc:
        report.skipped.append(f"{label}: {exc}")
        return
    digests = [_sha256(data) for _, data in parts]
    digest = _variant_digest(digests)
    if existing := DesignVariant.objects.filter(svg_sha256=digest).first():
        report.skipped.append(f"{label}: مستورد من قبل ({existing})")
        return
    design, _ = Design.objects.get_or_create(
        source=source,
        name_original=plan.name[:200],
        defaults={"pack": _pack(source, plan.pack), "category": plan.category[:80]},
    )
    if DesignVariant.objects.filter(design=design, code=plan.code).exists():
        report.skipped.append(f"{label}: للتصميم «{design}» نسخة بالرمز «{plan.code}» ببصمة أخرى؛ لم تُستورد")
        return
    variant = DesignVariant.objects.create(
        design=design, code=plan.code, folder_path=plan.folder.location[:500], svg_sha256=digest
    )

    seen: set[tuple[str, str]] = set()
    for (entry, data), file_digest in zip(parts, digests, strict=True):
        if (DesignFile.Role.ORIGINAL, file_digest) not in seen:
            seen.add((DesignFile.Role.ORIGINAL, file_digest))
            _store(variant, DesignFile.Role.ORIGINAL, entry, data, file_digest)
    stems = {e.stem.lower() for e in plan.parts} | {plan.folder.name.lower()}
    for entry in plan.files:
        role = classify(entry.name, stems)
        if role is None:
            continue
        if role == DesignFile.Role.ORIGINAL:
            role = DesignFile.Role.ALTERNATE  # نسخة الملف لآلة أخرى
        try:
            content = entry.read()
        except (scan.ScanError, OSError) as exc:
            report.notes.append(f"{entry.location}: {exc}")
            continue
        file_digest = _sha256(content)
        if role == "instructions":
            if not source.instructions:
                source.instructions.save(f"{file_digest[:16]}{entry.suffix}", ContentFile(content))
            continue
        if (role, file_digest) in seen:
            continue
        seen.add((role, file_digest))
        _store(variant, role, entry, content, file_digest)
    record_audit(
        action="designs.variant.import",
        actor=actor,
        target=f"variant:{variant.pk}",
        payload={"folder": plan.folder.location, "parts": [e.name for e in plan.parts]},
    )
    report.created.append(variant)


def import_folder(
    *,
    root: Path,
    source: DesignSource,
    listing: str | None = None,
    tree: bool = False,
    each_svg: list[Path] | tuple = (),
    actor=None,
) -> ImportReport:
    """يستورد كل مجلد فيه SVG تحت `root` وكل أرشيف zip لم يُفكّ (القواعد في `scan.plan`).

    يُعاد تشغيله بأمان: النسخة المعروفة ببصمتها تُتخطّى، وكل نسخة في معاملة مستقلة فلا يُسقط خطأ واحدة البقية.
    """
    try:
        result = scan.scan(root)
    except scan.ScanError as exc:
        raise DesignError(str(exc)) from exc
    plans = scan.plan(result, tree=tree, each_svg=each_svg, listing=listing)
    if not plans:
        raise DesignError(f"لا ملف SVG في {root}")
    report = ImportReport(notes=list(result.notes))
    for item in plans:
        _import_variant(source, item, actor, report)
    return report


def _read(row: DesignFile) -> bytes:
    with row.file.open("rb") as handle:
        return handle.read()


def _geometry(analysis: svg.Analysis) -> tuple:
    ops = sorted((k, g["count"], round(g["length_mm"])) for k, g in analysis.operations.items())
    return round(analysis.width_mm), round(analysis.height_mm), tuple(ops)


@transaction.atomic
def analyze_variant(variant: DesignVariant, *, actor=None) -> DesignVariant:
    """يقرأ أجزاء النسخة، ويحفظ تحليلها المجموع ونسخة جاهزة للقص لكل جزء، ثم يحدّث التقديرات.

    إعادته تستبدل نتيجته السابقة.
    """
    color_key = variant.design.source.color_key
    percent = float(variant.sale_scale_percent or 100)
    k = percent / 100
    rows = list(variant.files.filter(role=DesignFile.Role.ORIGINAL).exclude(file="").order_by("name", "pk"))
    try:
        if not rows:
            raise DesignError("لا ملف أصل مرفوع للنسخة")
        parts = []
        for row in rows:
            data = _read(row)
            parts.append(
                (row.name, svg.scaled(svg.analyze(data, color_key), k), svg.ready_to_cut(data, color_key, k))
            )
    except (svg.SvgError, DesignError) as exc:
        variant.analysis, variant.analysis_error, variant.analyzed_at = {}, str(exc), timezone.now()
        variant.save(update_fields=["analysis", "analysis_error", "analyzed_at", "updated_at"])
        return variant

    analyses = [analysis for _, analysis, _ in parts]
    combined = svg.combine(analyses)
    variant.analysis = combined.as_json()
    variant.analysis["outer_area_mm2"] = {
        kind: round(sum(svg.outer_area_mm2(a, kind) for a in analyses), 1)
        for kind in {g["material"] for g in combined.operations.values()}
    }
    if len(parts) > 1:
        variant.analysis["parts"] = [
            {"name": name, "width_mm": round(a.width_mm, 1), "height_mm": round(a.height_mm, 1)}
            for name, a, _ in parts
        ]
        # جزءان متطابقان هندسيًّا قد يكونان نسختين للملف نفسه فيتضاعف التقدير، أو لوحين مطلوبين معًا: يُراجعان.
        groups: dict[tuple, list[str]] = {}
        for name, a, _ in parts:
            groups.setdefault(_geometry(a), []).append(name)
        if same := [names for names in groups.values() if len(names) > 1]:
            variant.analysis["same_geometry"] = same
    if k != 1:
        variant.analysis["sale_scale_percent"] = percent
    variant.sheet_width_mm = Decimal(str(round(combined.width_mm, 1)))
    variant.sheet_height_mm = Decimal(str(round(combined.height_mm, 1)))
    variant.analysis_error, variant.analyzed_at = "", timezone.now()
    variant.save()

    _replace_ready_cut(
        variant, [(f"{PurePosixPath(name).stem}-ready.svg", ready) for name, _, ready in parts]
    )
    refresh_estimates(variant)
    record_audit(action="designs.variant.analyze", actor=actor, target=f"variant:{variant.pk}")
    return variant


def fit_to_sheet(variant: DesignVariant, *, actor=None) -> Decimal | None:
    """يضبط نسبة البيع على أكبر نسبة صحيحة يسع بها أصغرُ لوح فعّال من مادة النسخة مقاسَ ملفها، بالتدوير.

    يضبط النسبة وحدها؛ المقاس والتقدير وملف القص يتبعونها عند التحليل التالي. `None` = يسعه اللوح بمقاس الملف.
    """
    if not variant.sheet_width_mm or not variant.sheet_height_mm:
        raise DesignError("النسخة بلا مقاس: حلِّلها أولًا")
    # المقاس المحفوظ مقاس البيع المطبَّق في آخر تحليل، لا مقاس الملف.
    applied = Decimal(str(variant.analysis.get("sale_scale_percent", 100))) / 100
    short, long = sorted((variant.sheet_width_mm / applied, variant.sheet_height_mm / applied))
    sheets = [
        sorted((m.sheet_width_mm, m.sheet_height_mm))
        for m in Material.objects.filter(is_active=True, kind__in=selectors.material_kinds(variant))
    ]
    if not sheets:
        raise DesignError("لا مادة فعّالة من نوع مادة النسخة")
    ratio = min(min(sheet[0] / short, sheet[1] / long) for sheet in sheets)
    percent = None if ratio >= 1 else Decimal(int(ratio * 100))
    if percent is not None and percent < MIN_SALE_SCALE_PERCENT:
        raise DesignError(f"التصغير المطلوب دون {MIN_SALE_SCALE_PERCENT}٪ من مقاس الملف")
    if percent != variant.sale_scale_percent:
        variant.sale_scale_percent = percent
        variant.save(update_fields=["sale_scale_percent", "updated_at"])
        record_audit(
            action="designs.variant.sale_scale",
            actor=actor,
            target=f"variant:{variant.pk}",
            payload={"percent": None if percent is None else str(percent)},
        )
    return percent


def _replace_ready_cut(variant: DesignVariant, readies: list[tuple[str, bytes]]) -> None:
    """النتيجة نفسها تُبقي الملفات القائمة؛ وإلا تُستبدل، والقديمة تُحذف من المخزن بعد ثبوت المعاملة لا قبلها."""
    wanted = {_sha256(data): (name, data) for name, data in readies}
    old = list(variant.files.filter(role=DesignFile.Role.READY_CUT))
    if len(old) == len(wanted) and {row.sha256 for row in old} == wanted.keys():
        return
    for row in old:
        storage, stored = row.file.storage, row.file.name
        row.delete()
        if stored:
            transaction.on_commit(partial(storage.delete, stored))
    for digest, (name, data) in wanted.items():
        row = DesignFile(
            variant=variant,
            role=DesignFile.Role.READY_CUT,
            fmt="svg",
            name=name[:255],
            size_bytes=len(data),
            sha256=digest,
        )
        row.file.save(f"{digest[:16]}.svg", ContentFile(data), save=False)
        row.save()


def _settings_for(material: Material) -> dict[str, estimating.Setting]:
    latest: dict[str, estimating.Setting] = {}
    for cal in Calibration.objects.filter(material=material).order_by("-measured_on", "-id"):
        latest.setdefault(
            cal.operation,
            estimating.Setting(cal.speed_mm_s, cal.passes, cal.lines_per_cm, cal.pk),
        )
    return latest


@transaction.atomic
def refresh_estimates(variant: DesignVariant) -> list[VariantEstimate]:
    """تقدير وسعر لكل مادة فعّالة من نوع تطلبه النسخة؛ ما لم يعد ينطبق يُحذف."""
    rates = selectors.rates()
    operations = variant.analysis.get("operations", {})
    kinds = {g["material"] for g in operations.values()}
    areas = variant.analysis.get("outer_area_mm2", {})
    kept: list[VariantEstimate] = []
    for material in Material.objects.filter(is_active=True, kind__in=kinds):
        result = estimating.estimate(
            operations=operations,
            material_kind=material.kind,
            settings=_settings_for(material),
            material_area_mm2=areas.get(material.kind, 0.0),
            sheet_area_mm2=material.sheet_width_mm * material.sheet_height_mm,
            sheet_cost=material.sheet_cost,
        )
        if result is None:
            continue
        row, _ = VariantEstimate.objects.update_or_create(
            variant=variant,
            material=material,
            defaults={
                "seconds": result.seconds,
                "total_seconds": result.total_seconds,
                "complete": result.complete,
                "material_area_mm2": result.material_area_mm2,
                "material_cost": result.material_cost,
                "calibration_ids": result.calibration_ids,
                "price": pricing.price(
                    rates=rates,
                    material_cost=result.material_cost,
                    total_seconds=result.total_seconds,
                    complete=result.complete,
                    assembly_fee=variant.design.assembly_fee,
                    manual_price=variant.manual_price,
                ),
            },
        )
        kept.append(row)
    variant.estimates.exclude(pk__in=[row.pk for row in kept]).delete()
    return kept


@transaction.atomic
def approve(design: Design, *, actor=None) -> Design:
    missing = [
        label for label, value in (("الاسم العربي", design.name_ar), ("الفئة", design.category)) if not value
    ]
    if missing:
        raise DesignError("أكمل قبل الاعتماد: " + "، ".join(missing))
    if not design.variants.filter(analysis_error="", analyzed_at__isnull=False).exists():
        raise DesignError("لا نسخة محلَّلة بلا خطأ")
    try:
        design.personalization = catalog_domain.validate_schema(design.personalization)
    except catalog_domain.ParamError as exc:
        raise DesignError(f"حقول التخصيص: {exc}") from exc
    design.status = Design.Status.APPROVED
    design.save(update_fields=["personalization", "status", "updated_at"])
    record_audit(action="designs.design.approve", actor=actor, target=f"design:{design.pk}")
    return design


@transaction.atomic
def link_template(design: Design, template: ProductTemplate, *, actor=None) -> Design:
    """البيع يتوقف على الترخيص: لا ربط بقالب منتج إلا بترخيص تجاري لمصدر التصميم."""
    if design.source.license_kind != DesignSource.License.COMMERCIAL:
        raise DesignError(f"ترخيص «{design.source}» ليس تجاريًّا؛ لا يُربط التصميم بقالب للبيع")
    if design.status != Design.Status.APPROVED:
        raise DesignError("اعتمد التصميم قبل ربطه بقالب")
    design.product_template = template
    design.save(update_fields=["product_template", "updated_at"])
    record_audit(action="designs.design.link_template", actor=actor, target=f"design:{design.pk}")
    return design


def reprice_all() -> int:
    """يعيد تقدير كل نسخة محلَّلة وسعرها. يُستدعى من مهمة خلفية: يمرّ على الفهرس كله."""
    count = 0
    variants = DesignVariant.objects.filter(analyzed_at__isnull=False, analysis_error="")
    for variant in variants.select_related("design").iterator():
        refresh_estimates(variant)
        count += 1
    return count


@transaction.atomic
def save_pricing(
    *, minute_rate: Decimal, margin_pct: Decimal, round_to: Decimal = Decimal("5"), actor=None
) -> DesignPricing:
    """الصف الوحيد لإعداد التسعير. الأسعار تُعاد بعده بـ `tasks.reprice_all_async`."""
    row, _ = DesignPricing.objects.update_or_create(
        pk=1, defaults={"minute_rate": minute_rate, "margin_pct": margin_pct, "round_to": round_to}
    )
    record_audit(
        action="designs.pricing.save",
        actor=actor,
        target="pricing:1",
        payload={"minute_rate": str(minute_rate), "margin_pct": str(margin_pct), "round_to": str(round_to)},
    )
    return row


def _unique_slug(design: Design) -> str:
    base = slugify(design.name_en)[:70] or f"design-{design.pk}"
    taken = Design.objects.filter(slug=base).exclude(pk=design.pk).exists()
    return f"{base}-{design.pk}" if taken else base


@transaction.atomic
def list_design(design: Design, *, actor=None) -> Design:
    """ينشر التصميم في المتجر. إعادته لا تغيّر شيئًا، والرابط يثبت بعد أول نشر."""
    if missing := selectors.listing_blockers(design):
        raise DesignError("لا يُنشر، ينقصه: " + "، ".join(missing))
    if design.is_listed:
        return design
    design.slug = design.slug or _unique_slug(design)
    design.is_listed = True
    design.save(update_fields=["slug", "is_listed", "updated_at"])
    record_audit(action="designs.design.list", actor=actor, target=f"design:{design.pk}")
    return design


@transaction.atomic
def unlist_design(design: Design, *, actor=None) -> Design:
    if not design.is_listed:
        return design
    design.is_listed = False
    design.save(update_fields=["is_listed", "updated_at"])
    record_audit(action="designs.design.unlist", actor=actor, target=f"design:{design.pk}")
    return design
