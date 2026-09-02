"""تفکیک وظایف روی یک زنجیرهٔ ارزیابی — دو قاعده که هر دو یک چیز می‌گویند:
هیچ‌کس نباید دربارهٔ خودش تصمیم بگیرد، و هیچ‌کس نباید دو بار در یک تصمیم رأی
بدهد.

P0-10 — هیچ‌کس نباید ارزیابِ خودش باشد.

پیوند «کاربر ← پرسنل» از طریق `users.personnel_id` است، پس تداخل وقتی رخ می‌دهد که
یکی از سه ارزیابِ یک پرسنل، کاربری باشد که `personnel_id`اش همان پرسنل است. دو مسیر
می‌توانند این وضعیت را بسازند و هر دو گارد دارند:

1. HR دسترسی ارزیابی را تنظیم می‌کند و کاربرِ خودِ فرد را ارزیاب می‌گذارد.
2. دسترسی از قبل درست بوده و HR بعداً کاربرِ ارزیاب را به همان پرسنل لینک می‌کند.

این‌ها گاردهای *کد* برای پیام خطای تمیز هستند؛ پشتیبان واقعی، تریگرهای دیتابیس در
مایگریشن c3e8b1a76d94 است که مسیرهای دیگر (SQL دستی، endpoint آینده) را هم می‌گیرد.
"""
from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from app.models.evaluation import EvaluationRecord
from app.models.evaluation_access import EvaluationAccess
from app.models.org_unit import OrgUnit
from app.models.personnel import Personnel
from app.models.user import User
from app.services.workflow import hr_panel_is_shielded

_CONFLICT_DETAIL = (
    "یک نفر نمی‌تواند ارزیابِ خودش باشد؛ کاربر «{username}» به همین پرسنل متصل است."
)


def ensure_evaluators_are_not_the_subject(
    db: Session, personnel_id: int, evaluator_user_ids: list[int | None]
) -> None:
    """هنگام تنظیم دسترسی ارزیابی: هیچ‌یک از ارزیاب‌ها نباید خودِ این پرسنل باشد."""
    candidate_ids = [user_id for user_id in evaluator_user_ids if user_id is not None]
    if not candidate_ids:
        return

    conflicting = db.scalar(
        select(User.username).where(
            User.id.in_(candidate_ids), User.personnel_id == personnel_id
        )
    )
    if conflicting is not None:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=_CONFLICT_DETAIL.format(username=conflicting),
        )


#: صندلی‌های تکراری‌ای که بیانِ درست‌تری دارند، و آن بیان چیست. کلید، جفتِ
#: مرتب‌شدهٔ نام فیلدهاست.
_REDUNDANT_PAIRS: dict[tuple[str, str], str] = {
    ("unit_supervisor_user_id", "deputy_user_id"): (
        "«مسئول واحد» و «معاونت» یک نفرند. اگر این فرد مستقیماً توسط معاونت ارزیابی "
        "می‌شود، «مسئول واحد» را خالی بگذارید؛ معاونت خودش نمره‌دهندهٔ اول می‌شود."
    ),
    ("deputy_user_id", "ceo_user_id"): (
        "«معاونت» و «مدیرعامل» یک نفرند. اگر این فرد معاونتی بالای سرش ندارد، "
        "«معاونت» را خالی بگذارید؛ پرونده از منابع انسانی مستقیم به مدیرعامل می‌رود."
    ),
}


def ensure_chain_stages_are_not_redundant(
    db: Session,
    unit_supervisor_user_id: int | None,
    deputy_user_id: int | None,
    ceo_user_id: int | None,
) -> None:
    """یک نفر نباید دو صندلیِ *قابل‌ادغام* را در یک زنجیره داشته باشد.

    ایراد درست است: `may_act_at` عمداً اجازه می‌دهد مافوق در مرحلهٔ پایین‌تر
    بنشیند (بدون آن، ساختار واقعی سازمان قابل ثبت نبود)، پس یک نفر می‌تواند دو
    صندلی بگیرد و لاگ ممیزی *دو تأیید* نشان بدهد — دو رویداد، دو مُهر، یک آدم.

    ولی «هر سه باید متفاوت باشند» پاسخ درستی نیست، چون یکی از سه ترکیب اصلاً
    تکراری نیست: کسی که مستقیماً زیر نظر مدیرعامل کار می‌کند. مدیرعامل هم
    نمره‌دهندهٔ اولش است و هم تأییدکنندهٔ نهایی، و بالای سرش کسِ دیگری *وجود
    ندارد*. ممنوع‌کردنش یعنی آن افراد قابل ثبت نیستند — همان اشتباهی که یک بار
    با NOT NULL بودنِ ستون معاونت مرتکب شدیم و آدم‌ها را وادار کرد معاونتِ
    ساختگی بنویسند.

    پس فقط صندلی‌هایی رد می‌شوند که *بیان دیگری* دارند؛ برای هرکدام هم پیام
    می‌گوید آن بیان چیست. حالتِ مجاز بی‌صدا نمی‌ماند: `single_decider` روی
    پرونده آن را علامت می‌زند و سند نهایی چاپش می‌کند
    (`app/services/snapshot.py`).
    """
    seats = {
        "unit_supervisor_user_id": unit_supervisor_user_id,
        "deputy_user_id": deputy_user_id,
        "ceo_user_id": ceo_user_id,
    }
    for (first, second), remedy in _REDUNDANT_PAIRS.items():
        if seats[first] is None or seats[second] is None:
            continue
        if seats[first] != seats[second]:
            continue
        username = db.scalar(select(User.username).where(User.id == seats[first]))
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"{remedy} (کاربر «{username}»)",
        )


