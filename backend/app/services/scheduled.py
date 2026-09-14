"""کارهای زمان‌بندی‌شده (sweep) که سامانه را از حالت pull-based خارج می‌کنند:

۱) هشدار انقضای قرارداد به منابع انسانی برای کسانی که ارزیابیِ باز ندارند.
۲) یادآوری تأخیر (SLA) به صاحبِ فعلی پرونده‌هایی که مدت‌هاست در جریان مانده‌اند.

توابع خالص‌اند (فقط db می‌گیرند و اعلان می‌سازند)؛ commit با فراخواننده است تا هم از
endpoint دستی و هم از زمان‌بند و هم در تست قابل استفاده باشند. با notify_once از اسپم
جلوگیری می‌شود.
"""
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import today_local
from app.core.config import settings
from app.core.persian import fa_digits
from app.models.capability import UserCapability
from app.models.enums import (
    Capability,
    EvaluationStatus,
    ImprovementPlanStatus,
    PersonnelStatus,
    UserRole,
)
from app.models.evaluation import EvaluationRecord
from app.models.evaluation_document import EvaluationDocument
from app.models.improvement_plan import ImprovementPlan
from app.models.personnel import Personnel
from app.models.user import User
from app.services.ai.confirmations import purge_decided_actions
from app.services.audit import latest_check, record_full_verification
from app.services.delivery import run_delivery_sweep
from app.services.documents import archive_final_pdf
from app.services.login_guard import purge_stale
from app.services.notifications import already_notified, notify_once
from app.services.pdf import weasyprint_available
from app.services.sessions import purge_dead_sessions
from app.services.workflow import IS_OPEN_RECORD, owner_after_hr_review, scorer_seat


def _active_hr_ids(db: Session) -> list[int]:
    return list(
        db.scalars(select(User.id).where(User.role == UserRole.hr, User.is_active.is_(True)))
    )


def run_contract_expiry_sweep(db: Session) -> int:
    """به HR برای هر پرسنل فعالِ رو به انقضا که ارزیابی بازی ندارد، یک‌بار (در پنجره
    dedup) هشدار می‌دهد. خروجی: تعداد اعلان ساخته‌شده."""
    horizon = today_local() + timedelta(days=settings.contract_expiry_alert_days)

    open_evaluation_exists = (
        select(EvaluationRecord.id)
        .where(
            EvaluationRecord.subject_personnel_id == Personnel.id,
            IS_OPEN_RECORD,
        )
        .exists()
    )
    expiring = db.execute(
        select(Personnel.id, Personnel.full_name, Personnel.contract_end_date)
        .where(
            Personnel.status == PersonnelStatus.active,
            Personnel.contract_end_date <= horizon,
            ~open_evaluation_exists,
        )
        .order_by(Personnel.contract_end_date)
    ).all()

    hr_ids = _active_hr_ids(db)
    seen = already_notified(
        db,
        [f"contract_expiry:{personnel_id}" for personnel_id, _, _ in expiring],
        settings.notification_dedup_days,
    )
    created = 0
    today = today_local()
    for personnel_id, full_name, end_date in expiring:
        days = (end_date - today).days
        when = (
            f"{fa_digits(days)} روز دیگر"
            if days >= 0
            else f"{fa_digits(abs(days))} روز پیش (منقضی‌شده)"
        )
        message = (
            f"قرارداد «{full_name}» {when} به پایان می‌رسد و هنوز ارزیابی‌ای برایش آغاز نشده است"
        )
        for hr_id in hr_ids:
            if notify_once(
                db,
                user_id=hr_id,
                type_="contract_expiry",
                message=message,
                dedup_key=f"contract_expiry:{personnel_id}",
                within_days=settings.notification_dedup_days,
                link="/hr/dashboard",
                seen=seen,
            ):
                created += 1
    return created


