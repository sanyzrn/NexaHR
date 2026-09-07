"""تکمیل/لغوِ برنامهٔ بهبود، یک گذارِ *پایانی* است و باید قفل بگیرد.

پیش از این `_get_plan_or_404` با `db.get` می‌خواند — بی هیچ قفلی — و بعد
`status == open` را می‌سنجید و می‌نوشت. «بخوان، بسنج، بنویس» بدونِ قفل، در
برابر دو درخواستِ هم‌زمان بی‌فایده است: هر دو `open` می‌بینند و هر دو
می‌نویسند. وضعیتِ نهایی به این بند می‌شد که کدام commit دوم شد، و **دو
رویدادِ ممیزی** برای دو گذارِ متناقض ثبت می‌شد — روی چیزی که قرار است بگوید
چه شد.

سناریوهای واقعی‌اش دور از ذهن نیست: کلیکِ دوم پس از تایم‌اوت، دو تبِ باز، یا
دو کارشناسِ HR که هم‌زمان روی همان برنامه کار می‌کنند.

همان الگوی `test_score_write_lock`: پروندهٔ واقعاً commit‌شده، دو اتصالِ جدا،
و یک نخ که قفل را نگه می‌دارد.
"""
import threading
from datetime import date

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import hash_password
from app.models.enums import EvaluationStatus, ImprovementPlanStatus
from app.models.evaluation import EvaluationRecord
from app.models.improvement_plan import ImprovementPlan
from app.models.personnel import Personnel
from app.models.user import User

LOCK_HOLD_SECONDS = 0.6


@pytest.fixture
def committed_plan():
    engine = create_engine(settings.database_url)
    make_session = sessionmaker(bind=engine)

    with make_session() as setup:
        hr = User(
            username="plan_hr", password_hash=hash_password("Plan-Lock-1"), role="hr"
        )
        ceo = User(
            username="plan_ceo", password_hash=hash_password("Plan-Lock-1"), role="ceo"
        )
        setup.add_all([hr, ceo])
        setup.flush()
        hr_id, ceo_id = hr.id, ceo.id

        personnel = Personnel(
            personnel_code="P-PLAN",
            full_name="کارمندِ برنامه",
            job_title="کارشناس",
            org_unit="واحد تست",
            contract_start_date=date(2025, 1, 1),
            contract_end_date=date(2026, 1, 1),
        )
        setup.add(personnel)
        setup.flush()

        record = EvaluationRecord(
            evaluation_code="EVL-PLAN",
            subject_personnel_id=personnel.id,
            ceo_user_id=ceo_id,
            status=EvaluationStatus.finalized,
        )
        setup.add(record)
        setup.flush()

        plan = ImprovementPlan(
            evaluation_record_id=record.id,
            personnel_id=personnel.id,
            title="برنامهٔ آزمایشی",
            review_date=date(2026, 6, 1),
            status=ImprovementPlanStatus.open,
        )
        setup.add(plan)
        setup.flush()
        ids = {
            "plan_id": plan.id,
            "record_id": record.id,
            "personnel_id": personnel.id,
            "user_ids": [hr_id, ceo_id],
        }
        setup.commit()

    yield {"make_session": make_session, **ids}

    with make_session() as teardown:
        teardown.execute(
            text("ALTER TABLE audit_log DISABLE TRIGGER trg_audit_log_append_only")
        )
        teardown.execute(
            text("DELETE FROM audit_log WHERE evaluation_record_id = :r"),
            {"r": ids["record_id"]},
        )
        teardown.execute(
            text("ALTER TABLE audit_log ENABLE TRIGGER trg_audit_log_append_only")
        )
        teardown.execute(
            text("DELETE FROM improvement_plan_goals WHERE plan_id = :p"),
            {"p": ids["plan_id"]},
        )
        teardown.execute(
            text("DELETE FROM improvement_plans WHERE id = :p"), {"p": ids["plan_id"]}
        )
        teardown.execute(
            text("DELETE FROM evaluation_records WHERE id = :r"), {"r": ids["record_id"]}
        )
        teardown.execute(
            text("DELETE FROM personnel WHERE id = :p"), {"p": ids["personnel_id"]}
        )
        teardown.execute(
            text("DELETE FROM users WHERE id = ANY(:u)"), {"u": ids["user_ids"]}
        )
        teardown.commit()
    engine.dispose()


def _hold_lock_then_complete(committed_plan, lock_held: threading.Event) -> None:
    """گذارِ هم‌زمان: قفلِ ردیف را می‌گیرد، تکمیل می‌کند، بعد commit."""
    with committed_plan["make_session"]() as session:
        plan = session.scalar(
            select(ImprovementPlan)
            .where(ImprovementPlan.id == committed_plan["plan_id"])
            .with_for_update(of=ImprovementPlan)
        )
        plan.status = ImprovementPlanStatus.completed
        lock_held.set()
        threading.Event().wait(LOCK_HOLD_SECONDS)
        session.commit()


def test_a_second_connection_cannot_take_the_plan_lock(committed_plan):
    """اثباتِ اینکه قفل بین دو اتصال مؤثر است، نه فقط در SQLِ تولیدشده."""
    lock_held = threading.Event()
    holder = threading.Thread(
        target=_hold_lock_then_complete, args=(committed_plan, lock_held)
    )
    holder.start()
    try:
        assert lock_held.wait(timeout=5), "قفل‌گیرنده به‌موقع قفل را نگرفت"
        with committed_plan["make_session"]() as reader:
            reader.execute(text("SET LOCAL lock_timeout = '100ms'"))
            from sqlalchemy.exc import OperationalError

            with pytest.raises(OperationalError):
                reader.scalar(
                    select(ImprovementPlan)
                    .where(ImprovementPlan.id == committed_plan["plan_id"])
                    .with_for_update(of=ImprovementPlan)
                )
    finally:
        holder.join(timeout=5)


def test_cancel_racing_a_complete_sees_the_new_status_and_is_refused(committed_plan):
    """مسابقهٔ واقعی: «لغو» هم‌زمان با «تکمیل».

    با قفل، لغو تا commitِ تکمیل معطل می‌ماند و بعد وضعیتِ *به‌روزشده* را
    می‌بیند و رد می‌شود. بی قفل، هر دو `open` می‌دیدند و هر دو می‌نوشتند.
    """
    from fastapi import HTTPException

    from app.api.routers.improvement_plans import cancel_plan
    from app.schemas.auth import CurrentUser

    lock_held = threading.Event()
    holder = threading.Thread(
        target=_hold_lock_then_complete, args=(committed_plan, lock_held)
    )
    holder.start()
    try:
        assert lock_held.wait(timeout=5)
        actor = CurrentUser(
            id=committed_plan["user_ids"][0], username="plan_hr", role="hr", personnel_id=None
        )
        with committed_plan["make_session"]() as session:
            with pytest.raises(HTTPException) as raised:
                cancel_plan(
                    plan_id=committed_plan["plan_id"], db=session, current_user=actor
                )
            assert raised.value.status_code == 400
            assert "باز نیست" in raised.value.detail
    finally:
        holder.join(timeout=5)

    # و وضعیتِ نهایی یکی است، نه دو گذارِ متناقض.
    with committed_plan["make_session"]() as check:
        plan = check.get(ImprovementPlan, committed_plan["plan_id"])
        assert plan.status is ImprovementPlanStatus.completed
