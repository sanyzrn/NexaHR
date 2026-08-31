"""خطاهای سرویس هوش مصنوعی: هیچ ۵۰۰، و هر پیام قابلِ اقدام.

سه چیزی که کاربر واقعاً دید و این فایل جلوی هر سه را می‌گیرد
--------------------------------------------------------------
۱. «خطای داخلی سرور رخ داد؛ این شناسه را به پشتیبانی اعلام کنید» — یعنی کدِ ما
   شکسته بود، نه سرویس. دو راهِ فرار باز بود و هر دو با ورودیِ کاملاً معمولی
   می‌شکستند (`httpx.InvalidURL` که زیرمجموعهٔ `HTTPError` نیست، و
   `UnicodeEncodeError` از یک نویسهٔ *نامرئی* در کلید).

۲. `403: <!DOCTYPE html> <html lang=en> …` — پاسخِ HTML یک سرویس، خام در رابط.
   نه چیزی می‌گفت و نه در نوار پیام جا می‌شد.

۳. `429: Provider returned error` — حرفِ خودِ سرویس، ولی بی‌معنا برای کاربر.
   کدِ وضعیت تنها چیزی است که آن‌جا معنا دارد و ترجمه‌اش کارِ ماست.

اولی از همه مهم‌تر است: ۵۰۰ به کاربر می‌گوید «به پشتیبانی زنگ بزن» برای چیزی که
خودش می‌توانست در ده ثانیه درست کند.
"""
import asyncio

import httpx
import pytest
from sqlalchemy import select

from app.core.crypto import decrypt
from app.models.ai import AiProviderCredential
from app.models.enums import Capability
from app.services.ai.port import AiRequestFailed, ChatMessage
from app.services.ai.provider import OpenAiCompatibleAdapter, _error_text, clean_secret
from tests.helpers import auth_header, enable_ai_provider, make_user


def _admin(db):
    user = make_user(db, "support", username="err_admin", capabilities=[Capability.manage_ai])
    enable_ai_provider(db)
    db.commit()
    return user


def _adapter(**kw):
    kw.setdefault("base_url", "http://127.0.0.1:1/v1")
    kw.setdefault("api_key", "sk-test")
    kw.setdefault("model", "m")
    kw.setdefault("timeout_seconds", 5)
    return OpenAiCompatibleAdapter(**kw)


def _send(adapter):
    """کوروتین را همین‌جا اجرا کن.

    این سوئیت هیچ افزونهٔ تستِ async ندارد و آوردنِ یکی برای چند تست، وابستگی
    تازه‌ای است که ارزشش را ندارد.
    """
    return asyncio.run(adapter.send([ChatMessage("user", "سلام")]))


# ── هیچ ورودی‌ای نباید از آداپتور استثنای پیش‌بینی‌نشده بیرون بدهد ──────────


@pytest.mark.parametrize(
    ("label", "base_url"),
    [
        ("پورت غیرعددی", "http://example.com:abc/v1"),
        ("IPv6 نصفه", "http://[::1/v1"),
        ("نویسهٔ کنترلی", "http://exam\x00ple.com/v1"),
        ("خط جدید", "http://exam\nple.com/v1"),
    ],
)
def test_a_malformed_address_is_a_message_not_a_crash(label, base_url):
    """`httpx.InvalidURL` مستقیم از `Exception` می‌آید و نه از `HTTPError`.

    یعنی `except httpx.HTTPError` نمی‌گرفتش و یک پورتِ اشتباه — چیزی که هر کسی
    ممکن است تایپ کند — به ۵۰۰ می‌رسید.
    """
    with pytest.raises(AiRequestFailed) as caught:
        _send(_adapter(base_url=base_url))

    assert "آدرس سرویس معتبر نیست" in caught.value.detail, label
    # نمونهٔ آدرسِ درست در پیام باشد، وگرنه کاربر نمی‌داند چه شکلی باید بنویسد.
    assert "https://api.openai.com/v1" in caught.value.detail


