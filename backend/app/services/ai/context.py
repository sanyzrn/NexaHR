"""لایهٔ ۳ — آنچه مدل اجازه دارد ببیند.

مدل به دیتابیس دسترسی ندارد؛ هرچه می‌داند در همین متن به او داده می‌شود. پس
انتخابِ محتوای این متن یعنی انتخابِ اینکه *چه چیزی از سازمان بیرون می‌رود* — و
همین آن را یک تنظیمِ قابل‌مشاهدهٔ مدیر می‌کند، نه یک جزئیات پیاده‌سازی.

دو قاعده که استثنا ندارند
-------------------------
۱. **دامنه از دسترسیِ خودِ کاربر بیشتر نمی‌شود.** مسئول واحد در متنِ مدل فقط
   زیرمجموعهٔ خودش را می‌بیند، دقیقاً مثل صفحه‌ای که باز می‌کند. اگر این‌جا کوتاه
   می‌آمدیم، دستیار به یک راهِ فرعی برای دیدنِ چیزی تبدیل می‌شد که رابط اجازه‌اش
   را نمی‌دهد.
۲. **هیچ شناسه‌ای بیشتر از آنچه کار لازم دارد فرستاده نمی‌شود.** کد پرسنلی و نام
   و واحد لازم‌اند؛ تاریخ تولد و شمارهٔ تماس و نشانی نه — حتی اگر روی همان ردیف
   باشند.

شناسه اولِ هر خط می‌آید، چون کنش‌ها به همان ارجاع می‌دهند. بدون شناسه در متن،
هر شناسه‌ای که مدل تولید کند ساختگی است.
"""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import Capability, EvaluationStatus, UserRole
from app.models.evaluation import EvaluationRecord
from app.models.indicator import Indicator
from app.models.org_unit import OrgUnit
from app.models.personnel import Personnel
from app.models.user import User
from app.schemas.auth import CurrentUser

ROLE_LABELS = {
    UserRole.hr: "منابع انسانی",
    UserRole.unit_supervisor: "مسئول واحد",
    UserRole.deputy: "معاونت",
    UserRole.ceo: "مدیرعامل",
    UserRole.employee: "کارمند",
    UserRole.support: "مدیر سامانه",
}

#: نقش‌هایی که فهرست کاملِ پرسنل را در رابط هم می‌بینند — و فقط همان‌ها.
#:
#: تا امروز `deputy` و `ceo` و `support` هم این‌جا بودند، و هیچ‌کدام در رابط
#: فهرستِ کامل را نمی‌بینند: `routers/personnel.list_personnel` معاونت و
#: مدیرعامل را به ردیف‌های `EvaluationAccess`ِ خودشان محدود می‌کند و برای
#: `support` فهرستِ *تهی* برمی‌گرداند (`_ACCESS_COLUMN_BY_ROLE` ستونی برایش
#: ندارد). یعنی متنِ پرامپت پنجره‌ای باز کرده بود که رابط ندارد — دقیقاً همان
#: چیزی که قاعدهٔ ۱ بالای این فایل ممنوعش می‌کند. نامِ ثابت هم دروغ می‌گفت.
#:
#: `manage_personnel` جداگانه سنجیده می‌شود و همان‌جا می‌ماند: آن مجوز در رابط
#: هم کلِ فهرست را می‌دهد (`personnel/export.xlsx`, `POST /api/personnel`).
_ORG_WIDE_ROLES = {UserRole.hr}


def _visible_personnel_ids(db: Session, user: CurrentUser, caps: set[Capability]) -> set[int] | None:
    """`None` یعنی «همه» — و عمداً با «هیچ‌کس» یکی نیست.

    اگر برای «همه» فهرست تهی برمی‌گرداندیم، یک `IN ()` می‌شد که همه‌چیز را حذف
    می‌کند؛ همان اشتباهی که یک بار در فیلتر محل رخ داد.
    """
    if user.role in _ORG_WIDE_ROLES or Capability.manage_personnel in caps:
        return None

    from app.models.evaluation_access import EvaluationAccess

    rows = db.scalars(
        select(EvaluationAccess.personnel_id).where(
            (EvaluationAccess.unit_supervisor_user_id == user.id)
            | (EvaluationAccess.deputy_user_id == user.id)
            | (EvaluationAccess.ceo_user_id == user.id)
        )
    )
    ids = set(rows)
    if user.personnel_id:
        ids.add(user.personnel_id)
    return ids


