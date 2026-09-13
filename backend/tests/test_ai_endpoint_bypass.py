"""ابزارهای دستیار که سرویس را مستقیم صدا می‌زدند، نه endpoint را.

همان بیماریِ همیشگیِ این ریپو در نسخهٔ دستیارش: گاردی که *یک* مسیر دارد. هر
ابزارِ این‌جا در رابط پشتِ یک قاعده بود و از راه دستیار بی آن قاعده اجرا
می‌شد — سوییچِ ماژول، `may_act_at`، یکتاییِ حسابِ پرسنل، ترتیبِ تاریخِ
قرارداد، و بسته‌بودنِ سندِ برنامهٔ بهبود.

هر تست *پس از* واگذاری نوشته شده و با برگرداندنِ همان واگذاری قرمز می‌شود؛
یعنی چیزی را می‌سنجد که واقعاً از دست رفته بود، نه صرفاً رفتارِ فعلی را.
"""
from datetime import date

import pytest
from fastapi import HTTPException

from app.models.ai import AiPendingAction
from app.models.audit_log import AuditLog
from app.models.enums import Capability, ImprovementPlanStatus
from app.models.evaluation_access import EvaluationAccess
from app.models.org_unit import OrgUnit
from app.models.personnel import Personnel
from app.models.user import User
from app.schemas.auth import CurrentUser
from app.services.ai.tools import base as tools_base
from tests.helpers import (
    make_access,
    make_personnel,
    make_user,
    set_module,
)


def _ctx(db, user, caps=(), *, allow_writes=True) -> tools_base.ToolContext:
    return tools_base.ToolContext(
        db=db,
        user=CurrentUser(
            id=user.id,
            username=user.username,
            role=user.role,
            personnel_id=user.personnel_id,
            must_change_password=False,
            display_name=user.username,
        ),
        caps=frozenset(caps),
        conversation_id=0,
        allow_writes=allow_writes,
    )


def _run(db, user, tool: str, arguments: dict, caps=()):
    return tools_base.execute_tool(_ctx(db, user, caps), tools_base.REGISTRY[tool], arguments)


# ── سوییچِ ماژول ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("tool_name", ["preview_bulk_evaluations", "run_bulk_evaluations"])
def test_bulk_tools_respect_the_periods_module_switch(db_session, tool_name):
    """ماژولِ خاموش یعنی خاموش — از هر دری که وارد شوی.

    این دو ابزار `bulk_evaluation.plan/execute` را مستقیم صدا می‌زدند، پس
    `ensure_module_enabled(db, "periods")` که در بدنهٔ endpoint است اجرا
    نمی‌شد: رابط «ساخت گروهی» را ردّ می‌کرد و دستیار پروندهٔ واقعی می‌ساخت.
    """
    hr = make_user(db_session, "hr")
    set_module(db_session, "periods", False)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        _run(db_session, hr, tool_name, {"org_unit": "واحد تست"})
    assert exc.value.status_code == 403


def test_invite_self_assessment_respects_its_module_switch(db_session):
    """همان الگو، این‌بار روی `self_assessment`."""
    hr = make_user(db_session, "hr")
    person = make_personnel(db_session)
    set_module(db_session, "self_assessment", False)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        _run(db_session, hr, "invite_self_assessment", {"personnel_id": person.id})
    assert exc.value.status_code == 403


def test_bulk_cohort_without_only_managers_includes_managers(db_session):
    """نیاوردنِ «فقط مدیران» یعنی «هر دو» — نه «فقط غیرمدیران».

    امضای ابزار `only_managers: bool = False` بود و `CohortFilter` سه‌حالته
    است (`None` = هر دو). یعنی «برای واحد فروش پرونده بساز» بی‌صدا به «فقط
    غیرمدیرانِ واحد فروش» ترجمه می‌شد و مدیرِ واحد هیچ‌وقت پرونده نمی‌گرفت.
    """
    hr = make_user(db_session, "hr")
    unit = "واحد کوهورت"
    boss = make_personnel(db_session, org_unit=unit, is_manager=True)
    make_personnel(db_session, org_unit=unit, is_manager=False)
    set_module(db_session, "periods", True)
    db_session.commit()

    outcome = _run(db_session, hr, "preview_bulk_evaluations", {"org_unit": unit})
    listed = {row["personnel_id"] for row in outcome.ui["items"]}
    assert boss.id in listed, "مدیرِ واحد از کوهورت افتاده بود"


# ── زنجیرهٔ ارزیابی ────────────────────────────────────────────────────────


