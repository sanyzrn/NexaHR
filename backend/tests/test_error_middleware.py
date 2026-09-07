"""پاسخِ ۵۰۰ امن — تضمینی که در تولید کار می‌کند و هیچ تستی نداشت.

`main.request_context` چهار چیز را با هم وعده می‌دهد:

1. خطای مهارنشده به ۵۰۰ تبدیل شود و نه به یک خطای خامِ ASGI،
2. متنِ استثنا **به کاربر نرسد**،
3. یک شناسهٔ درخواست در هدرِ `X-Request-ID` و *داخلِ* متنِ فارسی بیاید تا
   کاربر بتواند همان را به پشتیبانی بگوید،
4. و آن درخواست در سنجهٔ ۵۰۰ شمرده شود.

`rg` روی کلِ `tests/` هیچ ارجاعی به `request_context` یا `X-Request-ID`
نداشت. تنها تستی که ۵۰۰ را می‌سنجید، `HTTPException(500)`ِ عمدی بود — که
FastAPI پیش از رسیدن به این میدل‌ور خودش مدیریتش می‌کند، پس از این مسیر
اصلاً رد نمی‌شود.

گزارشِ ممیزی با جهش نشان داد نتیجه‌اش چه بود: جایگزینیِ متنِ امن با
`repr(exc)` — یعنی نشتِ کاملِ استثنای داخلی به کلاینت — از ۲۵ تست سبز رد شد.

`raise_server_exceptions=False` لازم است: پیش‌فرضِ `TestClient` استثنا را
بالا می‌دهد تا در تست دیده شود، و آن‌وقت این تست خودِ رفتارِ تولید را
نمی‌سنجد.
"""
import re

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.db.session import get_db
from app.main import app

#: متنی که نباید هیچ‌وقت به کلاینت برسد.
SECRET = "internal-detail-that-must-not-leak"


@pytest.fixture
def crashing_client(db_session):
    """کلاینتی که یک وابستگیِ واقعی را به استثنا وادار می‌کند.

    `get_current_user` عمداً انتخاب شده و نه یک روتِ ساختگی: مسیرِ خطا باید
    همان مسیری باشد که یک درخواستِ واقعی طی می‌کند.
    """

    def _boom():
        raise RuntimeError(SECRET)

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _boom
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_an_unhandled_error_becomes_a_safe_persian_500(crashing_client):
    response = crashing_client.get("/api/evaluations")
    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "خطای داخلی سرور" in detail
    assert SECRET not in response.text, "متنِ استثنا به کلاینت رسید"
    assert "RuntimeError" not in response.text
    assert "Traceback" not in response.text


def test_the_request_id_is_both_a_header_and_something_the_user_can_read(crashing_client):
    """شناسه باید *در متن* هم باشد.

    کاربری که صفحهٔ خطا را می‌بیند هدرها را نمی‌خواند؛ تنها چیزی که می‌تواند
    به پشتیبانی بگوید همان رشته‌ای است که روی صفحه دیده.
    """
    response = crashing_client.get("/api/evaluations")
    request_id = response.headers.get("X-Request-ID")
    assert request_id, "هدرِ X-Request-ID نیامد"
    assert re.fullmatch(r"[0-9a-f]{12}", request_id), request_id
    assert request_id in response.json()["detail"]


def test_each_request_gets_its_own_id(crashing_client):
    first = crashing_client.get("/api/evaluations").headers["X-Request-ID"]
    second = crashing_client.get("/api/evaluations").headers["X-Request-ID"]
    assert first != second


def test_a_healthy_response_also_carries_the_id(client):
    """مسیرِ موفق هم شناسه می‌گیرد — وگرنه فقط خطاها قابلِ پیگیری‌اند."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert re.fullmatch(r"[0-9a-f]{12}", response.headers["X-Request-ID"])


def test_the_failure_is_counted_as_a_500_in_the_metrics(crashing_client, monkeypatch):
    """و در سنجه‌ها ۵۰۰ شمرده می‌شود، نه اینکه بی‌صدا گم شود."""
    seen: list[tuple] = []
    import app.main as main_module

    real = main_module.record_request
    monkeypatch.setattr(
        main_module,
        "record_request",
        lambda method, path, status, duration: seen.append((method, path, status)) or real(
            method, path, status, duration
        ),
    )
    crashing_client.get("/api/evaluations")
    assert any(status == 500 for _, _, status in seen), seen
    # و مسیر با قالبِ روت ثبت می‌شود، نه با URL خام.
    assert any(path.startswith("/api/evaluations") for _, path, _ in seen), seen