def _current_owner_ids(record: EvaluationRecord, hr_ids: list[int]) -> list[int]:
    """چه کسی *الان* روی این پرونده باید اقدام کند.

    `hr_ids` را فراخواننده می‌دهد و این‌جا گرفته نمی‌شود: صفِ مشترکِ منابع
    انسانی برای *همهٔ* پرونده‌ها یکی است، و پرسیدنش در هر پرونده یعنی هزار
    کوئریِ یکسان در یک جارو. روی دیتابیسِ هزارنفره همین یک سطر، ۲۵۰ کوئری از
    ۶۲۵۱ کوئریِ جاروی SLA بود.

    صاحبِ هر مرحله از شکلِ زنجیره می‌آید و نه فقط از وضعیت — و همین تفاوت،
    سه خرابیِ جدا می‌ساخت (`tests/test_scheduled.py`):

    * `hr_approved` بی‌قید «معاونت» فرض می‌شد. زنجیرهٔ بی‌معاونت از همین
      وضعیت مستقیم به مدیرعامل می‌رود، پس تابع `[None]` می‌داد و
      `notifications.user_id` — ستونی NOT NULL — کلِ جاروی شبانه را با
      NotNullViolation می‌بُرد.
    * جاروی پرونده‌های بی‌صاحب همان `[None]` را می‌گرفت، هیچ کاربر فعالی
      برایش پیدا نمی‌کرد، و پروندهٔ سالم را به منابع انسانی «گیرکرده» گزارش
      می‌داد — هر بار که اجرا می‌شد.
    * `draft` با «مسئول واحد، وگرنه معاونت» حساب می‌شد؛ در زنجیرهٔ مستقیمِ
      مدیرعامل هر دو خالی‌اند، پس فهرستِ تهی برمی‌گشت و آن پرونده هیچ‌وقت
      یادآوری نمی‌گرفت.
    """
    if record.status == EvaluationStatus.draft:
        _, scorer_id = scorer_seat(record)
        return [scorer_id] if scorer_id is not None else []
    if record.status == EvaluationStatus.submitted:
        return hr_ids
    if record.status == EvaluationStatus.hr_approved:
        return [owner_after_hr_review(record)]
    if record.status == EvaluationStatus.deputy_approved:
        return [record.ceo_user_id]
    return []


def run_sla_sweep(db: Session) -> int:
    """به صاحبِ فعلیِ هر پرونده‌ای که بیش از حد آستانه *در همین مرحله* مانده، یادآوری
    می‌فرستد. dedup_key شامل وضعیت است تا با هر مرحله جدیدِ گیرکرده دوباره فعال شود."""
    # قبلاً معیار created_at بود، یعنی «سن کل پرونده». نتیجه‌اش دو خطای متقارن بود:
    # پرونده‌ای که سه هفته در مراحل قبلی چرخیده، همان لحظهٔ رسیدن به مرحلهٔ جدید
    # فوراً تأخیردار اعلام می‌شد (مسئول تازه‌کار بی‌دلیل نهیب می‌خورد)، و هیچ راهی
    # نبود بفهمیم واقعاً کدام مرحله کند است.
    cutoff = datetime.now(UTC) - timedelta(days=settings.sla_reminder_days)
    stalled = db.scalars(
        select(EvaluationRecord).where(
            IS_OPEN_RECORD,
            EvaluationRecord.stage_entered_at <= cutoff,
        )
    )

    stalled = list(stalled)
    created = 0
    hr_ids = _active_hr_ids(db)
    seen = already_notified(
        db,
        [f"sla:{record.id}:{record.status.value}" for record in stalled],
        settings.sla_reminder_days,
    )
    for record in stalled:
        message = (
            f"پرونده {record.evaluation_code} ({record.subject.full_name}) بیش از "
            f"{fa_digits(settings.sla_reminder_days)} روز است در همین مرحله منتظر اقدام شماست"
        )
        for owner_id in _current_owner_ids(record, hr_ids):
            if notify_once(
                db,
                user_id=owner_id,
                type_="sla_reminder",
                message=message,
                dedup_key=f"sla:{record.id}:{record.status.value}",
                within_days=settings.sla_reminder_days,
                evaluation_record_id=record.id,
                link=f"/evaluations/{record.id}",
                seen=seen,
            ):
                created += 1
    return created


