"""کامنتِ سطح‌بالای منابع انسانی — دری که باز مانده بود (N15).

کامنتِ سطح‌بالا یادداشت نیست: با مرحلهٔ بازبینی برچسب می‌خورد و در سندِ
نهاییِ هش‌شده زیر «بررسی منابع انسانی» چاپ می‌شود. ولی `add_comment` نه
`ensure_hr_may_handle` را صدا می‌زد و نه صندلیِ HR را می‌سنجید، پس دو چیز
ممکن بود که هیچ‌جای دیگرِ سامانه ممکن نیست:

* کارشناسی که پروندهٔ *خودش* را با ۴۰۳ نمی‌توانست ببیند، در آن می‌نوشت؛
* کارشناسِ دوم روی پروندهٔ در اختیارِ کارشناسِ اول می‌نوشت.
"""
import pytest

from tests.helpers import (
    active_indicators,
    auth_header,
    full_valid_scores,
    make_access,
    make_hr_unit,
    make_personnel,
    make_user,
)


def _submit(client, db, person, sup):
    r = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": person.id},
        headers=auth_header(sup),
    )
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    r = client.put(
        f"/api/evaluations/{eid}/scores",
        json={"scores": full_valid_scores(active_indicators(db))},
        headers=auth_header(sup),
    )
    assert r.status_code in (200, 201), r.text
    r = client.post(f"/api/evaluations/{eid}/submit", headers=auth_header(sup))
    assert r.status_code == 200, r.text
    return eid, r.json()["status"]


def _comment(client, user, eid, text="یادداشتِ بررسی"):
    return client.post(
        f"/api/evaluations/{eid}/comments",
        json={"comment_text": text},
        headers=auth_header(user),
    )


@pytest.fixture
def chain(db_session):
    """یک زنجیرهٔ بی‌معاونت که پرونده‌اش به `submitted` می‌رسد."""
    db = db_session
    person = make_personnel(db, org_unit="واحد فروش")
    sup = make_user(db, "unit_supervisor")
    ceo = make_user(db, "ceo")
    make_access(db, person, sup, None, ceo)
    db.commit()
    return person, sup, ceo


def test_hr_cannot_comment_on_own_record(client, db_session, chain):
    """پروندهٔ خودِ کارشناس. پیش از این: GET → ۴۰۳ ولی POST → ۲۰۱."""
    db = db_session
    person, sup, ceo = chain
    hr = make_user(db, "hr", personnel_id=person.id)
    db.commit()

    eid, st = _submit(client, db, person, sup)
    assert st == "submitted"

    # همان ۴۰۳ که پیش از این هم بود — نقطهٔ مقایسه
    assert client.get(f"/api/evaluations/{eid}", headers=auth_header(hr)).status_code == 403
    r = _comment(client, hr, eid)
    assert r.status_code == 403, r.text
    assert "خودِ شما" in r.json()["detail"]


def test_hr_cannot_comment_on_teammate_record(client, db_session):
    """پروندهٔ هم‌تیمیِ واحدِ منابع انسانی تا وقتی باز است — سپرِ `hr_panel`."""
    db = db_session
    hr_unit = make_hr_unit(db)
    teammate = make_personnel(db, org_unit=hr_unit)
    hr = make_user(db, "hr")
    sup = make_user(db, "unit_supervisor")
    ceo = make_user(db, "ceo")
    make_access(db, teammate, sup, None, ceo)
    db.commit()

    eid, st = _submit(client, db, teammate, sup)
    # پروندهٔ واحدِ HR مرحلهٔ HR را ندارد، پس مستقیم `hr_approved` می‌شود
    assert st == "hr_approved"
    r = _comment(client, hr, eid)
    assert r.status_code == 403, r.text
    assert "منابع انسانی" in r.json()["detail"]


def test_first_hr_comment_claims_the_case(client, db_session, chain):
    """صندلیِ خالی: هر کارشناس می‌تواند، و با همان کامنت مالک می‌شود."""
    db = db_session
    person, sup, ceo = chain
    hr1 = make_user(db, "hr")
    db.commit()

    eid, _ = _submit(client, db, person, sup)
    assert client.get(f"/api/evaluations/{eid}", headers=auth_header(hr1)).json()["hr_user_id"] is None

    r = _comment(client, hr1, eid, "من بررسی می‌کنم")
    assert r.status_code == 201, r.text

    detail = client.get(f"/api/evaluations/{eid}", headers=auth_header(hr1)).json()
    assert detail["hr_user_id"] == hr1.id, "کامنت باید پرونده را claim کند، مثل تأیید"


def test_second_hr_cannot_comment_on_claimed_case(client, db_session, chain):
    """صندلیِ پرشده: فقط مالک. پیش از این هر کارشناسی ۲۰۱ می‌گرفت."""
    db = db_session
    person, sup, ceo = chain
    hr1 = make_user(db, "hr")
    hr2 = make_user(db, "hr")
    db.commit()

    eid, _ = _submit(client, db, person, sup)
    assert client.post(f"/api/evaluations/{eid}/hr-claim", headers=auth_header(hr1)).status_code == 200

    r = _comment(client, hr2, eid, "من hr دوم هستم")
    assert r.status_code == 403, r.text
    assert "کاربر دیگری" in r.json()["detail"]

    # و مالک همچنان می‌تواند
    assert _comment(client, hr1, eid).status_code == 201


def test_comment_is_not_stricter_than_approval(client, db_session, chain):
    """قاعدهٔ مرزی: هر کارشناسی که *بتواند تأیید کند* باید بتواند کامنت بگذارد.

    اگر کامنت مطالبهٔ claimِ قبلی می‌کرد، این نامتقارنی پیش می‌آمد: تأییدِ
    پروندهٔ بی‌مالک مجاز (`claimable_if_unassigned`) ولی کامنت روی همان
    پرونده ممنوع.
    """
    db = db_session
    person, sup, ceo = chain
    hr = make_user(db, "hr")
    db.commit()

    eid, _ = _submit(client, db, person, sup)
    # بی هیچ claimِ صریحی، هر دو اقدام باید ممکن باشند
    assert _comment(client, hr, eid).status_code == 201
    assert client.post(f"/api/evaluations/{eid}/hr-approve", headers=auth_header(hr)).status_code == 200


def test_deputy_seat_still_enforced(client, db_session, chain):
    """رگرسیون: بازنویسیِ گارد نباید صندلیِ معاونت را شل کرده باشد."""
    db = db_session
    person, sup, ceo = chain
    hr = make_user(db, "hr")
    other_deputy = make_user(db, "deputy")
    db.commit()

    eid, _ = _submit(client, db, person, sup)
    assert client.post(f"/api/evaluations/{eid}/hr-approve", headers=auth_header(hr)).status_code == 200
    # این زنجیره معاونت ندارد، پس هیچ معاونتی صندلیِ آن را ندارد
    r = _comment(client, other_deputy, eid)
    assert r.status_code == 403, r.text


def test_reply_path_unchanged(client, db_session, chain):
    """پاسخِ threaded عمداً بازتر است و باید همان بماند."""
    db = db_session
    person, sup, ceo = chain
    hr = make_user(db, "hr")
    db.commit()

    eid, _ = _submit(client, db, person, sup)
    parent = _comment(client, hr, eid, "نکتهٔ بررسی")
    assert parent.status_code == 201
    r = client.post(
        f"/api/evaluations/{eid}/comments",
        json={"comment_text": "پاسخِ مسئول واحد", "parent_comment_id": parent.json()["id"]},
        headers=auth_header(sup),
    )
    assert r.status_code == 201, r.text
