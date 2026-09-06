"""حذفِ دورهٔ ارزیابی — فقط وقتی هیچ پرونده‌ای به آن وصل نیست.

دوره در لحظهٔ ساختِ هر پرونده به آن می‌چسبد و نامش روی گزارش‌ها و کارنامه‌ها
می‌نشیند. تا پیش از این، دوره‌ای که با تایپِ اشتباه ساخته شده بود هیچ راهِ
برداشتنی نداشت.
"""
from datetime import date

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.enums import PeriodStatus
from app.models.evaluation_period import EvaluationPeriod
from tests.helpers import auth_header, make_access, make_personnel, make_user


def _period(db, name="دورهٔ آزمون", status=PeriodStatus.open):
    period = EvaluationPeriod(
        name=name, starts_on=date(2026, 1, 1), ends_on=date(2026, 12, 31), status=status
    )
    db.add(period)
    db.commit()
    return period


def test_an_empty_period_can_be_removed(client, db_session):
    hr = make_user(db_session, "hr", capabilities=[])
    period = _period(db_session, status=PeriodStatus.closed)

    removed = client.delete(f"/api/periods/{period.id}", headers=auth_header(hr))
    assert removed.status_code == 204, removed.text
    assert db_session.get(EvaluationPeriod, period.id) is None


def test_the_removal_is_written_to_the_audit_log(client, db_session):
    """«چه دوره‌ای حذف شد» پرسشی است که بعداً پرسیده می‌شود."""
    hr = make_user(db_session, "hr", capabilities=[])
    period = _period(db_session, name="دورهٔ اشتباه", status=PeriodStatus.closed)
    period_id = period.id

    assert client.delete(f"/api/periods/{period_id}", headers=auth_header(hr)).status_code == 204

    entry = db_session.scalars(
        select(AuditLog).where(AuditLog.event_type == "period_deleted").order_by(AuditLog.id.desc())
    ).first()
    assert entry is not None
    assert entry.old_value["id"] == period_id
    assert entry.old_value["name"] == "دورهٔ اشتباه"
    assert entry.old_value["starts_on"] == "2026-01-01"


def test_a_period_with_records_is_refused(client, db_session):
    """دوره‌ای که پرونده دارد بخشی از سابقهٔ آن پرونده‌هاست."""
    hr = make_user(db_session, "hr", capabilities=[])
    sup = make_user(db_session, "unit_supervisor")
    ceo = make_user(db_session, "ceo", capabilities=[])
    person = make_personnel(db_session, full_name="کارمند")
    make_access(db_session, person, sup, None, ceo)
    period = _period(db_session)

    created = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": person.id},
        headers=auth_header(sup),
    )
    assert created.status_code == 201, created.text

    refused = client.delete(f"/api/periods/{period.id}", headers=auth_header(hr))
    assert refused.status_code == 409, refused.text
    # پیام باید بگوید *چند* پرونده مانع است و راهِ درست چیست.
    assert "۱" in refused.json()["detail"] or "1" in refused.json()["detail"]
    assert "بستن" in refused.json()["detail"]
    assert db_session.get(EvaluationPeriod, period.id) is not None


def test_a_missing_period_is_404(client, db_session):
    hr = make_user(db_session, "hr", capabilities=[])
    db_session.commit()
    assert client.delete("/api/periods/999999", headers=auth_header(hr)).status_code == 404


def test_only_hr_may_remove_a_period(client, db_session):
    ceo = make_user(db_session, "ceo")
    period = _period(db_session, status=PeriodStatus.closed)
    refused = client.delete(f"/api/periods/{period.id}", headers=auth_header(ceo))
    assert refused.status_code == 403, refused.text
    assert db_session.get(EvaluationPeriod, period.id) is not None
