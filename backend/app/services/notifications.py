"""ساخت اعلان درون‌برنامه‌ای برای گیرنده(های) هر رویداد گردش‌کار.

اعلان‌ها در همان تراکنشِ رویداد ساخته می‌شوند (بدون commit جدا) تا با خود گذار
atomic باشند؛ اگر گذار rollback شود اعلانی هم باقی نمی‌ماند.
"""
import hashlib
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from app.models.evaluation import EvaluationRecord
from app.models.notification import Notification
from app.services.workflow import owner_after_hr_review, scorer_seat


def _queue_outbound(db: Session, notification: Notification) -> None:
    """ردیف صندوق خروجی را در همان تراکنش می‌سازد (P1-03).

    وارداتِ داخل تابع عمدی است: delivery به کانال‌ها و کانال‌ها به تنظیمات وابسته‌اند،
    و این ماژول در همه‌جای گردش‌کار وارد می‌شود. نگه‌داشتن آن زنجیره بیرون از
    زمانِ import، وابستگی چرخه‌ای را از ابتدا ناممکن می‌کند.

    فقط *ثبت* می‌شود؛ هیچ ارسالی این‌جا رخ نمی‌دهد. اگر ارسال روی مسیر درخواست
    بود، کندی سرویس پیامک به شکست «تأیید پرونده» ترجمه می‌شد.

    ماژولِ «اعلان بیرونی» این‌جا سنجیده می‌شود و نه در فرستنده: نقطهٔ درستِ
    خاموش‌کردن، *صف نریختن* است. اگر ردیف‌ها ساخته می‌شدند و فرستنده ردشان
    می‌کرد، خاموش‌کردن سوییچ یک صفِ روبه‌رشدِ ردیف‌های مرده می‌ساخت که روزی
    که کسی سوییچ را برگرداند، همه‌شان یک‌جا بیرون می‌رفتند. اعلانِ
    درون‌برنامه‌ای دست‌نخورده می‌ماند — آن هسته است، نه کانال.
    """
    from app.services.authorization import is_module_enabled
    from app.services.delivery import enqueue_for

    if not is_module_enabled(db, "outbound_notifications"):
        return
    # شناسه لازم است تا ردیف تحویل به آن ارجاع دهد
    db.flush()
    enqueue_for(db, notification)


def notify(
    db: Session,
    user_ids: Iterable[int],
    type_: str,
    message: str,
    evaluation_record_id: int | None = None,
    link: str | None = None,
) -> None:
    for user_id in set(user_ids):
        notification = Notification(
            user_id=user_id,
            type=type_,
            message=message,
            link=link,
            evaluation_record_id=evaluation_record_id,
        )
        db.add(notification)
        _queue_outbound(db, notification)


def notify_once(
    db: Session,
    user_id: int,
    type_: str,
    message: str,
    dedup_key: str,
    within_days: int,
    evaluation_record_id: int | None = None,
    link: str | None = None,
) -> bool:
    """اگر همین کاربر در پنجره اخیر اعلانی با همین dedup_key گرفته باشد، دوباره نمی‌سازد.
    خروجی True یعنی اعلان جدید ساخته شد. برای sweep های تکرارشونده تا از اسپم جلوگیری شود."""
    cutoff = datetime.now(UTC) - timedelta(days=within_days)
    exists = db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.dedup_key == dedup_key,
            Notification.created_at >= cutoff,
        )
    )
    if exists:
        return False
    notification = Notification(
        user_id=user_id,
        type=type_,
        message=message,
        link=link,
        evaluation_record_id=evaluation_record_id,
        dedup_key=dedup_key,
    )
    db.add(notification)
    _queue_outbound(db, notification)
    return True


def _active_user_ids_with_role(db: Session, role: UserRole) -> list[int]:
    from app.models.user import User

    return list(db.scalars(select(User.id).where(User.role == role, User.is_active.is_(True))))


def _hr_queue_ids(db: Session, record: EvaluationRecord) -> list[int]:
    """صفِ منابع انسانی، منهای خودِ موضوعِ پرونده.

    پروندهٔ کارمندانِ HR از این پس مرحلهٔ منابع انسانی ندارد، پس در حالتِ عادی
    این تفریق بی‌اثر است. ولی اعلانِ «پروندهٔ خودت در صفِ بررسی قرار گرفت» آن
    نوعی خرابی است که فقط یک بار و روی حسابِ یک آدمِ واقعی دیده می‌شود — و
    مهرِ `hr_review_skipped` روی پرونده‌های *گذشته* یا پرونده‌ای که پیش از این
    تغییر ساخته شده، تضمینی ندارد.
    """
    from app.models.user import User

    return list(
        db.scalars(
            select(User.id).where(
                User.role == UserRole.hr,
                User.is_active.is_(True),
                or_(
                    User.personnel_id.is_(None),
                    User.personnel_id != record.subject_personnel_id,
                ),
            )
        )
    )


