"""مسح مجلد تصاميم وأرشيفاته، وتحويله إلى خطة نسخ: ما أجزاء كل نسخة، وما اسم تصميمها ورمزها وفئتها وحزمتها.

نقي بلا Django ولا قاعدة. الأرشيف يُقرأ عضوًا عضوًا ولا يُفكّ على القرص، فلا مسار يخرج عن مكانه، وكل عضو محدود
الحجم. القواعد في docs/designs-catalog.md (الاستيراد).
"""

from __future__ import annotations

import os
import re
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

MAX_MEMBER_BYTES = 200 * 1024 * 1024
ARCHIVE_SEP = "!/"
CODE_MAX = 16
SKIPPED_DIRS = {"__macosx"}
_LISTING = re.compile(r"^(?P<title>.+?)-(?P<listing>\d{6,})$")
_VARIANT_NAME = re.compile(r"^(?P<name>.*?\S)\s*-\s*(?P<code>\d{1,3})$")
# مجلد لا يسمّي التصميم: رقم نسخة، أو وعاء صيغة («SVG»، «Files»، «SVG-<الاسم>»)؛ الاسم عندها من الحزمة.
_GENERIC = re.compile(r"^(?:\d{1,3}|svgs?|files?|.+\sfiles?|svg[-_ ].+)$", re.IGNORECASE)
# نسخة الملف نفسه لآلة بعينها؛ تبقى صيغة بديلة ولا تُعدّ جزءًا، وإلا تضاعف التقدير.
_MACHINE = re.compile(r"glowforge|cricut|silhouette|xtool|lightburn|cameo", re.IGNORECASE)


class ScanError(ValueError):
    pass


@dataclass(frozen=True)
class Entry:
    """ملف على القرص أو عضو في أرشيف. `location` مساره، والعضو `<الأرشيف>!/<المسار داخله>`."""

    name: str
    location: str
    size: int
    archive: str = ""
    member: str = ""

    @property
    def suffix(self) -> str:
        return PurePosixPath(self.name).suffix.lower()

    @property
    def stem(self) -> str:
        return PurePosixPath(self.name).stem

    def read(self) -> bytes:
        if self.size > MAX_MEMBER_BYTES:
            raise ScanError(f"{self.name}: أكبر من {MAX_MEMBER_BYTES // 2**20} م.ب")
        if not self.archive:
            return Path(self.location).read_bytes()
        with zipfile.ZipFile(self.archive) as archive, archive.open(self.member) as handle:
            data = handle.read(MAX_MEMBER_BYTES + 1)  # الحجم المصرَّح قد يكذب؛ الحدّ على المقروء فعلًا
        if len(data) > MAX_MEMBER_BYTES:
            raise ScanError(f"{self.name}: أكبر من {MAX_MEMBER_BYTES // 2**20} م.ب")
        return data


@dataclass
class Folder:
    """مجلد فيه SVG. `chain` أسماء المجلدات من الجذر إليه، والأرشيف باسمه بلا `.zip`."""

    location: str
    chain: tuple[str, ...]
    entries: list[Entry]

    @property
    def name(self) -> str:
        return self.chain[-1]

    @property
    def svgs(self) -> list[Entry]:
        return [e for e in self.entries if e.suffix == ".svg"]


@dataclass
class ScanResult:
    folders: list[Folder] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class VariantPlan:
    folder: Folder
    name: str
    code: str
    category: str
    pack: tuple[str, str] | None  # (رقم القائمة، العنوان)
    parts: list[Entry]  # ملفات SVG التي تُقصّ كلها لنسخة واحدة
    files: list[Entry]  # بقية ملفاتها: صيغ بديلة وصور وتعليمات


def _skipped(name: str) -> bool:
    return name.lower() in SKIPPED_DIRS or name.startswith(".")


def _scan_archive(archive: Path, chain: tuple[str, ...], result: ScanResult) -> None:
    try:
        handle = zipfile.ZipFile(archive)
    except (zipfile.BadZipFile, OSError) as exc:
        result.notes.append(f"{archive.name}: أرشيف لا يُقرأ ({exc})")
        return
    groups: dict[str, list[Entry]] = {}
    with handle:
        for info in handle.infolist():
            if info.is_dir():
                continue
            member = PurePosixPath(info.filename)
            if any(_skipped(p) or p == ".." for p in member.parts):
                continue
            if info.flag_bits & 0x1:
                result.notes.append(f"{archive.name}: {info.filename} مشفّر؛ تُخطّي")
                continue
            if info.file_size > MAX_MEMBER_BYTES:
                result.notes.append(f"{archive.name}: {info.filename} أكبر من الحد؛ تُخطّي")
                continue
            groups.setdefault("/".join(member.parts[:-1]), []).append(
                Entry(
                    name=member.name,
                    location=f"{archive}{ARCHIVE_SEP}{info.filename}",
                    size=info.file_size,
                    archive=str(archive),
                    member=info.filename,
                )
            )
    found = False
    for directory, entries in sorted(groups.items()):
        folder = Folder(
            location=f"{archive}{ARCHIVE_SEP}{directory}",
            chain=(*chain, *directory.split("/")) if directory else chain,
            entries=sorted(entries, key=lambda e: e.name),
        )
        if folder.svgs:
            result.folders.append(folder)
            found = True
    if not found:
        result.notes.append(f"{archive.name}: لا SVG فيه؛ لم يُستورد")