def build(db: Session, user: CurrentUser, caps: set[Capability], limit: int) -> str:
    """متنِ زمینه. `limit == 0` یعنی هیچ ردیفی از داده نرود."""
    lines: list[str] = []

    lines.append("## کاربر فعلی")
    lines.append(
        f"نقش: {ROLE_LABELS.get(user.role, user.role.value)}"
        + (f" — اختیارات: {', '.join(sorted(c.value for c in caps))}" if caps else "")
    )

    if limit <= 0:
        lines.append("\n(مدیر سامانه فرستادن دادهٔ سازمان به دستیار را خاموش کرده است.)")
        return "\n".join(lines)

    visible = _visible_personnel_ids(db, user, caps)

    # ── واحدها ────────────────────────────────────────────────────────────
    #
    # فهرستِ کاملِ واحدها در رابط هم گاردِ خودش را دارد
    # (`personnel/org-units` → `hr` یا `manage_personnel`)، پس همان شرط.
    # کسی که دامنه‌اش محدود است نامِ واحدِ افرادِ خودش را روی ردیفِ پرسنل
    # می‌بیند و به نقشهٔ کلِ سازمان نیازی ندارد.
    if visible is None:
        units = list(db.scalars(select(OrgUnit).where(OrgUnit.is_active.is_(True)).limit(60)))
        if units:
            lines.append("\n## واحدهای سازمانی")
            lines.append("، ".join(u.full_name for u in units))

    # ── شاخص‌ها ───────────────────────────────────────────────────────────
    indicators = list(
        db.scalars(select(Indicator).where(Indicator.is_active.is_(True)).limit(limit))
    )
    if indicators:
        lines.append("\n## شاخص‌های ارزیابی (فعال)")
        for ind in indicators:
            lines.append(f"[{ind.id}] {ind.category}: {ind.description[:160]}")

    # ── پرسنل ─────────────────────────────────────────────────────────────
    stmt = select(Personnel).order_by(Personnel.id.desc()).limit(limit)
    if visible is not None:
        if not visible:
            stmt = stmt.where(Personnel.id.is_(None))  # هیچ‌کس
        else:
            stmt = stmt.where(Personnel.id.in_(visible))
    people = list(db.scalars(stmt))
    if people:
        lines.append("\n## پرسنل")
        for p in people:
            lines.append(
                f"[{p.id}] {p.full_name} — کد {p.personnel_code} — {p.job_title}"
                f" — واحد {p.org_unit} — وضعیت {p.status.value}"
                f" — پایان قرارداد {p.contract_end_date.isoformat()}"
                + (" — مدیر" if p.is_manager else "")
            )

    # ── پرونده‌های در جریان ───────────────────────────────────────────────
    #
    # دامنه از `scope_evaluations_for_role` می‌آید و نه از `visible`ِ پرسنل.
    # این دو یکی نیستند و فرقشان دیده می‌شد: `visible` فهرستِ *پرسنلِ* قابل
    # مشاهده است، ولی این بلوک ستونِ «نتیجه» دارد. با دامنهٔ پرسنل، منابع
    # انسانی نتیجهٔ نهاییِ پروندهٔ *خودش* و پروندهٔ هم‌تیمی‌هایش را در متنِ مدل
    # می‌دید — همان دو چیزی که `scope_evaluations_for_role` عمداً از پنلش
    # حذف می‌کند. حالا همان تابعِ رابط اینجا هم تصمیم می‌گیرد، پس هر قاعده‌ای
    # که به آن اضافه شود خودبه‌خود این‌جا هم اعمال می‌شود.
    from app.api.routers.evaluations import scope_evaluations_for_role

    ev_stmt = (
        select(EvaluationRecord)
        .where(EvaluationRecord.status != EvaluationStatus.cancelled)
        .order_by(EvaluationRecord.id.desc())
        .limit(limit)
    )
    try:
        ev_stmt = scope_evaluations_for_role(ev_stmt, user)
    except HTTPException:
        # نقشی که در رابط هم به پرونده‌ها دسترسی ندارد (مثل `support`): بلوک
        # حذف می‌شود، نه اینکه بی‌دامنه بماند.
        ev_stmt = None
    records = list(db.scalars(ev_stmt)) if ev_stmt is not None else []
    if records:
        names = dict(db.execute(select(Personnel.id, Personnel.full_name)).all())
        lines.append("\n## پرونده‌های ارزیابی")
        for r in records:
            pct = f" — نتیجه {float(r.final_weighted_pct):.1f}٪" if r.final_weighted_pct else ""
            lines.append(
                f"[{r.id}] {r.evaluation_code} — {names.get(r.subject_personnel_id, '?')}"
                f" — وضعیت {r.status.value}{pct}"
            )

    # ── حساب‌ها: فقط برای کسی که در رابط هم می‌بیندشان ────────────────────
    if Capability.manage_users in caps:
        accounts = list(db.scalars(select(User).order_by(User.id).limit(limit)))
        lines.append("\n## حساب‌های کاربری")
        for a in accounts:
            lines.append(
                f"[{a.id}] {a.username} — {ROLE_LABELS.get(a.role, a.role.value)}"
                f" — {'فعال' if a.is_active else 'غیرفعال'}"
            )

    # شمارشِ پایان هم به همان دامنه بند است: «کل پرسنلِ سازمان» عددی است که
    # کارمند در هیچ صفحه‌ای نمی‌بیند، و به مدل هم نباید برود.
    count_stmt = select(func.count()).select_from(Personnel)
    if visible is not None:
        count_stmt = count_stmt.where(
            Personnel.id.in_(visible) if visible else Personnel.id.is_(None)
        )
    total = db.scalar(count_stmt) or 0
    lines.append(
        f"\n(پرسنلِ در دامنهٔ دید شما: {total}. فهرست بالا حداکثر {limit} ردیف اخیر است.)"
    )
    return "\n".join(lines)
