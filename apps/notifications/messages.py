"""قوالب الإشعارات بالعربية والإنجليزية (القسم 11 من المواصفات). نص خالص: يصلح للبريد ولواتساب.

الحقول: `number` رقم الطلب، `track_url` رابط التتبّع، `when` وقت الموعد، `address` عنوان الاستلام.
"""

from __future__ import annotations

Lang = str

ORDER_RECEIVED = "order_received"
PRODUCTION_STARTED = "production_started"
READY_PICKUP = "ready_pickup"
READY_DELIVERY = "ready_delivery"
OUT_FOR_DELIVERY = "out_for_delivery"
PICKUP_CONFIRMED = "pickup_confirmed"

# القالب ← اللغة ← (العنوان، النص).
TEXTS: dict[str, dict[Lang, tuple[str, str]]] = {
    ORDER_RECEIVED: {
        "ar": (
            "مسك: استلمنا طلبك رقم {number}",
            "استلمنا طلبك رقم {number} ودفعتك، شكرًا لثقتك بمسك.\nتابع طلبك من هنا:\n{track_url}",
        ),
        "en": (
            "Misk: we received your order #{number}",
            "We received your order #{number} and your payment. Thank you for choosing Misk.\n"
            "Track your order here:\n{track_url}",
        ),
    },
    PRODUCTION_STARTED: {
        "ar": (
            "مسك: بدأنا حفر طلبك رقم {number}",
            "بدأنا حفر طلبك رقم {number}.\nتابعه من هنا:\n{track_url}",
        ),
        "en": (
            "Misk: we started engraving your order #{number}",
            "We started engraving your order #{number}.\nFollow it here:\n{track_url}",
        ),
    },
    READY_PICKUP: {
        "ar": (
            "مسك: طلبك رقم {number} جاهز",
            "طلبك رقم {number} جاهز.\nاحجز موعد الاستلام من هنا:\n{track_url}",
        ),
        "en": (
            "Misk: your order #{number} is ready",
            "Your order #{number} is ready.\nBook your pickup time here:\n{track_url}",
        ),
    },
    READY_DELIVERY: {
        "ar": (
            "مسك: طلبك رقم {number} جاهز",
            "طلبك رقم {number} جاهز، وسنبلغك حين يخرج للتوصيل.\nتابعه من هنا:\n{track_url}",
        ),
        "en": (
            "Misk: your order #{number} is ready",
            "Your order #{number} is ready. We will let you know when it is out for delivery.\n"
            "Follow it here:\n{track_url}",
        ),
    },
    OUT_FOR_DELIVERY: {
        "ar": (
            "مسك: طلبك رقم {number} في الطريق",
            "طلبك رقم {number} في الطريق إليك.\nتابعه من هنا:\n{track_url}",
        ),
        "en": (
            "Misk: your order #{number} is on its way",
            "Your order #{number} is on its way to you.\nFollow it here:\n{track_url}",
        ),
    },
    PICKUP_CONFIRMED: {
        "ar": (
            "مسك: تأكّد موعد استلام طلبك رقم {number}",
            "تأكّد موعد استلام طلبك رقم {number}: {when}.\nعنوان الاستلام:\n{address}\n"
            "لتغيير الموعد:\n{track_url}",
        ),
        "en": (
            "Misk: pickup time confirmed for order #{number}",
            "Your pickup time for order #{number} is confirmed: {when}.\nPickup address:\n{address}\n"
            "To change the time:\n{track_url}",
        ),
    },
}


def render(template: str, lang: Lang, **fields: object) -> tuple[str, str]:
    """العنوان والنص بلغة العميل. لغة غير معروفة تُعامل عربية."""
    subject, body = TEXTS[template].get(lang) or TEXTS[template]["ar"]
    return subject.format(**fields), body.format(**fields)
