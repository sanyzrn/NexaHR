"""منطقهٔ زمانیِ سازمان — یک جا، و همان جا که تاریخ *دیده* یا *سنجیده* می‌شود.

سامانه همه‌جا در UTC ذخیره می‌کند و باید همین کار را بکند: زمانِ ذخیره‌شده
باید بی‌ابهام باشد و مستقل از این‌که سرور کجا اجرا می‌شود. ولی دو جا UTC
جوابِ *غلط* می‌دهد:

۱. **نمایش.** `to_jalali` ساعتِ دیواریِ UTC را به شمسی ترجمه می‌کرد، پس سندِ
   رسمیِ هش‌شده — همان PDFِ دارای QR — ساعتِ تهران را نشان نمی‌داد. تهران
   `UTC+3:30` است، و برای نهایی‌شدنِ ساعت ۱:۰۰ بامداد، سند *روزِ قبل* را چاپ
   می‌کرد:

       نهایی‌شده ۱:۰۰ بامدادِ ۱۴۰۴/۰۷/۱۵ تهران
       = ۲۱:۳۰ روزِ ۱۴۰۴/۰۷/۱۴ به‌وقتِ UTC
       ⇒ سند: «تاریخ نهایی‌شدن: ۱۴۰۴/۰۷/۱۴ ساعت ۲۱:۳۰»

۲. **«امروز».** هر پنجره‌ای که با `date.today()` سنجیده می‌شد، تاریخِ UTCِ
   سرور را «امروز» می‌گرفت. بین ۰۰:۰۰ و ۰۳:۲۹ بامدادِ تهران آن تاریخ *دیروز*
   است، پس مهلتی که دیشب تمام شده بود همچنان باز به‌نظر می‌رسید و
   `days_left` یکی بیشتر می‌شد.

پس قاعده: **ذخیره در UTC، سنجش و نمایش در وقتِ محلی.** این ماژول تنها جایی
است که آن مرز رد می‌شود؛ `datetime.now(UTC)` برای نوشتن سرِ جایش می‌ماند.
"""
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings


def org_timezone() -> ZoneInfo:
    """منطقهٔ زمانیِ سازمان از تنظیمات.

    نامِ نامعتبر به UTC برنمی‌گردد و صریح می‌شکند: یک غلطِ تایپی در
    `ORG_TIMEZONE` نباید بی‌صدا به همان رفتارِ اشتباهی برگردد که این ماژول
    برای رفعش نوشته شده — و روی سندِ رسمی، بی‌صدا بدترین حالت است.
    """
    try:
        return ZoneInfo(settings.org_timezone)
    except ZoneInfoNotFoundError as exc:  # pragma: no cover - پیکربندیِ خراب
        raise RuntimeError(
            f"ORG_TIMEZONE نامعتبر است: {settings.org_timezone!r}"
        ) from exc


def to_local(value: datetime) -> datetime:
    """هر `datetime` را به وقتِ محلیِ سازمان می‌آورد.

    `datetime`ِ بی‌منطقه UTC فرض می‌شود، چون در این سامانه هر ستونِ زمانی با
    `datetime.now(UTC)` نوشته می‌شود؛ همان فرضی که پیش از این *ضمنی* بود و
    ضمنی‌بودنش همین اشکال را ساخت.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(org_timezone())


def now_local() -> datetime:
    """«الان» به وقتِ سازمان."""
    return datetime.now(org_timezone())


def today_local() -> date:
    """«امروز» به وقتِ سازمان — جانشینِ `date.today()` در هر سنجشِ پنجره."""
    return now_local().date()


def local_day_start(day: date) -> datetime:
    """آغازِ آن روزِ *محلی*، به‌صورتِ یک لحظهٔ UTC.

    برای فیلترهای بازهٔ تاریخ. کاربر یک `date` می‌دهد و منظورش روزِ تقویمیِ
    خودش است، ولی ستون `timestamptz` است — پس مقایسهٔ مستقیمِ `date` با آن
    ستون، نیمه‌شبِ *UTC* را مرز می‌گیرد:

        فیلترِ «۱۵ مهر» ⇒ از ۰۰:۰۰ UTC ⇒ ۰۳:۳۰ بامدادِ ۱۵ مهر تهران

    یعنی سه‌ونیم ساعتِ اولِ آن روز جا می‌افتاد و سه‌ونیم ساعتِ آخرِ روزِ *قبل*
    اضافه می‌شد. رویدادی که ۱:۰۰ بامداد ثبت شده بود، زیر روزِ قبل دیده می‌شد.
    """
    return datetime.combine(day, time.min, tzinfo=org_timezone()).astimezone(UTC)


def local_day_end(day: date) -> datetime:
    """مرزِ بالای بازه‌ای که *شامل* خودِ `day` است — یعنی آغازِ روزِ بعد."""
    return local_day_start(day + timedelta(days=1))