def subject_belongs_to_hr(db: Session, personnel_id: int) -> bool:
    """آیا موضوعِ این پرونده عضوِ واحدِ منابع انسانی است؟

    اگر بله، پرونده مرحلهٔ بررسیِ منابع انسانی را ندارد
    (`EvaluationRecord.hr_review_skipped`). دلیلش با `ensure_not_deciding_about_oneself`
    یکی است و یک پله جلوتر می‌رود: آن گارد جلوی *اقدام و دیدنِ خودِ فرد* را
    می‌گیرد، ولی پرونده را در صفِ HR نگه می‌دارد — و آن صف در تیمِ کوچکِ منابع
    انسانی به دو بن‌بست می‌رسید:

    * کارشناسِ HR که مسئولِ مستقیمش مدیرِ HR است: تنها کسی که می‌توانست
      داوریِ بی‌طرف بکند، همان کسی بود که نمره را داده بود.
    * مدیرِ HR: تنها داورِ باقی‌مانده، زیردستِ خودش بود.

    پس مرحله حذف می‌شود، نه اینکه به کسی سپرده شود. بهایش را می‌پذیریم: پروندهٔ
    اعضای واحدِ منابع انسانی یک جفت‌چشمِ کمتر دارد، و در عوض آن جفت‌چشم متعلق به
    کسی نیست که موضوع یا هم‌تیمیِ موضوعِ همان پرونده است.

    ملاک عضویتِ *واحد* است و نه نقشِ حساب. نقش کار نمی‌کرد: هر حساب یک نقش
    دارد و `may_act_at` عمداً `hr` را از صندلی‌های زنجیره بیرون گذاشته، پس مدیرِ
    منابع انسانی که مسئولِ مستقیمِ کارشناسانش است نمی‌تواند نقشِ `hr` داشته
    باشد. با ملاکِ نقشی، پروندهٔ خودِ او از قلم می‌افتاد — همان حالتی که این
    تغییر برایش نوشته شد.
    """
    return personnel_id in hr_unit_personnel_ids(db, [personnel_id])


def hr_unit_personnel_ids(db: Session, personnel_ids: list[int]) -> set[int]:
    """کدام‌یک از این پرسنل‌ها در واحدِ منابع انسانی‌اند؟

    شکلِ دسته‌ای *پایه* است و نسخهٔ تک‌نفره رویش سوار می‌شود، نه برعکس: ساختِ
    دسته‌ای صدها پرونده را با هم باز می‌کند و یک پرسش به‌ازای هر نفر، همان
    N+1ای است که بقیهٔ آن تابع (مثل `access_by_person`) عمداً از آن پرهیز کرده.
    و دو پرسشِ جدا برای یک قاعده، یعنی روزی یکی شرطی را می‌گیرد و دیگری نمی‌گیرد.

    پیوند از راهِ *رشته* است چون `personnel.org_unit` کلید خارجی نیست
    (`models/org_unit.py` می‌گوید چرا). `is_active` واحد عمداً شرط نیست: واحدی
    که «برای ثبتِ تازه پیشنهاد نشو» علامت خورده، همچنان واحدِ منابع انسانیِ
    کسانی است که در آن مانده‌اند.
    """
    if not personnel_ids:
        return set()
    # نامِ کاملِ واحد در پایتون ساخته می‌شود و نه در SQL: قاعدهٔ چسباندنِ «محل /
    # واحد» یک جا زندگی می‌کند (`OrgUnit.full_name` ← `services/org_unit.join_site`)
    # و بازنویسی‌اش با concat، دو نسخه از یک قاعده می‌شد. تعداد واحدها ده‌هاست،
    # نه هزارها.
    names = {
        unit.full_name
        for unit in db.scalars(select(OrgUnit).where(OrgUnit.is_hr_unit.is_(True)))
    }
    if not names:
        return set()
    return set(
        db.scalars(
            select(Personnel.id).where(
                Personnel.id.in_(personnel_ids),
                Personnel.org_unit.in_(names),
            )
        )
    )


