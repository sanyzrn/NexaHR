"""ذخیره در UTC، سنجش و نمایش در وقتِ محلی (N11/N12).

پیش از این هر دو مرز UTC بودند، و برای تهران (`UTC+3:30`) نتیجه‌اش این:

* سندِ رسمیِ هش‌شده برای نهایی‌شدنِ ۱:۰۰ بامداد، *روزِ قبل* را چاپ می‌کرد؛
* بین ۰۰:۰۰ و ۰۳:۲۹ بامداد، «امروز»ِ سامانه دیروز بود، پس مهلتی که دیشب
  تمام شده بود باز به‌نظر می‌رسید.
"""
from datetime import UTC, date, datetime

import pytest

from app.core import clock
from app.core.config import settings
from app.services.evaluation_window import Window
from app.services.pdf import to_jalali


@pytest.fixture
def tehran(monkeypatch):
    monkeypatch.setattr(settings, "org_timezone", "Asia/Tehran")


def test_midnight_edge_keeps_the_local_day(tehran):
    """۲۱:۳۰ UTC همان ۱:۰۰ بامدادِ *فردا* در تهران است."""
    assert clock.to_local(datetime(2025, 10, 6, 21, 30, tzinfo=UTC)) == datetime(
        2025, 10, 7, 1, 0, tzinfo=clock.org_timezone()
    )


def test_naive_datetime_is_read_as_utc(tehran):
    """ستون‌های زمانی با `datetime.now(UTC)` نوشته می‌شوند؛ فرض باید صریح باشد."""
    naive = clock.to_local(datetime(2025, 10, 6, 21, 30))
    aware = clock.to_local(datetime(2025, 10, 6, 21, 30, tzinfo=UTC))
    assert naive == aware


def test_official_document_prints_the_local_day(tehran):
    """قلبِ ماجرا: تاریخِ روی سند.

    نهایی‌شده ۱:۰۰ بامدادِ ۷ اکتبر تهران = ۲۱:۳۰ ششم اکتبر UTC.
    سند باید ۱۵ مهر را بگوید، نه ۱۴ مهر.
    """
    rendered = to_jalali(datetime(2025, 10, 6, 21, 30, tzinfo=UTC))
    assert rendered == "۱۴۰۴/۰۷/۱۵ ساعت ۰۱:۰۰", rendered
    # همان لحظه با قاعدهٔ قدیمی «۱۴۰۴/۰۷/۱۴ ساعت ۲۱:۳۰» می‌شد
    assert "۱۴۰۴/۰۷/۱۴" not in rendered


def test_iso_string_snapshots_also_shift(tehran):
    """اسنپ‌شات‌ها رشتهٔ ISO نگه می‌دارند، نه `datetime`."""
    assert to_jalali("2025-10-06T21:30:00+00:00") == "۱۴۰۴/۰۷/۱۵ ساعت ۰۱:۰۰"


def test_invalid_timezone_fails_loudly(monkeypatch):
    """غلطِ تایپی نباید بی‌صدا به همان رفتارِ اشتباه برگردد."""
    monkeypatch.setattr(settings, "org_timezone", "Asia/Tehrn")
    with pytest.raises(RuntimeError, match="ORG_TIMEZONE"):
        clock.org_timezone()


def test_submission_window_uses_local_today(monkeypatch, tehran):
    """مهلتی که دیشبِ محلی تمام شده، امروز باز نیست.

    ساعت ۱:۰۰ بامدادِ ۷ اکتبر تهران است. مهلت ۶ اکتبر بوده، پس گذشته.
    با `date.today()`ِ UTC، «امروز» ۶ اکتبر دیده می‌شد و پنجره باز می‌ماند.
    """
    monkeypatch.setattr(clock, "now_local", lambda: datetime(
        2025, 10, 7, 1, 0, tzinfo=clock.org_timezone()
    ))
    window = Window(closes_on=date(2025, 10, 6))
    assert window.is_open is False
    assert window.days_left == -1


def test_submission_window_open_before_deadline(monkeypatch, tehran):
    monkeypatch.setattr(clock, "now_local", lambda: datetime(
        2025, 10, 5, 23, 0, tzinfo=clock.org_timezone()
    ))
    window = Window(closes_on=date(2025, 10, 6))
    assert window.is_open is True
    assert window.days_left == 1


def test_date_filter_boundary_is_the_local_midnight(tehran):
    """مرزِ بازهٔ فیلترِ تاریخ باید نیمه‌شبِ *محلی* باشد، نه UTC.

    این را تستِ خودِ سوئیت لو داد: ساعت ۰۰:۰۷ بامدادِ تهران، ردیفی که همان
    لحظه ساخته می‌شد با فیلترِ «امروز» پیدا نمی‌شد — چون ستون `timestamptz`
    است و مقایسهٔ مستقیمِ یک `date` با آن، نیمه‌شبِ UTC را مرز می‌گیرد. یعنی
    سه‌ونیم ساعتِ اولِ هر روزِ محلی از فیلتر جا می‌افتاد و زیرِ روزِ قبل دیده
    می‌شد.
    """
    from app.core.clock import local_day_end, local_day_start

    day = date(2025, 10, 7)
    start = local_day_start(day)
    end = local_day_end(day)

    # نیمه‌شبِ ۷ اکتبرِ تهران = ۲۰:۳۰ ششمِ اکتبر به‌وقتِ UTC
    assert start == datetime(2025, 10, 6, 20, 30, tzinfo=UTC)
    assert end == datetime(2025, 10, 7, 20, 30, tzinfo=UTC)
    assert (end - start).total_seconds() == 24 * 3600

    # لحظه‌ای که پیش از این زیرِ روزِ قبل می‌افتاد، حالا داخلِ بازه است
    one_am_local = datetime(2025, 10, 6, 21, 30, tzinfo=UTC)  # ۱:۰۰ بامدادِ ۷ اکتبر
    assert start <= one_am_local < end


def test_filter_boundary_moves_with_the_timezone(monkeypatch):
    """اگر سازمان UTC باشد، مرز همان نیمه‌شبِ UTC است — قاعده یکی است."""
    from app.core.clock import local_day_start

    monkeypatch.setattr(settings, "org_timezone", "UTC")
    assert local_day_start(date(2025, 10, 7)) == datetime(2025, 10, 7, 0, 0, tzinfo=UTC)