def scan(root: Path) -> ScanResult:
    """كل مجلد فيه SVG تحت `root`، وكل أرشيف zip لم يُفكّ بجواره (مجلد باسمه). `root` نفسه قد يكون أرشيفًا."""
    result = ScanResult()
    if root.is_file():
        if root.suffix.lower() != ".zip":
            raise ScanError(f"ليس مجلدًا ولا أرشيف zip: {root}")
        _scan_archive(root, (root.stem,), result)
        return result

    directories = [root, *sorted(p for p in root.rglob("*") if p.is_dir())]
    for directory in directories:
        rel = directory.relative_to(root).parts
        if any(_skipped(p) for p in rel):
            continue
        entries = [
            Entry(name=p.name, location=str(p), size=p.stat().st_size)
            for p in sorted(directory.iterdir())
            if p.is_file()
        ]
        folder = Folder(location=str(directory), chain=(root.name, *rel), entries=entries)
        if folder.svgs:
            result.folders.append(folder)
        elif len(rel) == 2 and not any(directory.rglob("*.svg")):
            result.notes.append(f"{'/'.join(rel)}: لا SVG فيه؛ لم يُستورد")

    for archive in sorted(root.rglob("*.zip")):
        rel = archive.relative_to(root).parts
        if any(_skipped(p) for p in rel[:-1]):
            continue
        if archive.with_suffix("").is_dir():
            continue  # فُكّ بجواره فقُرئ مجلده؛ قراءته مرتين تكرّر الملفات البديلة
        _scan_archive(archive, (root.name, *rel[:-1], archive.stem), result)
    return result


def split_variant_name(folder_name: str) -> tuple[str, str]:
    """«Personalised Baby Milestone Bank-03» → («Personalised Baby Milestone Bank»، «03»)."""
    m = _VARIANT_NAME.match(folder_name.strip())
    return (m.group("name"), m.group("code")) if m else (folder_name.strip(), "")


def pack_of(chain: Iterable[str], listing: str | None = None) -> tuple[str, str] | None:
    """أقرب مجلد أو أرشيف اسمه «<العنوان>-<رقم القائمة>»، أو الرقم المعطى إن لم يوجد."""
    for part in reversed(tuple(chain)):
        m = _LISTING.match(part)
        if m and (listing is None or m.group("listing") == listing):
            return m.group("listing"), m.group("title").replace("-", " ")
    return (listing, listing) if listing else None


def _common_prefix(names: list[str]) -> str:
    words = [n.split(" ") for n in names]
    prefix: list[str] = []
    for column in zip(*words, strict=False):
        if len(set(column)) != 1:
            break
        prefix.append(column[0])
    return " ".join(prefix)


def _identity(folder: Folder, pack: tuple[str, str] | None, siblings: list[str]) -> tuple[str, str]:
    name = folder.name
    if m := _LISTING.match(name):
        return m.group("title").replace("-", " "), ""
    title = pack[1] if pack else None
    if title and _GENERIC.match(name):
        return title, name if name.isdigit() else ""
    if title and len(folder.chain) >= 2 and _GENERIC.match(folder.chain[-2]) and len(siblings) > 1:
        # «Files/Box 150 150 70 3mm» وأخواتها: نسخ تصميم الحزمة، ورمز كل منها ما يميّزها.
        if prefix := _common_prefix(siblings):
            return title, name[len(prefix) :].strip()[:CODE_MAX]
    return split_variant_name(name)


def _under(location: str, roots: list[str]) -> bool:
    """المجلد داخل أحد `roots`، أو الأرشيف الذي هو فيه أحدها أو داخل أحدها."""
    path = os.path.normcase(os.path.normpath(location.split(ARCHIVE_SEP)[0]))
    return any(path == r or path.startswith(r.rstrip(os.sep) + os.sep) for r in roots)


def plan(
    result: ScanResult,
    *,
    tree: bool = False,
    each_svg: Iterable[str | Path] = (),
    listing: str | None = None,
) -> list[VariantPlan]:
    """قرار المالك 2026-11-21: المجلد نسخة واحدة وكل SVG فيه جزء منها.

    - `tree`: المجلد الأول تحت الجذر فئة، وملفات SVG المفردة في الجذر أو في الفئة نفسها تصاميم مستقلة.
    - `each_svg`: مجلدات أو أرشيفات كل SVG فيها نسخة مستقلة (مجموعة لوحات يختار العميل إحداها).
    """
    roots = [os.path.normcase(os.path.normpath(str(p))) for p in each_svg]
    by_parent: dict[tuple[str, ...], list[str]] = {}
    for folder in result.folders:
        by_parent.setdefault(folder.chain[:-1], []).append(folder.name)

    plans: list[VariantPlan] = []
    for folder in result.folders:
        pack = pack_of(folder.chain, listing)
        category = folder.chain[1] if tree and len(folder.chain) > 1 else ""
        loose = tree and len(folder.chain) <= 2
        name, code = _identity(folder, pack, by_parent.get(folder.chain[:-1], []))
        if loose or _under(folder.location, roots):
            for svg in folder.svgs:
                companions = [
                    e for e in folder.entries if e.suffix != ".svg" and e.stem.lower() == svg.stem.lower()
                ]
                own_name, own_code = split_variant_name(svg.stem) if loose else (name, svg.stem[:CODE_MAX])
                plans.append(VariantPlan(folder, own_name, own_code, category, pack, [svg], companions))
            continue
        svgs = folder.svgs
        plain = [e for e in svgs if not _MACHINE.search(e.stem)]
        parts = plain or svgs
        files = [e for e in folder.entries if e not in parts]
        plans.append(VariantPlan(folder, name, code, category, pack, parts, files))
    return plans
