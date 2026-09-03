"""ابزارهای پروندهٔ ارزیابی: جست‌وجو، جزئیات، آغاز، گذارِ گردش‌کار، دیدگاه، خودارزیابی.

قاعدهٔ قرارداد با رابط:
* دامنهٔ دید ارزیابی‌ها از `scope_evaluations_for_role` می‌آید — همان تابعی
  که فهرستِ رابط استفاده می‌کند، پس دستیار هیچ پنجرهٔ دیده‌بانیِ اضافه‌ای
  باز نمی‌کند.
* هر گذار وضعیت از `workflow.apply_transition` می‌گذرد؛ گاردِ نقش و مرحله و
  «تصمیم دربارهٔ خود» همان است که دکمه‌های رابط می‌بینند.
* ثبت امتیاز عمداً ابزار ندارد: نمره‌دهی یعنی وزن و شواهد و قانونِ نسخه؛
  یک جملهٔ چت آن را نیمه‌کاره می‌سازد. دستیار پرونده را می‌خواند، پیش
  می‌برد و توضیح می‌دهد — امتیاز را فرم ثبت می‌کند.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import Capability, EvaluationStatus, UserRole
from app.models.evaluation import EvaluationRecord
from app.models.personnel import Personnel
from app.services.ai.tools.base import ToolContext, ToolOutcome, json_content, tool

_STATUS_LABELS = {
    "draft": "نمره‌دهی",
    "submitted": "بررسی منابع انسانی",
    "hr_approved": "بررسی معاونت",
    "deputy_approved": "تأیید نهایی مدیرعامل",
    "finalized": "نهایی‌شده",
    "cancelled": "لغوشده",
}


def _record_or_404(db: Session, evaluation_id: int) -> EvaluationRecord:
    record = db.get(EvaluationRecord, int(evaluation_id))
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "پروندهٔ ارزیابی پیدا نشد")
    return record


def _subject_name(db: Session, record: EvaluationRecord) -> str:
    person = db.get(Personnel, record.subject_personnel_id)
    return person.full_name if person else "?"


def _describe_record(db: Session, record: EvaluationRecord) -> dict:
    return {
        "id": record.id,
        "evaluation_code": record.evaluation_code,
        "subject_personnel_id": record.subject_personnel_id,
        "status": record.status.value,
        "status_label": _STATUS_LABELS.get(record.status.value, record.status.value),
        "final_weighted_pct": float(record.final_weighted_pct) if record.final_weighted_pct is not None else None,
        "recommendation": record.recommendation,
    }


@tool(
    name="search_evaluations",
    description=(
        "جست‌وجوی پرونده‌های ارزیابی در دامنهٔ دسترسی خودتان (بسته به نقش). می‌توانید بر وضعیت، واحد، کد پرونده یا نام "
        "فرد فیلتر کنید."
    ),
    category="ارزیابی",
    read_only=True,
    parameters={
        "type": "object",
        "properties": {
            "q": {"type": "string", "description": "بخشی از کد پرونده یا نام فرد"},
            "status": {"type": "string", "enum": [s.value for s in EvaluationStatus]},
            "subject_personnel_id": {"type": "integer"},
            "limit": {"type": "integer"},
        },
    },
)
def search_evaluations(
    ctx: ToolContext, q: str = "", status: str = "", subject_personnel_id: int | None = None, limit: int = 15
) -> ToolOutcome:
    from app.api.routers.evaluations import _apply_evaluation_filters, scope_evaluations_for_role

    db = ctx.db
    query = select(EvaluationRecord)
    query = scope_evaluations_for_role(query, ctx.user)
    status_filter = EvaluationStatus(status) if status else None
    query = _apply_evaluation_filters(
        query,
        q=q or None,
        status_filter=status_filter,
        org_unit=None,
        created_from=None,
        created_to=None,
        min_final_pct=None,
        max_final_pct=None,
        subject_personnel_id=subject_personnel_id,
    )
    records = list(
        db.scalars(query.order_by(EvaluationRecord.created_at.desc()).limit(max(1, min(int(limit or 15), 50))))
    )
    items = []
    for record in records:
        item = _describe_record(db, record)
        item["subject_name"] = _subject_name(db, record)
        items.append(item)
    return ToolOutcome(
        content=json_content({"matches": len(items), "evaluations": items}),
        ui={"kind": "evaluation_list", "items": items},
        summary=f"جست‌وجوی پرونده‌ها ({len(items)} نتیجه)",
    )


def _describe_search_evaluations(q="", status="", **_):
    bits = []
    if q:
        bits.append(f"«{q}»")
    if status:
        bits.append(f"وضعیت {status}")
    return "جست‌وجوی پرونده‌ها" + (" " + " ".join(bits) if bits else "")


search_evaluations.describe = _describe_search_evaluations


@tool(
    name="get_evaluation",
    description=(
        "نمای کامل یک پرونده: مرحلهٔ گردش‌کار، امتیاز شاخص‌ها، نتیجهٔ نهایی، دیدگاه‌ها و خودارزیابی (در حد دسترسی نقش "
        "شما)."
    ),
    category="ارزیابی",
    read_only=True,
    parameters={"type": "object", "properties": {"evaluation_id": {"type": "integer"}}, "required": ["evaluation_id"]},
)
def get_evaluation(ctx: ToolContext, evaluation_id: int) -> ToolOutcome:
    db = ctx.db
    record = _record_or_404(db, evaluation_id)
    # همان گاردِ GET تکیِ رابط: خودِ موضوع پرونده نمی‌بیند؛ زنجیره و منابع انسانی می‌بینند.
    from app.api.routers.evaluations import _ensure_can_view, _to_detail

    _ensure_can_view(record, ctx.user)
    detail = _to_detail(db, record, ctx.user)
    payload = detail.model_dump(mode="json")
    # نثرِ مدل باید خوانا بماند؛ بدنه‌های سنگین رابط را کوتاه می‌کنیم.
    payload.pop("final_snapshot", None)
    return ToolOutcome(
        content=json_content(payload),
        ui={"kind": "evaluation_card", "evaluation": _describe_record(db, record)},
        summary=f"جزئیات پروندهٔ {record.evaluation_code} ({_subject_name(db, record)})",
    )


@tool(
    name="create_evaluation",
    description=(
        "آغاز پروندهٔ ارزیابی برای یک پرسنل. فقط مسئول واحدِ همان فرد (یا معاونت، برای پرسنلِ نشانِ «مدیر») می‌تواند "
        "آغاز کند؛ پرسنل باید فعال و دارای زنجیره باشد."
    ),
    category="ارزیابی",
    risky=True,
    parameters={"type": "object", "properties": {"personnel_id": {"type": "integer"}}, "required": ["personnel_id"]},
)
def create_evaluation(ctx: ToolContext, personnel_id: int) -> ToolOutcome:
    from app.api.routers.evaluations import create_evaluation as create_endpoint
    from app.schemas.evaluation import EvaluationCreate

    record = create_endpoint(
        payload=EvaluationCreate(subject_personnel_id=int(personnel_id)),
        db=ctx.db,
        current_user=ctx.user,
    )
    return ToolOutcome(
        content=json_content({
            "created": True,
            "evaluation": _describe_record(ctx.db, record),
            "subject_name": _subject_name(ctx.db, record),
            "note": "پرونده در مرحلهٔ نمره‌دهی است؛ ثبت امتیاز از فرم نمره‌دهی انجام می‌شود.",
        }),
        summary=f"پروندهٔ ارزیابی {_subject_name(ctx.db, record)} آغاز شد ({record.evaluation_code})",
    )


#: اقدام‌های `advance_evaluation` — هر کدام با گاردِ نقشِ endpointِ خودش و
#: خودِ فراخوانی.
#:
#: چرا گاردِ نقش این‌جا تکرار می‌شود: مسیرِ دستیار *تابعِ* endpoint را صدا
#: می‌زند و نه خودِ HTTP را، پس `Depends(...)`ها اجرا نمی‌شوند. برای اقدام‌هایی
#: که گذار دارند این بی‌خطر است — `ensure_transition_allowed` همان سنجشِ
#: `may_act_at` را دارد — ولی `hr_claim` هیچ گذاری در `TRANSITIONS` ندارد و
#: تنها گاردِ نقشش همان `Depends(require_roles(hr))` بود. پس بی این جدول،
#: هر نقشی می‌توانست از راهِ دستیار پروندهٔ صفِ منابع انسانی را «تحویل بگیرد».
#:
#: کلیدها با `enum`ِ شِمای ابزار یکی‌اند و `test_ai_workflow_parity` همین
#: برابری را می‌سنجد — فهرستی که با واقعیت جدا بیفتد، همان چیزی است که
#: `return` را از مسیر دستیار شکسته نگه داشته بود (`KeyError` → ۵۰۰).


def _stage(stage_role: UserRole):
    """قرینهٔ `require_chain_stage`: مافوق می‌تواند کارِ مرحلهٔ پایین‌تر را بکند."""
    from app.services.workflow import may_act_at

    return lambda role: may_act_at(role, stage_role)


def _exact(*roles: UserRole):
    """قرینهٔ `require_roles`: نقشِ دقیق، بی سلسله‌مراتب."""
    return lambda role: role in roles


@dataclass(frozen=True)
class _Advance:
    """یک اقدام: گاردِ نقش، فراخوانیِ endpoint، و اجباری‌بودنِ دلیل."""

    may: Callable[[UserRole], bool]
    run: Callable[..., None]
    needs_reason: bool = False


def _run_submit(db, user, evaluation_id: int, reason: str) -> None:
    from app.api.routers import evaluations as ep

    ep.submit_evaluation(evaluation_id=evaluation_id, db=db, current_user=user)


def _run_hr_approve(db, user, evaluation_id: int, reason: str) -> None:
    from app.api.routers import evaluations as ep

    ep.hr_approve(evaluation_id=evaluation_id, db=db, current_user=user)


def _run_deputy_approve(db, user, evaluation_id: int, reason: str) -> None:
    from app.api.routers import evaluations as ep

    ep.deputy_approve(evaluation_id=evaluation_id, db=db, current_user=user)


def _run_ceo_finalize(db, user, evaluation_id: int, reason: str) -> None:
    from fastapi import BackgroundTasks

    from app.api.routers import evaluations as ep

    # سندِ نهایی در پس‌زمینه آرشیو می‌شود. این‌جا درخواستی در کار نیست که صف را
    # خالی کند، پس کارها بی‌درنگ همین‌جا اجرا می‌شوند — وگرنه PDF تا اولین
    # جاروی زمان‌بند ساخته نمی‌شد.
    tasks = BackgroundTasks()
    ep.ceo_finalize(
        evaluation_id=evaluation_id, background_tasks=tasks, db=db, current_user=user
    )
    for task in tasks.tasks:
        task.func(*task.args, **task.kwargs)


def _run_return(db, user, evaluation_id: int, reason: str) -> None:
    from app.api.routers import evaluations as ep
    from app.schemas.evaluation import ReturnRequest

    ep.return_evaluation(
        evaluation_id=evaluation_id,
        payload=ReturnRequest(reason=reason),
        db=db,
        current_user=user,
    )


def _run_cancel(db, user, evaluation_id: int, reason: str) -> None:
    from app.api.routers import evaluations as ep
    from app.schemas.evaluation import CancelRequest

    ep.cancel_evaluation(
        evaluation_id=evaluation_id,
        payload=CancelRequest(reason=reason),
        db=db,
        current_user=user,
    )


def _run_hr_claim(db, user, evaluation_id: int, reason: str) -> None:
    from app.api.routers import evaluations as ep

    ep.hr_claim(evaluation_id=evaluation_id, db=db, current_user=user)


_ADVANCE: dict[str, _Advance] = {
    "submit": _Advance(_stage(UserRole.unit_supervisor), _run_submit),
    "hr_approve": _Advance(_exact(UserRole.hr), _run_hr_approve),
    "deputy_approve": _Advance(_stage(UserRole.deputy), _run_deputy_approve),
    "ceo_finalize": _Advance(_stage(UserRole.ceo), _run_ceo_finalize),
    "return": _Advance(
        _exact(UserRole.hr, UserRole.deputy, UserRole.ceo), _run_return, needs_reason=True
    ),
    "cancel": _Advance(_exact(UserRole.hr), _run_cancel, needs_reason=True),
    "hr_claim": _Advance(_exact(UserRole.hr), _run_hr_claim),
}

#: همان فهرست، برای `enum`ِ شِما — تا یک‌جا نوشته شود و نه دو‌جا.
_ADVANCE_ACTIONS = tuple(_ADVANCE)


@tool(
    name="advance_evaluation",
    description=(
        "پیش‌بردن پرونده در زنجیرهٔ تأیید: submit (ارسال از نمره‌دهی)، hr_approve، deputy_approve، ceo_finalize، return "
        "(برگشت با دلیل الزامی)، cancel (لغو با دلیل، منابع انسانی)، hr_claim (تحویل‌گرفتن). مجوز هر گذار را ماشین حالت "
        "سامانه می‌سنجد."
    ),
    category="ارزیابی",
    risky=True,
    parameters={
        "type": "object",
        "properties": {
            "evaluation_id": {"type": "integer"},
            "action": {"type": "string", "enum": list(_ADVANCE_ACTIONS)},
            "reason": {"type": "string", "description": "برای return و cancel الزامی"},
        },
        "required": ["evaluation_id", "action"],
    },
)
def advance_evaluation(ctx: ToolContext, evaluation_id: int, action: str, reason: str = "") -> ToolOutcome:
    """همان مسیرِ رسمیِ رابط، نه یک نسخهٔ موازی.

    پیش از این بدنه مستقیم `apply_transition` را صدا می‌زد. ماشین حالت فقط
    *گذار* را می‌سنجد؛ هر چیزِ دیگری که یک تأیید لازم دارد در خودِ endpoint
    است، و هیچ‌کدامش این‌جا اجرا نمی‌شد:

    * `submit` بی `finalize_scoring` می‌گذشت — یعنی بی اعتبارسنجیِ شواهد، بی
      وارسیِ کاملِ شاخص‌ها، و بی محاسبهٔ نتیجه. پرونده با
      `final_weighted_pct = None` وارد صفِ منابع انسانی می‌شد و بعد سرِ گاردِ
      `ceo_finalize` گیر می‌کرد.
    * `ceo_finalize` بی `final_snapshot` و بی `verify_token` نهایی می‌کرد.
      `finalized` وضعیتِ پایانی است و جاروی بازسازیِ سند هم عمداً پرونده‌های
      بی‌اسنپ‌شات را رد می‌کند، پس آن پرونده *برای همیشه* بی‌کارنامه می‌ماند —
      بی‌آنکه در هیچ گزارشی دیده شود.
    * `ensure_hr_may_handle` در روترهاست، نه در گذار. یعنی کارمندِ منابع
      انسانی می‌توانست پروندهٔ خودش را تأیید یا لغو کند — دقیقاً همان چیزی که
      همهٔ گاردهای HTTP برایش نوشته شده‌اند.
    * `reason` گرفته می‌شد و هیچ‌جا نمی‌نشست: نه کامنت، نه رویدادِ ممیزی.
    * و دو اکشنِ فهرست‌شده (`return`، `hr_claim`) اصلاً در `TRANSITIONS`
      نیستند؛ `TRANSITIONS[action]` روی آن‌ها `KeyError` می‌داد که به ۵۰۰
      ترجمه می‌شد. `return` هم — رایج‌ترین اقدامِ اصلاحیِ کلِ گردش‌کار — از
      مسیر دستیار اصلاً کار نمی‌کرد.

    حالا هر اکشن به endpointِ خودش می‌رود؛ همان انتخابِ خودکارِ گذار بر پایهٔ
    شکلِ زنجیره، همان گاردها، همان لاگ. مثل `create_evaluation` و
    `add_evaluation_comment` در همین فایل.
    """
    db = ctx.db
    action = (action or "").strip()
    reason = (reason or "").strip()
    spec = _ADVANCE.get(action)
    if spec is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "اقدام نامعتبر است؛ یکی از این‌ها: " + "، ".join(_ADVANCE_ACTIONS),
        )
    if not spec.may(ctx.user.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "شما اجازه دسترسی به این بخش را ندارید")
    if spec.needs_reason and not reason:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "برای برگشت یا لغو، ذکر دلیل الزامی است")

    record = _record_or_404(db, evaluation_id)
    before_status = record.status.value

    spec.run(db, ctx.user, int(evaluation_id), reason)

    record = _record_or_404(db, evaluation_id)
    db.refresh(record)
    subject = _subject_name(db, record)
    return ToolOutcome(
        content=json_content(
            {
                "advanced": True,
                "action": action,
                "evaluation": _describe_record(db, record),
                "subject_name": subject,
                "previous_status": before_status,
            }
        ),
        summary=(
            f"پروندهٔ {record.evaluation_code} ({subject}) "
            f"از «{_STATUS_LABELS.get(before_status, before_status)}» "
            f"به «{_STATUS_LABELS.get(record.status.value)}» رفت"
        ),
    )


def _describe_advance(evaluation_id, action, reason="", **_):
    return f"گذار «{action}» روی پروندهٔ #{evaluation_id}" + (f" با دلیل «{reason}»" if reason else "")


advance_evaluation.describe = _describe_advance


@tool(
    name="add_evaluation_comment",
    description="ثبت دیدگاه روی پروندهٔ ارزیابی (پاسخِ رشته‌ای با parent_comment_id). "
    "فقط اعضای زنجیره و منابع انسانی، و فقط در مرحله‌ای که رابط هم اجازه می‌دهد؛ پس از تأیید کاربر ثبت می‌شود.",
    category="ارزیابی",
    risky=True,
    read_only=False,
    parameters={
        "type": "object",
        "properties": {
            "evaluation_id": {"type": "integer"},
            "comment_text": {"type": "string"},
            "parent_comment_id": {"type": "integer", "description": "برای پاسخ به یک دیدگاه"},
        },
        "required": ["evaluation_id", "comment_text"],
    },
)
def add_evaluation_comment(
    ctx: ToolContext, evaluation_id: int, comment_text: str, parent_comment_id: int | None = None
) -> ToolOutcome:
    """همان مسیرِ رسمیِ رابط، نه یک نسخهٔ موازی.

    پیش از این بدنهِ خودش stage می‌ساخت: attributionِ مرحله غلط از آب درمی‌آمد و
    شایستگیِ ثبت هم از ماتریسِ مرحله/صندلیِ رابط بازتر بود. حالا endpointِ رسمی
    صدا زده می‌شود — همان گاردِ مرحله و صندلی، همان برچسبِ stage، همان لاگ.
    اجرا هم فقط از نقطهٔ تأیید رخ می‌دهد (risky=True)."""
    from app.api.routers.evaluations import add_comment as add_comment_endpoint
    from app.schemas.evaluation import CommentCreate

    comment = add_comment_endpoint(
        evaluation_id=int(evaluation_id),
        payload=CommentCreate(
            comment_text=(comment_text or "").strip()[:4000],
            parent_comment_id=int(parent_comment_id) if parent_comment_id else None,
        ),
        db=ctx.db,
        current_user=ctx.user,
    )
    return ToolOutcome(
        content=json_content({"comment_id": comment.id, "stage": comment.stage.value}),
        summary="دیدگاه روی پرونده ثبت شد",
    )


@tool(
    name="invite_self_assessment",
    description="فرستادن دعوت‌نامهٔ خودارزیابی به یک پرسنل (منابع انسانی). پروندهٔ باز لازم دارد.",
    category="ارزیابی",
    risky=True,
    capabilities=(Capability.manage_personnel,),
    roles=(UserRole.hr,),
    parameters={"type": "object", "properties": {"personnel_id": {"type": "integer"}}, "required": ["personnel_id"]},
)
def invite_self_assessment(ctx: ToolContext, personnel_id: int) -> ToolOutcome:
    from app.services.self_assessment import invite

    db = ctx.db
    person = db.get(Personnel, int(personnel_id))
    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "پرسنلی با این شناسه پیدا نشد")
    record = invite(db, person, ctx.user.id)
    db.commit()
    return ToolOutcome(
        content=json_content({
            "invited": True,
            "personnel_id": person.id,
            "evaluation_code": record.evaluation_code if record else None,
        }),
        summary=f"دعوت خودارزیابی برای «{person.full_name}» فرستاده شد",
    )


@tool(
    name="my_open_cases",
    description=(
        "پرونده‌های بازِ روی میزِ خودتان بسته به نقش: نمره‌دهیِ در جریان، صف بررسی منابع انسانی، تأیید معاونت، تأیید "
        "نهایی."
    ),
    category="ارزیابی",
    read_only=True,
    parameters={"type": "object", "properties": {"limit": {"type": "integer"}}},
)
def my_open_cases(ctx: ToolContext, limit: int = 15) -> ToolOutcome:
    db = ctx.db
    from app.api.routers.evaluations import sa_false

    role = ctx.user.role
    if role == UserRole.unit_supervisor:
        stage_condition = (EvaluationRecord.status == EvaluationStatus.draft) & (
            EvaluationRecord.unit_supervisor_user_id == ctx.user.id
        )
    elif role == UserRole.hr:
        # صفِ مشترکِ منابع انسانی — همان چیزی که فهرست رابط هم نشان می‌دهد.
        stage_condition = EvaluationRecord.status == EvaluationStatus.submitted
    elif role == UserRole.deputy:
        # هر دو پا به صندلیِ خودِ این معاونت گره خورده است؛ پیش از این پال
        # `hr_approved` بدون فیلترِ مالک بود و پروندهٔ معاونت‌های دیگر را هم
        # نشان می‌داد (C-2 در گزارش ممیزی).
        stage_condition = (
            (EvaluationRecord.deputy_user_id == ctx.user.id)
            & (
                (EvaluationRecord.status == EvaluationStatus.hr_approved)
                | (EvaluationRecord.status == EvaluationStatus.draft)
            )
        )
    elif role == UserRole.ceo:
        stage_condition = EvaluationRecord.status == EvaluationStatus.deputy_approved
    elif role == UserRole.employee:
        # کارمند فقط نتیجهٔ نهاییِ *خودش* را می‌بیند — همان قاعدهٔ
        # scope_evaluations_for_role. پیش از این هیچ فیلترِ موضوعی نبود و
        # نمره و پیشنهادِ کل سازمان برمی‌گشت.
        if ctx.user.personnel_id is None:
            stage_condition = sa_false()
        else:
            stage_condition = (EvaluationRecord.status == EvaluationStatus.finalized) & (
                EvaluationRecord.subject_personnel_id == ctx.user.personnel_id
            )
    else:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "این نقش به پرونده‌های ارزیابی دسترسی ندارد")

    stmt = (
        select(EvaluationRecord)
        .where(stage_condition)
        .order_by(EvaluationRecord.stage_entered_at)
        .limit(max(1, min(int(limit or 15), 50)))
    )
    records = list(db.scalars(stmt))
    items = []
    for record in records:
        item = _describe_record(db, record)
        item["subject_name"] = _subject_name(db, record)
        item["stage_entered_at"] = record.stage_entered_at.isoformat() if record.stage_entered_at else None
        items.append(item)
    return ToolOutcome(
        content=json_content({"count": len(items), "cases": items}),
        ui={"kind": "evaluation_list", "items": items},
        summary=f"پرونده‌های بازِ روی میز شما ({len(items)} پرونده)",
    )


@tool(
    name="explain_evaluation_rules",
    description=(
        "خواندن طرح نمره‌دهیِ مؤثر یک پرونده (یا طرح فعال): وزن بخش‌ها، آستانه‌های برچسب، قانون شواهد، سقف امتیاز ویژه "
        "— به زبان ساده."
    ),
    category="ارزیابی",
    read_only=True,
    parameters={
        "type": "object",
        "properties": {
            "evaluation_id": {"type": "integer", "description": "پروندهٔ مقصد؛ اگر خالی باشد طرح فعال می‌آید"},
        },
    },
)
def explain_evaluation_rules(ctx: ToolContext, evaluation_id: int | None = None) -> ToolOutcome:
    db = ctx.db
    from app.models.scoring_scheme import ScoringScheme
    from app.services.scoring_scheme import active_scheme

    scheme = None
    if evaluation_id:
        record = _record_or_404(db, evaluation_id)
        if record.scoring_scheme_id is not None:
            scheme = db.get(ScoringScheme, record.scoring_scheme_id)
        else:
            scheme = active_scheme(db)
    else:
        scheme = active_scheme(db)
    if scheme is None:
        return ToolOutcome(
            content=json_content({"note": "طرحی ثبت نشده؛ قواعد پیش‌فرض قدیمی اعمال می‌شود."}), summary="قواعد نمره‌دهی"
        )
    payload = {
        "version": scheme.version,
        "name": scheme.name,
        "status": scheme.status.value,
        "general_section_weight": float(scheme.general_section_weight),
        "specialized_section_weight": float(scheme.specialized_section_weight),
        "evidence_required_scores": scheme.evidence_required_scores,
        "evidence_min_words": scheme.evidence_min_words,
        "evidence_max_words": scheme.evidence_max_words,
        "bonus_max_points": float(scheme.bonus_max_points),
        "improvement_plan_max_pct": float(scheme.improvement_plan_max_pct),
        "thresholds": scheme.thresholds,
        "indicator_weights": {str(k): float(v) for k, v in (scheme.indicator_weights or {}).items()},
    }
    return ToolOutcome(
        content=json_content(payload),
        summary=f"قواعد طرح نمره‌دهی نسخهٔ {scheme.version}",
    )
