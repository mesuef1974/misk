from django.conf import settings
from django.http import HttpRequest
from django.utils import translation

RTL_LANGUAGES = ("ar", "fa", "he", "ur")


def site(request: HttpRequest) -> dict:
    # بلا LocaleMiddleware تعود اللغة الافتراضية (ar)؛ معه تعود اللغة المفاوَضة، ويتبعها الاتجاه.
    lang = translation.get_language() or settings.LANGUAGE_CODE
    return {
        "SITE_TITLE": settings.SITE_TITLE,
        "LANGUAGE_CODE": lang,
        "LANG_DIR": "rtl" if lang.split("-")[0] in RTL_LANGUAGES else "ltr",
    }
