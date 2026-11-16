"""قواعد خالصة بلا Django: التحقق من مخطط المعاملات ومن قيم الطلب."""

from __future__ import annotations

from typing import Any

FIELD_TYPES = {"text", "int", "bool", "choice"}
DEFAULT_TEXT_LENGTH = 200


class ParamError(ValueError):
    """خطأ في مخطط المعاملات أو في القيم المرسلة. `errors` قاموس: اسم الحقل ثم الرسالة."""

    def __init__(self, errors: dict[str, str]):
        super().__init__("; ".join(f"{key}: {message}" for key, message in errors.items()))
        self.errors = errors


def validate_schema(schema: Any) -> list[dict[str, Any]]:
    if not isinstance(schema, list):
        raise ParamError({"param_schema": "يجب أن يكون قائمة حقول"})
    errors: dict[str, str] = {}
    seen: set[str] = set()
    for index, field in enumerate(schema):
        key = f"param_schema[{index}]"
        if not isinstance(field, dict) or not isinstance(field.get("name"), str) or not field["name"]:
            errors[key] = "كل حقل يحتاج name نصيًّا"
            continue
        name = field["name"]
        if name in seen:
            errors[key] = f"الاسم {name} مكرر"
            continue
        seen.add(name)
        kind = field.get("type")
        if kind not in FIELD_TYPES:
            errors[key] = f"النوع يجب أن يكون أحد {sorted(FIELD_TYPES)}"
        elif kind == "choice" and not (isinstance(field.get("choices"), list) and field["choices"]):
            errors[key] = "حقل choice يحتاج قائمة choices غير فارغة"
        elif kind == "text" and "max_length" in field and not _is_int(field["max_length"], minimum=1):
            errors[key] = "max_length عدد صحيح موجب"
    if errors:
        raise ParamError(errors)
    return schema


def clean_params(schema: list[dict[str, Any]], params: Any) -> dict[str, Any]:
    """يعيد القيم منظَّفة بترتيب المخطط. يرفض الحقول المجهولة والناقصة والخارجة عن الحدود."""
    if not isinstance(params, dict):
        raise ParamError({"params": "يجب أن يكون كائنًا"})
    errors: dict[str, str] = {}
    cleaned: dict[str, Any] = {}
    known = {field["name"] for field in schema}
    for name in sorted(params.keys() - known):
        errors[name] = "حقل غير معرَّف في القالب"
    for field in schema:
        name = field["name"]
        if name not in params or params[name] in (None, ""):
            if field.get("required", True):
                errors[name] = "مطلوب"
            continue
        value, error = _clean_value(field, params[name])
        if error:
            errors[name] = error
        else:
            cleaned[name] = value
    if errors:
        raise ParamError(errors)
    return cleaned


def _clean_value(field: dict[str, Any], value: Any) -> tuple[Any, str]:
    kind = field["type"]
    if kind == "text":
        if not isinstance(value, str):
            return None, "نص"
        value = " ".join(value.split())
        limit = int(field.get("max_length", DEFAULT_TEXT_LENGTH))
        if len(value) > limit:
            return None, f"أطول من {limit} حرفًا"
    elif kind == "int":
        if not _is_int(value):
            return None, "عدد صحيح"
        if ("min" in field and value < field["min"]) or ("max" in field and value > field["max"]):
            return None, "خارج المدى المسموح"
    elif kind == "bool":
        if not isinstance(value, bool):
            return None, "قيمة منطقية"
    elif value not in field["choices"]:
        return None, "ليست من الخيارات"
    return value, ""


def _is_int(value: Any, *, minimum: int | None = None) -> bool:
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return minimum is None or value >= minimum
