import pytest

from apps.core import services
from apps.core.models import AuditLog


@pytest.mark.django_db
def test_health_ok(client):
    res = client.get("/health/")
    assert res.status_code == 200
    assert res.json()["db"] == "ok"


@pytest.mark.django_db
def test_ping(client):
    res = client.get("/api/ping")
    assert res.status_code == 200
    assert res.json()["ok"] is True


@pytest.mark.django_db
def test_me_requires_auth(client):
    assert client.get("/api/me").status_code == 401


@pytest.mark.django_db
def test_audit_idempotent_on_request_id():
    a = services.record_audit(action="x", target="t", request_id="r1")
    b = services.record_audit(action="x", target="t", request_id="r1")
    assert a.pk == b.pk
    assert AuditLog.objects.count() == 1


@pytest.mark.django_db
def test_audit_endpoint_staff_only(client, staff_user, django_user_model):
    plain = django_user_model.objects.create_user(username="u", password="x" * 12)
    client.force_login(plain)
    assert client.get("/api/audit").status_code == 403
    client.force_login(staff_user)
    assert client.get("/api/audit").status_code == 200


def test_spa_shell_is_arabic_rtl_regardless_of_browser_locale(client):
    res = client.get("/anything/here", HTTP_ACCEPT_LANGUAGE="en-US,en;q=0.9")
    assert res.status_code == 200
    assert b'id="app"' in res.content
    assert b'<html lang="ar" dir="rtl">' in res.content


def test_static_storage_has_no_django_manifest():
    """Manifest storage يعيد تسمية ملف الدخول فتستورد أجزاء Vite نسخة ثانية ويُركَّب التطبيق مرتين (صفحة فارغة)."""
    from importlib import import_module

    base = import_module("config.settings.base")
    assert "Manifest" not in base.STORAGES["staticfiles"]["BACKEND"]
    assert base.WHITENOISE_IMMUTABLE_FILE_TEST("", "/static/assets/main-BAm3HWoC.js")
    assert not base.WHITENOISE_IMMUTABLE_FILE_TEST("", "/static/admin/css/base.css")
