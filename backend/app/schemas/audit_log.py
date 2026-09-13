from datetime import datetime

from pydantic import BaseModel


class AuditLogRead(BaseModel):
    id: int
    evaluation_record_id: int | None
    evaluation_code: str | None
    actor_user_id: int
    actor_username: str | None
    # نامِ آدم، اگر ثبت شده باشد؛ وگرنه همان نام کاربری. UI نباید خودش این
    # جایگزینی را انجام بدهد و در هر صفحه یک‌جور بنویسدش.
    actor_display_name: str | None = None
    event_type: str
    old_value: dict | None
    new_value: dict | None
    created_at: datetime


class AuditLogPage(BaseModel):
    total: int
    items: list[AuditLogRead]


class AuditIntegrityRead(BaseModel):
    """نتیجهٔ راستی‌آزمایی زنجیرهٔ هش لاگ حسابرسی.

    broken_at_id عمداً فقط *اولین* ردیف ناسازگار است: از نقطهٔ شکست به بعد همهٔ
    حلقه‌ها می‌شکنند، پس فهرست‌کردن همه‌شان نویز است و آن‌چه باید بررسی شود همان اولی.
    """

    ok: bool
    checked: int
    broken_at_id: int | None
    reason: str | None
    #: کلِ زنجیره سنجیده شد یا فقط بخشی از آن؟ «سبز» روی بخش با «سبزِ کامل»
    #: یکی نیست: بررسیِ بخشی، دست‌بردن در ردیف‌های *پیش از* نقطهٔ شروعش را
    #: نمی‌بیند.
    full: bool = True
    #: لنگر — تا کدام ردیف قبلاً کامل سنجیده شده بود، و کِی.
    #:
    #: `null` یعنی این پاسخ از ابتدای زنجیره آمده (یا لنگری هنوز ساخته نشده).
    #: رابط این دو تاریخ را لازم دارد تا بتواند بگوید «سریع» یعنی چه: بی آن‌ها
    #: کاربر یک عددِ کوچکِ «بررسی‌شده» می‌دید و نمی‌فهمید بقیه کجا رفت.
    anchor_log_id: int | None = None
    anchor_verified_at: datetime | None = None
