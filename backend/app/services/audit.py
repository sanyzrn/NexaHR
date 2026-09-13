"""ثبت رویدادهای حسابرسی — با زنجیرهٔ هش، تا لاگ «مستندات» نباشد بلکه «مدرک» باشد.

مسئله (P1-09): لاگ فقط «به‌عرف» append-only بود. هیچ‌چیز جلوی UPDATE/DELETE روی
audit_log را نمی‌گرفت، پس این لاگ فقط برای کسی که *از قبل* به دارندهٔ دسترسی
دیتابیس اعتماد دارد چیزی را ثابت می‌کرد — و طبق P0-03 آن دسترسی دست همان نقشی
است که لاگ قرار بود پاسخ‌گو نگهش دارد.

راه‌حل، دو لایه:

* هر ردیف هشِ محتوای خودش را نگه می‌دارد، به‌علاوهٔ هشِ ردیف قبلی. دست‌بردن در یک
  ردیفِ میانی، همهٔ حلقه‌های بعدی را می‌شکند؛ بازنویسیِ نامرئی یعنی بازمحاسبهٔ کل
  دنبالهٔ بعد از آن.
* تریگر دیتابیس UPDATE و DELETE را روی جدول رد می‌کند (مایگریشن e8f4b127d905).
  تریگر به‌جای REVOKE استفاده شده چون این استقرار یک نقش دیتابیس بیشتر ندارد —
  همان نقشی که مایگریشن‌ها را هم اجرا می‌کند — پس REVOKE عملاً چیزی را نمی‌بست.

آن‌چه این‌جا *نیست*: ارسال به یک sink بیرونیِ append-only. زنجیرهٔ هش دست‌کاری را
قابل‌کشف می‌کند، ولی کسی که هم دیتابیس و هم کد را در اختیار دارد می‌تواند کل زنجیره
را از نو بسازد. کشفِ قطعی به یک نسخهٔ بیرون از کنترل همین برنامه نیاز دارد — یک
تصمیم زیرساختی که هنوز گرفته نشده است.
"""
import hashlib
import json
from datetime import datetime  # noqa: TC003  (در امضای `_walk` استفاده می‌شود)

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.audit_chain_check import AuditChainCheck
from app.models.audit_log import AuditLog

# ریشهٔ زنجیره: ردیف اول قبلی ندارد، پس به یک مقدار ثابت گره می‌خورد.
GENESIS_HASH = "0" * 64

# قفل توصیه‌ای مخصوص افزودن به زنجیره. بدون آن، دو تراکنش هم‌زمان می‌توانند یک
# prev_hash را بخوانند و زنجیره را دوشاخه کنند — که دقیقاً همان چیزی است که
# راستی‌آزمایی بعداً به‌عنوان «شکستگی» گزارش می‌کند.
_CHAIN_LOCK_KEY = 774_120_559


def _canonical(
    *,
    actor_user_id: int,
    event_type: str,
    evaluation_record_id: int | None,
    old_value: dict | None,
    new_value: dict | None,
    prev_hash: str,
) -> str:
    """نمایش متعارف محتوای یک ردیف.

    sort_keys برای این است که همان دادهٔ منطقی همیشه یک رشته بدهد — وگرنه ترتیب
    کلیدهای دیکشنری، هش را عوض می‌کرد و راستی‌آزمایی تصادفی شکست می‌خورد.
    created_at عمداً در هش نیست: مقدارش را سرور در لحظهٔ INSERT می‌گذارد و پیش از
    درج در دسترس نیست.
    """
    payload = {
        "actor_user_id": actor_user_id,
        "event_type": event_type,
        "evaluation_record_id": evaluation_record_id,
        "old_value": old_value,
        "new_value": new_value,
        "prev_hash": prev_hash,
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def compute_hash(**fields) -> str:
    return hashlib.sha256(_canonical(**fields).encode("utf-8")).hexdigest()


def _last_hash(db: Session) -> str:
    last = db.scalar(select(AuditLog).order_by(AuditLog.id.desc()).limit(1))
    return last.entry_hash if last is not None else GENESIS_HASH


def log_event(
    db: Session,
    actor_user_id: int,
    event_type: str,
    evaluation_record_id: int | None = None,
    old_value: dict | None = None,
    new_value: dict | None = None,
) -> None:
    # قفل تا پایان تراکنش نگه داشته می‌شود، پس افزودن‌های هم‌زمان سریالایز می‌شوند
    # و زنجیره دوشاخه نمی‌شود.
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _CHAIN_LOCK_KEY})

    prev_hash = _last_hash(db)
    entry_hash = compute_hash(
        actor_user_id=actor_user_id,
        event_type=event_type,
        evaluation_record_id=evaluation_record_id,
        old_value=old_value,
        new_value=new_value,
        prev_hash=prev_hash,
    )
    db.add(
        AuditLog(
            evaluation_record_id=evaluation_record_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            old_value=old_value,
            new_value=new_value,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
        )
    )
    db.flush()


