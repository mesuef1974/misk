"""واجهة مزوّد الإشعارات ومزوّدا السجل والبريد (القسم 11 و13 من المواصفات).

واتساب لم يُربط بعد: كل ما يعرفه باقي النظام عن القناة هو `NotificationProvider`. مزوّد WhatsApp Cloud API
يُضاف صنفًا هنا ويُسجَّل في `_REGISTRY`؛ الخدمات والقوالب لا تتغير.

لا وسيلة اتصال بالعميل مخزَّنة بعد (PDPPL، قرار التشفير)، فـ `Message.to` فارغ اليوم: مزوّد البريد
يرسل إلى بريد المشغِّل `NOTIFY_OPERATOR_EMAIL` ليبلّغ العميل بنفسه، ومزوّد السجل يسجّل الحدث بلا نصّه.
"""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from typing import Protocol

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """المزوّد رفض الإرسال أو لم يُجب. الإرسال يُعاد بالمفتاح نفسه."""


@dataclass(frozen=True)
class Message:
    order_id: int
    kind: str
    lang: str
    subject: str
    body: str
    idempotency_key: str
    to: str = ""


class NotificationProvider(Protocol):
    name: str

    def send(self, message: Message) -> str:
        """يرسل ويعيد مرجع المزوّد. يرمي `ProviderError` لما يُعاد. إعادته بالمفتاح نفسه لا تكرّر."""


class LogProvider:
    """يسجّل أن الإشعار استحقّ، بلا نصّه: في النص رابط التتبّع السري وعنوان الاستلام."""

    name = "log"

    def send(self, message: Message) -> str:
        logger.info(
            "notification kind=%s lang=%s order=%s chars=%d",
            message.kind,
            message.lang,
            message.order_id,
            len(message.body),
        )
        return f"log_{message.idempotency_key}"


class EmailProvider:
    """بريد نصّي إلى العميل إن عُرف عنوانه، وإلا إلى بريد المشغِّل."""

    name = "email"

    def __init__(self, operator: str):
        self._operator = operator

    def send(self, message: Message) -> str:
        try:
            send_mail(
                message.subject,
                message.body,
                settings.DEFAULT_FROM_EMAIL,
                [message.to or self._operator],
            )
        except (smtplib.SMTPException, OSError) as exc:
            raise ProviderError("email_failed") from exc
        return f"email_{message.idempotency_key}"


def _email_provider() -> NotificationProvider | None:
    # بلا بريد مشغِّل لا مستلم اليوم، فالمزوّد معطَّل كله بدل أن يتعثّر كل إشعار.
    operator = settings.NOTIFY_OPERATOR_EMAIL
    return EmailProvider(operator) if operator else None


_REGISTRY = {"log": LogProvider, "email": _email_provider}


def active() -> NotificationProvider | None:
    """المزوّد المضبوط بـ `NOTIFY_PROVIDER`، أو None إن كانت الإشعارات معطَّلة."""
    factory = _REGISTRY.get(settings.NOTIFY_PROVIDER)
    return factory() if factory else None
