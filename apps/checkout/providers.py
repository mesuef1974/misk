"""واجهة مزوّد الدفع ومزوّد الاختبار (القسم 10 من المواصفات).

البوابة لم تُختر بعد (الطلب 9): كل ما يعرفه باقي النظام عن المزوّد هو `PaymentProvider`.
مزوّد حقيقي يُضاف صنفًا هنا ويُسجَّل في `_REGISTRY`؛ الخدمات والمسارات لا تتغير.

مزوّد الاختبار لا يتصل بأحد: جلسته حتمية من مفتاح idempotency، وإشعاره يوقَّع بـ HMAC-SHA256 على
«الطابع.الجسم» بسرّ `PAYMENT_WEBHOOK_SECRET`، فلا يُقبل إشعار من غير حامل السرّ ولا إشعار قديم يُعاد.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Protocol

from django.conf import settings

SIGNATURE_HEADER = "X-Misk-Signature"
SIGNATURE_TOLERANCE_S = 5 * 60
CAPTURED, FAILED = "payment.captured", "payment.failed"
EVENT_KINDS = frozenset({CAPTURED, FAILED})


class ProviderError(Exception):
    """المزوّد رفض النداء أو لم يُجب. النداء يُعاد بالمفتاح نفسه."""


class SignatureError(Exception):
    """توقيع الإشعار مفقود أو خاطئ أو قديم، أو جسمه ليس على صيغة المزوّد."""


@dataclass(frozen=True)
class Session:
    session_id: str
    url: str


@dataclass(frozen=True)
class Event:
    event_id: str
    kind: str
    session_id: str
    reference: str
    amount: Decimal
    currency: str


class PaymentProvider(Protocol):
    name: str

    def create_session(
        self, *, idempotency_key: uuid.UUID, amount: Decimal, currency: str, description: str
    ) -> Session:
        """يفتح صفحة دفع مستضافة. إعادته بالمفتاح نفسه تعيد الجلسة نفسها."""

    def parse_event(self, *, body: bytes, headers: Mapping[str, str], now: float) -> Event:
        """يتحقق من التوقيع ثم يقرأ الحدث. يرمي `SignatureError` لكل ما لا يوثَق به."""

    def refund(self, *, reference: str, amount: Decimal, currency: str, idempotency_key: uuid.UUID) -> str:
        """يستردّ المبلغ ويعيد مرجع الاسترداد. إعادته بالمفتاح نفسه لا تستردّ مرتين."""


def sign(secret: str, body: bytes, timestamp: int) -> str:
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def _verify(secret: str, body: bytes, header: str, now: float) -> None:
    parts = dict(part.split("=", 1) for part in header.split(",") if "=" in part)
    try:
        timestamp = int(parts["t"])
        given = parts["v1"]
    except (KeyError, ValueError) as exc:
        raise SignatureError("signature_missing") from exc
    if abs(now - timestamp) > SIGNATURE_TOLERANCE_S:
        raise SignatureError("signature_expired")
    expected = sign(secret, body, timestamp).split("v1=", 1)[1]
    if not hmac.compare_digest(expected, given):
        raise SignatureError("signature_invalid")


class TestProvider:
    """مزوّد الاختبار: يسلك سلوك بوابة حقيقية (جلسة، إشعار موقَّع، استرداد) بلا مال."""

    __test__ = False  # ليس صنف اختبار لـ pytest
    name = "test"

    def __init__(self, secret: str):
        self._secret = secret

    def create_session(
        self, *, idempotency_key: uuid.UUID, amount: Decimal, currency: str, description: str
    ) -> Session:
        session_id = f"test_{idempotency_key.hex}"
        return Session(session_id=session_id, url=f"/checkout/test-pay/{session_id}")

    def parse_event(self, *, body: bytes, headers: Mapping[str, str], now: float) -> Event:
        _verify(self._secret, body, headers.get(SIGNATURE_HEADER, ""), now)
        try:
            data = json.loads(body)
            event = Event(
                event_id=str(data["id"]),
                kind=str(data["type"]),
                session_id=str(data["session_id"]),
                reference=str(data.get("reference", "")),
                amount=Decimal(str(data["amount"])),
                currency=str(data["currency"]),
            )
        except (ValueError, KeyError, TypeError, InvalidOperation) as exc:
            raise SignatureError("bad_payload") from exc
        if event.kind not in EVENT_KINDS or not event.event_id or not event.amount.is_finite():
            raise SignatureError("bad_payload")
        return event

    def refund(self, *, reference: str, amount: Decimal, currency: str, idempotency_key: uuid.UUID) -> str:
        return f"refund_{idempotency_key.hex}"

    def signed_event(self, *, kind: str, session_id: str, amount: Decimal, currency: str, now: float):
        """جسم إشعار وترويسته كما ترسلهما البوابة: لمسار محاكاة الطاقم وللاختبارات."""
        body = json.dumps(
            {
                "id": f"evt_{uuid.uuid4().hex}",
                "type": kind,
                "session_id": session_id,
                "reference": f"txn_{session_id}",
                "amount": str(amount),
                "currency": currency,
            }
        ).encode()
        return body, {SIGNATURE_HEADER: sign(self._secret, body, int(now))}


def _test_provider() -> PaymentProvider | None:
    # بلا سرّ لا يُتحقق من إشعار، فالمزوّد معطَّل كله بدل أن يقبل ما لا يوثَق به.
    secret = settings.PAYMENT_WEBHOOK_SECRET
    return TestProvider(secret) if secret else None


_REGISTRY = {"test": _test_provider}


def active() -> PaymentProvider | None:
    """المزوّد المضبوط بـ `PAYMENT_PROVIDER`، أو None إن كان الدفع معطَّلًا."""
    factory = _REGISTRY.get(settings.PAYMENT_PROVIDER)
    return factory() if factory else None


def by_name(name: str) -> PaymentProvider | None:
    """لمسار الإشعار واسترداد دفعة قديمة: المزوّد الفعّال وحده يُجاب عنه."""
    provider = active()
    return provider if provider is not None and provider.name == name else None
