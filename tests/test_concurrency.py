"""سباقات حقيقية على PostgreSQL: معاملتان في خيطين، كلٌّ باتصاله، وترتيب الأقفال يُفرض بأحداث لا بتوقيت.

SQLite يقفل القاعدة كلها ولا ينفّذ FOR UPDATE، فلا يثبت شيئًا هنا: تُتخطّى عليه، وتعمل في CI على Postgres.
"""

from __future__ import annotations

import threading
import uuid

import pytest
from django.db import connection, connections

from apps.orders import services as order_services
from apps.orders.models import Customer, Order
from apps.production import domain, services
from apps.production.models import Placement, Sheet

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(connection.vendor != "postgresql", reason="أقفال الصفوف تحتاج PostgreSQL"),
]

WAIT_S = 10  # سقف لكل انتظار كي لا يعلق الاختبار إن انكسر القفل
BLOCKED_S = 0.5  # مدة نعدّ بعدها الخيط محجوبًا على القفل


class Worker(threading.Thread):
    """يشغّل الدالة في خيط باتصال قاعدة خاص به، ويحفظ نتيجتها أو استثناءها لتفحصه الخيط الرئيسي."""

    def __init__(self, target):
        super().__init__(daemon=True)
        self._target_fn = target
        self.result = None
        self.error: BaseException | None = None

    def run(self):
        try:
            self.result = self._target_fn()
        except BaseException as exc:  # noqa: BLE001 — يُعاد رفعه في الخيط الرئيسي
            self.error = exc
        finally:
            connections.close_all()

    def finish(self):
        self.join(WAIT_S)
        assert not self.is_alive(), "الخيط لم ينتهِ: قفل عالق"
        if self.error is not None:
            raise self.error
        return self.result


def _item(material, quantity):
    return order_services.ItemInput(
        template_slug="name-tag", material_id=material.pk, params={"text": "نور"}, quantity=quantity
    )


def _confirmed_order(material, quantity):
    order = order_services.create_order(
        client_ref=uuid.uuid4(), customer_name="زبون تجريبي", items=[_item(material, quantity)]
    )
    return order_services.transition(order_id=order.pk, to_status="confirmed")


def _cancel(order_id):
    return order_services.transition(order_id=order_id, to_status="cancelled")


def test_cancel_during_planning_waits_then_releases_the_pieces(material, name_tag, calibration, monkeypatch):
    """التخطيط يقفل الطلب ثم يرتّب: الإلغاء المتزامن ينتظره، ثم يجد ألواحه ويرفع قطعه."""
    order = _confirmed_order(material, 3)
    packing, resume = threading.Event(), threading.Event()
    real_pack = domain.pack

    def slow_pack(*args, **kwargs):
        packing.set()
        assert resume.wait(WAIT_S)
        return real_pack(*args, **kwargs)

    monkeypatch.setattr(domain, "pack", slow_pack)
    planner = Worker(lambda: services.plan_sheets(material_id=material.pk))
    planner.start()
    assert packing.wait(WAIT_S)

    canceller = Worker(lambda: _cancel(order.pk))
    canceller.start()
    canceller.join(BLOCKED_S)
    assert canceller.is_alive(), "الإلغاء لم ينتظر قفل التخطيط على الطلب"

    resume.set()
    assert len(planner.finish()) == 1
    assert canceller.finish().status == Order.Status.CANCELLED
    assert not Placement.objects.filter(order_item__order=order).exists()
    assert not Sheet.objects.exists()


def test_planning_after_uncommitted_cancel_skips_the_order(material, name_tag, calibration):
    """الإلغاء يقفل الطلب أولًا: التخطيط ينتظره ثم يعيد فحص الحالة فلا يضع قطع الطلب الملغى."""
    order = _confirmed_order(material, 3)
    cancelled, commit = threading.Event(), threading.Event()

    def cancel_and_hold():
        from django.db import transaction

        with transaction.atomic():
            _cancel(order.pk)
            cancelled.set()
            assert commit.wait(WAIT_S)

    canceller = Worker(cancel_and_hold)
    canceller.start()
    assert cancelled.wait(WAIT_S)

    planner = Worker(lambda: services.plan_sheets(material_id=material.pk))
    planner.start()
    planner.join(BLOCKED_S)
    assert planner.is_alive(), "التخطيط لم ينتظر قفل الإلغاء على الطلب"

    commit.set()
    canceller.finish()
    assert planner.finish() == []
    assert not Placement.objects.exists()
    assert Order.objects.get(pk=order.pk).status == Order.Status.CANCELLED


def test_concurrent_creates_with_one_client_ref_make_one_order(material, name_tag, monkeypatch):
    """كلا الطلبين يجتاز فحص الوجود قبل أن يُدرج أيٌّ منهما: القيد يحسم، والخاسر يعيد طلب الفائز."""
    client_ref = uuid.uuid4()
    both_checked = threading.Barrier(2, timeout=WAIT_S)
    first_check = threading.local()
    real_existing = order_services._existing_order

    def existing_after_both_checked(ref):
        found = real_existing(ref)
        if not getattr(first_check, "done", False):
            first_check.done = True
            both_checked.wait()
        return found

    monkeypatch.setattr(order_services, "_existing_order", existing_after_both_checked)

    def create():
        return order_services.create_order(
            client_ref=client_ref, customer_name="زبون متزامن", items=[_item(material, 1)]
        )

    workers = [Worker(create) for _ in range(2)]
    for worker in workers:
        worker.start()
    orders = [worker.finish() for worker in workers]

    assert orders[0].pk == orders[1].pk
    assert Order.objects.filter(client_ref=client_ref).count() == 1
    assert Customer.objects.count() == 1  # زبون الخاسر رجع مع نقطة الحفظ
    assert orders[0].items.count() == 1