def test_set_chain_refuses_a_user_who_can_never_act_at_that_seat(db_session):
    """`may_act_at` هم باید اعمال شود، نه فقط `is_active`.

    `resolve()` تنها فعال‌بودن را می‌سنجید، پس یک حسابِ «کارمند» روی صندلیِ
    معاونت می‌نشست: پرونده به آن مرحله می‌رسید و چون آن آدم هیچ‌وقت مجاز به
    اقدام نبود، برای همیشه همان‌جا می‌ماند.
    """
    hr = make_user(db_session, "hr")
    ceo = make_user(db_session, "ceo", capabilities=[])
    plain = make_user(db_session, "employee", capabilities=[])
    person = make_personnel(db_session)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        _run(
            db_session,
            hr,
            "set_evaluation_access",
            {"personnel_id": person.id, "deputy": plain.username, "ceo": ceo.username},
        )
    assert exc.value.status_code == 400
    assert "این مرحله" in exc.value.detail


def test_set_chain_refuses_a_supervisor_for_a_manager_instead_of_dropping_it(db_session):
    """قانونِ «مدیر مسئولِ واحد ندارد» باید *بگوید* چرا، نه بی‌صدا پاک کند.

    ابزار `sup_id = None` می‌گذاشت و موفق برمی‌گشت، پس HR فکر می‌کرد صندلی
    پر شده است. رابط همان‌جا ۴۰۰ می‌دهد.
    """
    hr = make_user(db_session, "hr")
    ceo = make_user(db_session, "ceo", capabilities=[])
    sup = make_user(db_session, "unit_supervisor", capabilities=[])
    boss = make_personnel(db_session, is_manager=True)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        _run(
            db_session,
            hr,
            "set_evaluation_access",
            {"personnel_id": boss.id, "unit_supervisor": sup.username, "ceo": ceo.username},
        )
    assert exc.value.status_code == 400
    assert "مدیر" in exc.value.detail


# ── حساب و پرسنل ──────────────────────────────────────────────────────────


def test_create_user_refuses_a_second_account_on_one_personnel(db_session):
    """یک پرسنل، یک حسابِ فعال — همان گاردی که در `POST /api/users` هست.

    بدون این، کارنامهٔ خودِ کارمند و قاعده‌های خودارزیابی که همگی روی
    «پرسنل ↔ حساب» بنا شده‌اند، دو مالک پیدا می‌کنند.
    """
    admin = make_user(db_session, "hr", capabilities=[Capability.manage_users])
    person = make_personnel(db_session)
    make_user(db_session, "employee", personnel_id=person.id, capabilities=[])
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        _run(
            db_session,
            admin,
            "create_user",
            {
                "username": "second-account",
                "role": "employee",
                "password": "StrongPass123",
                "personnel_id": person.id,
            },
            caps=[Capability.manage_users],
        )
    assert exc.value.status_code == 400
    from sqlalchemy import select

    still_linked = db_session.scalars(
        select(User).where(User.personnel_id == person.id, User.is_active.is_(True))
    ).all()
    assert len(still_linked) == 1


def test_update_personnel_refuses_an_end_date_before_the_start_date(db_session):
    """ترتیبِ تاریخ باید *پس از* اعمالِ تغییر سنجیده شود.

    ابزار فقط خوانابودنِ تاریخ را می‌سنجید، پس آپدیتِ تک‌فیلدی می‌توانست
    پایانِ قرارداد را پیش از شروع بگذارد و گزارشِ «قراردادهای رو به اتمام» را
    بی‌صدا بد مرتب کند.
    """
    hr = make_user(db_session, "hr")
    person = make_personnel(
        db_session, contract_start_date=date(2026, 1, 1), contract_end_date=date(2027, 1, 1)
    )
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        _run(
            db_session,
            hr,
            "update_personnel",
            {"personnel_id": person.id, "contract_end_date": "2025-01-01"},
        )
    assert exc.value.status_code == 400
    db_session.refresh(person)
    assert person.contract_end_date == date(2027, 1, 1)


