"""كتابة فهرس التصاميم: الاستيراد والتحليل والتقدير والاعتماد. كل عملية idempotent وتُسجَّل في سجل التدقيق."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from decimal import Decimal
from functools import partial
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.catalog import domain as catalog_domain
from apps.catalog.models import Calibration, Material, ProductTemplate
from apps.core.services import record_audit

from . import estimate as estimating
from . import svg
from .models import Design, DesignFile, DesignPack, DesignSource, DesignVariant, VariantEstimate

ALTERNATE_FORMATS = {".dxf", ".eps", ".pdf", ".cdr", ".ai"}
IMAGE_FORMATS = {".png", ".jpg", ".jpeg", ".webp"}
IGNORED = {"desktop.ini", "thumbs.db", ".ds_store"}
_VARIANT_NAME = re.compile(r"^(?P<name>.*?\S)\s*-\s*(?P<code>\d{1,3})$")
_LISTING = re.compile(r"^(?P<title>.+?)-(?P<listing>\d{6,})$")
_INSTRUCTIONS = re.compile(r"size\s*check|lightburn", re.IGNORECASE)
_SIZE_REFERENCE = re.compile(r"size\s*preview", re.IGNORECASE)


class DesignError(ValueError):
    pass


@dataclass
class ImportReport:
    created: list[DesignVariant] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def split_variant_name(folder_name: str) -> tuple[str, str]:
    """«Personalised Baby Milestone Bank-03» → («Personalised Baby Milestone Bank»، «03»)."""
    m = _VARIANT_NAME.match(folder_name.strip())
    return (m.group("name"), m.group("code")) if m else (folder_name.strip(), "")


def classify(path: Path, variant_stem: str) -> str | None:
    """دور الملف في النسخة، أو «instructions» لملف تعليمات المصدر، أو None لما يُتجاهل."""
    name, ext = path.name.lower(), path.suffix.lower()
    if name in IGNORED:
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
    if ext == ".png" and path.stem.lower() == variant_stem.lower():
        return DesignFile.Role.CUT_LAYOUT
    return DesignFile.Role.COVER


def _variant_folders(root: Path) -> list[Path]:
    folders = [p for p in [root, *sorted(root.rglob("*"))] if p.is_dir() and any(p.glob("*.svg"))]
    if not folders:
        raise DesignError(f"لا ملف SVG في {root}")
    return folders


def _pack_for(source: DesignSource, folder: Path, root: Path, listing: str | None) -> DesignPack | None:
    for candidate in [folder, *folder.parents]:
        m = _LISTING.match(candidate.name)
        if m and (listing is None or m.group("listing") == listing):
            pack, _ = DesignPack.objects.get_or_create(
                source=source,
                listing_id=m.group("listing"),
                defaults={"title": m.group("title").replace("-", " ")},
            )
            return pack
        if candidate == root.parent:
            break
    if listing:
        pack, _ = DesignPack.objects.get_or_create(
            source=source, listing_id=listing, defaults={"title": listing}
        )
        return pack
    return None


def _original_svg(folder: Path) -> Path:
    svgs = sorted(folder.glob("*.svg"))
    return next((p for p in svgs if p.stem.lower() == folder.name.lower()), svgs[0])


@transaction.atomic
def _import_variant(
    source: DesignSource, folder: Path, root: Path, listing: str | None, actor
) -> DesignVariant | str:
    original = _original_svg(folder)
    data = original.read_bytes()
    digest = _sha256(data)
    if existing := DesignVariant.objects.filter(svg_sha256=digest).first():
        return f"{folder.name}: مستورد من قبل ({existing})"
    name, code = split_variant_name(folder.name)
    design, _ = Design.objects.get_or_create(
        source=source, name_original=name, defaults={"pack": _pack_for(source, folder, root, listing)}
    )
    if DesignVariant.objects.filter(design=design, code=code).exists():
        return f"{folder.name}: للتصميم نسخة بالرمز «{code}» ببصمة أخرى؛ لم تُستورد"
    variant = DesignVariant.objects.create(
        design=design, code=code, folder_path=str(folder), svg_sha256=digest
    )

    for path in sorted(folder.iterdir()):
        if not path.is_file():
            continue
        role = classify(path, folder.name)
        if role is None:
            continue
        if role == DesignFile.Role.ORIGINAL and path != original:
            role = DesignFile.Role.ALTERNATE
        content = data if path == original else path.read_bytes()
        file_digest = _sha256(content)
        if role == "instructions":
            if not source.instructions:
                source.instructions.save(f"{file_digest[:16]}{path.suffix.lower()}", ContentFile(content))
            continue
        row = DesignFile(
            variant=variant,
            role=role,
            fmt=path.suffix.lower().lstrip("."),
            name=path.name,
            size_bytes=len(content),
            sha256=file_digest,
        )
        if role == DesignFile.Role.ALTERNATE:
            row.external_path = str(path)  # الصيغ الكبيرة تبقى مكانها (قرار المالك 2026-11-20)
        else:
            row.file.save(f"{file_digest[:16]}{path.suffix.lower()}", ContentFile(content), save=False)
        row.save()
    record_audit(
        action="designs.variant.import",
        actor=actor,
        target=f"variant:{variant.pk}",
        payload={"folder": str(folder)},
    )
    return variant


def import_folder(
    *, root: Path, source: DesignSource, listing: str | None = None, actor=None
) -> ImportReport:
    """يستورد كل مجلد فيه SVG تحت `root`. يُعاد تشغيله بأمان: النسخة المعروفة ببصمتها تُتخطّى."""
    report = ImportReport()
    for folder in _variant_folders(root):
        result = _import_variant(source, folder, root, listing, actor)
        if isinstance(result, str):
            report.skipped.append(result)
        else:
            report.created.append(result)
    return report


def _original_bytes(variant: DesignVariant) -> bytes:
    original = variant.files.filter(role=DesignFile.Role.ORIGINAL).exclude(file="").first()
    if original is None:
        raise DesignError("لا ملف أصل مرفوع للنسخة")
    with original.file.open("rb") as handle:
        return handle.read()


@transaction.atomic
def analyze_variant(variant: DesignVariant, *, actor=None) -> DesignVariant:
    """يقرأ الأصل، ويحفظ التحليل والنسخة الجاهزة للقص، ثم يحدّث التقديرات. إعادته تستبدل نتيجته السابقة."""
    color_key = variant.design.source.color_key
    try:
        data = _original_bytes(variant)
        analysis = svg.analyze(data, color_key)
        ready = svg.ready_to_cut(data, color_key)
    except (svg.SvgError, DesignError) as exc:
        variant.analysis, variant.analysis_error, variant.analyzed_at = {}, str(exc), timezone.now()
        variant.save(update_fields=["analysis", "analysis_error", "analyzed_at", "updated_at"])
        return variant

    variant.analysis = analysis.as_json()
    variant.analysis["outer_area_mm2"] = {
        kind: round(svg.outer_area_mm2(analysis, kind), 1)
        for kind in {g["material"] for g in analysis.operations.values()}
    }
    variant.sheet_width_mm = Decimal(str(round(analysis.width_mm, 1)))
    variant.sheet_height_mm = Decimal(str(round(analysis.height_mm, 1)))
    variant.analysis_error, variant.analyzed_at = "", timezone.now()
    variant.save()

    _replace_ready_cut(variant, ready)
    refresh_estimates(variant)
    record_audit(action="designs.variant.analyze", actor=actor, target=f"variant:{variant.pk}")
    return variant


def _replace_ready_cut(variant: DesignVariant, ready: bytes) -> None:
    """النتيجة نفسها تُبقي الملف القائم؛ وإلا يُستبدل، والملف القديم يُحذف من المخزن بعد ثبوت المعاملة لا قبلها."""
    digest = _sha256(ready)
    old = list(variant.files.filter(role=DesignFile.Role.READY_CUT))
    if len(old) == 1 and old[0].sha256 == digest:
        return
    for row in old:
        storage, name = row.file.storage, row.file.name
        row.delete()
        if name:
            transaction.on_commit(partial(storage.delete, name))
    row = DesignFile(
        variant=variant,
        role=DesignFile.Role.READY_CUT,
        fmt="svg",
        name=f"{Path(variant.folder_path).name}-ready.svg",
        size_bytes=len(ready),
        sha256=digest,
    )
    row.file.save(f"{digest[:16]}.svg", ContentFile(ready), save=False)
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
    """تقدير لكل مادة فعّالة من نوع تطلبه النسخة؛ ما لم يعد ينطبق يُحذف."""
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
