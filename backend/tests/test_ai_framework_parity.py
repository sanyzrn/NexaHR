"""ابزارهای چارچوب هم باید از همان درِ رابط رد شوند.

سه ابزار در `ai/tools/framework.py` سرویس یا مدل را مستقیم صدا می‌زدند و
گاردهای *درونِ* endpoint را جا می‌گذاشتند. هر سه یک شکلِ خرابی داشتند: کاری که
در رابط ممکن نیست، از راه دستیار ممکن بود.

* `activate_scoring_scheme` گاردِ «فقط پیش‌نویس» را نداشت، پس یک نسخهٔ
  *بازنشسته* دوباره فعال می‌شد — برگشتِ بی‌صدای قاعدهٔ نمره‌دهیِ سازمان، و هر
  پروندهٔ تازه‌ای با آن نسخهٔ احیاشده مهر می‌خورد.
* `create_indicator` نسخهٔ چارچوب را جلو نمی‌برد (`_publish`) و
  `display_order` را صفر می‌گذاشت.
* `update_indicator` نه گاردِ «بازنویسیِ معنا» را داشت و نه `_publish` را —
  یعنی متنِ شاخصی که قبلاً نمره خورده بی هیچ ردی عوض می‌شد.
"""
import pytest
from fastapi import HTTPException

from app.models.enums import Capability, SchemeStatus
from app.models.indicator import Indicator
from app.models.scoring_scheme import ScoringScheme
from app.schemas.auth import CurrentUser
from app.services.ai.tools import base as tools_base
from tests.helpers import (
    active_indicators,
    auth_header,
    full_valid_scores,
    make_access,
    make_personnel,
    make_user,
)


def _ctx(db, user, caps) -> tools_base.ToolContext:
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
    )


def _run(db, user, tool: str, arguments: dict):
    return tools_base.execute_tool(
        _ctx(db, user, [Capability.manage_scoring]), tools_base.REGISTRY[tool], arguments
    )


@pytest.fixture()
def scoring_hr(db_session):
    hr = make_user(db_session, "hr", capabilities=[Capability.manage_scoring])
    db_session.commit()
    return hr


# ── طرح نمره‌دهی: احیای نسخهٔ بازنشسته ─────────────────────────────────────


def _draft_and_activate(client, db_session, drafter, activator) -> int:
    """یک نسخهٔ تازه می‌سازد و فعالش می‌کند، پس نسخهٔ قبلی بازنشسته می‌شود."""
    drafted = client.post(
        "/api/scoring-schemes",
        json={
            "name": "نسخهٔ آزمایشی",
            "general_section_weight": 0.6,
            "specialized_section_weight": 0.4,
            "evidence_required_scores": [1, 2, 5],
            "evidence_min_words": 5,
            "evidence_max_words": 30,
            "thresholds": [
                {"upper_exclusive": 95, "label": "نیازمند بازنگری"},
                {"upper_exclusive": 101, "label": "قابل تمدید"},
            ],
            "indicator_weights": {},
        },
        headers=auth_header(drafter),
    )
    assert drafted.status_code in (200, 201), drafted.text
    scheme_id = drafted.json()["id"]
    done = client.post(
        f"/api/scoring-schemes/{scheme_id}/activate", headers=auth_header(activator)
    )
    assert done.status_code == 200, done.text
    return scheme_id


def test_the_copilot_cannot_revive_a_retired_scheme(client, db_session, scoring_hr):
    other = make_user(db_session, "hr", capabilities=[Capability.manage_scoring])
    db_session.commit()

    retired_id = db_session.scalar(
        ScoringScheme.__table__.select().with_only_columns(ScoringScheme.id).limit(1)
    )
    # نسخهٔ فعالِ فعلی را با یک نسخهٔ تازه بازنشسته می‌کنیم.
    _draft_and_activate(client, db_session, scoring_hr, other)
    db_session.expire_all()
    retired = db_session.get(ScoringScheme, retired_id)
    assert retired.status is SchemeStatus.retired, "پیش‌شرطِ تست: نسخهٔ قبلی باید بازنشسته باشد"

    # رابط رد می‌کند…
    refused = client.post(
        f"/api/scoring-schemes/{retired_id}/activate", headers=auth_header(scoring_hr)
    )
    assert refused.status_code == 400, refused.text

    # …و دستیار هم همان را رد می‌کند.
    with pytest.raises(HTTPException) as err:
        _run(db_session, scoring_hr, "activate_scoring_scheme", {"scheme_id": retired_id})
    assert err.value.status_code == 400
    db_session.rollback()
    db_session.expire_all()
    assert db_session.get(ScoringScheme, retired_id).status is SchemeStatus.retired