#: پیامِ شکستی که *فقط* از لنگر می‌آید و نه از خودِ زنجیره.
ANCHOR_MISMATCH = (
    "لنگر با خودِ لاگ نمی‌خواند: یا ردیفِ لنگر دست‌کاری شده یا ردیفی از لاگ که "
    "به آن اشاره می‌کند"
)


def latest_anchor(db: Session) -> "AuditChainCheck | None":
    """تازه‌ترین راستی‌آزماییِ *موفقِ* کامل — یعنی همان لنگر.

    ردیف‌های ناموفق لنگر نیستند و این‌جا نمی‌آیند؛ آن‌ها فقط تاریخچه‌اند و
    `latest_check` می‌خواندشان.
    """
    # `log_id IS NOT NULL` یک گاردِ دوم است، نه تکرار: لنگرِ بی‌شناسه یعنی
    # `id > NULL` در کوئریِ بررسیِ سریع، که برای *هیچ* ردیفی درست نیست — یعنی
    # بررسی بی‌صدا هیچ‌چیز را نمی‌سنجید و همیشه سبز می‌شد. ساختِ چنین لنگری از
    # همان اول جلوگیری شده (`record_full_verification` روی لاگِ خالی چیزی ثبت
    # نمی‌کند)؛ این خط برای ردیف‌هایی است که از راهِ دیگری پیدا شوند.
    return db.scalar(
        select(AuditChainCheck)
        .where(AuditChainCheck.ok.is_(True), AuditChainCheck.log_id.is_not(None))
        .order_by(AuditChainCheck.id.desc())
        .limit(1)
    )


def latest_check(db: Session) -> "AuditChainCheck | None":
    """تازه‌ترین راستی‌آزماییِ کامل، سالم یا ناسالم.

    نشانِ صفحه این را لازم دارد و نه لنگر را: اگر بررسیِ دیشب شکسته باشد،
    لنگر همان‌جای قبلی می‌ماند و بی این، رابط هیچ‌وقت خبردار نمی‌شد.
    """
    return db.scalar(select(AuditChainCheck).order_by(AuditChainCheck.id.desc()).limit(1))


