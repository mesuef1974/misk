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
    assert res.json() == {"id": staff_user.pk, "username": "staff", "is_staff": True, "admin_url": "/admin/"}
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
    """الرد نفسه لكلمة المرور الخاطئة: لا يُعرف منه أن كلمة مرور حساب غير مشرف صحيحة."""
    django_user_model.objects.create_user(username="u", password="x" * 12)
    right, wrong = _login(client, username="u"), _login(client, username="u", password="y" * 12)
    assert right.status_code == wrong.status_code == 401
    assert right.json() == wrong.json()
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


def _fail_logins(client, count, **extra):
    for _ in range(count):
        client.post(
            "/api/auth/login",
            {"username": "staff", "password": "y" * 12},
            content_type="application/json",
            **extra,
        )


@pytest.mark.django_db
def test_lockout_is_per_username_and_address_pair(client, staff_user, django_user_model, settings):
    """محاولات زائر لا تقفل مشرفًا من عنوان آخر، ولا تقفل اسمًا آخر من العنوان نفسه."""
    settings.AXES_ENABLED = True
    django_user_model.objects.create_user(username="second", password="x" * 12, is_staff=True)
    attacker = {"REMOTE_ADDR": "203.0.113.9"}
    _fail_logins(client, settings.AXES_FAILURE_LIMIT, **attacker)
    body = {"username": "staff", "password": "x" * 12}
    assert (
        client.post("/api/auth/login", body, content_type="application/json", **attacker).status_code == 429
    )
    other_name = client.post(
        "/api/auth/login",
        {"username": "second", "password": "x" * 12},
        content_type="application/json",
        **attacker,
    )
    assert other_name.status_code == 200
    client.post("/api/auth/logout")
    elsewhere = client.post(
        "/api/auth/login", body, content_type="application/json", REMOTE_ADDR="198.51.100.4"
    )
    assert elsewhere.status_code == 200


@pytest.mark.django_db
def test_lockout_behind_proxy_keys_on_forwarded_client(client, staff_user, settings):
    """خلف الوكيل REMOTE_ADDR واحد لكل الزوار؛ القفل يتبع العنوان الذي كتبه الوكيل."""
    settings.AXES_ENABLED = True
    settings.TRUSTED_PROXY_COUNT = 1
    proxy = {"REMOTE_ADDR": "10.0.0.1"}
    _fail_logins(client, settings.AXES_FAILURE_LIMIT, HTTP_X_FORWARDED_FOR="203.0.113.9", **proxy)
    body = {"username": "staff", "password": "x" * 12}
    post = lambda forwarded: client.post(  # noqa: E731
        "/api/auth/login", body, content_type="application/json", HTTP_X_FORWARDED_FOR=forwarded, **proxy
    )
    assert post("203.0.113.9").status_code == 429
    # خانة يكتبها العميل قبل خانة الوكيل لا تُخرجه من القفل.
    assert post("198.51.100.4, 203.0.113.9").status_code == 429
    assert post("198.51.100.4").status_code == 200


