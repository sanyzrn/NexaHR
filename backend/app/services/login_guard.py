"""قفل حساب پس از تلاش‌های ناموفق ورود (P0-04).

محدودیت نرخِ per-IP لایهٔ اول است، ولی دو سوراخ دارد که این ماژول می‌بندد:
شمارنده‌اش درون‌پروسه است (با N کارگر، N برابر می‌شود و با ری‌استارت صفر) و اصلاً
per-IP است، پس یک حملهٔ توزیع‌شده روی یک حساب مشخص را نمی‌بیند.

هر تابع فقط روی session کار می‌کند و commit نمی‌کند؛ commit با فراخواننده است تا
شمارش شکست و ثبت audit در یک تراکنش بمانند.
"""
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import UserRole
from app.models.login_attempt import LoginAttempt
from app.models.user import User


def _now() -> datetime:
    return datetime.now(UTC)


def _as_aware(value: datetime | None) -> datetime | None:
    """Postgres مقدار timezone-aware برمی‌گرداند، ولی ردیفی که همین تراکنش ساخته و
    هنوز refresh نشده می‌تواند naive باشد؛ مقایسه‌ی این دو TypeError می‌دهد."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def locked_until(db: Session, username: str) -> datetime | None:
    """اگر این نام کاربری الان قفل است، لحظهٔ پایان قفل؛ وگرنه None."""
    row = db.get(LoginAttempt, username)
    if row is None:
        return None
    until = _as_aware(row.locked_until)
    if until is None or until <= _now():
        return None
    return until


def record_failure(db: Session, username: str) -> datetime | None:
    """یک شکست را می‌شمارد و در صورت عبور از آستانه قفل می‌کند.

    خروجی: لحظهٔ پایان قفل اگر همین تلاش باعث قفل شد، وگرنه None — تا فراخواننده
    بداند که باید رویداد امنیتی ثبت و به HR اطلاع بدهد.
    """
    now = _now()
    window_start = now - timedelta(minutes=settings.login_attempt_window_minutes)

    # «بخوان، جمع کن، بنویس» بی قفل، دو خرابیِ سنجیده‌شده داشت — هر دو با دو
    # اتصالِ واقعی و درهم‌آمیزیِ اجباری بازتولید شدند:
    #
    # * دو شکستِ هم‌زمان روی ردیفِ موجود، هر دو `failed_count` یکسانی را
    #   می‌خواندند و هر دو همان `n+1` را می‌نوشتند: شمارش می‌شد ۱ به‌جای ۲.
    #   یعنی مهاجمی که درخواست‌ها را موازی می‌فرستد، سقفِ قفل را می‌کِشد بالا —
    #   دقیقاً همان کاری که یک ابزارِ brute-force به‌طور پیش‌فرض می‌کند.
    # * و وقتی ردیف *نبود*، دو INSERT هم‌زمان یعنی `UniqueViolation` که از
    #   `record_failure` بیرون می‌زد و `auth._fail` هیچ گیرنده‌ای برایش ندارد:
    #   ۵۰۰ روی خودِ endpointِ ورود.
    #
    # هر دو یک ریشه دارند و یک درمان: ردیف را *پیش از خواندن* اتمی بساز و قفل
    # کن، بعد بخوان.
    #
    # `on_conflict_do_update` و نه `do_nothing`: با `DO NOTHING`، اگر ردیفِ
    # متعارض را تراکنشی نوشته باشد که بعداً rollback می‌کند، insert دوباره
    # تلاش نمی‌کند و ردیف اصلاً ساخته نمی‌شود. `DO UPDATE` در همان حالت تلاش
    # را تکرار می‌کند و همیشه یک ردیفِ قفل‌شده تحویل می‌دهد.
    #
    # و SET عمداً بی‌اثر است (`username` روی خودش): هر مقدارِ دیگری —
    # `last_failed_at` از همه وسوسه‌انگیزتر — پنجرهٔ بازنشانی را از بین می‌برد،
    # چون شرطِ پایینِ همین تابع دقیقاً همان ستون را با `window_start` می‌سنجد.
    insert = pg_insert(LoginAttempt).values(
        username=username, failed_count=0, first_failed_at=now, last_failed_at=now
    )
    db.execute(
        insert.on_conflict_do_update(
            index_elements=["username"], set_={"username": insert.excluded.username}
        )
    )
    # `populate_existing` لازم است و نه تزئینی: اگر همین session پیش‌تر این
    # ردیف را دیده باشد (`locked_until` چند خط بالاتر همین کار را می‌کند)،
    # بی آن، ORM نسخهٔ کهنهٔ داخلِ identity map را برمی‌گرداند و کلِ این قفل
    # بی‌اثر می‌شود.
    row = db.scalars(
        select(LoginAttempt)
        .where(LoginAttempt.username == username)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()

    if (_as_aware(row.last_failed_at) or now) < window_start:
        # پنجره تمام شده: یک تلاش ناموفق شش ساعت پیش نباید در قفلِ امروز نقش داشته باشد.
        row.failed_count = 0
        row.first_failed_at = now
        row.locked_until = None

    row.failed_count += 1
    row.last_failed_at = now

    if row.failed_count >= settings.login_max_failed_attempts:
        row.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
        # شمارنده صفر می‌شود تا پس از پایان قفل، دوباره یک سهمیهٔ کامل داشته باشد
        # (نه این‌که هر تلاش بعدی بلافاصله دوباره قفل کند).
        row.failed_count = 0
        db.flush()
        return row.locked_until

    db.flush()
    return None


def clear_failures(db: Session, username: str) -> None:
    """ورود موفق، تاریخچهٔ شکست را پاک می‌کند."""
    db.execute(delete(LoginAttempt).where(LoginAttempt.username == username))


def purge_stale(db: Session) -> int:
    """ردیف‌های قدیمیِ بی‌قفل را حذف می‌کند.

    چون نام‌های کاربری ناموجود هم شمرده می‌شوند (تا رفتار قفل، وجود حساب را لو ندهد)،
    یک مهاجم می‌تواند با نام‌های تصادفی جدول را باد کند. این جارو رشد را مهار می‌کند.
    """
    cutoff = _now() - timedelta(minutes=settings.login_attempt_window_minutes)
    result = db.execute(
        delete(LoginAttempt).where(
            LoginAttempt.last_failed_at < cutoff,
            (LoginAttempt.locked_until.is_(None)) | (LoginAttempt.locked_until < _now()),
        )
    )
    return result.rowcount or 0


def notify_hr_of_lockout(db: Session, username: str, until: datetime) -> None:
    """قفل‌شدن یک حساب یک رویداد امنیتی است، نه یک جزئیات فنی — HR باید ببیندش."""
    from app.services.notifications import notify_once

    hr_ids = list(
        db.scalars(select(User.id).where(User.role == UserRole.hr, User.is_active.is_(True)))
    )
    if not hr_ids:
        return
    message = (
        f"حساب «{username}» به دلیل تلاش‌های ناموفق پیاپی برای ورود، تا "
        f"{settings.login_lockout_minutes} دقیقه قفل شد"
    )
    for hr_id in hr_ids:
        notify_once(
            db,
            user_id=hr_id,
            type_="account_locked",
            message=message,
            # کلید شامل لحظهٔ پایان قفل است تا هر قفل تازه دوباره اطلاع داده شود
            dedup_key=f"lockout:{username}:{until.isoformat()}",
            within_days=1,
            link="/hr/audit-log",
        )


def unlock(db: Session, username: str) -> bool:
    """قفلِ این نام کاربری را برمی‌دارد. خروجی: قفل بود یا نه.

    قفلِ خودکار در برابر حدسِ رمز درست است، ولی بی راهِ باز کردن، خودش یک
    اهرم می‌شود: پیام‌های متمایزِ «چنین کاربری نیست» و «رمز اشتباه است» —
    که تصمیمِ آگاهانه و مستندی است — به مهاجم اجازه می‌دهند حساب‌های معتبر
    را بشمارد، و بعد هرکدام را با پنج درخواست قفل کند. تنها درمانِ موجود
    «پانزده دقیقه صبر کن» بود، که مهاجم می‌تواند تا ابد تکرارش کند.

    این تابع شکلِ سنجش را عوض نمی‌کند (نه آستانه، نه زمانِ برابرِ پاسخ)؛ فقط
    یک راهِ خروج اضافه می‌کند که ردِ ممیزی دارد.
    """
    row = db.get(LoginAttempt, username)
    if row is None:
        return False
    was_locked = locked_until(db, username) is not None
    db.execute(delete(LoginAttempt).where(LoginAttempt.username == username))
    db.flush()
    return was_locked
