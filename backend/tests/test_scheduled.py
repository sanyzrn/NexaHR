"""تست‌های sweep های اعلان فعالانه: انقضای قرارداد، تأخیر مراحل (SLA)، و یکتاسازی."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.clock import today_local
from app.models.enums import Capability
from app.models.evaluation import EvaluationRecord
from app.services.scheduled import run_contract_expiry_sweep, run_sla_sweep
from tests.helpers import (
    active_indicators,
    auth_header,
    full_valid_scores,
    make_access,
    make_personnel,
    make_user,
)


def _notifications_for(db, user_id, type_):
    from app.models.notification import Notification

    return list(
        db.scalars(
            select(Notification).where(
                Notification.user_id == user_id, Notification.type == type_
            )
        )
    )


def test_contract_expiry_sweep_notifies_hr_once(client, db_session):
    hr = make_user(db_session, "hr")
    make_personnel(
        db_session,
        full_name="قرارداد نزدیک",
        contract_end_date=today_local() + timedelta(days=10),
    )
    make_personnel(
        db_session,
        full_name="قرارداد دور",
        contract_end_date=today_local() + timedelta(days=200),
    )
    db_session.commit()

    created = run_contract_expiry_sweep(db_session)
    db_session.commit()
    assert created >= 1

    notes = _notifications_for(db_session, hr.id, "contract_expiry")
    assert any("قرارداد نزدیک" in n.message for n in notes)
    assert not any("قرارداد دور" in n.message for n in notes)

    # اجرای دوباره در پنجره dedup نباید اعلان تکراری بسازد
    again = run_contract_expiry_sweep(db_session)
    db_session.commit()
    assert again == 0
    assert len(_notifications_for(db_session, hr.id, "contract_expiry")) == len(notes)


def test_contract_expiry_skips_personnel_with_open_evaluation(client, db_session):
    hr = make_user(db_session, "hr")
    sup = make_user(db_session, "unit_supervisor")
    dep = make_user(db_session, "deputy")
    ceo = make_user(db_session, "ceo")
    personnel = make_personnel(
        db_session,
        full_name="در حال ارزیابی",
        contract_end_date=today_local() + timedelta(days=5),
    )
    make_access(db_session, personnel, sup, dep, ceo)
    db_session.commit()

    # ارزیابی باز ← نباید هشدار انقضا بگیرد (کار در جریان است)
    client.post(
        "/api/evaluations", json={"subject_personnel_id": personnel.id}, headers=auth_header(sup)
    )

    run_contract_expiry_sweep(db_session)
    db_session.commit()
    notes = _notifications_for(db_session, hr.id, "contract_expiry")
    assert not any("در حال ارزیابی" in n.message for n in notes)


def test_sla_sweep_reminds_current_owner_of_stalled_file(client, db_session):
    sup = make_user(db_session, "unit_supervisor")
    dep = make_user(db_session, "deputy")
    ceo = make_user(db_session, "ceo")
    personnel = make_personnel(db_session)
    make_access(db_session, personnel, sup, dep, ceo)
    db_session.commit()

    r = client.post(
        "/api/evaluations", json={"subject_personnel_id": personnel.id}, headers=auth_header(sup)
    )
    evaluation_id = r.json()["id"]

    # تازه است ← هنوز تأخیری نیست
    assert run_sla_sweep(db_session) == 0
    db_session.commit()

    # پرونده را مصنوعاً قدیمی می‌کنیم (بیش از آستانه SLA).
    # معیار stage_entered_at است نه created_at: آن‌چه اهمیت دارد «چقدر در این مرحله
    # مانده» است، نه «سن کل پرونده» (P1-02).
    record = db_session.get(EvaluationRecord, evaluation_id)
    record.stage_entered_at = datetime.now(UTC) - timedelta(days=5)
    db_session.flush()

    created = run_sla_sweep(db_session)
    db_session.commit()
    assert created == 1
    # صاحب فعلی در وضعیت draft همان مسئول واحد است
    notes = _notifications_for(db_session, sup.id, "sla_reminder")
    assert len(notes) == 1
    assert record.evaluation_code in notes[0].message

    # اجرای دوباره در پنجره dedup تکرار نمی‌کند
    assert run_sla_sweep(db_session) == 0


def test_sla_owner_follows_the_stage(client, db_session):
    hr = make_user(db_session, "hr")
    sup = make_user(db_session, "unit_supervisor")
    dep = make_user(db_session, "deputy")
    ceo = make_user(db_session, "ceo")
    personnel = make_personnel(db_session)
    make_access(db_session, personnel, sup, dep, ceo)
    db_session.commit()

    indicators = active_indicators(db_session)
    r = client.post(
        "/api/evaluations", json={"subject_personnel_id": personnel.id}, headers=auth_header(sup)
    )
    evaluation_id = r.json()["id"]
    client.put(
        f"/api/evaluations/{evaluation_id}/scores",
        json={"scores": full_valid_scores(indicators)},
        headers=auth_header(sup),
    )
    client.post(f"/api/evaluations/{evaluation_id}/submit", headers=auth_header(sup))
    client.post(f"/api/evaluations/{evaluation_id}/hr-approve", headers=auth_header(hr))

    # اکنون در وضعیت hr_approved (نوبت معاونت)؛ ساعتِ همین مرحله را عقب می‌بریم
    record = db_session.get(EvaluationRecord, evaluation_id)
    record.stage_entered_at = datetime.now(UTC) - timedelta(days=5)
    db_session.flush()

    run_sla_sweep(db_session)
    db_session.commit()
    assert len(_notifications_for(db_session, dep.id, "sla_reminder")) == 1


def test_admin_run_endpoint_requires_diagnostics_capability(client, db_session):
    hr = make_user(db_session, "hr", capabilities=[Capability.view_diagnostics])
    sup = make_user(db_session, "unit_supervisor")
    db_session.commit()

    r = client.post("/api/admin/run-scheduled-jobs", headers=auth_header(hr))
    assert r.status_code == 200
    assert "contract_expiry" in r.json() and "sla_reminder" in r.json()

    assert client.post("/api/admin/run-scheduled-jobs", headers=auth_header(sup)).status_code == 403


# ── صاحبِ مرحله وقتی زنجیره صندلیِ خالی دارد ───────────────────────────────
#
# سه شکلِ سالمِ زنجیره وجود دارد و `_current_owner_ids` فقط دو تای اولش را
# می‌شناخت: صاحبِ هر وضعیت را از خودِ *وضعیت* حساب می‌کرد، نه از شکلِ زنجیره.
# نتیجه‌اش سه خرابیِ متفاوت بود که هر سه فقط روی زنجیره‌های واقعی دیده می‌شدند.


def _stall(db, evaluation_id: int) -> EvaluationRecord:
    """ساعتِ مرحله را عقب می‌برد تا پرونده «تأخیردار» شمرده شود."""
    record = db.get(EvaluationRecord, evaluation_id)
    record.stage_entered_at = datetime.now(UTC) - timedelta(days=5)
    db.flush()
    return record


def test_sla_sweep_survives_a_chain_without_a_deputy(client, db_session):
    """پرونده‌ای که در `hr_approved` مانده و معاونتی ندارد، جاروی SLA را می‌شکست.

    مقصدِ بعدیِ چنین پرونده‌ای خودِ مدیرعامل است (`ceo_finalize` وقتی معاونتی
    در زنجیره نباشد)، ولی `_current_owner_ids` برای این وضعیت بی‌قید
    `[record.deputy_user_id]` برمی‌گرداند — یعنی `[None]`. و
    `notifications.user_id` ستونی NOT NULL است، پس اولین flush با
    NotNullViolation می‌افتاد و *کلِ* جارو — یادآوریِ همهٔ پرونده‌های دیگر هم —
    با آن می‌رفت.
    """
    hr = make_user(db_session, "hr")
    sup = make_user(db_session, "unit_supervisor")
    ceo = make_user(db_session, "ceo", capabilities=[])
    personnel = make_personnel(db_session)
    make_access(db_session, personnel, sup, None, ceo)
    db_session.commit()

    evaluation_id = client.post(
        "/api/evaluations", json={"subject_personnel_id": personnel.id}, headers=auth_header(sup)
    ).json()["id"]
    client.put(
        f"/api/evaluations/{evaluation_id}/scores",
        json={"scores": full_valid_scores(active_indicators(db_session))},
        headers=auth_header(sup),
    )
    client.post(f"/api/evaluations/{evaluation_id}/submit", headers=auth_header(sup))
    client.post(f"/api/evaluations/{evaluation_id}/hr-approve", headers=auth_header(hr))
    _stall(db_session, evaluation_id)

    assert run_sla_sweep(db_session) == 1
    db_session.commit()
    # و یادآوری به کسی رفته که واقعاً می‌تواند اقدام کند.
    assert len(_notifications_for(db_session, ceo.id, "sla_reminder")) == 1


def test_a_chain_without_a_deputy_is_not_reported_as_orphaned(client, db_session):
    """همان ریشه، خرابیِ دوم: هشدارِ دروغِ «پرونده گیر کرده».

    جاروی پرونده‌های بی‌صاحب صاحب را از همان تابع می‌پرسید، `[None]` می‌گرفت،
    هیچ کاربر فعالی برایش پیدا نمی‌کرد و به منابع انسانی خبر می‌داد که مسئولِ
    مرحله دیگر کاربر فعالی نیست — دربارهٔ پرونده‌ای کاملاً سالم، و هر بار که
    جارو اجرا می‌شد.
    """
    from app.services.scheduled import run_orphaned_case_sweep

    hr = make_user(db_session, "hr")
    sup = make_user(db_session, "unit_supervisor")
    ceo = make_user(db_session, "ceo", capabilities=[])
    personnel = make_personnel(db_session)
    make_access(db_session, personnel, sup, None, ceo)
    db_session.commit()

    evaluation_id = client.post(
        "/api/evaluations", json={"subject_personnel_id": personnel.id}, headers=auth_header(sup)
    ).json()["id"]
    client.put(
        f"/api/evaluations/{evaluation_id}/scores",
        json={"scores": full_valid_scores(active_indicators(db_session))},
        headers=auth_header(sup),
    )
    client.post(f"/api/evaluations/{evaluation_id}/submit", headers=auth_header(sup))
    client.post(f"/api/evaluations/{evaluation_id}/hr-approve", headers=auth_header(hr))

    assert run_orphaned_case_sweep(db_session) == 0
    db_session.commit()
    assert _notifications_for(db_session, hr.id, "orphaned_case") == []


def test_sla_sweep_reaches_a_ceo_who_is_the_scorer(client, db_session):
    """خرابیِ سوم: پروندهٔ «مستقیمِ مدیرعامل» در `draft` هیچ یادآوری نمی‌گرفت.

    صاحبِ وضعیت `draft` با فرضِ «مسئول واحد، وگرنه معاونت» حساب می‌شد؛ در این
    زنجیره هر دو خالی‌اند، پس تابع فهرستِ تهی می‌داد و پرونده بی‌صدا می‌ماند.
    """
    from app.models.evaluation_access import EvaluationAccess

    ceo = make_user(db_session, "ceo", capabilities=[])
    personnel = make_personnel(db_session)
    db_session.add(
        EvaluationAccess(
            personnel_id=personnel.id,
            unit_supervisor_user_id=None,
            deputy_user_id=None,
            ceo_user_id=ceo.id,
        )
    )
    db_session.commit()

    evaluation_id = client.post(
        "/api/evaluations", json={"subject_personnel_id": personnel.id}, headers=auth_header(ceo)
    ).json()["id"]
    _stall(db_session, evaluation_id)

    assert run_sla_sweep(db_session) == 1
    db_session.commit()
    assert len(_notifications_for(db_session, ceo.id, "sla_reminder")) == 1
