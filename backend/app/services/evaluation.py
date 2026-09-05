from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.core.text_limits import BONUS_REASON_MIN
from app.models.indicator import Indicator
from app.services.scoring_scheme import LEGACY_RULES, Rules

#: صندلی‌های زنجیرهٔ ارزیابی به ترتیب مرحله — برای پیام‌های خطای خوانا.
_CHAIN_SEATS: tuple[tuple[str, str], ...] = (
    ("مسئول واحد", "unit_supervisor_user_id"),
    ("معاونت", "deputy_user_id"),
    ("مدیرعامل", "ceo_user_id"),
)


def inactive_seat_labels(db: Session, access) -> list[str]:
    """صندلی‌هایی از زنجیره که کاربرِ نشسته بر آن‌ها غیرفعال است.

    وضعیتِ فعال‌بودن صندلی‌ها فقط هنگام *نوشتنِ* دسترسی سنجیده می‌شد؛ حسابی که
    بعداً غیرفعال شود (جدایی، انتقال) صندلی را مرده می‌گذاشت و پرونده‌ای که
    بعداً باز می‌شد هرگز جلو نمی‌رفت — و یادآوریِ SLA هم برای حسابِ مرده
    می‌رفت (M-1 در گزارش ممیزی). بازکردنِ پرونده روی زنجیرهٔ نیمه‌مُرده ممنوع.
    """
    from app.models.evaluation_access import EvaluationAccess
    from app.models.user import User

    if not isinstance(access, EvaluationAccess):
        return []
    labels: list[str] = []
    for label, field_name in _CHAIN_SEATS:
        user_id = getattr(access, field_name)
        if user_id is None:
            continue
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            labels.append(label)
    return labels


#: همان سه صندلی، به‌علاوهٔ صندلیِ منابع انسانی — که برخلاف آن سه از یک صفِ
#: مشترک شروع می‌شود ولی وقتی *برداشته* شد، فقط همان کارشناس می‌تواند اقدام کند
#: (`workflow.claimable_if_unassigned`). پس مالکِ HR هم یک صندلیِ قفل‌شونده است.
_SEATS_ON_RECORD: tuple[tuple[str, str], ...] = (
    ("مسئول واحد", "unit_supervisor_user_id"),
    ("معاونت", "deputy_user_id"),
    ("مدیرعامل", "ceo_user_id"),
    ("منابع انسانی", "hr_user_id"),
)


def occupied_seats_in_open_records(db: Session, user_id: int) -> list[tuple[str, str]]:
    """صندلی‌هایی از پرونده‌های *باز* که این کاربر رویشان نشسته.

    خروجی: فهرستِ (کدِ پرونده، برچسبِ صندلی) — چیزی که پیام خطا باید نشان بدهد
    تا منابع انسانی بداند کدام پرونده‌ها را باید اول جایگزین کند.

    فقط پروندهٔ *باز*، عمداً: پروندهٔ نهایی‌شده یا لغوشده گذاری ندارد و صندلیِ
    رویش دیگر کاری نمی‌کند. و فقط پرونده و نه ردیفِ `evaluation_access`:
    ردیفِ دسترسی برای هر مسئولِ واحدی همیشه وجود دارد، پس سنجیدنِ آن یعنی
    تغییرِ نقش عملاً هیچ‌وقت ممکن نباشد.
    """
    from app.models.evaluation import EvaluationRecord
    from app.services.workflow import IS_OPEN_RECORD

    seat_columns = [getattr(EvaluationRecord, field) for _, field in _SEATS_ON_RECORD]
    records = db.scalars(
        select(EvaluationRecord)
        .where(IS_OPEN_RECORD, or_(*[column == user_id for column in seat_columns]))
        .order_by(EvaluationRecord.id)
    ).all()
    return [
        (record.evaluation_code, label)
        for record in records
        for label, field in _SEATS_ON_RECORD
        if getattr(record, field) == user_id
    ]