def test_client_ip_trusts_only_proxy_written_hops(rf, settings):
    from apps.core.auth import client_ip

    request = rf.get("/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="1.1.1.1, 2.2.2.2 , 3.3.3.3")
    settings.TRUSTED_PROXY_COUNT = 0
    assert client_ip(request) == "10.0.0.1"  # بلا وكيل موثوق الترويسة يكتبها أي أحد
    settings.TRUSTED_PROXY_COUNT = 1
    assert client_ip(request) == "3.3.3.3"
    settings.TRUSTED_PROXY_COUNT = 2
    assert client_ip(request) == "2.2.2.2"
    settings.TRUSTED_PROXY_COUNT = 4
    assert client_ip(request) == "10.0.0.1"  # الترويسة أقصر من عدد الوكلاء
    settings.TRUSTED_PROXY_COUNT = 1
    assert client_ip(rf.get("/", REMOTE_ADDR="10.0.0.1")) == "10.0.0.1"
    assert client_ip(rf.get("/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="x, مزوَّر")) == "10.0.0.1"
    assert client_ip(rf.get("/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="2001:DB8::1")) == "2001:db8::1"


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["/api/docs/", "/api/openapi.json"])
def test_api_docs_are_staff_only(client, staff_user, django_user_model, path):
    assert client.get(path).status_code == 302
    client.force_login(django_user_model.objects.create_user(username="u", password="x" * 12))
    assert client.get(path).status_code == 302
    client.force_login(staff_user)
    assert client.get(path).status_code == 200


@pytest.mark.django_db
def test_audit_limit_is_validated_and_capped(client, staff_user):
    client.force_login(staff_user)
    assert client.get("/api/audit?limit=-1").status_code == 422
    assert client.get("/api/audit?limit=0").status_code == 422
    assert client.get("/api/audit?limit=1").status_code == 200
    assert client.get("/api/audit?limit=100000").status_code == 200


@pytest.mark.django_db
def test_audit_survives_concurrent_duplicate(monkeypatch):
    """طلب متزامن بالمفتاح نفسه سبق بعد الفحص: قيد التفرّد يرفض الإدراج فيُعاد صف الأول."""
    first = services.record_audit(action="x", target="t", request_id="r1")
    real_filter = AuditLog.objects.filter
    calls = []

    def racing_filter(*args, **kwargs):
        calls.append(1)
        return AuditLog.objects.none() if len(calls) == 1 else real_filter(*args, **kwargs)

    monkeypatch.setattr(AuditLog.objects, "filter", racing_filter)
    assert services.record_audit(action="x", target="t", request_id="r1").pk == first.pk
    assert AuditLog.objects.count() == 1


@pytest.mark.django_db
def test_audit_without_request_id_is_never_deduplicated():
    services.record_audit(action="x", target="t")
    services.record_audit(action="x", target="t")
    assert AuditLog.objects.count() == 2


@pytest.mark.django_db
def test_audit_keeps_actor_name_after_user_is_deleted(staff_user):
    row = services.record_audit(action="x", actor=staff_user)
    staff_user.delete()
    row.refresh_from_db()
    assert row.actor is None
    assert row.actor_name == "staff"


@pytest.mark.django_db
def test_audit_truncates_oversized_request_id(client, staff_user):
    client.force_login(staff_user)
    assert client.get("/api/audit", headers={"X-Request-ID": "r" * 500}).status_code == 200
    assert AuditLog.objects.get(action="audit.view").request_id == "r" * 64


@pytest.mark.django_db
def test_content_security_policy_header(client, staff_user, settings):
    policy = client.get("/")["Content-Security-Policy"]
    assert "script-src 'self'" in policy and "frame-ancestors 'none'" in policy
    assert "unsafe-inline" not in policy.split("script-src")[1].split(";")[0]
    assert "unsafe-eval" not in policy
    assert "Content-Security-Policy" in client.get("/api/ping")
    client.force_login(staff_user)
    assert "Content-Security-Policy" not in client.get("/api/docs/")  # Swagger من CDN، للمشرفين فقط
    settings.CONTENT_SECURITY_POLICY = ""
    assert "Content-Security-Policy" not in client.get("/")


@pytest.mark.django_db
def test_me_reveals_admin_url_to_staff_only(client, staff_user, django_user_model, settings):
    client.force_login(django_user_model.objects.create_user(username="u", password="x" * 12))
    assert client.get("/api/me").json()["admin_url"] is None
    client.force_login(staff_user)
    assert client.get("/api/me").json()["admin_url"] == "/" + settings.ADMIN_URL


@pytest.mark.django_db
def test_admin_inherits_platform_identity(client, staff_user, settings):
    from django.contrib.staticfiles import finders

    # صفحة الدخول والصفحة الرئيسية للوحة تحملان ألوان المنصة واسمها.
    login_page = client.get("/" + settings.ADMIN_URL + "login/").content.decode()
    client.force_login(staff_user)
    index = client.get("/" + settings.ADMIN_URL).content.decode()
    for page in (login_page, index):
        assert "/static/brand/tokens.css" in page
        assert "/static/core/admin-theme.css" in page
        assert (
            page.index("admin/css/dark_mode.css")
            < page.index("brand/tokens.css")
            < page.index("core/admin-theme.css")
        )
        assert settings.SITE_TITLE in page
    # الملفان موجودان فعلًا حيث يجمعهما collectstatic.
    assert finders.find("brand/tokens.css")
    assert finders.find("core/admin-theme.css")


def test_spa_applies_stored_theme_before_paint(client):
    from django.contrib.staticfiles import finders

    # سكربت الوضع ملف ثابت يسبق حزم الواجهة في <head>، فيُضبط data-theme قبل الرسم.
    page = client.get("/").content.decode()
    assert page.index("/static/core/theme-init.js") < page.index("src/main.ts")
    assert finders.find("core/theme-init.js")
