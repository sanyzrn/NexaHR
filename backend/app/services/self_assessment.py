"""خودارزیابی: چه کسی دارد، چه کسی می‌بیند، و دعوت‌کردنِ کارمند به انجامش.

دو قاعده که منابع انسانی تعیین کرده و این ماژول تنها جای اعمالشان است.

۱. چه کسی خودارزیابی دارد — قاعده‌ای زنجیره‌محور، نه نقش‌محور
--------------------------------------------------------------
هر کسی که *موضوعِ* یک پروندهٔ ارزیابی است، مگر مدیرعامل و معاونت‌ها.

نقش‌محور بودنِ قبلی یک اشکالِ واقعی می‌ساخت: گاردِ مسیرها `require_roles(employee)`
بود، یعنی مسئولِ واحد — که خودش هم ارزیابی می‌شود — نه‌تنها خودارزیابی نمی‌توانست
بکند، *کارنامهٔ نهایی خودش را هم نمی‌دید*. ریشه‌اش این بود که «نقش» هم‌زمان دو
چیز را تعیین می‌کرد: چه کاری می‌کنی، و آیا ارزیابی می‌شوی. این دو از هم جدا شدند.

۲. چه کسی خودارزیابی را می‌بیند — فقط خودِ فرد و منابع انسانی
-------------------------------------------------------------
مدیر مستقیم، معاونت و مدیرعامل هیچ‌وقت. نه پیش از ثبتِ نمره‌شان، نه پس از آن.

پیش از این سه سوییچِ پنل مدیریت بود (پیش‌فرض خاموش) به‌علاوهٔ یک گاردِ زمانی که
اجازه می‌داد نمره‌دهنده *پس از* قفل‌شدنِ نمرهٔ خودش ببیند. هر دو برداشته شدند:
به کارمند گفته می‌شود «فقط شما و منابع انسانی»، و سوییچی که یک نفر می‌تواند
بی‌سروصدا روشنش کند، آن جمله را به یک تنظیم تبدیل می‌کند نه یک تضمین.

بهایش را می‌دانیم و پذیرفته‌ایم: گفت‌وگو دربارهٔ فاصلهٔ دو دیدگاه — که در ادبیاتِ
ارزیابیِ ۱۸۰ درجه فایدهٔ اصلی روش است — از مسیرِ مدیر مستقیم حذف می‌شود و فقط
منابع انسانی می‌تواند رویش کاری بکند.

دعوت، و اینکه چرا مسدودکننده نیست
---------------------------------
خودارزیابی از قبل کار می‌کرد ولی هیچ‌کس خبر نداشت؛ «اختیاری» با «کسی خبرش نکرده»
یکی نیست. پس منابع انسانی از فهرست پرسنل دعوت می‌فرستد و می‌تواند تکرارش کند.

مسدودکننده نشد چون یک کارمندِ در مرخصی کلِ چرخهٔ ارزیابی سازمان را متوقف می‌کرد
— همان بن‌بستی که یک بار از گردش‌کار حذف شد. به‌جایش مهلتِ واقعی گذاشته شد
(`services/evaluation_window.py`).

اعلانِ خودکار عمداً نیست
------------------------
هنگام باز شدنِ پرونده هیچ اعلانی نمی‌رود. تصمیمِ صریحِ منابع انسانی است: هیچ
پیامی نباید به فرد بگوید پرونده‌اش در حال بررسی است. تنها اعلان، همین دعوتِ
دستیِ خودارزیابی است و متنش هم فقط دربارهٔ خودِ خودارزیابی حرف می‌زند.
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import EvaluationStatus, UserRole
from app.models.evaluation import EvaluationRecord
from app.models.personnel import Personnel
from app.models.user import User
from app.services.audit import log_event
from app.services.notifications import notify

#: خودارزیابی فقط تا پیش از قطعی‌شدن نمرهٔ ارزیاب معنا دارد: بعد از آن دیگر
#: «دیدگاه مستقل» نیست، واکنش به نمره است.
#:
#: فقط `draft` — هر دو مسیر (عادی و «مدیر») از همین وضعیت شروع می‌شوند.
#:
#: `hr_approved` یک بازماندهٔ قدیمی بود: زمانی مسیر «مدیر» مستقیماً در
#: `hr_approved` ساخته می‌شد. آن رفتار برداشته شد (توضیحش کنار ساختِ پرونده در
#: `api/routers/evaluations.py` است) ولی این عضو ماند و پنجره را ناپیوسته
#: می‌کرد: باز در `draft`، بسته در `submitted`، و دوباره باز در `hr_approved` —
#: یعنی درست بعد از آن‌که نمرهٔ ارزیاب ثبت *و* توسط منابع انسانی تأیید شده بود.
#: همان چیزی که سطر بالا می‌گوید نباید ممکن باشد.
OPEN_STATUSES = frozenset({EvaluationStatus.draft})

#: حالت‌هایی که رابط باید از هم جدا نشان بدهد. رشته و نه بولین: «دعوت نشده» و
#: «دعوت شده ولی انجام نداده» و «پرونده‌ای نیست» سه چیز متفاوت‌اند و هر سه به
#: کنشِ متفاوتی می‌رسند.
STATE_NO_CASE = "no_case"
STATE_NO_ACCOUNT = "no_account"
STATE_CLOSED = "closed"
STATE_PENDING = "pending"
STATE_INVITED = "invited"
STATE_SUBMITTED = "submitted"


#: نقش‌هایی که خودارزیابی ندارند.
#:
#: قاعده‌ای که منابع انسانی داد: «همه، به‌جز مدیرعامل و معاونت‌ها». بقیهٔ شرط‌ها
#: زنجیره‌ای‌اند و نه نقشی — کسی خودارزیابی دارد که موضوعِ یک پروندهٔ ارزیابی باشد.
EXCLUDED_ROLES = frozenset({UserRole.ceo, UserRole.deputy})

#: نقش‌هایی که خودارزیابیِ *دیگران* را می‌بینند.
#:
#: فقط منابع انسانی. خودِ فرد از مسیرِ `/api/me` به خودارزیابیِ خودش می‌رسد و
#: این مجموعه دربارهٔ او حرف نمی‌زند.
VIEWER_ROLES = frozenset({UserRole.hr})


def may_self_assess(role: UserRole) -> bool:
    """آیا این نقش اصلاً خودارزیابی دارد؟

    شرطِ لازم است نه کافی: فرد باید موضوعِ همان پرونده هم باشد، که مسیرهای
    `/api/me` جداگانه می‌سنجند.
    """
    return role not in EXCLUDED_ROLES


def may_view(record: EvaluationRecord, role: UserRole) -> bool:
    """آیا این نقش می‌تواند خودارزیابیِ این پرونده را ببیند؟

    فقط منابع انسانی. نه مدیر مستقیم، نه معاونت، نه مدیرعامل — و نه پیش از ثبتِ
    نمره‌شان و نه پس از آن.

    پیش از این دو لایه بود که هر دو برداشته شدند: سه سوییچِ پنل مدیریت (پیش‌فرض
    خاموش) و یک گاردِ زمانی که اجازه می‌داد نمره‌دهنده پس از قفل‌شدنِ نمرهٔ خودش
    ببیند. آن گارد برای این ساخته شده بود که خودارزیابی «لنگرِ» نمره‌دهی نشود،
    و مسئله‌اش را هم حل می‌کرد — ولی قاعدهٔ تازه اصلاً به آن نیازی ندارد، چون
    نمره‌دهنده هیچ‌وقت نمی‌بیند.

    `record` در امضا مانده چون قاعده ممکن است دوباره پرونده‌محور شود؛ حذفش یعنی
    همهٔ فراخوان‌ها باید عوض شوند تا برگردد.
    """
    return role in VIEWER_ROLES


def open_record_for(db: Session, personnel_id: int) -> EvaluationRecord | None:
    """پروندهٔ بازِ این فرد که هنوز پنجرهٔ خودارزیابی‌اش باز است."""
    return db.scalar(
        select(EvaluationRecord)
        .where(
            EvaluationRecord.subject_personnel_id == personnel_id,
            EvaluationRecord.status.in_(OPEN_STATUSES),
        )
        .order_by(EvaluationRecord.created_at.desc())
        .limit(1)
    )


def state_of(record: EvaluationRecord | None, has_account: bool) -> str:
    if record is None:
        return STATE_NO_CASE
    if record.self_assessment_submitted_at is not None:
        return STATE_SUBMITTED
    if record.status not in OPEN_STATUSES:
        return STATE_CLOSED
    if not has_account:
        return STATE_NO_ACCOUNT
    return STATE_INVITED if record.self_assessment_invited_at is not None else STATE_PENDING


def invite(db: Session, personnel: Personnel, actor_user_id: int) -> EvaluationRecord:
    """دعوت کارمند به خودارزیابی. خطاها همگی می‌گویند *چرا* و راهِ بعدی چیست."""
    account = db.scalar(select(User).where(User.personnel_id == personnel.id, User.is_active.is_(True)))
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "این فرد حساب کاربری فعالی ندارد، پس اعلانی دریافت نمی‌کند. "
                "ابتدا از همین صفحه برایش حساب بسازید."
            ),
        )

    record = open_record_for(db, personnel.id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "پروندهٔ بازی برای این فرد وجود ندارد. خودارزیابی به یک پروندهٔ ارزیابی وصل "
                "می‌شود، پس ابتدا مسئول واحد باید پرونده را آغاز کند."
            ),
        )
    if record.self_assessment_submitted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="این فرد خودارزیابی‌اش را قبلاً ثبت کرده است",
        )
    # دعوتِ دوم «خطا» نیست، یادآوری است.
    #
    # پیش از این بارِ دوم ۴۰۹ می‌گرفت — برای همیشه. یعنی اگر اعلان گم می‌شد یا
    # کارمند آن را می‌بست، منابع انسانی هیچ راهی برای رساندنِ دوبارهٔ خبر نداشت
    # و تنها کارِ ممکن این بود که تلفنی بگوید. پنجره کوتاه است و فرصت از دست
    # می‌رفت. سرریزِ اعلان هم خطر نیست: هر یادآوری یک کلیکِ آگاهانهٔ منابع
    # انسانی است، نه چیزی خودکار.
    is_reminder = record.self_assessment_invited_at is not None

    record.self_assessment_invited_at = datetime.now(UTC)
    record.self_assessment_invited_by_user_id = actor_user_id
    notify(
        db,
        [account.id],
        type_="self_assessment_invited",
        message=(
            "یادآوری: هنوز خودارزیابیِ این دوره را ثبت نکرده‌اید. تا پیش از قطعی‌شدنِ "
            "نمرهٔ ارزیاب می‌توانید دیدگاهتان را ثبت کنید."
            if is_reminder
            else "فرم خودارزیابی این دوره برای شما باز است. دیدگاه خودتان دربارهٔ "
            "عملکردتان را می‌توانید تا پایان مهلت ثبت کنید."
        ),
        evaluation_record_id=record.id,
        link=f"/me?self-assessment={record.id}",
    )
    log_event(
        db,
        actor_user_id=actor_user_id,
        event_type="self_assessment_reminded" if is_reminder else "self_assessment_invited",
        evaluation_record_id=record.id,
        new_value={"personnel_id": personnel.id, "notified_user_id": account.id},
    )
    return record