def verify_chain(db: Session, limit: int | None = None, *, since_anchor: bool = False) -> dict:
    """زنجیره را بازمحاسبه و با آن‌چه ذخیره شده مقایسه می‌کند.

    خروجی: وضعیت کلی + شناسهٔ اولین ردیفِ ناسازگار (اگر باشد). عمداً اولین را
    برمی‌گرداند نه همه: از نقطهٔ شکست به بعد همهٔ حلقه‌ها می‌شکنند، پس فهرست‌کردن
    همه‌شان فقط نویز است — چیزی که باید بررسی شود همان اولی است.

    `since_anchor` — بررسیِ تعاملی
    ------------------------------
    از لنگر به بعد می‌سنجد، نه از ابتدای تاریخ. هزینه‌اش به *فعالیتِ از آخرین
    جارو تا حالا* بند است و نه به سنِ سامانه.

    پیش از استفاده، خودِ لنگر وارسی می‌شود: هشی که لنگر نگه داشته باید هنوز با
    `entry_hash`ِ همان ردیفِ لاگ یکی باشد. بی این وارسی، لنگر یک عددِ
    بی‌پشتوانه بود — کسی که به دیتابیس دست دارد `log_id` را روی سرِ زنجیره
    می‌گذاشت و «بررسی» عملاً هیچ ردیفی را نمی‌سنجید و همیشه سبز می‌شد.

    اگر لنگری نباشد (سامانهٔ تازه، یا جارویی که هنوز اجرا نشده) خودبه‌خود به
    بررسیِ کامل برمی‌گردد. «سریع ولی ناقص» هیچ‌وقت پیش‌فرضِ خاموش نیست.

    `limit` پنجرهٔ *انتهایی* است، نه ابتدایی
    ---------------------------------------
    پیش از این `order_by(id).limit(n)` بود، یعنی `n` ردیفِ *اولی که در تاریخِ
    سامانه نوشته شده*. پارامتر هیچ‌جا استفاده نمی‌شد پس چیزی خراب نبود، ولی
    اولین کسی که برای سرعت «۱۰۰۰ ردیفِ آخر را بسنج» می‌نوشت، سنجشی می‌گرفت که
    هرگز به فعالیتِ اخیر نگاه نمی‌کند — و همیشه هم سبز است.

    حالا `n` ردیفِ آخر برداشته می‌شود و از `prev_hash`ِ خودِ قدیمی‌ترین ردیفِ
    همان پنجره شروع می‌شود. یعنی *درونِ* پنجره کامل سنجیده می‌شود و مرزِ
    ابتداییِ پنجره مبنا گرفته می‌شود. `full` در خروجی می‌گوید کدام حالت بوده،
    تا «سبز» با «سبزِ کامل» اشتباه گرفته نشود: پنجرهٔ انتهایی حذفِ ردیفی
    *پیش از* پنجره را نمی‌بیند.
    """
    if since_anchor and limit is not None:
        # دو پنجرهٔ متفاوت با دو معنیِ متفاوت. پذیرفتنِ هر دو یعنی یکی بی‌صدا
        # نادیده گرفته شود، و بعد کسی سنجشی بگیرد که فکر می‌کند چیزِ دیگری را
        # سنجیده — همان جنسِ خرابی که خودِ `limit` یک بار داشت.
        raise ValueError("`since_anchor` و `limit` با هم معنا ندارند؛ یکی را انتخاب کنید")

    anchor = latest_anchor(db) if since_anchor else None
    if anchor is not None:
        stored_hash = db.scalar(select(AuditLog.entry_hash).where(AuditLog.id == anchor.log_id))
        if stored_hash != anchor.entry_hash:
            return {
                "ok": False,
                "checked": 0,
                "broken_at_id": anchor.log_id,
                "reason": ANCHOR_MISMATCH,
                "full": False,
                "anchor_log_id": anchor.log_id,
                "anchor_verified_at": anchor.verified_at,
            }
        rows = list(db.scalars(select(AuditLog).where(AuditLog.id > anchor.log_id).order_by(AuditLog.id)))
        return _walk(
            rows,
            expected_prev=anchor.entry_hash,
            full=False,
            anchor_log_id=anchor.log_id,
            anchor_verified_at=anchor.verified_at,
        )

    full = limit is None
    if full:
        rows = list(db.scalars(select(AuditLog).order_by(AuditLog.id)))
        expected_prev = GENESIS_HASH
    else:
        tail = list(db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)))
        rows = list(reversed(tail))
        # مرزِ پنجره: حلقهٔ قدیمی‌ترین ردیفِ پنجره مبناست، چون ردیفِ پیش از آن
        # خوانده نشده. اگر پنجره تصادفاً از ابتدای زنجیره شروع شود، همان
        # GENESIS است و تفاوتی نمی‌کند.
        expected_prev = rows[0].prev_hash if rows else GENESIS_HASH

    return _walk(rows, expected_prev=expected_prev, full=full)