def ensure_not_deciding_about_oneself(record, current_user) -> None:
    """کسی که موضوعِ پرونده است، نباید هیچ نقشی در رسیدگی به آن داشته باشد.

    سه مرحلهٔ زنجیره از قبل گارد داشتند، ولی مرحلهٔ منابع انسانی نه — و آن مرحله
    اتفاقاً تنها مرحله‌ای است که *صاحب از پیش تعیین‌شده* ندارد و از یک صف مشترک
    برداشته می‌شود. یعنی کارمندِ منابع انسانی می‌توانست پروندهٔ خودش را از صف
    بردارد، تأییدش کند، لغوش کند، یا اعتراض خودش را رد کند — و هیچ گاردی مانعش
    نبود، چون همهٔ آن endpointها فقط «نقش = hr» را می‌سنجیدند.

    گارد فقط روی *اقدام* نیست، روی *دیدن* هم هست: پیش از نهایی‌شدن، پروندهٔ در
    جریان شواهدِ ارزیاب را دارد. کسی که موضوع آن است نباید آن را از پنل HR بخواند.

    در سازمانی با یک نفر HR، این یعنی پروندهٔ خودِ او تا وقتی حساب HR دومی نباشد
    پیش نمی‌رود. این هزینه، آگاهانه است: بدیلش این است که یک نفر تنها، ارزیابیِ
    خودش را تأیید کند.
    """
    if current_user.personnel_id is None:
        return
    if current_user.personnel_id != record.subject_personnel_id:
        return
    raise HTTPException(
        status_code=http_status.HTTP_403_FORBIDDEN,
        detail=(
            "این پروندهٔ ارزیابیِ خودِ شماست؛ رسیدگی به آن باید توسط کاربر دیگری از "
            "منابع انسانی انجام شود."
        ),
    )


def ensure_hr_may_handle(record, current_user) -> None:
    """گاردِ کاملِ منابع انسانی روی یک پرونده — دو قاعده، یک در.

    `ensure_not_deciding_about_oneself` پروندهٔ *خودِ* کاربر را می‌بندد. این تابع
    آن را نگه می‌دارد و قاعدهٔ دوم را رویش می‌گذارد: پروندهٔ *هم‌تیمی‌ها* هم تا
    وقتی باز است بسته می‌ماند (`workflow.hr_panel_is_shielded` می‌گوید چرا و تا
    کِی).

    یک تابع و نه دو، چون این گارد باید در *هر* نقطه‌ای که منابع انسانی به یک
    پرونده دست می‌زند بنشیند — دیدن، لغو، تمدید مهلت، برداشتن از صف، واگذاری،
    تغییر مسئولِ مرحله. نسخهٔ قبلی همین را با فراخوانیِ پراکندهٔ
    `ensure_not_deciding_about_oneself` انجام می‌داد و در یکی از آن نقطه‌ها
    (`reassign`) اصلاً فراخوانی نشده بود.

    برای نقش‌های زنجیره بی‌اثر است: آن‌ها پرونده را از راهِ صندلیِ خودشان
    می‌بینند، نه از پنلِ منابع انسانی، و بستنِ این در روی آن‌ها یعنی قطعِ خودِ
    زنجیره.
    """
    ensure_not_deciding_about_oneself(record, current_user)
    if current_user.role is not UserRole.hr:
        return
    if not hr_panel_is_shielded(record):
        return
    raise HTTPException(
        status_code=http_status.HTTP_403_FORBIDDEN,
        detail=(
            "این پرونده متعلق به واحد منابع انسانی است و تا پیش از ثبت نهایی از "
            "پنل منابع انسانی قابل دسترسی نیست؛ رسیدگی به آن با معاونت و مدیرعامل است."
        ),
    )


def ensure_user_link_is_not_self_evaluation(db: Session, user: User, personnel_id: int) -> None:
    """هنگام لینک کردن یک کاربر به پرسنل: آن کاربر نباید از قبل ارزیابِ همان پرسنل باشد."""
    is_evaluator_on_access = db.scalar(
        select(EvaluationAccess.id).where(
            EvaluationAccess.personnel_id == personnel_id,
            or_(
                EvaluationAccess.unit_supervisor_user_id == user.id,
                EvaluationAccess.deputy_user_id == user.id,
                EvaluationAccess.ceo_user_id == user.id,
            ),
        )
    )
    is_evaluator_on_record = db.scalar(
        select(EvaluationRecord.id).where(
            EvaluationRecord.subject_personnel_id == personnel_id,
            or_(
                EvaluationRecord.unit_supervisor_user_id == user.id,
                EvaluationRecord.deputy_user_id == user.id,
                EvaluationRecord.ceo_user_id == user.id,
            ),
        )
    )
    if is_evaluator_on_access is not None or is_evaluator_on_record is not None:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=(
                f"کاربر «{user.username}» ارزیابِ این پرسنل است؛ نمی‌توان او را به "
                "همین پرسنل متصل کرد (کسی نمی‌تواند ارزیابِ خودش باشد)."
            ),
        )
