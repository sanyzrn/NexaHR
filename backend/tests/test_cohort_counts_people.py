"""سرکوبِ کوهورت باید *نفر* بشمارد، نه پرونده (N4).

قیدِ یکتای دیتابیس فقط پروندهٔ باز را محدود می‌کند، پس هر نفر در هر دوره یک
پروندهٔ نهایی‌شده روی هم جمع می‌کند. با شمارشِ پرونده، واحدی با *یک* نفر که
پنج دوره ارزیابی شده از آستانهٔ پنج رد می‌شد و «میانگین واحد» منتشر می‌شد —
عددی که میانگینِ گروه نبود، نمرهٔ همان یک نفر بود با برچسبِ گروهی.
"""
import pytest

from app.core.config import settings
from app.models.evaluation import EvaluationRecord, EvaluationStatus
from tests.helpers import auth_header, make_personnel, make_user

pytestmark = pytest.mark.usefixtures("no_cohort_suppression_off")


@pytest.fixture
def no_cohort_suppression_off(monkeypatch):
    """آستانه را روی ۵ می‌گذارد — همان پیش‌فرضِ محصول.

    فایل‌های تستِ دیگر آن را عمداً روی ۱ می‌گذارند تا سرکوب سرِ راهشان نباشد؛
    این فایل دقیقاً دربارهٔ خودِ سرکوب است.
    """
    monkeypatch.setattr(settings, "min_cohort_size", 5)


def _finalized(db, person, pct=67.4, code="X"):
    record = EvaluationRecord(
        subject_personnel_id=person.id,
        unit_supervisor_user_id=make_user(db, "unit_supervisor").id,
        ceo_user_id=make_user(db, "ceo").id,
        status=EvaluationStatus.finalized,
        final_weighted_pct=pct,
        general_score_pct=pct,
        specialized_score_pct=pct,
        evaluation_code=code,
    )
    db.add(record)
    db.flush()
    return record


def _unit_row(payload, unit):
    return next((u for u in payload["by_org_unit"] if u["org_unit"] == unit), None)


def test_one_person_many_periods_is_still_suppressed(client, db_session):
    """پنج پرونده، یک نفر → میانگینِ واحد نباید منتشر شود."""
    db = db_session
    unit = "واحد تک‌نفره"
    person = make_personnel(db, org_unit=unit)
    for i in range(5):
        _finalized(db, person, code=f"EVL-SOLO-{i}")
    hr = make_user(db, "hr")
    db.commit()

    r = client.get("/api/dashboard/report/summary", headers=auth_header(hr))
    assert r.status_code == 200, r.text
    row = _unit_row(r.json(), unit)
    assert row is not None, "ردیفِ واحد باید بماند — تعداد افشا نیست"
    assert row["count"] == 5, "شمارِ نمایشی همچنان «تعداد ارزیابی» است"
    assert row["avg_final_pct"] is None, "میانگینِ یک نفر نباید منتشر شود"


def test_five_people_is_published(client, db_session):
    """پنج نفر → همان آستانه، این بار واقعاً برآورده شده."""
    db = db_session
    unit = "واحد پرجمعیت"
    for i in range(5):
        _finalized(db, make_personnel(db, org_unit=unit), code=f"EVL-MANY-{i}")
    hr = make_user(db, "hr")
    db.commit()

    r = client.get("/api/dashboard/report/summary", headers=auth_header(hr))
    row = _unit_row(r.json(), unit)
    assert row is not None and row["avg_final_pct"] is not None, row


def test_four_people_eight_records_is_suppressed(client, db_session):
    """مرزِ دقیق: هشت پرونده ولی چهار نفر — پرونده رد می‌شد، نفر نه."""
    db = db_session
    unit = "واحد مرزی"
    for i in range(4):
        person = make_personnel(db, org_unit=unit)
        _finalized(db, person, code=f"EVL-EDGE-{i}a")
        _finalized(db, person, code=f"EVL-EDGE-{i}b")
    hr = make_user(db, "hr")
    db.commit()

    r = client.get("/api/dashboard/report/summary", headers=auth_header(hr))
    row = _unit_row(r.json(), unit)
    assert row["count"] == 8
    assert row["avg_final_pct"] is None, "۸ پرونده ولی ۴ نفر — هنوز زیر آستانه"


def test_hr_dashboard_uses_the_same_rule(client, db_session):
    """داشبورد و گزارش نباید دو قاعدهٔ متفاوت داشته باشند."""
    db = db_session
    unit = "واحد داشبورد"
    person = make_personnel(db, org_unit=unit)
    for i in range(6):
        _finalized(db, person, code=f"EVL-DASH-{i}")
    hr = make_user(db, "hr")
    db.commit()

    r = client.get("/api/dashboard/overview", headers=auth_header(hr))
    assert r.status_code == 200, r.text
    row = _unit_row(r.json(), unit)
    assert row is not None, r.json().get("by_org_unit")
    assert row["avg_final_pct"] is None
    assert row["avg_general_pct"] is None, "دو عددِ جزء همان چیز را لو می‌دادند"
    assert row["avg_specialized_pct"] is None


def test_period_trend_counts_people(client, db_session):
    """روندِ دوره‌ای هم از همان قاعده رد می‌شود."""
    db = db_session
    person = make_personnel(db, org_unit="واحد روند")
    for i in range(5):
        _finalized(db, person, code=f"EVL-TREND-{i}")
    hr = make_user(db, "hr")
    db.commit()

    r = client.get("/api/dashboard/period-trend", headers=auth_header(hr))
    assert r.status_code == 200, r.text
    no_period = [p for p in r.json() if p["name"] == "بدون دوره"]
    assert no_period, r.json()
    assert no_period[0]["avg_final_pct"] is None