@pytest.mark.parametrize(
    ("label", "api_key"),
    [
        ("حرف فارسی", "sk-کلید"),
        ("خط تیرهٔ بلند", "sk-ab—cd"),
        ("حرف لاتینِ مزین", "sk-abcdé"),
    ],
)
def test_a_visible_non_ascii_key_says_which_character(label, api_key):
    """پیام باید *خودِ نویسه* را نشان بدهد.

    خطای اصلی `UnicodeEncodeError: 'ascii' codec can't encode…` بود با شمارهٔ
    بایت — چیزی که به کاربر نمی‌شود گفت. کسی که یک «ی» فارسی وسط کلیدش جا مانده
    باید بداند دنبالِ چه بگردد.
    """
    with pytest.raises(AiRequestFailed) as caught:
        _send(_adapter(api_key=api_key))

    detail = caught.value.detail
    assert "کلید API نویسهٔ غیرانگلیسی دارد" in detail, label
    assert any(ch in detail for ch in api_key if ord(ch) > 127), "خودِ نویسه باید در پیام باشد"


def test_the_model_name_gets_the_same_guard():
    with pytest.raises(AiRequestFailed) as caught:
        _send(_adapter(model="مدل"))
    assert "نام مدل نویسهٔ غیرانگلیسی دارد" in caught.value.detail


# ── نویسه‌های نامرئی: بی‌سروصدا پاک، نه رد ────────────────────────────────


@pytest.mark.parametrize(
    ("label", "raw"),
    [
        ("فاصلهٔ صفر", "sk-ab​cd"),
        ("نیم‌فاصله", "sk-ab‌cd"),
        ("نشانهٔ چپ‌به‌راست", "sk-ab‎cd"),
        ("نشانهٔ راست‌به‌چپ", "sk-ab‏cd"),
        ("علامت ترتیب بایت", "sk-ab﻿cd"),
        ("فاصلهٔ دو سر", "  sk-abcd  "),
    ],
)
def test_invisible_characters_are_stripped_silently(label, raw):
    """این‌ها هیچ‌وقت بخشی از یک کلید نیستند و کاربر هم نمی‌بیندشان.

    رد کردنشان با پیام یعنی کاربر به دنبالِ چیزی می‌رود که روی صفحه دیده
    نمی‌شود. کپی‌کردنِ کلید از یک متنِ راست‌به‌چپ خیلی راحت یکی از این‌ها را
    همراه می‌آورد.
    """
    assert clean_secret(raw) == "sk-abcd", label


def test_a_non_breaking_space_becomes_a_normal_one():
    # NFKC این کار را می‌کند؛ آزمودنش لازم است چون رفتارِ نرمال‌سازی بی‌صداست.
    assert clean_secret("sk-ab cd") == "sk-ab cd"


def test_cleaning_keeps_a_visible_wrong_character_instead_of_hiding_it():
    """پاک‌کردنِ نویسهٔ دیدنی یعنی کلیدی به سرویس برود که کاربر وارد نکرده.

    آن‌وقت پاسخ ۴۰۱ می‌شود و کاربر دنبالِ اشکالی می‌گردد که وجود ندارد. پس
    این‌جا دست‌نخورده می‌ماند و `send` صریح ردش می‌کند.
    """
    assert clean_secret("sk-ab—cd") == "sk-ab—cd"


def test_a_clean_key_passes_through_untouched():
    assert clean_secret("sk-ant-api03_AbC-123_xyz") == "sk-ant-api03_AbC-123_xyz"


# ── متنِ خطا: خواندنی، و با راهنمایی که خودِ سرویس نمی‌دهد ────────────────


def test_an_html_error_page_becomes_one_readable_line():
    """همان ۴۰۳ی که کاربر دید — صفحهٔ خطای گوگل.

    وقتی درخواست به خودِ API نمی‌رسد (مسیر اشتباه، دیوار میانی)، پاسخ HTML است.
    ریختنِ ۳۰۰ نویسه از `<!DOCTYPE html>…` هم چیزی نمی‌گوید و هم چیدمان را
    خراب می‌کند.
    """
    page = (
        "<!DOCTYPE html>\n<html lang=en>\n<meta charset=utf-8>\n"
        "<title>Error 403 (Forbidden)!!1</title>\n<style>*{margin:0;padding:0}</style>\n"
        "<p><b>403.</b> <ins>That’s an error.</ins>"
    )

    text = _error_text(httpx.Response(403, text=page))

    assert "<" not in text and "DOCTYPE" not in text
    assert "Error 403 (Forbidden)" in text, "عنوانِ صفحه تنها بخشِ معنادار آن است"
    assert len(text) < 260, "باید در یک نوار پیام جا شود"