def ensure_no_open_chain_seat(db: Session, user_id: int, *, action: str) -> None:
    """اگر کاربر در پروندهٔ بازی صندلی دارد، تغییر را رد می‌کند.

    چرا رد و نه هشدار: تغییرِ نقشِ کسی که صندلی دارد، پرونده را *بی‌صدا* قفل
    می‌کند. صندلی روی ردیف می‌ماند، ولی صاحبش دیگر از `require_chain_stage`
    رد نمی‌شود و هیچ‌کسِ دیگری هم روی آن ردیف نیست. پرونده می‌ماند و فقط
    جاروی شبانه — آن هم فردا — «گیر کرده» گزارشش می‌کند.

    راهِ درست این است که منابع انسانی *اول* با «تغییر مسئول مرحله» جایگزین
    بگذارد و بعد نقش را عوض کند؛ همان ابزاری که برای نجاتِ پروندهٔ گیرکرده
    ساخته شده، این‌جا پیش از گیرکردن به کار می‌رود. پیام خطا صریح می‌گوید کدام
    پرونده‌ها، تا این کار حدس‌زدنی نباشد.
    """
    seats = occupied_seats_in_open_records(db, user_id)
    if not seats:
        return
    listed = "، ".join(f"{code} ({label})" for code, label in seats[:5])
    more = f" و {len(seats) - 5} مورد دیگر" if len(seats) > 5 else ""
    raise HTTPException(
        status_code=http_status.HTTP_409_CONFLICT,
        detail=(
            f"{action} ممکن نیست: این کاربر در {len(seats)} پروندهٔ باز مسئولِ "
            f"مرحله است — {listed}{more}. اول با «تغییر مسئول مرحله» جایگزینش "
            "کنید."
        ),
    )


def word_count(text_value: str | None) -> int:
    if not text_value:
        return 0
    return len([token for token in text_value.split() if token])


def next_evaluation_code(db: Session) -> str:
    seq_value = db.execute(text("SELECT nextval('evaluation_code_seq')")).scalar_one()
    return f"EVL-{seq_value:04d}"


def _fa(number: float | int) -> str:
    """عدد فارسی برای پیام‌های خطا — پیام قاعده به فارسی است، عددش هم باید باشد."""
    return f"{number:g}".translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def recommendation_for(final_pct: float, rules: Rules = LEGACY_RULES) -> str:
    """نتیجه پیشنهادی بر اساس امتیاز نهایی وزنی؛ بازه‌های نیم‌باز، بدون شکاف روی [0, 100]."""
    return rules.recommendation_for(final_pct)


def validate_evidence(
    scores: list[dict],
    indicators_by_id: dict[int, Indicator],
    rules: Rules = LEGACY_RULES,
) -> None:
    """قاعدهٔ شواهد را از طرح نمره‌دهی می‌خواند، نه از ثابت‌ها (P1-04).

    پیام‌های خطا هم از همان قاعده ساخته می‌شوند: پیش از این «حداقل ۳ کلمه» در
    متن خطا هاردکد بود، پس سازمانی که حداقل را ۵ می‌گذاشت، خطایی می‌گرفت که
    عدد اشتباه می‌گفت. هرگز به اعتبارسنجی فرانت‌اند تنها اعتماد نمی‌شود.
    """
    violations = []
    too_long = []
    for row in scores:
        count = word_count(row.get("evidence_text"))
        indicator = indicators_by_id.get(row["indicator_id"])
        label = indicator.category if indicator else f"شاخص #{row['indicator_id']}"
        # حداقل کلمات فقط برای امتیازهایی که طرح مشخص کرده اجباری است.
        if row["score"] in rules.evidence_required_scores and count < rules.evidence_min_words:
            violations.append(
                f"«{label}» (حداقل {_fa(rules.evidence_min_words)} کلمه لازم است، "
                f"در حال حاضر: {_fa(count)} کلمه)"
            )
        # سقف کلمات برای هر شواهدِ واردشده اعمال می‌شود (هر امتیازی)؛ فقط
        # اعتبارسنجی فرانت‌اند کافی نیست — کاربر می‌تواند مستقیماً API را صدا بزند.
        if count > rules.evidence_max_words:
            too_long.append(
                f"«{label}» (حداکثر {_fa(rules.evidence_max_words)} کلمه مجاز است، "
                f"در حال حاضر: {_fa(count)} کلمه)"
            )

    messages = []
    if violations:
        messages.append("شواهد عینی برای شاخص‌های زیر ناقص است: " + "؛ ".join(violations))
    if too_long:
        messages.append("شواهد عینی برای شاخص‌های زیر بیش از حد طولانی است: " + "؛ ".join(too_long))
    if messages:
        raise ValueError(" | ".join(messages))


