import importlib

import pytest

from apps.core import services
from apps.core.models import AuditLog


@pytest.mark.django_db
def test_health_ok(client):
    res = client.get("/health/")
    assert res.status_code == 200
    assert res.json()["db"] == "ok"


@pytest.mark.django_db
def test_health_is_exempt_from_https_redirect(client, settings, monkeypatch):
    # فاحص Railway يسأل بـ HTTP: مسار الصحة يجيب 200 وكل ما عداه يُحوَّل إلى HTTPS.
    monkeypatch.setenv("ALLOWED_HOSTS", "example.test")
    monkeypatch.setenv("DATABASE_URL", "sqlite://:memory:")
    production = importlib.import_module("config.settings.production")
    settings.SECURE_SSL_REDIRECT = True
    settings.SECURE_REDIRECT_EXEMPT = production.SECURE_REDIRECT_EXEMPT
    assert client.get("/health/").status_code == 200
    assert client.get("/api/ping").status_code == 301
    assert client.get("/health/x").status_code == 301


def test_planning_async_requires_shared_redis_in_production(monkeypatch):
    # بلا Redis يضع الويب المهمة في ذاكرته والعامل لا يراها: الإنتاج يرفض الإقلاع بدل تعطّل التخطيط بصمت.
    from django.core.exceptions import ImproperlyConfigured

    base = importlib.import_module("config.settings.base")
    monkeypatch.setenv("ALLOWED_HOSTS", "example.test")
    monkeypatch.setenv("DATABASE_URL", "sqlite://:memory:")
    monkeypatch.setenv("PLANNING_ASYNC", "true")
    monkeypatch.delenv("REDIS_URL", raising=False)
    try:
        importlib.reload(base)
        with pytest.raises(ImproperlyConfigured, match="REDIS_URL"):
            importlib.reload(importlib.import_module("config.settings.production"))
        monkeypatch.setenv("REDIS_URL", "redis://example.test:6379/0")
        importlib.reload(base)
        assert importlib.reload(importlib.import_module("config.settings.production")).PLANNING_ASYNC is True
    finally:
        monkeypatch.delenv("PLANNING_ASYNC")
        monkeypatch.delenv("REDIS_URL")
        importlib.reload(base)


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