def test_the_draft_guard_lives_in_the_service_not_the_router(db_session, scoring_hr):
    """گارد باید *داخل* `activate()` باشد تا فراخوانندهٔ بعدی هم از آن بگذرد."""
    from app.services.scoring_scheme import activate, active_scheme

    current = active_scheme(db_session)
    assert current is not None
    with pytest.raises(HTTPException) as err:
        activate(db_session, current, actor_user_id=scoring_hr.id)
    assert err.value.status_code == 400
    db_session.rollback()


# ── شاخص‌ها: نسخهٔ چارچوب و ترتیب فرم ─────────────────────────────────────


def _framework_version(db) -> int:
    from app.models.indicator_framework import IndicatorFramework

    return db.scalar(
        IndicatorFramework.__table__.select()
        .with_only_columns(IndicatorFramework.version)
        .order_by(IndicatorFramework.version.desc())
        .limit(1)
    )


def test_adding_an_indicator_through_the_copilot_bumps_the_framework(db_session, scoring_hr):
    before = _framework_version(db_session)
    outcome = _run(
        db_session,
        scoring_hr,
        "create_indicator",
        {"section": "general", "category": "همکاری", "description": "کارِ تیمی و پاسخ‌گویی"},
    )
    assert outcome.summary
    db_session.expire_all()
    assert _framework_version(db_session) == before + 1, (
        "بی جلو رفتنِ نسخه، شاخصِ تازه در هیچ پروندهٔ بازی دیده نمی‌شود و مهرِ "
        "`indicator_framework_id` پرونده‌های آینده به نسخه‌ای اشاره می‌کند که "
        "این شاخص را ندارد"
    )


def test_a_new_indicator_lands_at_the_end_of_its_section(db_session, scoring_hr):
    """`display_order = 0` شاخصِ تازه را سرِ فرمِ نمره‌دهی می‌نشاند."""
    from app.models.enums import IndicatorSection

    highest = max(
        i.display_order
        for i in active_indicators(db_session)
        if i.section is IndicatorSection.general
    )
    _run(
        db_session,
        scoring_hr,
        "create_indicator",
        {"section": "general", "category": "نظم", "description": "حضورِ به‌موقع"},
    )
    db_session.expire_all()
    added = max(
        (i for i in active_indicators(db_session) if i.section is IndicatorSection.general),
        key=lambda i: i.id,
    )
    assert added.display_order > highest


def test_deactivating_an_indicator_through_the_copilot_bumps_the_framework(
    db_session, scoring_hr
):
    target = active_indicators(db_session)[0]
    before = _framework_version(db_session)
    _run(db_session, scoring_hr, "update_indicator", {"indicator_id": target.id, "is_active": False})
    db_session.expire_all()
    assert _framework_version(db_session) == before + 1
    assert db_session.get(Indicator, target.id).is_active is False


def test_rewording_a_scored_indicator_needs_a_stated_reason(client, db_session, scoring_hr):
    """گاردِ P1-05 — مسیرِ دستیار از کنارش می‌گذشت."""
    sup = make_user(db_session, "unit_supervisor", capabilities=[])
    dep = make_user(db_session, "deputy", capabilities=[])
    ceo = make_user(db_session, "ceo", capabilities=[])
    personnel = make_personnel(db_session)
    make_access(db_session, personnel, sup, dep, ceo)
    db_session.commit()
    record_id = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": personnel.id},
        headers=auth_header(sup),
    ).json()["id"]
    indicators = active_indicators(db_session)
    client.put(
        f"/api/evaluations/{record_id}/scores",
        json={"scores": full_valid_scores(indicators)},
        headers=auth_header(sup),
    )
    db_session.commit()
    target = indicators[0]
    original = target.description

    with pytest.raises(HTTPException) as err:
        _run(
            db_session,
            scoring_hr,
            "update_indicator",
            {"indicator_id": target.id, "description": "متنِ کاملاً تازه و بی‌ربط"},
        )
    assert err.value.status_code == 409
    db_session.rollback()
    db_session.expire_all()
    assert db_session.get(Indicator, target.id).description == original

    # و با اعلامِ صریحِ «اصلاح نگارشی است» می‌گذرد و دلیلش ثبت می‌شود.
    _run(
        db_session,
        scoring_hr,
        "update_indicator",
        {
            "indicator_id": target.id,
            "description": "متنِ اصلاح‌شده",
            "wording_fix_reason": "غلط املایی داشت",
        },
    )
    db_session.expire_all()
    assert db_session.get(Indicator, target.id).description == "متنِ اصلاح‌شده"


def test_the_wording_reason_is_in_the_tool_schema():
    """بی این کلید، دستیار فقط ۴۰۹ می‌گرفت و راهی برای گذشتن نداشت."""
    spec = tools_base.REGISTRY["update_indicator"]
    assert "wording_fix_reason" in spec.parameters["properties"]