def validate_bonus(
    bonus_points: float,
    bonus_reason: str | None,
    rules: Rules = LEGACY_RULES,
) -> None:
    """امتیاز ویژه را در برابر قواعدِ همان پرونده می‌سنجد.

    `compute_result` عدد خارج از بازه را بی‌صدا می‌بُرد تا محاسبه هرگز نتیجهٔ
    بی‌معنا ندهد؛ ولی در لحظهٔ *ثبت*، بریدن بی‌صدا بدترین کار ممکن است: ارزیاب ۸
    می‌زند، سامانه ۵ ذخیره می‌کند و چیزی نمی‌گوید. این تابع همان‌جا خطا می‌دهد.
    """
    if bonus_points < 0:
        raise ValueError("امتیاز ویژه نمی‌تواند منفی باشد")
    if bonus_points > 0 and rules.bonus_max_points <= 0:
        raise ValueError("امتیاز ویژه در طرح نمره‌دهی این پرونده فعال نیست")
    if bonus_points > rules.bonus_max_points:
        raise ValueError(
            f"امتیاز ویژه حداکثر می‌تواند {_fa(rules.bonus_max_points)} باشد "
            f"(مقدار واردشده: {_fa(bonus_points)})"
        )
    # دلیل، بخشِ اجباریِ این قابلیت است نه تزئین آن: نمره‌ای که کسی نتواند
    # توضیحش را بخواند، در سند تصمیمِ تمدید قرارداد قابل دفاع نیست.
    reason = (bonus_reason or "").strip()
    if bonus_points > 0 and len(reason) < BONUS_REASON_MIN:
        raise ValueError(
            f"توضیح امتیاز ویژه باید حداقل {_fa(BONUS_REASON_MIN)} نویسه باشد"
        )


def applied_bonus(raw: float | None, rules: Rules, base_pct: float) -> float:
    """امتیازِ ویژه‌ای که *واقعاً* اعمال می‌شود — نه عددی که ارزیاب وارد کرده.

    دو سقف دارد: سقفِ طرح، و فاصلهٔ تا ۱۰۰. سقفِ دوم روی *افزوده* می‌نشیند و نه
    روی حاصلِ جمع، تا این تساوی همیشه برقرار بماند:

        امتیاز فرم + امتیاز ویژه = امتیاز نهایی

    مقدارِ خامِ ثبت‌شده دست‌نخورده در خودِ پرونده و در ردِ ممیزی می‌ماند؛ این‌جا
    فقط اثرش محاسبه می‌شود.

    و چرا یک *تابع* و نه دو خط داخلِ `compute_result`: سندِ نهایی هم همین عدد را
    لازم دارد و پیش از این نسخهٔ خودش را نداشت — مقدارِ خام را چاپ می‌کرد. با
    پایهٔ ۹۸ و امتیازِ خامِ ۵، سند سه عدد نشان می‌داد که با هم جمع نمی‌شدند:
    «۹۸ + ۵ = ۱۰۰». نوشتنِ دوبارهٔ همین فرمول در `snapshot.py` همان جفتِ همتایی
    می‌شد که روزی از هم دور می‌افتد.
    """
    return round(max(0.0, min(float(raw or 0.0), rules.bonus_max_points, 100.0 - base_pct)), 2)