def test_a_generic_provider_message_gets_the_status_explained():
    """همان ۴۲۹ی که کاربر دید: «Provider returned error» چیزی نمی‌گوید."""
    text = _error_text(httpx.Response(429, json={"error": {"message": "Provider returned error"}}))

    assert "Provider returned error" in text, "حرفِ خودِ سرویس حذف نمی‌شود"
    assert "سهمیه" in text and "دوباره امتحان" in text


@pytest.mark.parametrize(
    ("code", "needle"),
    [(401, "کلید API پذیرفته نشد"), (403, "دسترسی را رد کرد"), (404, "وجود ندارد"), (503, "در دسترس نیست")],
)
def test_each_status_carries_its_own_fix(code, needle):
    """تفاوتِ ۴۰۱ با «مدل پیدا نشد» چهار رفعِ متفاوت است."""
    assert needle in _error_text(httpx.Response(code, json={"error": {"message": "x"}}))


def test_the_service_s_own_sentence_is_never_replaced():
    """وقتی سرویس حرفِ گویایی دارد، همان مهم‌ترین بخشِ پیام است."""
    text = _error_text(
        httpx.Response(404, json={"error": {"message": "The model `gpt-5-turbo` does not exist"}})
    )
    assert "gpt-5-turbo" in text


def test_an_empty_body_still_says_something():
    assert "بدون توضیح" in _error_text(httpx.Response(502, text=""))


def test_a_string_shaped_error_field_is_read_too():
    # بعضی سرویس‌ها `{"error": "..."}` می‌دهند و نه `{"error": {"message": …}}`.
    assert "bad request" in _error_text(httpx.Response(400, json={"error": "bad request"}))


# ── و همین‌ها از راهِ مسیرِ واقعی ─────────────────────────────────────────


@pytest.mark.parametrize(
    ("label", "payload"),
    [
        ("پورت غیرعددی", {"base_url": "http://x:abc/v1", "model": "m", "api_key": "k"}),
        ("خط جدید در آدرس", {"base_url": "http://x\ny/v1", "model": "m", "api_key": "k"}),
        ("کلید فارسی", {"base_url": "http://127.0.0.1:1/v1", "model": "m", "api_key": "کلید"}),
        ("کلید با نیم‌فاصله", {"base_url": "http://127.0.0.1:1/v1", "model": "m", "api_key": "s‌k"}),
        ("مدل فارسی", {"base_url": "http://127.0.0.1:1/v1", "model": "مدل", "api_key": "k"}),
    ],
)
def test_the_test_connection_route_never_returns_500(client, db_session, label, payload):
    """گاردِ نهایی: مسیرِ «آزمودن اتصال» باید *همیشه* ۲۰۰ با توضیح بدهد.

    این مسیر کارش همین است که خرابی را نشان بدهد؛ ۵۰۰ گرفتنش یعنی ابزارِ
    عیب‌یابی خودش عیب دارد.
    """
    admin = _admin(db_session)

    response = client.post("/api/ai/settings/test", json=payload, headers=auth_header(admin))

    assert response.status_code == 200, f"{label}: {response.text[:200]}"
    body = response.json()
    assert body["ok"] is False
    assert body["detail"], label
    assert "پشتیبانی" not in body["detail"], f"{label}: پیامِ ۵۰۰ به کاربر رسیده"


def test_a_saved_key_is_cleaned_before_it_reaches_the_database(client, db_session):
    """نویسهٔ نامرئی نباید در دیتابیس بنشیند و هر بار سرِ درخواست پاک شود.

    اگر فقط سرِ درخواست پاک شود، `api_key_hint` هم چهار نویسهٔ آخرِ *ناپاک* را
    نشان می‌دهد و کاربر کلیدِ خودش را در فهرست نمی‌شناسد.
    """
    admin = _admin(db_session)
    client.put(
        "/api/ai/settings",
        json={"provider": "anthropic", "api_key": "  sk-ant‏-1234  "},
        headers=auth_header(admin),
    )

    row = db_session.scalar(
        select(AiProviderCredential).where(AiProviderCredential.provider == "anthropic")
    )
    assert decrypt(row.api_key_encrypted) == "sk-ant-1234"
