"""تغییرِ نقش و غیرفعال‌سازی، وقتی کاربر صندلیِ پروندهٔ بازی را دارد (N14).

پیش از این هیچ گاردی نبود: نقشِ مسئولِ واحد عوض می‌شد، صندلی روی ردیفِ
پرونده می‌ماند، و صاحبش دیگر از `require_chain_stage` رد نمی‌شد. پرونده
*بی‌صدا* قفل می‌شد — تنها خبررسانش جاروی شبانه بود، آن هم فردا.
"""
import pytest

from app.models.enums import UserRole
from tests.helpers import (
    active_indicators,
    auth_header,
    full_valid_scores,
    make_access,
    make_personnel,
    make_user,
)


def _open_record(client, db, person, sup):
    r = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": person.id},
        headers=auth_header(sup),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture
def seated(db_session):
    """یک مسئولِ واحد با یک پروندهٔ باز زیرِ دستش."""
    db = db_session
    person = make_personnel(db, org_unit="واحد فروش")
    sup = make_user(db, "unit_supervisor")
    ceo = make_user(db, "ceo")
    hr = make_user(db, "hr")
    make_access(db, person, sup, None, ceo)
    db.commit()
    return person, sup, ceo, hr


def test_role_change_is_blocked_while_seated(client, db_session, seated):
    person, sup, ceo, hr = seated
    _open_record(client, db_session, person, sup)

    r = client.patch(
        f"/api/users/{sup.id}", json={"role": "employee"}, headers=auth_header(hr)
    )
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert "تغییر نقش" in detail
    assert "مسئول واحد" in detail, detail
    assert "تغییر مسئول مرحله" in detail, "پیام باید راهِ رفع را بگوید"


def test_deactivation_is_blocked_while_seated(client, db_session, seated):
    person, sup, ceo, hr = seated
    _open_record(client, db_session, person, sup)

    r = client.patch(
        f"/api/users/{sup.id}", json={"is_active": False}, headers=auth_header(hr)
    )
    assert r.status_code == 409, r.text
    assert "غیرفعال" in r.json()["detail"]


def test_error_names_the_blocking_records(client, db_session, seated):
    """منابع انسانی باید بداند *کدام* پرونده‌ها را جایگزین کند."""
    person, sup, ceo, hr = seated
    eid = _open_record(client, db_session, person, sup)
    code = client.get(f"/api/evaluations/{eid}", headers=auth_header(hr)).json()["evaluation_code"]

    r = client.patch(
        f"/api/users/{sup.id}", json={"role": "employee"}, headers=auth_header(hr)
    )
    assert code in r.json()["detail"], r.json()["detail"]


def test_unrelated_edits_are_not_blocked(client, db_session, seated):
    """نامِ کامل و رمز صندلی را دست نمی‌زنند و نباید رد شوند."""
    person, sup, ceo, hr = seated
    _open_record(client, db_session, person, sup)

    r = client.patch(
        f"/api/users/{sup.id}", json={"full_name": "نامِ تازه"}, headers=auth_header(hr)
    )
    assert r.status_code == 200, r.text


def test_same_role_resubmitted_is_not_blocked(client, db_session, seated):
    """فرستادنِ همان نقشِ فعلی، بیرون‌رفتن از زنجیره نیست."""
    person, sup, ceo, hr = seated
    _open_record(client, db_session, person, sup)

    r = client.patch(
        f"/api/users/{sup.id}", json={"role": "unit_supervisor"}, headers=auth_header(hr)
    )
    assert r.status_code == 200, r.text


def test_allowed_once_the_record_is_finalized(client, db_session, seated):
    """پروندهٔ بسته گذاری ندارد، پس صندلیِ رویش کاری نمی‌کند."""
    db = db_session
    person, sup, ceo, hr = seated
    eid = _open_record(client, db, person, sup)
    assert client.put(
        f"/api/evaluations/{eid}/scores",
        json={"scores": full_valid_scores(active_indicators(db))},
        headers=auth_header(sup),
    ).status_code in (200, 201)
    assert client.post(f"/api/evaluations/{eid}/submit", headers=auth_header(sup)).status_code == 200
    assert client.post(f"/api/evaluations/{eid}/hr-approve", headers=auth_header(hr)).status_code == 200
    assert client.post(f"/api/evaluations/{eid}/ceo-finalize", headers=auth_header(ceo)).status_code == 200

    # پرسنلِ *دیگری* برای اتصال: «کارمند» پرسنل لازم دارد، و اتصال به کسی که
    # خودش ارزیابی‌اش کرده، گاردِ «ارزیابِ خودش» را می‌زند.
    own_person = make_personnel(db, org_unit="واحد فروش")
    db.commit()
    r = client.patch(
        f"/api/users/{sup.id}", json={"role": "employee", "personnel_id": own_person.id},
        headers=auth_header(hr),
    )
    assert r.status_code == 200, r.text


def test_hr_owner_of_a_claimed_case_is_also_seated(client, db_session, seated):
    """صندلیِ منابع انسانی هم قفل‌شونده است — وقتی برداشته شد، فقط مالک."""
    db = db_session
    person, sup, ceo, hr = seated
    hr_owner = make_user(db, "hr")
    hr_admin = make_user(db, "hr")
    db.commit()

    eid = _open_record(client, db, person, sup)
    assert client.put(
        f"/api/evaluations/{eid}/scores",
        json={"scores": full_valid_scores(active_indicators(db))},
        headers=auth_header(sup),
    ).status_code in (200, 201)
    assert client.post(f"/api/evaluations/{eid}/submit", headers=auth_header(sup)).status_code == 200
    assert client.post(f"/api/evaluations/{eid}/hr-claim", headers=auth_header(hr_owner)).status_code == 200

    r = client.patch(
        f"/api/users/{hr_owner.id}", json={"role": "employee"}, headers=auth_header(hr_admin)
    )
    assert r.status_code == 409, r.text
    assert "منابع انسانی" in r.json()["detail"]


def test_copilot_deactivation_uses_the_same_guard(client, db_session, seated):
    """مسیرِ همکار endpoint را صدا نمی‌زند، پس گاردش را جدا لازم دارد."""
    from fastapi import HTTPException

    from app.schemas.auth import CurrentUser
    from app.services.ai.actions import _do_deactivate_user

    db = db_session
    person, sup, ceo, hr = seated
    _open_record(client, db, person, sup)

    actor = CurrentUser(
        id=hr.id, username=hr.username, role=UserRole.hr, personnel_id=None,
        full_name=hr.username, must_change_password=False,
    )
    with pytest.raises(HTTPException) as exc:
        _do_deactivate_user(db, {"user_id": sup.id}, actor)
    assert exc.value.status_code == 409
