"""خواندن، ساختن و فعال‌کردن طرح نمره‌دهی (P1-04).

`Rules` — یک ساختار ساده و تغییرناپذیر — تنها چیزی است که موتور محاسبه می‌بیند.
منبعش می‌تواند یک ردیف دیتابیس باشد یا ثابت‌های قدیمی؛ محاسبه فرقش را نمی‌فهمد
و لازم هم نیست بفهمد. این جداسازی چیزی است که اجازه می‌دهد «پیش‌نمایش» یک طرحِ
هنوز-فعال‌نشده دقیقاً همان کدِ محاسبهٔ واقعی را اجرا کند، نه یک کپیِ موازی که
دیر یا زود با اصل فرق می‌کند.
"""
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import constants
from app.models.enums import SchemeStatus
from app.models.scoring_scheme import ScoringScheme


@dataclass(frozen=True)
class Rules:
    """قواعد نمره‌دهی، مستقل از این‌که از کجا آمده‌اند."""

    general_section_weight: float
    specialized_section_weight: float
    evidence_required_scores: tuple[int, ...]
    evidence_min_words: int
    evidence_max_words: int
    #: [(سقف بازه — exclusive, برچسب), ...] — مرتب و پیوسته
    thresholds: tuple[tuple[float, str], ...]
    #: {indicator_id: weight}؛ شاخصِ غایب وزن ۱ می‌گیرد
    indicator_weights: dict[int, float]
    #: شمارهٔ نسخه، یا None وقتی از ثابت‌ها آمده (فقط مسیر بازگشتی)
    version: int | None = None
    #: سقف امتیاز ویژه (صفر = غیرفعال). پیش‌فرضِ اینجا فقط برای فراخوان‌های
    #: قدیمی است که این قاعده را نمی‌شناسند؛ مسیرهای واقعی مقدارش را می‌دهند.
    bonus_max_points: float = constants.BONUS_MAX_POINTS
    #: تا این درصد، پرونده واجدِ برنامهٔ بهبود است
    improvement_plan_max_pct: float = constants.IMPROVEMENT_PLAN_MAX_PCT

    def weight_for(self, indicator_id: int) -> float:
        return self.indicator_weights.get(indicator_id, 1.0)

    def recommendation_for(self, final_pct: float) -> str:
        for upper_exclusive, label in self.thresholds:
            if final_pct < upper_exclusive:
                return label
        return self.thresholds[-1][1]


#: قواعدِ پیش از P1-04، به‌عنوان مبنای نسخهٔ ۱ و به‌عنوان مسیر بازگشتی برای
#: پرونده‌هایی که به هر دلیل طرحی ندارند. عمداً از خودِ constants خوانده می‌شود
#: تا اگر کسی آن فایل را دست بزند، نسخهٔ ۱ همچنان بازتابش باشد.
LEGACY_RULES = Rules(
    general_section_weight=constants.GENERAL_SECTION_WEIGHT,
    specialized_section_weight=constants.SPECIALIZED_SECTION_WEIGHT,
    evidence_required_scores=tuple(constants.EVIDENCE_REQUIRED_SCORES),
    evidence_min_words=constants.EVIDENCE_REQUIRED_MIN_WORDS,
    evidence_max_words=constants.EVIDENCE_MAX_WORDS,
    thresholds=tuple((float(u), label) for u, label in constants.FINAL_RESULT_THRESHOLDS),
    indicator_weights={},
    bonus_max_points=constants.BONUS_MAX_POINTS,
    improvement_plan_max_pct=constants.IMPROVEMENT_PLAN_MAX_PCT,
)


def rules_from(scheme: ScoringScheme) -> Rules:
    return Rules(
        general_section_weight=float(scheme.general_section_weight),
        specialized_section_weight=float(scheme.specialized_section_weight),
        evidence_required_scores=tuple(int(s) for s in scheme.evidence_required_scores),
        evidence_min_words=scheme.evidence_min_words,
        evidence_max_words=scheme.evidence_max_words,
        thresholds=tuple(
            (float(row["upper_exclusive"]), row["label"]) for row in scheme.thresholds
        ),
        # کلیدهای JSONB رشته‌اند؛ برگرداندنشان به int این‌جا انجام می‌شود تا بقیهٔ
        # کد لازم نباشد بداند این داده از JSON آمده.
        indicator_weights={int(k): float(v) for k, v in (scheme.indicator_weights or {}).items()},
        version=scheme.version,
        bonus_max_points=float(scheme.bonus_max_points),
        improvement_plan_max_pct=float(scheme.improvement_plan_max_pct),
    )


def active_scheme(db: Session) -> ScoringScheme | None:
    return db.scalar(select(ScoringScheme).where(ScoringScheme.status == SchemeStatus.active))


def rules_for_record(db: Session, record) -> Rules:
    """قواعدی که این پرونده باید با آن‌ها محاسبه شود.

    نکتهٔ کل این ماژول همین یک تابع است: از `record.scoring_scheme_id` می‌خواند،
    نه از طرح فعال. پرونده‌ای که پارسال ساخته شده با قواعد پارسال حساب می‌شود،
    حتی اگر امروز HR وزن‌ها را عوض کرده باشد.
    """
    if record.scoring_scheme_id is not None:
        scheme = db.get(ScoringScheme, record.scoring_scheme_id)
        if scheme is not None:
            return rules_from(scheme)
    # پروندهٔ بی‌مهر: نباید پیش بیاید (مایگریشن همه را مهر زده و ساخت جدید هم
    # مهر می‌زند)، ولی محاسبه‌ای که به‌خاطر دادهٔ ناقص ۵۰۰ بدهد بدتر از محاسبه‌ای
    # است که به رفتار قبلی برگردد.
    scheme = active_scheme(db)
    return rules_from(scheme) if scheme is not None else LEGACY_RULES


