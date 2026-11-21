"""إشارات الاستلام. تُرسَل داخل معاملة الخدمة، فمن يستقبلها يكتب في المعاملة نفسها.

الإشعارات تعتمد على الاستلام لا العكس؛ الإشارة تُبقي الاعتماد في هذا الاتجاه.
"""

from __future__ import annotations

from django.dispatch import Signal

# kwargs: order (Order)، appointment (PickupAppointment)، previous (الموعد السابق أو None).
# يُرسَل بعد كل حجز أو تغيير موعد، لا عند إعادة الحجز بالموعد نفسه.
pickup_booked = Signal()
