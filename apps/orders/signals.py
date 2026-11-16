"""إشارات الطلبات. تُرسَل داخل معاملة الخدمة، فمن يستقبلها يكتب في المعاملة نفسها وفشله يُرجِع الانتقال.

الإنتاج يعتمد على الطلبات لا العكس؛ الإشارة تُبقي الاعتماد في هذا الاتجاه.
"""

from __future__ import annotations

from django.dispatch import Signal

# kwargs: order (Order)، actor (المستخدم أو None).
order_cancelled = Signal()