def test_making_someone_a_manager_clears_the_stale_supervisor_seat(db_session):
    """«مدیر شدن» یعنی صندلیِ مسئولِ واحدش دیگر معنا ندارد.

    endpoint ردیفِ دسترسی را پاک می‌کند؛ ابزار نمی‌کرد، پس یک مسئولِ واحدِ
    قدیمی روی پروندهٔ کسی می‌ماند که دیگر زیر دستش نیست.
    """
    hr = make_user(db_session, "hr")
    sup = make_user(db_session, "unit_supervisor", capabilities=[])
    ceo = make_user(db_session, "ceo", capabilities=[])
    person = make_personnel(db_session, is_manager=False)
    make_access(db_session, person, sup, None, ceo)
    db_session.commit()

    _run(db_session, hr, "update_personnel", {"personnel_id": person.id, "is_manager": True})

    from sqlalchemy import select

    access = db_session.scalar(
        select(EvaluationAccess).where(EvaluationAccess.personnel_id == person.id)
    )
    assert access.unit_supervisor_user_id is None


def test_new_org_unit_lands_at_the_bottom_of_the_list(db_session):
    """`display_order` = بیشینه + ۱، وگرنه واحدِ تازه بالای همه می‌نشیند."""
    from sqlalchemy import select

    hr = make_user(db_session, "hr")
    db_session.add(OrgUnit(site=None, name="واحد قدیمی", is_active=True, display_order=7))
    db_session.commit()

    _run(db_session, hr, "create_org_unit", {"name": "واحد تازه"})

    unit = db_session.scalar(select(OrgUnit).where(OrgUnit.name == "واحد تازه"))
    assert unit.display_order == 8


# ── برنامهٔ بهبود ─────────────────────────────────────────────────────────


def test_goal_of_a_closed_plan_cannot_be_flipped(db_session, make_plan):
    """سندِ بسته بسته می‌ماند؛ و تغییرِ هدف رویدادِ ممیزی دارد.

    ابزار نه `_ensure_plan_open` داشت، نه `improvement_goal_updated` را
    می‌نوشت، نه قفلِ `for_update` برنامه را می‌گرفت.
    """
    from sqlalchemy import select

    hr, plan, goal = make_plan
    plan.status = ImprovementPlanStatus.completed
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        _run(db_session, hr, "update_improvement_plan_goal", {"goal_id": goal.id, "is_done": True})
    assert exc.value.status_code == 409

    plan.status = ImprovementPlanStatus.open
    db_session.commit()
    _run(db_session, hr, "update_improvement_plan_goal", {"goal_id": goal.id, "is_done": True})
    events = set(
        db_session.scalars(
            select(AuditLog.event_type).where(AuditLog.event_type == "improvement_goal_updated")
        )
    )
    assert "improvement_goal_updated" in events


def test_the_ceo_queue_only_shows_this_ceos_own_cases(db_session):
    """صفِ مدیرعامل هم مثل بقیهٔ صف‌ها به صندلیِ خودش بند است.

    شاخه‌های معاونت و مسئولِ واحد این فیلتر را داشتند و این یکی نداشت: هر
    پرونده‌ای که به `deputy_approved` رسیده بود، روی میزِ *هر* مدیرعاملی
    می‌نشست. در سازمانِ تک‌مدیرعاملی تفاوتی ندارد؛ در نصبی با دو شرکت زیرِ
    یک سامانه، هرکدام پرونده‌های دیگری را هم می‌دید.
    """
    from app.models.enums import EvaluationStatus
    from app.models.evaluation import EvaluationRecord

    mine = make_user(db_session, "ceo", capabilities=[])
    theirs = make_user(db_session, "ceo", capabilities=[])
    sup = make_user(db_session, "unit_supervisor", capabilities=[])
    subject_a = make_personnel(db_session, full_name="پروندهٔ من")
    subject_b = make_personnel(db_session, full_name="پروندهٔ آن یکی")
    db_session.add_all(
        [
            EvaluationRecord(
                evaluation_code="EV-MINE",
                subject_personnel_id=subject_a.id,
                unit_supervisor_user_id=sup.id,
                ceo_user_id=mine.id,
                status=EvaluationStatus.deputy_approved,
            ),
            EvaluationRecord(
                evaluation_code="EV-THEIRS",
                subject_personnel_id=subject_b.id,
                unit_supervisor_user_id=sup.id,
                ceo_user_id=theirs.id,
                status=EvaluationStatus.deputy_approved,
            ),
        ]
    )
    db_session.commit()

    outcome = _run(db_session, mine, "my_open_cases", {})
    codes = {row.get("evaluation_code") for row in outcome.ui["items"]}
    assert "EV-MINE" in codes
    assert "EV-THEIRS" not in codes, codes


# ── تبلیغ در برابر اجرا ───────────────────────────────────────────────────