def compute_result(
    scores: list[dict],
    indicators_by_id: dict[int, Indicator],
    rules: Rules = LEGACY_RULES,
    bonus_points: float = 0.0,
) -> dict:
    """درصد هر بخش و امتیاز نهایی وزنی، بر اساس قواعد داده‌شده.

    وزنِ هر شاخص هم از طرح می‌آید: شاخصی که وزن ندارد ۱ می‌گیرد، یعنی حالت
    پیش‌فرض دقیقاً همان میانگین سادهٔ قبلی است. با وزن‌های نابرابر، سقفِ بخش هم
    باید وزنی شود — وگرنه یک شاخصِ سنگین می‌تواند درصد را از ۱۰۰ بالاتر ببرد.
    """
    general_sum = general_max = specialized_sum = specialized_max = 0.0
    for row in scores:
        indicator = indicators_by_id[row["indicator_id"]]
        weight = rules.weight_for(row["indicator_id"])
        if indicator.section.value == "general":
            general_sum += row["score"] * weight
            general_max += 5 * weight
        else:
            specialized_sum += row["score"] * weight
            specialized_max += 5 * weight

    general_pct = round((general_sum / general_max) * 100, 1) if general_max else 0.0
    specialized_pct = round((specialized_sum / specialized_max) * 100, 1) if specialized_max else 0.0

    # وزنِ بخشی که *در این پرونده هیچ شاخصی ندارد* بین بخش‌های موجود پخش می‌شود.
    #
    # بدون این، بخشِ غایب با درصدِ صفر وارد جمع می‌شد و سقفِ نمره را به سهمِ
    # خودش پایین می‌آورد: چارچوبی که فقط شاخصِ «عمومی» دارد، به کسی که به هر
    # سؤال ۵ داده ۶۰ می‌داد — و ۶۰ در جدولِ آستانه‌ها «تمدید مشروط به برنامهٔ
    # بهبود» است. با فقط شاخصِ «تخصصی» عدد ۴۰ می‌شد، یعنی «عدم تمدید». نمرهٔ
    # کامل، پیشنهادِ اخراج.
    #
    # و رسیدن به آن حالت کارِ سختی نبود: هیچ گاردی جلوی خالی‌شدنِ یک بخش را
    # نمی‌گیرد (`indicators.delete_indicator` فقط شاخصِ نمره‌خورده را نگه
    # می‌دارد)، و پرونده‌ای که زیر چارچوبِ تک‌بخشی باز شود همین را می‌گیرد.
    #
    # پخش‌کردن، تفسیرِ درستِ «۶۰/۴۰ بین دو بخش» وقتی یکی از دو بخش وجود ندارد:
    # نسبت‌ها بین آن‌چه هست حفظ می‌شود و سقف ۱۰۰ می‌ماند.
    sections = [
        (general_pct, rules.general_section_weight, general_max),
        (specialized_pct, rules.specialized_section_weight, specialized_max),
    ]
    present = [(pct, weight) for pct, weight, maximum in sections if maximum]
    weight_sum = sum(weight for _, weight in present)
    if not present:
        base_pct = 0.0
    elif weight_sum > 0:
        base_pct = round(sum(pct * weight for pct, weight in present) / weight_sum, 1)
    else:
        # طرح به *همهٔ* بخش‌های موجود وزنِ صفر داده. عددی که این‌جا درست باشد
        # وجود ندارد؛ میانگینِ ساده از صفرِ خشک بهتر است، چون صفر یعنی
        # «عدم تمدید» برای همه.
        base_pct = round(sum(pct for pct, _ in present) / len(present), 1)

    # امتیاز ویژه: کارِ خارج از شرح وظایف که در هیچ شاخصی جا نمی‌شود. دو مهار
    # دارد و هر دو لازم‌اند —
    #   ۱) سقفِ نسخهٔ طرح، تا یک ارزیاب نتواند فرم را با عددی دلخواه دور بزند؛
    #   ۲) سقفِ ۱۰۰، چون این ستون در همه‌جای سامانه «درصد» است: میانگین واحد،
    #      مقایسهٔ افراد و جدول آستانه‌ها همه روی بازهٔ [۰,۱۰۰] معنا دارند.
    # سقف دوم روی *امتیازِ اضافه‌شده* اعمال می‌شود نه روی حاصل جمع، تا این تساوی
    # همیشه برقرار بماند: «امتیاز فرم + امتیاز ویژه = امتیاز نهایی». اگر جمع را
    # می‌بریدیم، سند نهایی سه عددی نشان می‌داد که با هم جمع نمی‌شوند.
    # مقدار خامِ *ثبت‌شده* دست‌نخورده در خود پرونده می‌ماند؛ این‌جا فقط اثرش روی
    # نتیجه محاسبه می‌شود.
    applied = applied_bonus(bonus_points, rules, base_pct)
    final_pct = round(base_pct + applied, 1)

    return {
        "general_score_pct": general_pct,
        "specialized_score_pct": specialized_pct,
        # امتیازِ فرم، پیش از امتیاز ویژه. در سند نهایی و لاگ ممیزی می‌نشیند تا
        # بعداً بشود گفت این عدد از کجا آمده، نه فقط اینکه چند شد.
        "base_weighted_pct": base_pct,
        "bonus_points": applied,
        "final_weighted_pct": final_pct,
        "recommendation": rules.recommendation_for(final_pct),
        # نسخهٔ طرحی که این نتیجه با آن حساب شده — در لاگ ممیزی و سند نهایی
        # می‌نشیند تا بعداً بشود گفت «با کدام قواعد».
        "scheme_version": rules.version,
    }