def current_rules(db: Session) -> Rules:
    """قواعد طرح فعال — برای پرونده‌های *جدید* و برای نمایش در UI."""
    scheme = active_scheme(db)
    return rules_from(scheme) if scheme is not None else LEGACY_RULES


def next_version(db: Session) -> int:
    return (db.scalar(select(func.max(ScoringScheme.version))) or 0) + 1


def ensure_scheme_is_valid(scheme: ScoringScheme) -> None:
    """قواعدِ طرح را دوباره از دروازهٔ `SchemeInput` رد می‌کند.

    گاردِ ورودی در آن اسکیما زندگی می‌کند و فقط روی *ساخت* اعمال می‌شود. تا
    امروز فعال‌سازی هیچ‌چیز را دوباره نمی‌سنجید، پس هر پیش‌نویسی که از راهی
    غیرِ آن اسکیما ساخته شده بود — و مسیرِ دستیار دقیقاً همان راه بود — بی
    هیچ مانعی به قاعدهٔ نمره‌دهیِ کلِ سازمان تبدیل می‌شد.

    آن راه بسته شد، ولی این‌جا کمربندِ دوم است و نه تکرار: پیش‌نویس‌هایی که
    *پیش از* آن اصلاح ساخته شده‌اند هنوز در دیتابیس نشسته‌اند، و بستنِ درِ
    ورودی چیزی را که از قبل تو آمده بیرون نمی‌کند.
    """
    from pydantic import ValidationError

    from app.core.validation_errors import persian_validation_message
    from app.schemas.scoring_scheme import SchemeInput

    try:
        SchemeInput(
            name=scheme.name,
            general_section_weight=float(scheme.general_section_weight),
            specialized_section_weight=float(scheme.specialized_section_weight),
            evidence_required_scores=list(scheme.evidence_required_scores or []),
            evidence_min_words=scheme.evidence_min_words,
            evidence_max_words=scheme.evidence_max_words,
            bonus_max_points=float(scheme.bonus_max_points),
            improvement_plan_max_pct=float(scheme.improvement_plan_max_pct),
            thresholds=list(scheme.thresholds or []),
            indicator_weights={int(k): float(v) for k, v in (scheme.indicator_weights or {}).items()},
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=(
                "این پیش‌نویس قواعدِ معتبری ندارد و فعال نمی‌شود: "
                + persian_validation_message(exc.errors())
            ),
        ) from exc


def activate(db: Session, scheme: ScoringScheme, *, actor_user_id: int) -> None:
    """طرح را فعال و طرح فعلی را بازنشسته می‌کند.

    جداسازیِ وظایف *داخلِ سرویس* سنجیده می‌شود، نه در endpoint: سازندهٔ طرح
    نمی‌تواند خودش فعالش کند. پیش از این این قانون فقط در مسیر رابط بود و
    دستیار — که همین تابع را مستقیم صدا می‌زد — از آن عبور می‌کرد (H-2 در
    گزارش ممیزی): یک نفرِ تنها با مجوزِ manage_scoring می‌توانست قاعدهٔ
    نمره‌دهیِ کل سازمان را بسازد و فعال کند.

    به همان استدلال، «فقط پیش‌نویس فعال می‌شود» هم این‌جاست و نه در endpoint.
    آن گارد فقط در روتر بود و مسیر دستیار از کنارش می‌گذشت، پس یک نسخهٔ
    *بازنشسته* از راه دستیار دوباره فعال می‌شد — یعنی برگشتِ بی‌صدای قاعدهٔ
    نمره‌دهیِ سازمان، و هر پروندهٔ تازه‌ای با آن نسخهٔ احیاشده مهر می‌خورد.
    نسخهٔ فعال یا بازنشسته تغییرناپذیر است؛ راهِ درست، پیش‌نویسِ تازه است.

    نکته: برای نسخهٔ ۱ که با seed آمده `created_by_user_id is None` است، پس
    گاردِ دو‌نفره روی آن اصلاً اعمال نمی‌شود — دلیلِ دیگری برای این‌که گاردِ
    «فقط پیش‌نویس» جدا و همیشگی باشد.

    commit با فراخواننده است تا لاگ ممیزی در همان تراکنش بنشیند.
    """
    if scheme.status is not SchemeStatus.draft:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="فقط پیش‌نویس را می‌توان فعال کرد؛ نسخهٔ فعال یا بازنشسته تغییرناپذیر است",
        )
    if scheme.created_by_user_id is not None and scheme.created_by_user_id == actor_user_id:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail=(
                "فعال‌سازی طرح باید توسط کاربر دیگری از منابع انسانی انجام شود؛ "
                "سازندهٔ طرح نمی‌تواند خودش آن را فعال کند"
            ),
        )
    ensure_scheme_is_valid(scheme)
    now = datetime.now(UTC)
    previous = active_scheme(db)
    if previous is not None:
        previous.status = SchemeStatus.retired
        previous.retired_at = now
        # قبل از درج فعالِ تازه flush می‌شود، وگرنه ایندکس یکتای جزئی
        # (uq_single_active_scheme) وسط همین تراکنش دو ردیف فعال می‌بیند.
        db.flush()

    scheme.status = SchemeStatus.active
    scheme.activated_at = now
    scheme.activated_by_user_id = actor_user_id
    db.flush()