ADVERTISED_ONLY_TO_THEIR_OWNERS = (
    "report_summary",
    "employee_vs_unit",
    "dashboard_overview",
    "expiring_contracts",
    "search_audit_log",
    "list_org_units",
)


def test_no_tool_is_advertised_to_someone_who_cannot_run_it(db_session):
    """«تبلیغِ ابزاری که اجرا نمی‌شود = پیشنهادِ مطمئن با دکمهٔ مرده».

    این جمله داک‌استرینگِ خودِ `allowed_tools` است و هفت ابزار نقضش می‌کردند:
    `guarded_inline=True` بی اعلانِ نقش، `is_allowed` را برای همه True
    می‌کند، پس ابزار در فهرستِ کارمند می‌آمد و در لحظهٔ اجرا ۴۰۳ می‌گرفت.
    """
    person = make_personnel(db_session)
    employee = make_user(db_session, "employee", personnel_id=person.id, capabilities=[])
    db_session.commit()

    advertised = {
        spec.name
        for spec in tools_base.allowed_tools(
            _ctx(db_session, employee).user, frozenset(), allow_writes=True
        )
    }
    leaked = advertised & set(ADVERTISED_ONLY_TO_THEIR_OWNERS)
    assert leaked == set(), f"به کارمند تبلیغ شد ولی اجرا نمی‌شود: {sorted(leaked)}"
    # کارمند شاخهٔ خودش را در `my_open_cases` دارد، پس تبلیغش درست است.
    assert "my_open_cases" in advertised


def test_support_is_not_offered_the_case_queue_it_cannot_read(db_session):
    """`my_open_cases` برای هر نقشی شاخه دارد جز `support` — که ۴۰۳ می‌گیرد."""
    support = make_user(db_session, "support", capabilities=[])
    db_session.commit()

    advertised = {
        spec.name
        for spec in tools_base.allowed_tools(
            _ctx(db_session, support).user, frozenset(), allow_writes=True
        )
    }
    assert "my_open_cases" not in advertised
    with pytest.raises(HTTPException) as exc:
        _run(db_session, support, "my_open_cases", {})
    assert exc.value.status_code == 403


def test_org_map_is_not_readable_by_a_plain_employee(db_session):
    """نقشهٔ سازمان با شمارِ پرسنلِ هر واحد، دادهٔ HR است.

    `list_org_units` پرچمِ `guarded_inline` داشت و بدنه‌اش هیچ گاردی نداشت؛
    `context.py` همین نقشه را عمداً از نقش‌های محدود پنهان می‌کند.
    """
    person = make_personnel(db_session)
    employee = make_user(db_session, "employee", personnel_id=person.id, capabilities=[])
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        _run(db_session, employee, "list_org_units", {})
    assert exc.value.status_code == 403


# ── لایه‌بندیِ طرحِ نمره‌دهی ────────────────────────────────────────────────

#: آنچه «کدام دکمه را فشار بده تا نمره بالا برود» را می‌گوید.
GAMEABLE_FIELDS = (
    "indicator_weights",
    "evidence_required_scores",
    "evidence_min_words",
    "evidence_max_words",
    "bonus_max_points",
    "improvement_plan_max_pct",
)

#: آنچه «با چه معیاری قضاوت می‌شوی» را می‌گوید — همان که روی کارنامه هم هست.
OPEN_FIELDS = ("thresholds", "general_section_weight", "specialized_section_weight")


def test_scheme_internals_are_hidden_from_someone_without_manage_scoring(db_session, a_scheme):
    """کارمند آستانه‌ها را می‌بیند، وزنِ شاخص‌ها را نه.

    ابزار `guarded_inline` بی‌گارد بود و کلِ طرح را به هر کاربرِ دارای دستیار
    می‌داد؛ در رابط هر پنج endpointِ خواندنِ طرح پشتِ `manage_scoring` است.
    """
    import json

    person = make_personnel(db_session)
    employee = make_user(db_session, "employee", personnel_id=person.id, capabilities=[])
    db_session.commit()

    payload = json.loads(_run(db_session, employee, "explain_evaluation_rules", {}).content)
    for field in GAMEABLE_FIELDS:
        assert field not in payload, f"«{field}» به کسی رسید که مجوزش را ندارد"
    for field in OPEN_FIELDS:
        assert field in payload, f"«{field}» باید برای همه باز بماند"


