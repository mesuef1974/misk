"""إشارات الطلبات. تُرسَل داخل معاملة الخدمة، فمن يستقبلها يكتب في المعاملة نفسها وفشله يُرجِع الانتقال.

الإنتاج يعتمد على الطلبات لا العكس؛ الإشارة تُبقي الاعتماد في هذا الاتجاه.
"""

from __future__ import annotations

from django.dispatch import Signal

# kwargs: order (Order)، actor (المستخدم أو None).
order_cancelled = Signal()

# kwargs: order (Order). يُرسَل قبل الانتقال إلى «جاهز»؛ المستقبِل يرفضه برفع OrderError،
# والإنتاج يرفضه ما بقيت في الطلب قطعة لم تُقصّ.
order_ready_requested = Signal()

# kwargs: order (Order)، previous (الحالة السابقة)، actor. يُرسَل بعد حفظ كل انتقال، داخل المعاملة.
# المستقبِل لا يرفض الانتقال: ما يطول يؤجّله إلى ما بعد التثبيت.
order_transitioned = Signal()