def _login(client, username="staff", password="x" * 12, **extra):
    return client.post(
        "/api/auth/login",
        {"username": username, "password": password},
        content_type="application/json",
        **extra,
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
    for url in ("/api/auth/logout", "/api/orders"):  # جلسة عامة وجلسة مشرف: الرسالة عربية في الحالين
        stale = strict.post(url, {}, content_type="application/json", HTTP_X_CSRFTOKEN=token)
        assert (stale.status_code, stale.json()["detail"]) == (403, "رمز CSRF مفقود أو غير صالح؛ حدّث الصفحة")
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


@pytest.mark.django_db
def test_rotating_addresses_cannot_keep_guessing_one_name(client, staff_user, django_user_model, settings):
    """قفل الزوج وحده يتيح خمس محاولات من كل عنوان؛ الحدّ الثاني يبطّئ التخمين على الاسم مهما تبدّل العنوان:
    بعده تُجرَّب كلمة مرور واحدة في كل فترة، وما سواها يُرفض بلا تجربة ولو كان صحيحًا."""
    settings.AXES_ENABLED = True
    django_user_model.objects.create_user(username="second", password="x" * 12, is_staff=True)
    for index in range(services.NAME_FAILURE_LIMIT):
        _fail_logins(client, 1, REMOTE_ADDR=f"203.0.113.{index + 1}")
    guess = client.post(
        "/api/auth/login",
        {"username": "staff", "password": "y" * 12},
        content_type="application/json",
        REMOTE_ADDR="203.0.113.200",
    )
    assert (guess.status_code, guess.json()["detail"]) == (429, services.NAME_LOCKED)  # أخذ فرصة الفترة
    body = {"username": "staff", "password": "x" * 12}
    fresh = client.post("/api/auth/login", body, content_type="application/json", REMOTE_ADDR="198.51.100.4")
    assert fresh.status_code == 429  # لم تُجرَّب: الفرصة مأخوذة
    assert fresh.json()["detail"] == services.NAME_LOCKED
    assert client.get("/api/me").status_code == 401
    other = client.post(
        "/api/auth/login",
        {"username": "second", "password": "x" * 12},
        content_type="application/json",
        REMOTE_ADDR="198.51.100.4",
    )
    assert other.status_code == 200  # الحدّ لكل اسم: لا يقفل حسابًا آخر


@pytest.mark.django_db
def test_name_limit_is_above_pair_limit_and_off_with_axes(client, staff_user, settings):
    assert services.NAME_FAILURE_LIMIT > settings.AXES_FAILURE_LIMIT
    settings.AXES_ENABLED = False  # التطوير والاختبار: لا عدّاد ولا قفل
    _fail_logins(client, services.NAME_FAILURE_LIMIT + 1)
    assert _login(client).status_code == 200


def _guess_from_many_addresses(count, username="staff"):
    """زائر يدوّر العناوين بلا كوكي جهاز: محاولة فاشلة واحدة من كل عنوان."""
    from django.test import Client

    stranger = Client()
    for index in range(count):
        stranger.post(
            "/api/auth/login",
            {"username": username, "password": "y" * 12},
            content_type="application/json",
            REMOTE_ADDR=f"203.0.113.{index + 1}",
        )


@pytest.mark.django_db
def test_name_limit_spares_a_device_that_signed_in_before(client, staff_user, settings):
    """هـ1: غريب يعرف الاسم لا يقفل المشرف خارج جهازه المعتاد، ويبقى محجوبًا هو وكل جهاز جديد."""
    from django.test import Client

    settings.AXES_ENABLED = True
    first = _login(client)
    assert first.status_code == 200
    cookie = first.cookies[services.DEVICE_COOKIE]
    assert cookie["httponly"] and cookie["samesite"] == "Strict" and cookie["path"] == "/api/auth/"
    client.post("/api/auth/logout")
    _guess_from_many_addresses(services.NAME_FAILURE_LIMIT + 1)  # الأخيرة تأخذ فرصة الفترة
    assert _login(Client()).status_code == 429  # جهاز لم يُدخَل منه
    assert _login(client).status_code == 200  # جهاز المشرف
    # كوكي مُعبث به أو لاسم آخر لا يعفي.
    forged = Client()
    forged.cookies[services.DEVICE_COOKIE] = cookie.value + "x"
    assert _login(forged).status_code == 429


@pytest.mark.django_db
def test_device_failures_are_limited_per_device(client, staff_user, settings):
    """كوكي جهاز مسروق لا يفتح تخمينًا بلا حدّ: فشله يُعدّ عليه، ويُبطَّأ وحده دون الاسم."""
    settings.AXES_ENABLED = True
    assert _login(client).status_code == 200
    client.post("/api/auth/logout")
    for index in range(services.NAME_FAILURE_LIMIT + 1):  # الأخيرة تأخذ فرصة الفترة
        client.post(
            "/api/auth/login",
            {"username": "staff", "password": "y" * 12},
            content_type="application/json",
            REMOTE_ADDR=f"198.51.100.{index + 1}",
        )
    assert _login(client).status_code == 429
    from django.test import Client

    assert _login(Client()).status_code == 200  # الاسم لم يُحجب على غيره


@pytest.mark.django_db
def test_owner_on_a_new_device_gets_in_once_the_slow_slot_frees(client, staff_user, settings):
    """ح1: بلوغ الحدّ لا يقفل صاحب الحساب على جهاز جديد: الفرصة التالية تجرّب كلمته فيدخل، ويُصفَّر العدّاد."""
    from django.core.cache import cache
    from django.test import Client

    settings.AXES_ENABLED = True
    _guess_from_many_addresses(services.NAME_FAILURE_LIMIT + 1)
    owner = Client()
    assert _login(owner, REMOTE_ADDR="198.51.100.4").status_code == 429
    cache.delete(services._slow_slot_key(services._name_failures_key("staff")))  # انقضت الفترة
    assert _login(owner, REMOTE_ADDR="198.51.100.4").status_code == 200
    assert cache.get(services._name_failures_key("staff")) is None
    owner.post("/api/auth/logout")
    _guess_from_many_addresses(1)
    assert _login(Client(), REMOTE_ADDR="198.51.100.5").status_code == 200  # لا حجب بعد خطأ واحد


@pytest.mark.django_db
def test_a_locked_pair_cannot_hog_the_slow_slot(client, staff_user, settings):
    """عنوان قفله axes لا يأخذ فرصة الفترة، فلا يحجب به المهاجم صاحب الحساب."""
    from django.core.cache import cache
    from django.test import Client

    settings.AXES_ENABLED = True
    locked = {"REMOTE_ADDR": "203.0.113.250"}
    _fail_logins(client, settings.AXES_FAILURE_LIMIT, **locked)  # يُقفل الزوج قبل بلوغ حدّ الاسم
    _guess_from_many_addresses(services.NAME_FAILURE_LIMIT)
    cache.delete(services._slow_slot_key(services._name_failures_key("staff")))  # انقضت الفترة
    _fail_logins(client, 10, **locked)  # إغراق من الزوج المقفول
    assert _login(Client(), REMOTE_ADDR="198.51.100.4").status_code == 200


@pytest.mark.django_db
def test_sign_in_resets_the_device_counter(client, staff_user, settings):
    """ح2: مشرف أخطأ حتى قُبيل الحدّ ثم دخل لا يُحجب بعد خطأ واحد لاحق."""
    settings.AXES_ENABLED = True
    assert _login(client).status_code == 200
    client.post("/api/auth/logout")
    for round_ in range(2):
        for index in range(services.NAME_FAILURE_LIMIT - 1):
            client.post(
                "/api/auth/login",
                {"username": "staff", "password": "y" * 12},
                content_type="application/json",
                REMOTE_ADDR=f"198.51.{round_}.{index + 1}",
            )
        assert _login(client, REMOTE_ADDR="198.51.100.250").status_code == 200
        client.post("/api/auth/logout")


@pytest.mark.django_db
def test_failures_rejected_by_pair_lock_do_not_count_on_the_name(client, staff_user, settings):
    """هـ1: بعد أن يقفل axes الزوج لا تُجرَّب كلمة المرور، فلا يكفي عنوان واحد لقفل الاسم."""
    from django.test import Client

    settings.AXES_ENABLED = True
    _fail_logins(client, services.NAME_FAILURE_LIMIT + 5, REMOTE_ADDR="203.0.113.7")
    assert _login(Client(), REMOTE_ADDR="198.51.100.4").status_code == 200


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
def test_client_address_diagnostics_is_staff_only(client, staff_user, django_user_model, settings):
    path = "/api/diagnostics/client-address"
    assert client.get(path).status_code == 401
    django_user_model.objects.create_user("plain", password="x" * 12)
    client.login(username="plain", password="x" * 12)
    assert client.get(path).status_code == 401

    client.force_login(staff_user)
    settings.TRUSTED_PROXY_COUNT = 1
    seen = client.get(
        path,
        REMOTE_ADDR="10.0.0.1",
        HTTP_X_FORWARDED_FOR="1.1.1.1, 203.0.113.9",
        HTTP_X_REAL_IP="203.0.113.9",
    )
    assert seen.json() == {
        "remote_addr": "10.0.0.1",
        "x_forwarded_for": "1.1.1.1, 203.0.113.9",
        "x_real_ip": "203.0.113.9",
        "trusted_proxy_count": 1,
        "client_ip": "203.0.113.9",
    }
    bare = client.get(path, REMOTE_ADDR="10.0.0.1").json()
    assert (bare["x_forwarded_for"], bare["x_real_ip"], bare["client_ip"]) == ("", "", "10.0.0.1")


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
def test_audit_truncates_oversized_request_id():
    assert services.record_audit(action="x", request_id="r" * 500).request_id == "r" * 64


@pytest.mark.django_db
def test_repeated_request_id_does_not_hide_audit_views(client, staff_user, django_user_model):
    """الترويسة يكتبها العميل: تكرارها لا يُسقط اطّلاع مشرف آخر من السجل."""
    other = django_user_model.objects.create_user(username="other", password="x" * 12, is_staff=True)
    for user in (staff_user, other):
        client.force_login(user)
        assert client.get("/api/audit", headers={"X-Request-ID": "same"}).status_code == 200
    views = AuditLog.objects.filter(action="audit.view")
    assert sorted(views.values_list("actor_name", flat=True)) == ["other", "staff"]


@pytest.mark.django_db
def test_repeated_request_id_does_not_hide_logins(staff_user):
    from django.test import Client

    for _ in range(2):
        client = Client()
        res = client.post(
            "/api/auth/login",
            {"username": "staff", "password": "x" * 12},
            content_type="application/json",
            headers={"X-Request-ID": "same"},
        )
        assert res.status_code == 200, res.content
        assert client.post("/api/auth/logout", headers={"X-Request-ID": "same"}).status_code == 200
    assert AuditLog.objects.filter(action="auth.login", actor=staff_user).count() == 2
    assert AuditLog.objects.filter(action="auth.logout", actor=staff_user).count() == 2


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


@pytest.mark.django_db
def test_admin_header_shows_ribbon_lockup_for_each_palette(client, staff_user, settings):
    import re

    from django.contrib.staticfiles import finders

    # شعار اللوحة قفل الشريط بنسخة السمة الجارية لا اسمًا نصيًّا؛ الاسم باقٍ لقارئ الشاشة.
    client.force_login(staff_user)
    index = client.get("/" + settings.ADMIN_URL).content.decode()
    assert re.search(r'<a class="brand-logo" href="[^"]+"><span class="brand-name">', index)
    css = open(finders.find("core/admin-theme.css"), encoding="utf-8").read()
    palettes = [
        "navy",
        "royal-blue",
        "teal",
        "emerald",
        "olive",
        "purple",
        "rose",
        "chocolate",
        "black",
        "oud",
    ]
    for palette in palettes:
        name = f"misk-lockup-ribbon-{palette}.png"
        assert (
            f'html[data-palette="{palette}"] #site-name a.brand-logo {{ background-image: url("../brand/logo/{name}"); }}'
            in css
        )
        assert finders.find(f"brand/logo/{name}")


def test_spa_applies_stored_theme_before_paint(client):
    from django.contrib.staticfiles import finders

    # سكربت الوضع ملف ثابت يسبق حزم الواجهة في <head>، فيُضبط data-theme قبل الرسم.
    page = client.get("/").content.decode()
    assert page.index("/static/core/theme-init.js") < page.index("src/main.ts")
    assert finders.find("core/theme-init.js")


@pytest.mark.django_db
def test_shell_health_and_robots_answer_head_and_reject_writes(client):
    # أدوات مراقبة التوفر تسأل بـ HEAD؛ كان require_GET يرفضه بـ 405.
    for url in ("/", "/orders", "/health/", "/robots.txt"):
        assert client.head(url).status_code == 200, url
        assert client.post(url).status_code == 405, url
    res = client.get("/robots.txt")
    assert res["Content-Type"].startswith("text/plain")
    assert res.content.decode() == "User-agent: *\nDisallow: /\n"


def test_webmanifest_is_served_as_manifest_json(settings):
    from whitenoise.media_types import MediaTypes

    types = MediaTypes(extra_types=settings.WHITENOISE_MIMETYPES)
    assert types.get_type("static/site.webmanifest") == "application/manifest+json"


@pytest.mark.django_db
def test_pending_migrations_exits_zero_when_all_are_applied(capsys):
    from django.core.management import call_command

    call_command("pending_migrations")
    assert "مطبَّقة" in capsys.readouterr().out


@pytest.mark.django_db
def test_pending_migrations_exits_three_and_names_them(monkeypatch, capsys):
    """د8: رمز الانتظار 3 لا 1، فلا يختلط بعطل القاعدة أو الإعداد."""
    from django.core.management import call_command
    from django.db.migrations.executor import MigrationExecutor

    from apps.core.management.commands.pending_migrations import PENDING_EXIT

    class Pending:
        app_label, name = "orders", "0099_later"

    monkeypatch.setattr(MigrationExecutor, "migration_plan", lambda self, targets: [(Pending, False)])
    with pytest.raises(SystemExit) as stop:
        call_command("pending_migrations")
    assert stop.value.code == PENDING_EXIT
    assert "orders.0099_later" in capsys.readouterr().out


@pytest.fixture
def media_files(settings, tmp_path):
    root = tmp_path / "media"
    (root / "designs" / "files").mkdir(parents=True)
    (root / "designs" / "files" / "a.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', "utf-8")
    (root / "designs" / "files" / "a.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "secret.txt").write_text("x", "utf-8")
    settings.MEDIA_ROOT = root
    return root


@pytest.fixture
def staff_client(client, django_user_model):
    client.force_login(django_user_model.objects.create_user("staff", password="x", is_staff=True))
    return client


@pytest.mark.django_db
def test_media_hidden_from_anonymous_and_non_staff(client, django_user_model, media_files):
    # أصول التصاميم مرخّصة: غير المشرف لا يراها ولا يعرف أنها موجودة.
    assert client.get("/media/designs/files/a.svg").status_code == 404
    client.force_login(django_user_model.objects.create_user("user", password="x"))
    assert client.get("/media/designs/files/a.svg").status_code == 404


@pytest.mark.django_db
def test_media_svg_inline_sandboxed_for_staff(staff_client, media_files):
    res = staff_client.get("/media/designs/files/a.svg")
    assert res.status_code == 200
    assert res["Content-Type"] == "image/svg+xml"
    assert res["Content-Disposition"].startswith("inline")
    assert "sandbox" in res["Content-Security-Policy"]
    assert "script-src" not in res["Content-Security-Policy"]
    assert res["Cache-Control"] == "private, max-age=3600"
    assert b"<svg" in b"".join(res.streaming_content)


@pytest.mark.django_db
def test_media_non_image_downloads_as_attachment(staff_client, media_files):
    res = staff_client.get("/media/designs/files/a.pdf")
    assert res.status_code == 200
    assert res["Content-Disposition"].startswith("attachment")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path", ["../secret.txt", "designs/../../secret.txt", "designs/files/missing.svg", "designs"]
)
def test_media_rejects_traversal_missing_and_dirs(staff_client, media_files, path):
    assert staff_client.get(f"/media/{path}").status_code == 404


@pytest.mark.django_db
def test_media_rejects_writes(staff_client, media_files):
    assert staff_client.post("/media/designs/files/a.svg").status_code == 405
