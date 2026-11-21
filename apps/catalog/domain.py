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
        elif kind == "choice":
            error = _choices_error(field.get("choices"))
            if error:
                errors[key] = error
        elif kind == "int":
            bounds = [field[bound] for bound in ("min", "max") if bound in field]
            if not all(_is_int(bound) for bound in bounds):
                errors[key] = "min وmax عددان صحيحان"
            elif len(bounds) == 2 and bounds[0] > bounds[1]:
                errors[key] = "min أكبر من max"
        elif kind == "text" and "max_length" in field and not _is_int(field["max_length"], minimum=1):
            errors[key] = "max_length عدد صحيح موجب"
    if errors:
        raise ParamError(errors)
    return schema


def validate_material_kinds(kinds: Any, known: set[str]) -> list[str]:
    if not isinstance(kinds, list) or not all(isinstance(kind, str) and kind in known for kind in kinds):
        raise ParamError({"material_kinds": f"قائمة من {sorted(known)}"})
    if len(set(kinds)) != len(kinds):
        raise ParamError({"material_kinds": "أنواع مكررة"})
    return kinds


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
        raw = params.get(name)
        if field["type"] == "text" and isinstance(raw, str):
            raw = " ".join(raw.split())  # قبل فحص الفراغ: نص من مسافات فقط فارغ
        if raw is None or raw == "":
            if field.get("required", True):
                errors[name] = "مطلوب"
            continue
        value, error = _clean_value(field, raw)
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
        # حدّ غير صحيح في قالب حُفظ قبل فحص المخطط يُهمَل ولا يكسر الطلب.
        low, high = field.get("min"), field.get("max")
        if (_is_int(low) and value < low) or (_is_int(high) and value > high):
            return None, "خارج المدى المسموح"
    elif kind == "bool":
        if not isinstance(value, bool):
            return None, "قيمة منطقية"
    elif value not in field["choices"]:
        return None, "ليست من الخيارات"
    return value, ""


def _choices_error(choices: Any) -> str:
    if not isinstance(choices, list) or not choices:
        return "حقل choice يحتاج قائمة choices غير فارغة"
    if not all(isinstance(choice, str) or _is_int(choice) for choice in choices):
        return "كل خيار نص أو عدد صحيح"
    if len({(type(choice), choice) for choice in choices}) != len(choices):
        return "خيارات مكررة"
    return ""


def _is_int(value: Any, *, minimum: int | None = None) -> bool:
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return minimum is None or value >= minimum