def employee_results_are_visible(db: Session) -> bool:
    """آیا «کارنامه من» در این سازمان چیزی نشان می‌دهد؟

    اعلانی که به صفحه‌ای لینک بدهد که «این بخش فعال نشده است» می‌گوید، بدتر از
    نبودنِ اعلان است: کارمند خبردار می‌شود تصمیمی درباره‌اش گرفته شده و بعد به
    دری می‌رسد که بسته است — و چون اعلان‌ها به صندوقِ خروجی هم می‌روند
    (`_queue_outbound`)، همان پیام ممکن است با ایمیل و پیامک هم برود.

    ماژول `employee_evaluation_visibility` پیش‌فرض *خاموش* است، پس این حالت
    نادر نیست؛ حالتِ پیش‌فرض است.

    گاردِ `require_module` روی این مسیر نمی‌نشیند: آن گارد برای *نوشتن* است و
    این‌جا اصلاً درخواستی از کارمند نیامده — تأییدِ مدیرعامل است که اعلان را
    می‌سازد.
    """
    from app.services.authorization import is_module_enabled

    return is_module_enabled(db, "employee_evaluation_visibility")


def subject_user_ids(db: Session, personnel_id: int) -> list[int]:
    """حساب‌های فعالِ متصل به این پرسنل — گیرندهٔ اعلان‌های «دربارهٔ خودت».

    عمداً نقش سنجیده نمی‌شود. تا امروز `User.role == employee` بود، و نتیجه‌اش
    این بود که مسئولِ واحد و کارمندِ منابع انسانی و معاونت — که خودشان هم
    ارزیابی می‌شوند — هیچ‌وقت خبر نمی‌شدند که پروندهٔ *خودشان* نهایی شد.
    «چه کسی ارزیابی می‌شود» با «چه نقشی در زنجیره دارد» یکی نیست؛ همان
    تفکیکی که `require_own_personnel` در مسیرهای `/api/me` انجام داد.
    """
    from app.models.user import User

    return list(
        db.scalars(
            select(User.id).where(
                User.personnel_id == personnel_id,
                User.is_active.is_(True),
            )
        )
    )


def _tell_the_scorer(record: EvaluationRecord, evaluator_id: int | None) -> list[int]:
    """نمره‌دهنده را خبر کن — مگر همان کسی باشد که این کار را کرد.

    در مسیرِ «مستقیمِ مدیرعامل» نمره‌دهنده و تأییدکنندهٔ نهایی یک نفرند، و
    اعلانِ «پروندهٔ … تأیید نهایی شد» به کسی که همین حالا خودش تأییدش کرده،
    فقط سر و صداست. اعلانی که هیچ‌وقت کاری به دنبال ندارد، بقیهٔ اعلان‌ها را
    هم بی‌ارزش می‌کند.
    """
    if evaluator_id is None or evaluator_id == record.ceo_user_id:
        return []
    return [evaluator_id]


def _active_hr_ids(db: Session) -> list[int]:
    from app.models.user import User

    return list(
        db.scalars(select(User.id).where(User.role == UserRole.hr, User.is_active.is_(True)))
    )


#: چند کدِ پرونده در متنِ اعلان بیاید. بیشتر از این، پیام از حدِ خواندنی بیرون
#: می‌زند و مابقی با «و N مورد دیگر» شمرده می‌شوند.
_MAX_LISTED_SEATS = 10