def test_scheme_internals_stay_visible_to_a_scoring_admin(db_session, a_scheme):
    """لایه‌بندی نباید قابلیت را برای صاحبش خراب کند."""
    import json

    admin = make_user(db_session, "hr", capabilities=[Capability.manage_scoring])
    db_session.commit()

    payload = json.loads(
        _run(
            db_session, admin, "explain_evaluation_rules", {}, caps=[Capability.manage_scoring]
        ).content
    )
    for field in GAMEABLE_FIELDS + OPEN_FIELDS:
        assert field in payload, f"«{field}» از دستِ صاحبِ مجوز افتاد"


@pytest.fixture()
def a_scheme(db_session):
    """طرحِ فعال، با هر شش میدانِ داخلی پر.

    ساختِ طرحِ تازه ممکن نیست — `uq_single_active_scheme` فقط یک طرحِ فعال
    می‌پذیرد و seed یکی دارد. پس همان را پر می‌کنیم؛ نتیجه واقعی‌تر هم هست.
    """
    from app.services.scoring_scheme import active_scheme

    scheme = active_scheme(db_session)
    assert scheme is not None, "طرحِ فعالی در دیتابیسِ تست نیست"
    scheme.evidence_required_scores = [4, 5]
    scheme.evidence_min_words = 20
    scheme.evidence_max_words = 200
    scheme.bonus_max_points = 5
    scheme.improvement_plan_max_pct = 10
    scheme.thresholds = {"60": "نیازمند بهبود", "75": "قابل قبول", "90": "عالی"}
    scheme.indicator_weights = {"1": 3, "2": 12}
    db_session.commit()
    return scheme


# ── ممیزیِ کنشِ ردشده ──────────────────────────────────────────────────────


def test_a_guard_refused_risky_call_is_written_to_the_audit_log(db_session):
    """قوی‌ترین نشانهٔ حمله نباید نامرئی باشد.

    گاردِ لحظهٔ *پیشنهاد* پیش از `execute_tool` بالا می‌آید، پس هیچ‌کدام از دو
    رویدادِ آن‌جا نوشته نمی‌شد و تنها ردّش یک `StepTrace` در پاسخِ همان نوبت
    بود. ابزارِ فقط-خواندنیِ ردشده لاگ می‌گرفت و پرخطر نه — برعکسِ چیزی که
    باید.
    """
    from sqlalchemy import select

    from app.services.ai.orchestrator import _execute_call

    person = make_personnel(db_session)
    employee = make_user(db_session, "employee", personnel_id=person.id, capabilities=[])
    db_session.commit()

    ctx = _ctx(db_session, employee)
    with pytest.raises(HTTPException):
        _execute_call(
            ctx,
            tools_base.REGISTRY["grant_capabilities"],
            {"user_id": employee.id, "capabilities": ["manage_users"]},
            allow_writes=True,
            steps=[],
            created_pending=[],
        )
    db_session.commit()

    refused = db_session.scalars(
        select(AuditLog).where(AuditLog.event_type == "ai_tool_refused")
    ).all()
    assert len(refused) == 1
    assert refused[0].new_value["tool"] == "grant_capabilities"


# ── مرحله‌بندیِ فایل ──────────────────────────────────────────────────────


def test_excel_from_a_non_importer_never_becomes_personnel_staging(db_session):
    """گزارشِ ردیف‌به‌ردیفِ ورودِ گروهی، یک اوراکلِ وجود است.

    «این کد پرسنلی از قبل ثبت شده است» و «این نام کاربری هست» به ازای هر
    ردیف، یعنی هر کاربرِ دارای دستیار می‌تواند وجودِ کد و نام کاربری را
    بسنجد — در حالی که در رابط حتی پیش‌نمایشِ ورود را هم نمی‌بیند.
    """
    from io import BytesIO

    from openpyxl import Workbook

    from app.models.ai import AiConversation
    from app.services.ai.tools.uploads import is_personnel_staging, stage_upload

    XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    known = make_personnel(db_session)
    person = make_personnel(db_session)
    employee = make_user(db_session, "employee", personnel_id=person.id, capabilities=[])
    convo = AiConversation(user_id=employee.id, title="t")
    db_session.add(convo)
    db_session.flush()

    # فایل باید *واقعاً* قالبِ پرسنل باشد، وگرنه تست بی‌اثر است: اکسلِ ناقص
    # به‌هرحال به شاخهٔ بازرسیِ عمومی می‌افتد و چیزی را نمی‌سنجد.
    book = Workbook()
    sheet = book.active
    sheet.append(
        [
            "کد پرسنلی", "نام و نام خانوادگی", "عنوان شغلی", "واحد سازمانی",
            "شروع قرارداد", "پایان قرارداد",
        ]
    )
    sheet.append([known.personnel_code, "کسی", "کارشناس", "واحد تست", "2025-01-01", "2026-01-01"])
    buffer = BytesIO()
    book.save(buffer)
    content = buffer.getvalue()
    db_session.commit()

    # همان بایت‌ها از دستِ HR: ثابت می‌کند فایل قالبِ درستی دارد و اوراکل واقعاً
    # در دسترس بود — پس ردِ مسیر برای کارمند، نتیجهٔ گارد است نه فایلِ خراب.
    hr = make_user(db_session, "hr")
    hr_convo = AiConversation(user_id=hr.id, title="t")
    db_session.add(hr_convo)
    db_session.flush()
    db_session.commit()
    importer_upload, summary = stage_upload(
        db_session, _ctx(db_session, hr).user, hr_convo.id, "people.xlsx", XLSX, content
    )
    assert is_personnel_staging(importer_upload)
    assert any("کد پرسنلی" in str(err) for row in summary["rows"] for err in row.get("errors", []))

    upload, _ = stage_upload(
        db_session, _ctx(db_session, employee).user, convo.id, "people.xlsx", XLSX, content
    )
    assert not is_personnel_staging(upload)


