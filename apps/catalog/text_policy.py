"""قواعد خالصة بلا Django: كشف النص الديني ولفظ الجلالة في الأسماء والكلمات المسيئة.

الكشف الآلي لا يلتقط كل شيء (docs/storefront-spec.md القسم 6)، فكل ما يُكشف هنا يذهب إلى المراجعة
اليدوية ولا يُعتمد عليه وحده. المقارنة على نص مطبَّع: بلا تشكيل ولا تطويل، وبألف وياء وتاء مربوطة موحَّدة.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_MARKS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ‌-‏]")
# رموز مركّبة لا يفكّها NFKC كلها (﷽ وﷺ وﷻ)؛ U+FDFC رمز الريال فيُستثنى.
_HONORIFICS = re.compile(r"[ﷰ-ﷻ﷽]")
_NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)
_ALEF = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه"})

# عبارات دينية بعد التطبيع. تُطابَق على النص بمسافاته، وعلى النص بلا مسافات لما يُكتب متصلًا أو مفرَّقًا.
_PHRASES_AR = (
    "بسم الله",
    "لا اله الا",
    "الحمد لله",
    "سبحان",
    "استغفر",
    "ما شاء الله",
    "ان شاء الله",
    "صلي الله",
    "رسول الله",
    "رضي الله",
    "جزاك الله",
    "بارك الله",
    "حسبي الله",
    "حسبنا الله",
    "توكلت علي",
    "لا حول ولا قوه",
    "قل هو",
    "قل اعوذ",
    "اعوذ بالله",
    "الرحمن الرحيم",
    "رب العالمين",
    "جل جلاله",
    "عز وجل",
    "ايه الكرسي",
    "القران",
)
_PHRASES_EN = (
    "bismillah",
    "subhan",
    "alhamdulillah",
    "alhamdulilah",
    "mashallah",
    "masha allah",
    "inshallah",
    "insha allah",
    "astaghfir",
    "la ilaha",
    "quran",
    "koran",
)
# بداية كلمة: «subhanallah» تُلتقط من «subhan». و«allah» وحدها كلمة كاملة، وفي آخر اسم (Abdallah) اسم علم.
_PHRASES_EN_RE = re.compile(r"\b(?:" + "|".join(re.escape(p) for p in _PHRASES_EN) + ")")
_COMPOUND_EN = re.compile(r"^[a-z]{3,}[au]llah$")
# لفظ الجلالة كلمةً مستقلة، بسوابق العطف والجر.
_DIVINE_WORD = re.compile(r"^(?:[وف]?[بتك]?الله|[وف]?لله|[وف]?اللهم)$")
# اسم علم مركّب: «عبدالله» متصلًا، أو «سيف الله» بكلمتين أولاهما من أسماء معروفة.
_COMPOUND_JOINED = re.compile(r"^[ء-ي]{2,}الله$")
_COMPOUND_FIRST = frozenset(
    "عبد عبيد سيف نصر عطا جار ضيف خلف فضل هبه رزق سعد امه فتح نور عون خير حمد دخيل معتز".split()
)

_OFFENSIVE_AR = frozenset(
    "كلب حمار غبي حقير تافه وسخ قذر خنزير لعين ملعون زباله حيوان سافل منحط واطي عاهر عاهره "
    "شرموط شرموطه زاني زانيه قحبه خول منيوك كس زب طيز".split()
)
_OFFENSIVE_EN = frozenset(
    "fuck fucking fucker shit bitch asshole bastard dick pussy cunt slut whore nigger nigga faggot "
    "retard motherfucker bullshit".split()
)


@dataclass(frozen=True)
class Verdict:
    religious: bool = False
    # لفظ الجلالة داخل اسم علم مركّب (عبدالله): ليس نصًّا دينيًّا، لكنه يُراجَع.
    divine_name: bool = False
    offensive: bool = False

    @property
    def needs_review(self) -> bool:
        return self.religious or self.divine_name


def normalize(text: str) -> str:
    """NFKC يفكّ الرموز المركّبة (ﷲ و﷽ وﷺ) وصيغ العرض؛ ثم يُزال التشكيل والتطويل وعلامات الترقيم."""
    text = unicodedata.normalize("NFKC", text)
    text = _MARKS.sub("", text).translate(_ALEF).casefold()
    return " ".join(_NON_WORD.sub(" ", text).split())


def _strip_article(word: str) -> str:
    for prefix in ("وال", "بال", "كال", "فال", "ال", "و"):
        if word.startswith(prefix) and len(word) - len(prefix) >= 2:
            return word[len(prefix) :]
    return word


def inspect(text: str) -> Verdict:
    if _HONORIFICS.search(text):
        return Verdict(religious=True)
    norm = normalize(text)
    if not norm:
        return Verdict()
    words = norm.split()
    joined = norm.replace(" ", "")

    offensive = any(
        w in _OFFENSIVE_EN or w in _OFFENSIVE_AR or _strip_article(w) in _OFFENSIVE_AR for w in words
    )

    religious = any(p in norm or p.replace(" ", "") in joined for p in _PHRASES_AR) or bool(
        _PHRASES_EN_RE.search(norm)
    )
    divine_name = False
    if not religious:
        for index, word in enumerate(words):
            if word == "allah":
                religious = True
            elif _COMPOUND_EN.match(word):
                divine_name = True
            elif _DIVINE_WORD.match(word):
                if word == "الله" and index > 0 and words[index - 1] in _COMPOUND_FIRST:
                    divine_name = True
                else:
                    religious = True
            elif _COMPOUND_JOINED.match(word):
                divine_name = True
        # حروف مفرَّقة بمسافات («ا ل ل ه») تُجمع وتُفحص.
        if (
            not religious
            and len(words) > 1
            and all(len(w) == 1 for w in words)
            and _DIVINE_WORD.match(joined)
        ):
            religious = True
    return Verdict(religious=religious, divine_name=divine_name and not religious, offensive=offensive)