def notify_vacated_seats(db: Session, *, user_id: int, person_label: str) -> int:
    """صندلی‌هایی که با رفتنِ یک نفر بی‌صاحب شدند را به منابع انسانی گزارش می‌کند.

    این مکملِ `scheduled.run_orphaned_case_sweep` است و تکرارش نیست. آن جارو
    فقط پرونده‌ای را می‌گیرد که صاحبِ *مرحلهٔ فعلی*‌اش مرده باشد — یعنی همین
    حالا گیر کرده — و شبانه اجرا می‌شود. این‌جا دو چیزِ دیگر لازم بود:

    * **زمان.** خروج از سازمان یک اقدامِ آگاهانهٔ منابع انسانی است. اینکه
      نتیجه‌اش را فردا شب از یک جارو بشنود، دیر است؛ همان لحظه باید بداند.
    * **صندلی‌هایی که هنوز گیر نکرده‌اند.** مسئولِ واحدی که می‌رود، پروندهٔ
      زیرمجموعه‌اش ممکن است الان روی میزِ معاونت باشد. چیزی گیر نکرده و جارو
      هم درست ردش می‌کند — تا روزی که پرونده *برگردد* و آن صندلی مرده باشد.
      آن روز کسی نمی‌داند چرا.

    یک اعلانِ *تجمیعی* و نه یکی به‌ازای هر پرونده: مدیرِ سی‌نفره‌ای که می‌رود،
    در ضربِ تعدادِ کارشناسانِ HR صد اعلان می‌ساخت و صندوقِ همه را بی‌مصرف
    می‌کرد. پیگیریِ تک‌تکِ پرونده‌ها کارِ همان جاروی شبانه است.

    پروندهٔ *خودِ* این فرد در این فهرست نمی‌آید، چون
    `personnel._close_out_departure` پیش از این تماس لغوش کرده و دیگر باز
    نیست — پس این تابع باید *پس از* آن صدا زده شود.

    خروجی: تعداد اعلانِ ساخته‌شده (صفر یعنی صندلیِ بی‌صاحبی نبود).
    """
    from app.core.config import settings
    from app.services.evaluation import occupied_seats_in_open_records

    seats = occupied_seats_in_open_records(db, user_id)
    if not seats:
        return 0

    listed = "، ".join(f"{code} ({label})" for code, label in seats[:_MAX_LISTED_SEATS])
    hidden = len(seats) - _MAX_LISTED_SEATS
    more = f" و {hidden} مورد دیگر" if hidden > 0 else ""
    message = (
        f"«{person_label}» از سازمان خارج شد و در {len(seats)} پروندهٔ باز مسئولِ "
        f"مرحله بود: {listed}{more}. برای هرکدام با «تغییر مسئول مرحله» جایگزین "
        "تعیین کنید، وگرنه آن پرونده‌ها در همان مرحله می‌مانند."
    )

    # کلیدِ dedup به *مجموعهٔ* پرونده‌ها گره خورده و نه فقط به فرد: اگر فردا
    # پروندهٔ تازه‌ای روی همان صندلیِ مرده باز شود، مجموعه عوض می‌شود و اعلانِ
    # تازه می‌آید. بی این، فقط شمارش در کلید بود و دو مجموعهٔ هم‌اندازه یکی
    # دیده می‌شدند.
    #
    # و *هش* می‌شود و نه فهرست: `dedup_key` ستونی ۱۲۰ نویسه‌ای است و مدیرِ
    # دوازده‌زیرمجموعه‌ای از آن بیرون می‌زد — با `DataError` روی مسیرِ خروجِ
    # پرسنل، یعنی خودِ اقدام شکست می‌خورد. تستِ فهرستِ بلند همین را گرفت.
    fingerprint = hashlib.sha256(
        ",".join(sorted({code for code, _ in seats})).encode()
    ).hexdigest()[:16]
    created = 0
    for hr_id in _active_hr_ids(db):
        if notify_once(
            db,
            user_id=hr_id,
            type_="seats_vacated",
            message=message,
            dedup_key=f"seats_vacated:{user_id}:{fingerprint}",
            within_days=settings.notification_dedup_days,
        ):
            created += 1
    return created


