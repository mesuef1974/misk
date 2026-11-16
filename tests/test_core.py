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


def _login(client, username="staff", password="x" * 12):
    return client.post(
        "/api/auth/login", {"username": username, "password": password}, content_type="application/json"
    )


@pytest.mark.django_db
def test_login_opens_staff_session_and_audits(client, staff_user):
    res = _login(client)
    assert res.status_code == 200, res.content
    assert res.json() == {"id": staff_user.pk, "username": "staff", "is_staff": True}
    assert client.get("/api/me").json()["username"] == "staff"
    assert AuditLog.objects.filter(action="auth.login", actor=staff_user).count() == 1


@pytest.mark.django_db
def test_login_rejects_bad_credentials_with_one_message(client, staff_user, django_user_model):
    django_user_model.objects.create_user(username="off", password="x" * 12, is_staff=True, is_active=False)
    wrong_password = _login(client, password="y" * 12)
    unknown_user = _login(client, username="nobody")
    inactive = _login(client, username="off")
    assert [r.status_code for r in (wrong_password, unknown_user, inactive)] == [401, 401, 401]
    assert wrong_password.json() == unknown_user.json() == inactive.json()
    assert client.get("/api/me").status_code == 401
    assert not AuditLog.objects.filter(action="auth.login").exists()


@pytest.mark.django_db
def test_login_refuses_non_staff_and_opens_no_session(client, django_user_model):
    django_user_model.objects.create_user(username="u", password="x" * 12)
    assert _login(client, username="u").status_code == 403
    assert client.get("/api/me").status_code == 401


@pytest.mark.django_db
def test_login_validates_payload_bounds(client, staff_user):
    assert _login(client, password="").status_code == 422
    assert _login(client, password="x" * 129).status_code == 422
    assert _login(client, username="s" * 151).status_code == 422


@pytest.mark.django_db
def test_login_requires_csrf_token(staff_user):
    from django.test import Client

    strict = Client(enforce_csrf_checks=True)
    assert _login(strict).status_code == 403
    strict.get("/")  # قشرة SPA تضع كوكي CSRF
    token = strict.cookies["csrftoken"].value
    res = strict.post(
        "/api/auth/login",
        {"username": "staff", "password": "x" * 12},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert res.status_code == 200, res.content
    # login يبدّل الرمز: القديم يُرفض والجديد من الكوكي يُقبل.
    assert strict.post("/api/auth/logout", HTTP_X_CSRFTOKEN=token).status_code == 403
    fresh = strict.cookies["csrftoken"].value
    assert fresh != token
    assert strict.post("/api/auth/logout", HTTP_X_CSRFTOKEN=fresh).status_code == 200


@pytest.mark.django_db
def test_login_rotates_session_key(client, staff_user):
    client.get("/")
    session = client.session
    session["marker"] = 1
    session.save()
    before = client.session.session_key
    assert _login(client).status_code == 200
    assert client.session.session_key != before


@pytest.mark.django_db
def test_logout_closes_session_and_audits(client, staff_user):
    assert client.post("/api/auth/logout").status_code == 401
    _login(client)
    assert client.post("/api/auth/logout").json() == {"ok": True}
    assert client.get("/api/me").status_code == 401
    assert AuditLog.objects.filter(action="auth.logout", actor=staff_user).count() == 1


@pytest.mark.django_db
def test_login_locks_out_after_repeated_failures(client, staff_user, settings):
    settings.AXES_ENABLED = True
    for _ in range(settings.AXES_FAILURE_LIMIT):
        _login(client, password="y" * 12)
    locked = _login(client)  # كلمة المرور الصحيحة لا تفتح حسابًا مقفلًا
    assert locked.status_code == 429
    assert client.get("/api/me").status_code == 401
