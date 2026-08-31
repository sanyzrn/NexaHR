"""مهلتِ ثبت: تا چه تاریخی می‌شود نمره یا خودارزیابی ثبت کرد.

مسئله
-----
`EvaluationPeriod` از اول دو ستون `starts_on` و `ends_on` داشت، ولی هیچ‌جا
اعمال نمی‌شد — یعنی «دورهٔ ارزیابی شهریور» فقط یک برچسب بود و ثبتِ نمره ماه‌ها
بعد هم بی‌صدا می‌گرفت. منابع انسانی می‌گوید مهلت باید واقعی باشد: بعد از پایانِ
دوره، ثبت ممکن نیست — نه خودارزیابی و نه ارزیابیِ تیم.

و یک استثنا که خودشان خواستند: بعد از پایانِ مهلت، منابع انسانی بتواند برای یک
پروندهٔ مشخص دوباره باز کند (کسی در مرخصی بوده، پرونده دیر باز شده).

تمدید *تاریخ‌دار* است و نه یک پرچمِ «باز شد»
--------------------------------------------
پرچم یعنی پرونده‌ای که یک بار باز شود، برای همیشه باز می‌ماند و کسی یادش
نمی‌رود ببنددش — همان چیزی که مهلت را از اول بی‌معنا می‌کند. تاریخ خودش را
می‌بندد.

چه چیزی مهلت دارد و چه چیزی نه
------------------------------
فقط *ثبت* — خودارزیابی و ثبتِ نمرهٔ ارزیاب. مرحله‌های بررسی و تأیید (منابع
انسانی، معاونت، مدیرعامل) عمداً بیرون‌اند: بستنِ آن‌ها یعنی پرونده‌ای که یک روز
دیر به میز رسیده، برای همیشه نیمه‌کاره می‌ماند و هیچ راهِ خروجی ندارد.

پرونده‌ای که به هیچ دوره‌ای وصل نیست (`period_id` خالی) مهلتی ندارد. این عمدی
است: پرونده‌های پیش از معرفیِ دوره‌ها نباید یک‌شبه غیرقابل‌ثبت شوند.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.evaluation import EvaluationRecord
from app.models.evaluation_period import EvaluationPeriod


@dataclass(frozen=True)
class Window:
    """مهلتِ ثبتِ یک پرونده."""

    #: آخرین روزِ مجاز. `None` یعنی این پرونده اصلاً مهلتی ندارد.
    closes_on: date | None
    #: آیا این تاریخ از تمدیدِ منابع انسانی آمده، نه از خودِ دوره.
    extended: bool = False

    @property
    def unlimited(self) -> bool:
        return self.closes_on is None

    @property
    def is_open(self) -> bool:
        return self.unlimited or date.today() <= self.closes_on

    @property
    def days_left(self) -> int | None:
        """چند روز مانده. منفی یعنی گذشته."""
        return None if self.closes_on is None else (self.closes_on - date.today()).days


def window_for(db: Session, record: EvaluationRecord) -> Window:
    """مهلتِ این پرونده: تاریخِ پایانِ دوره، یا تمدیدی که از آن جلوتر است.

    تمدید فقط وقتی معنا دارد که *دیرتر* از پایانِ دوره باشد. تمدیدی که عقب‌تر
    باشد مهلت را کوتاه نمی‌کند — «باز کردنِ دوباره» هیچ‌وقت نباید چیزی را ببندد.
    """
    period_end: date | None = None
    if record.period_id is not None:
        period = db.get(EvaluationPeriod, record.period_id)
        period_end = period.ends_on if period else None

    extension = record.submission_extended_until
    if extension is not None and (period_end is None or extension > period_end):
        return Window(closes_on=extension, extended=True)
    return Window(closes_on=period_end)


def ensure_open(db: Session, record: EvaluationRecord, activity: str) -> Window:
    """اگر مهلت گذشته باشد، با پیامی که *تاریخ* را می‌گوید رد کن.

    گفتنِ خودِ تاریخ عمدی است: «مهلت گذشته» کاربر را می‌فرستد سراغِ منابع انسانی
    بی‌آنکه بداند چقدر دیر کرده یا اصلاً مهلت کِی بوده.
    """
    window = window_for(db, record)
    if window.is_open:
        return window
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"مهلت {activity} این دوره در {window.closes_on:%Y-%m-%d} به پایان رسیده است. "
            "برای ثبتِ دیرهنگام، منابع انسانی می‌تواند مهلت این پرونده را تمدید کند."
        ),
    )