def notify_for_workflow_action(db: Session, record: EvaluationRecord, action: str) -> None:
    """نفر بعدی زنجیره (یا نفر قبلی، در برگشت پرونده) را از رویداد باخبر می‌کند."""
    code = record.evaluation_code
    name = record.subject.full_name
    link = f"/evaluations/{record.id}"

    # نمره‌دهندهٔ اول و نفرِ بعد از منابع انسانی — هر دو از یک قاعدهٔ مشترک
    # (`workflow`)، چون همین دو محاسبه در چهار جای دیگر هم لازم است و
    # نسخه‌های جداشان هر کدام برای یک شکلِ زنجیره `None` می‌دادند.
    _, evaluator_id = scorer_seat(record)
    after_hr_id = owner_after_hr_review(record)

    recipients: list[int] = []
    message = ""
    if action in ("submit", "manager_submit", "ceo_submit"):
        recipients = _hr_queue_ids(db, record)
        message = f"پرونده {code} ({name}) در صف بررسی منابع انسانی قرار گرفت"
    # پروندهٔ بی‌مرحلهٔ HR: ثبتِ نمره مستقیم روی میزِ نفرِ بعدیِ زنجیره می‌نشیند.
    # `after_hr_id` همان «بعد از منابع انسانی» است و این‌جا هم درست جواب می‌دهد:
    # معاونت، و اگر معاونتی در زنجیره نباشد، خودِ مدیرعامل.
    elif action == "submit_hr_subject":
        recipients = [after_hr_id]
        message = f"پرونده {code} ({name}) در انتظار بررسی و تأیید شماست"
    elif action in ("manager_submit_hr_subject", "ceo_submit_hr_subject"):
        # مرحله‌های میانی غایب‌اند؛ تنها تأییدکنندهٔ باقی‌مانده مدیرعامل است.
        recipients = [record.ceo_user_id]
        message = f"پرونده {code} ({name}) در انتظار تأیید نهایی شماست"
    elif action == "hr_approve":
        recipients = [after_hr_id]
        message = f"پرونده {code} ({name}) در انتظار بررسی و تأیید شماست"
    elif action == "hr_approve_manager":
        # مسیر «مدیر»: مرحلهٔ معاونت مصرف شده، پس نفرِ بعدی مدیرعامل است.
        recipients = [record.ceo_user_id]
        message = f"پرونده {code} ({name}) در انتظار تأیید نهایی شماست"
    elif action == "deputy_approve":
        recipients = [record.ceo_user_id]
        message = f"پرونده {code} ({name}) در انتظار تأیید نهایی شماست"
    elif action == "ceo_finalize":
        recipients = _tell_the_scorer(record, evaluator_id)
        message = f"پرونده {code} ({name}) تأیید نهایی شد"
    elif action == "hr_return":
        # `evaluator_id` نه `unit_supervisor_user_id`: در مسیر «مدیر» دومی خالی
        # است، پس برگشتِ منابع انسانی به هیچ‌کس اعلان نمی‌داد و معاونت هیچ‌وقت
        # نمی‌فهمید پرونده‌اش برگشته — پرونده در `draft` می‌ماند و کسی خبر ندارد.
        recipients = [evaluator_id] if evaluator_id is not None else []
        message = f"پرونده {code} ({name}) توسط منابع انسانی برگشت داده شد؛ دلیل در کامنت‌های پرونده"
    elif action == "deputy_return":
        recipients = _hr_queue_ids(db, record)
        message = f"پرونده {code} ({name}) توسط معاونت برگشت داده شد؛ دلیل در کامنت‌های پرونده"
    # بی‌مرحلهٔ HR، برگشت یک پله بیشتر عقب می‌رود: تا خودِ نمره‌دهنده.
    elif action in (
        "deputy_return_hr_subject",
        "ceo_return_manager_hr_subject",
        "ceo_return_ceo_only",
    ):
        recipients = _tell_the_scorer(record, evaluator_id)
        message = (
            f"پرونده {code} ({name}) برگشت داده شد و در انتظار اصلاح شماست؛ "
            "دلیل در کامنت‌های پرونده"
        )
    elif action == "ceo_return":
        # برگشت از مدیرعامل هم به همان کسی می‌رود که پرونده را به او داده بود.
        recipients = [after_hr_id]
        message = f"پرونده {code} ({name}) توسط مدیرعامل برگشت داده شد؛ دلیل در کامنت‌های پرونده"
    elif action == "ceo_return_manager":
        # در مسیر «مدیر» پرونده به صف منابع انسانی برمی‌گردد، نه به معاونت.
        recipients = _hr_queue_ids(db, record)
        message = f"پرونده {code} ({name}) توسط مدیرعامل برگشت داده شد؛ دلیل در کامنت‌های پرونده"
    elif action == "cancel":
        # همهٔ کسانی که روی این پرونده نقشی داشتند باید بدانند دیگر منتظرشان نیست.
        recipients = [
            user_id
            for user_id in (record.unit_supervisor_user_id, record.deputy_user_id, record.ceo_user_id)
            if user_id is not None
        ]
        message = f"پرونده {code} ({name}) توسط منابع انسانی لغو شد؛ دلیل در کامنت‌های پرونده"

    if recipients and message:
        notify(
            db,
            recipients,
            type_=f"workflow_{action}",
            message=message,
            evaluation_record_id=record.id,
            link=link,
        )

    if action == "ceo_finalize":
        # اگر خود کارمند حساب فعال دارد، نتیجه نهایی به او هم ابلاغ می‌شود
        # («کارنامه من») — ولی فقط اگر آن صفحه اصلاً چیزی نشان بدهد.
        subject_ids = subject_user_ids(db, record.subject_personnel_id)
        if subject_ids and employee_results_are_visible(db):
            notify(
                db,
                subject_ids,
                type_="evaluation_finalized_self",
                message=f"ارزیابی عملکرد شما ({code}) نهایی شد؛ نتیجه در «کارنامه من» قابل مشاهده است",
                evaluation_record_id=record.id,
                link="/me",
            )


def notify_stage_owner_reassigned(
    db: Session, record: EvaluationRecord, new_owner_id: int, stage_label: str
) -> None:
    """مسئول جدید مرحله باید بداند پرونده‌ای روی میزش آمده — وگرنه پرونده دوباره
    همان‌جا می‌ماند و بازتخصیص هیچ چیزی را حل نکرده است."""
    notify(
        db,
        [new_owner_id],
        type_="workflow_reassigned",
        message=(
            f"پرونده {record.evaluation_code} ({record.subject.full_name}) به‌عنوان "
            f"«{stage_label}» به شما واگذار شد"
        ),
        evaluation_record_id=record.id,
        link=f"/evaluations/{record.id}",
    )