def run_orphaned_case_sweep(db: Session) -> int:
    """پرونده‌های بازی که مسئولِ مرحلهٔ فعلی‌شان دیگر کاربر فعالی نیست را به HR گزارش می‌کند.

    این دقیقاً همان حالتی است که ابزارهای لغو/بازتخصیص برای آن ساخته شدند: گذار،
    برابری `current_user.id` با مسئول ثبت‌شده را لازم دارد، پس اگر آن حساب غیرفعال
    شود پرونده تا ابد سر جایش می‌ماند. بدون این جارو، HR فقط موقع تمدید قرارداد —
    یعنی بدترین لحظهٔ ممکن — متوجهش می‌شد.
    """
    open_records = list(db.scalars(select(EvaluationRecord).where(IS_OPEN_RECORD)))
    hr_ids = _active_hr_ids(db)
    created = 0

    # وضعیت submitted صاحب مشخصی ندارد (هر HR فعالی می‌تواند اقدام کند)، پس
    # «بی‌صاحب» بودنش معنای دیگری دارد و این‌جا موضوعیت ندارد.
    owners_by_record = {
        record.id: _current_owner_ids(record, hr_ids)
        for record in open_records
        if record.status != EvaluationStatus.submitted
    }

    # یک کوئری برای همهٔ صندلی‌ها، نه یکی به‌ازای هر پرونده. تعدادِ صندلی‌های
    # متمایز به اندازهٔ *سازمان* است و نه به اندازهٔ تاریخِ پرونده‌ها، پس این
    # مجموعه کوچک می‌ماند حتی وقتی پرونده‌ها ده‌هزارتا شوند — و همان است که
    # پرسیدنِ یکی‌یکی را بی‌معنا می‌کند.
    seat_ids = {owner_id for owners in owners_by_record.values() for owner_id in owners}
    active_seat_ids = (
        set(db.scalars(select(User.id).where(User.id.in_(seat_ids), User.is_active.is_(True))))
        if seat_ids
        else set()
    )
    seen = already_notified(
        db,
        [
            f"orphaned:{record.id}:{record.status.value}"
            for record in open_records
            if record.id in owners_by_record
        ],
        settings.notification_dedup_days,
    )

    for record in open_records:
        owner_ids = owners_by_record.get(record.id)
        if not owner_ids:
            continue
        if any(owner_id in active_seat_ids for owner_id in owner_ids):
            continue

        message = (
            f"پرونده {record.evaluation_code} ({record.subject.full_name}) گیر کرده است: "
            "مسئول مرحلهٔ فعلی دیگر کاربر فعالی نیست. مسئول جدید تعیین کنید یا پرونده را لغو کنید."
        )
        for hr_id in hr_ids:
            if notify_once(
                db,
                user_id=hr_id,
                type_="orphaned_case",
                message=message,
                dedup_key=f"orphaned:{record.id}:{record.status.value}",
                within_days=settings.notification_dedup_days,
                evaluation_record_id=record.id,
                link=f"/evaluations/{record.id}",
                seen=seen,
            ):
                created += 1
    return created