def _walk(
    rows: list[AuditLog],
    *,
    expected_prev: str,
    full: bool,
    anchor_log_id: int | None = None,
    anchor_verified_at: "datetime | None" = None,
) -> dict:
    """پیمایشِ مشترکِ هر سه حالت — کامل، پنجرهٔ انتهایی، و از لنگر به بعد.

    یک پیاده‌سازی و نه سه‌تا: قاعدهٔ «هر ردیف هم با قبلی می‌خواند هم با محتوای
    خودش» همان قاعده است، از هر نقطه‌ای که شروع شود.
    """
    checked = 0
    for row in rows:
        checked += 1
        recomputed = compute_hash(
            actor_user_id=row.actor_user_id,
            event_type=row.event_type,
            evaluation_record_id=row.evaluation_record_id,
            old_value=row.old_value,
            new_value=row.new_value,
            prev_hash=row.prev_hash,
        )
        if row.prev_hash != expected_prev:
            return {
                "ok": False,
                "checked": checked,
                "broken_at_id": row.id,
                "reason": "حلقهٔ زنجیره با ردیف قبلی نمی‌خواند (ردیفی حذف یا جابه‌جا شده)",
                "full": full,
                "anchor_log_id": anchor_log_id,
                "anchor_verified_at": anchor_verified_at,
            }
        if recomputed != row.entry_hash:
            return {
                "ok": False,
                "checked": checked,
                "broken_at_id": row.id,
                "reason": "محتوای این ردیف با هشِ ثبت‌شده‌اش نمی‌خواند (ردیف ویرایش شده)",
                "full": full,
                "anchor_log_id": anchor_log_id,
                "anchor_verified_at": anchor_verified_at,
            }
        expected_prev = row.entry_hash

    return {
        "ok": True,
        "checked": checked,
        "broken_at_id": None,
        "reason": None,
        "full": full,
        "anchor_log_id": anchor_log_id,
        "anchor_verified_at": anchor_verified_at,
    }


def record_full_verification(db: Session) -> dict:
    """زنجیره را *کامل* می‌سنجد و نتیجه را در دفتر ثبت می‌کند.

    **تنها جایی در کلِ سامانه که لنگر جلو می‌رود** — و عمداً همین یک جا، چون
    قاعده‌اش یک خط است و آن خط باید جایی باشد که کسی از کنارش رد نشود:

        لنگر فقط پس از یک راستی‌آزماییِ کاملِ موفق جلو می‌رود.

    اگر لنگر بی آن بررسی جلو می‌رفت، خودش نقطهٔ کور می‌شد: بررسیِ تعاملی فقط از
    لنگر به بعد را می‌بیند، پس هر دست‌کاری در ردیف‌های *پیش از* آن برای همیشه
    نامرئی می‌ماند — و نشانِ صفحه هم سبز می‌ماند. یعنی یک بهینه‌سازی، تضمینِ
    اصلیِ این لاگ را بی‌صدا خراب می‌کرد.

    شکست هم ثبت می‌شود، با همان دلیل که `models/audit_chain_check.py` می‌گوید:
    بی ثبتِ شکست، رابط چیزی جز «سبزِ سریع» نمی‌دید.

    خروجی همان دیکشنریِ `verify_chain` است به‌علاوهٔ `advanced` — که می‌گوید
    این اجرا لنگر را تکان داد یا نه (زنجیرهٔ سالم ولی بی رویدادِ تازه، تکانش
    نمی‌دهد).

    commit با فراخواننده است، مثل بقیهٔ جاروها.
    """
    head = db.scalar(select(AuditLog).order_by(AuditLog.id.desc()).limit(1))
    if head is None:
        # لاگِ خالی چیزی برای سنجیدن و برای لنگر انداختن ندارد. ثبتِ یک ردیفِ
        # «سالم» با `log_id` خالی، لنگری می‌ساخت که به هیچ‌جا اشاره نمی‌کند.
        return {**verify_chain(db), "advanced": False}

    result = verify_chain(db)

    check = AuditChainCheck(
        ok=result["ok"],
        log_id=head.id,
        # هشِ لنگر فقط وقتی معنا دارد که بررسی موفق بوده باشد. در بررسیِ ناموفق
        # خالی می‌ماند تا هیچ‌وقت به‌اشتباه مبنای بررسیِ سریع نشود.
        entry_hash=head.entry_hash if result["ok"] else None,
        verified_rows=result["checked"],
        broken_at_id=result["broken_at_id"],
        reason=result["reason"],
    )
    db.add(check)
    db.flush()

    previous = db.scalar(
        select(AuditChainCheck.log_id)
        .where(AuditChainCheck.ok.is_(True), AuditChainCheck.id < check.id)
        .order_by(AuditChainCheck.id.desc())
        .limit(1)
    )
    advanced = bool(result["ok"] and (previous is None or head.id > previous))
    return {**result, "advanced": advanced}
