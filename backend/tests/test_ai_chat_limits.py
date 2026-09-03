"""سقفِ گفت‌وگوی دستیار (N13).

پیش از این `/api/ai/chat` هیچ سقفی نداشت: نه سقفِ نرخِ per-IP (فقط سه مسیرِ
ورود و تأیید داشتند) و نه سقفِ روزانه — چون پیش‌فرضِ ستون صفر بود و کد صفر را
«بی‌حد» می‌خواند. یعنی *همهٔ* حساب‌ها بی‌حد بودند، در سامانه‌ای که هر پیامش یک
فراخوانِ پرداختی است و کلِ تاریخچهٔ گفت‌وگو را با خود می‌برد.
"""

from app.api.routers.ai import resolve_daily_limit
from app.core.config import settings
from app.models.ai import AiUserAccess
from tests.helpers import auth_header, enable_ai_provider, make_user


class _Access:
    def __init__(self, limit: int):
        self.daily_message_limit = limit


def test_zero_means_system_default_not_unlimited():
    """قلبِ ماجرا: صفر پیش از این «بی‌حد» بود."""
    assert resolve_daily_limit(_Access(0)) == settings.ai_daily_message_limit
    assert resolve_daily_limit(_Access(0)) is not None


def test_default_is_a_real_number():
    assert settings.ai_daily_message_limit == 100


def test_positive_value_wins_over_default():
    assert resolve_daily_limit(_Access(7)) == 7


def test_negative_one_is_explicit_unlimited():
    """بی‌حد باید چیزی باشد که کسی *انتخابش* می‌کند، نه پیش‌فرض."""
    assert resolve_daily_limit(_Access(-1)) is None


def test_stored_default_of_new_row_resolves_to_the_cap(db_session):
    """ردیفِ تازه بی هیچ مایگریشنی زیرِ سقف می‌آید."""
    db = db_session
    user = make_user(db, "hr")
    access = AiUserAccess(user_id=user.id)
    db.add(access)
    db.flush()
    assert access.daily_message_limit == 0
    assert resolve_daily_limit(access) == settings.ai_daily_message_limit


def test_chat_is_rate_limited(client, db_session, monkeypatch):
    """سقفِ نرخِ per-IP روی خودِ مسیر می‌نشیند.

    سهمیه در همین تست مصرف می‌شود و فیکسچرِ `_reset_rate_limiter` سطل را
    بعدش خالی می‌کند، پس تست‌های دیگر آسیب نمی‌بینند.
    """
    monkeypatch.setattr(settings, "ai_chat_rate_limit", "3/minute")
    db = db_session
    enable_ai_provider(db)
    user = make_user(db, "hr")
    db.add(AiUserAccess(user_id=user.id, enabled=True))
    db.commit()

    # سقفِ ثبت‌شده روی خودِ decorator است و در import قطعی می‌شود، پس عددِ
    # واقعیِ اجرا همان پیکربندیِ ماژول است؛ این‌جا فقط می‌سنجیم که *سقفی هست*.
    codes = [
        client.post("/api/ai/chat", json={"message": "سلام"}, headers=auth_header(user)).status_code
        for _ in range(25)
    ]
    assert 429 in codes, f"هیچ درخواستی رد نشد: {sorted(set(codes))}"


def test_chat_route_is_registered_with_the_limiter():
    """گاردِ رگرسیون: اگر کسی decorator را برداشت، این می‌شکند.

    ثبتِ سقف در `limiter._route_limits` اتفاق می‌افتد و کلیدش نامِ کاملِ تابع
    است — یعنی سنجشِ *مستقیمِ* همان چیزی که برداشتنش سوراخ را باز می‌کند.
    """
    from app.core.rate_limit import limiter

    assert "app.api.routers.ai.chat" in limiter._route_limits