# ── نگهداریِ جدولِ کنش‌ها ──────────────────────────────────────────────────


def test_decided_actions_are_purged_after_the_retention_window(db_session):
    """کارتِ تأیید فقط ظاهرِ گفت‌وگوست؛ سندش در گزارش رویدادها می‌ماند.

    هیچ جارویی این جدول را نمی‌دید، پس با هر گفت‌وگو بزرگ‌تر می‌شد.
    """
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from app.models.ai import AiConversation
    from app.services.ai.confirmations import PENDING_RETENTION_DAYS, purge_decided_actions

    user = make_user(db_session, "hr")
    convo = AiConversation(user_id=user.id, title="t")
    db_session.add(convo)
    db_session.flush()

    now = datetime.now(UTC)
    old = now - timedelta(days=PENDING_RETENTION_DAYS + 1)

    def _row(status: str, created, expires):
        return AiPendingAction(
            conversation_id=convo.id,
            user_id=user.id,
            tool_name="create_personnel",
            arguments_json="{}",
            summary="s",
            status=status,
            created_at=created,
            expires_at=expires,
        )

    stale_decided = _row("confirmed", old, old)
    stale_abandoned = _row("pending", old, old)
    fresh_decided = _row("rejected", now, now)
    live_pending = _row("pending", old, now + timedelta(hours=1))
    db_session.add_all([stale_decided, stale_abandoned, fresh_decided, live_pending])
    db_session.commit()

    assert purge_decided_actions(db_session) == 2
    db_session.commit()

    left = set(db_session.scalars(select(AiPendingAction.id)))
    assert left == {fresh_decided.id, live_pending.id}


@pytest.fixture()
def make_plan(db_session):
    """یک برنامهٔ بهبودِ باز با یک هدف، روی پرونده‌ای نهایی‌شده."""
    from app.models.improvement_plan import ImprovementPlan, ImprovementPlanGoal

    hr = make_user(db_session, "hr")
    sup = make_user(db_session, "unit_supervisor", capabilities=[])
    ceo = make_user(db_session, "ceo", capabilities=[])
    person = make_personnel(db_session)
    make_access(db_session, person, sup, None, ceo)
    record = _finalized_record(db_session, person, sup, ceo)
    plan = ImprovementPlan(
        evaluation_record_id=record.id,
        personnel_id=person.id,
        title="برنامهٔ تست",
        review_date=date(2026, 6, 1),
        owner_user_id=hr.id,
        status=ImprovementPlanStatus.open,
        created_by_user_id=hr.id,
    )
    db_session.add(plan)
    db_session.flush()
    goal = ImprovementPlanGoal(plan_id=plan.id, description="هدفِ تست", is_done=False)
    db_session.add(goal)
    db_session.commit()
    return hr, plan, goal


def _finalized_record(db, person: Personnel, sup: User, ceo: User):
    from app.models.enums import EvaluationStatus
    from app.models.evaluation import EvaluationRecord

    record = EvaluationRecord(
        evaluation_code=f"EV-{person.id}",
        subject_personnel_id=person.id,
        unit_supervisor_user_id=sup.id,
        ceo_user_id=ceo.id,
        status=EvaluationStatus.finalized,
    )
    db.add(record)
    db.flush()
    return record