def run_improvement_review_sweep(db: Session) -> int:
    """برای برنامه‌های بهبودِ بازی که تاریخ بازنگری‌شان نزدیک (یا گذشته) است، به HR و
    مسئول پیگیری یادآوری می‌فرستد. dedup_key شامل تاریخ بازنگری است تا با جابه‌جایی
    تاریخ دوباره فعال شود."""
    horizon = today_local() + timedelta(days=settings.improvement_review_alert_days)
    due_plans = db.scalars(
        select(ImprovementPlan).where(
            ImprovementPlan.status == ImprovementPlanStatus.open,
            ImprovementPlan.review_date <= horizon,
        )
    )

    due_plans = list(due_plans)
    hr_ids = _active_hr_ids(db)
    seen = already_notified(
        db,
        [
            f"improvement_review:{plan.id}:{plan.review_date.isoformat()}"
            for plan in due_plans
        ],
        settings.notification_dedup_days,
    )
    created = 0
    today = today_local()
    for plan in due_plans:
        days = (plan.review_date - today).days
        when = (
            f"{fa_digits(days)} روز دیگر"
            if days >= 0
            else f"{fa_digits(abs(days))} روز پیش (گذشته)"
        )
        message = (
            f"تاریخ بازنگری برنامه بهبود «{plan.title}» "
            f"({plan.personnel.full_name}) {when} است"
        )
        recipients = set(hr_ids)
        if plan.owner_user_id is not None:
            recipients.add(plan.owner_user_id)
        for user_id in recipients:
            if notify_once(
                db,
                user_id=user_id,
                type_="improvement_review_due",
                message=message,
                dedup_key=f"improvement_review:{plan.id}:{plan.review_date.isoformat()}",
                within_days=settings.notification_dedup_days,
                link=f"/improvement-plans/{plan.id}",
                seen=seen,
            ):
                created += 1
    return created


def run_audit_anchor_sweep(db: Session) -> int:
    """زنجیرهٔ ممیزی را کامل می‌سنجد و لنگر را جلو می‌برد. خروجی: ۱ اگر جلو رفت.

    **چرا این‌جا و نه روی مسیرِ درخواست:** بررسیِ کامل از ابتدای تاریخ حساب
    می‌کند و آن عدد هیچ‌وقت کوچک نمی‌شود. جای چنین کاری پس‌زمینه است، نه
    لحظه‌ای که منابع انسانی صفحهٔ گزارش رویدادها را باز می‌کند.

    **چرا با فاصلهٔ خودش:** زمان‌بند هر پنج دقیقه اجرا می‌شود. بی این گارد،
    همان هزینه فقط جابه‌جا می‌شد.

    **و اگر شکست خورد:** لنگر تکان نمی‌خورد (قاعده‌اش در
    `audit.record_full_verification`) و منابع انسانی خبردار می‌شود. اعلان
    اختیاری نیست: از این پس بررسیِ تعاملی فقط *پس از* لنگر را می‌بیند، پس
    دست‌کاری در ردیف‌های پیش از لنگر در رابط دیده نمی‌شود. کشفی که به کسی
    نرسد، کشف نیست.
    """
    last = latest_check(db)
    if last is not None:
        due_after = last.verified_at + timedelta(hours=settings.audit_full_verify_interval_hours)
        if datetime.now(UTC) < due_after:
            return 0

    outcome = record_full_verification(db)
    if outcome["ok"]:
        return 1 if outcome["advanced"] else 0

    watchers = list(
        db.scalars(
            select(User.id)
            .join(UserCapability, UserCapability.user_id == User.id)
            .where(
                UserCapability.capability == Capability.view_audit_log,
                User.is_active.is_(True),
            )
            .distinct()
        )
    )
    message = (
        "راستی‌آزماییِ زنجیرهٔ گزارش رویدادها شکست خورد: "
        f"{outcome['reason']} (نخستین ردیفِ ناسازگار: {fa_digits(outcome['broken_at_id'] or 0)}). "
        "یعنی ردیفی از لاگ مستقیماً در دیتابیس ویرایش یا حذف شده است."
    )
    # کلیدِ dedup شاملِ نقطهٔ شکست است: شکستِ *تازه* در جای دیگر باید دوباره
    # خبر بدهد، ولی همان شکست هر شب یک اعلانِ تکراری نسازد.
    dedup = f"audit_chain_broken:{outcome['broken_at_id']}"
    seen = already_notified(db, [dedup], settings.notification_dedup_days)
    for user_id in watchers:
        notify_once(
            db,
            user_id=user_id,
            type_="audit_chain_broken",
            message=message,
            dedup_key=dedup,
            within_days=settings.notification_dedup_days,
            link="/hr/audit-log",
            seen=seen,
        )
    return 0


#: چند سند در هر جارو ساخته شود. رندر PDF گران است و جارو هر پنج دقیقه اجرا
#: می‌شود؛ بدون سقف، یک backlog بزرگ (مثلاً سروری که تازه WeasyPrint گرفته) کل
#: پنجرهٔ جارو را می‌بلعد و بقیهٔ یادآوری‌ها را عقب می‌اندازد. با این سقف، backlog
#: در چند دور تخلیه می‌شود.
_DOCUMENT_BACKFILL_BATCH = 20


def run_document_backfill_sweep(db: Session) -> int:
    """پرونده‌های نهایی‌شده‌ای که هنوز PDF آرشیوی ندارند را می‌سازد (P2-05).

    از وقتی رندر PDF از مسیر درخواستِ نهایی‌سازی بیرون رفته، ساخت سند یک کار
    پس‌زمینه است — و کار پس‌زمینه ممکن است اصلاً اجرا نشود: پروسه ری‌استارت شود،
    کتابخانهٔ بومی نصب نباشد، یا رندر خطا بدهد. این جارو همان تضمینِ «بالاخره
    ساخته می‌شود» است که وعده‌اش را داده‌ایم.

    نهایی‌شده‌هایی که snapshot ندارند رد می‌شوند: سندی که از روی snapshot ساخته
    نشود، سندِ همان لحظه نیست و ادعای byte-stable بودن را باطل می‌کند.
    """
    if not weasyprint_available():
        return 0

    has_document = (
        select(EvaluationDocument.id)
        .where(EvaluationDocument.evaluation_record_id == EvaluationRecord.id)
        .exists()
    )
    pending = db.scalars(
        select(EvaluationRecord)
        .where(
            EvaluationRecord.status == EvaluationStatus.finalized,
            EvaluationRecord.final_snapshot.is_not(None),
            ~has_document,
        )
        .order_by(EvaluationRecord.finalized_at)
        .limit(_DOCUMENT_BACKFILL_BATCH)
    ).all()

    created = 0
    for record in pending:
        if archive_final_pdf(db, record) is not None:
            created += 1
    return created


def run_all_sweeps(db: Session) -> dict[str, int]:
    """همه sweep ها را اجرا و commit می‌کند؛ نقطه ورود زمان‌بند و endpoint دستی."""
    summary = {
        "contract_expiry": run_contract_expiry_sweep(db),
        "sla_reminder": run_sla_sweep(db),
        "orphaned_case": run_orphaned_case_sweep(db),
        "improvement_review": run_improvement_review_sweep(db),
        # سندهای جامانده — تضمین «بالاخره ساخته می‌شود» برای رندرِ پس‌زمینه‌ای
        "documents_archived": run_document_backfill_sweep(db),
        # نگهداری، نه اعلان: ردیف‌های منقضیِ شمارش تلاش ورود را پاک می‌کند تا جدول
        # با نام‌های کاربریِ تصادفیِ یک حملهٔ enumeration باد نکند.
        "stale_login_attempts_purged": purge_stale(db),
        # همان دستهٔ نگهداری: کارتِ تأییدِ تصمیم‌گرفته‌شده فقط ظاهرِ گفت‌وگوست و
        # سندش در گزارش رویدادها می‌ماند، پس نباید تا ابد در جدول بنشیند.
        "decided_ai_actions_purged": purge_decided_actions(db),
        # و نشست‌های مرده. هر چرخشِ توکن یک ردیف می‌ساخت و هیچ‌چیز برشان
        # نمی‌داشت — تنها جدولی که جاروی نگهداری نداشت.
        "dead_sessions_purged": purge_dead_sessions(db),
        # راستی‌آزماییِ کاملِ زنجیره — با فاصلهٔ خودش، نه هر پنج دقیقه.
        "audit_chain_anchored": run_audit_anchor_sweep(db),
    }
    # تحویل بیرونی *بعد* از بقیه می‌آید: جاروهای بالا ممکن است همین حالا اعلان
    # تازه ساخته باشند، و بی‌معناست که تا اجرای بعدی معطل بمانند.
    summary.update(
        {f"delivery_{key}": value for key, value in run_delivery_sweep(db).items()}
    )
    db.commit()
    return summary
