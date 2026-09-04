"""مسیرِ کاملِ نجات، از خروجِ یک نفر تا حرکتِ دوبارهٔ پرونده.

سؤالی که این فایل جواب می‌دهد: «اعلان رفت برای HR — بعدش چی؟» یعنی آیا
منابع انسانی *واقعاً* می‌تواند کاری بکند، یا اعلان به بن‌بست می‌رسد.
"""

from sqlalchemy import select

from app.models.enums import Capability, SeparationReason
from app.models.notification import Notification
from tests.helpers import (
    active_indicators,
    auth_header,
    full_valid_scores,
    make_access,
    make_personnel,
    make_user,
)


def _leave(client, actor, personnel):
    return client.patch(
        f"/api/personnel/{personnel.id}",
        json={"status": "inactive", "separation_reason": SeparationReason.resignation.value},
        headers=auth_header(actor),
    )


def test_full_recovery_path_after_a_supervisor_departs(client, db_session):
    """خروجِ مسئولِ واحد → پروندهٔ قفل‌شده → بازتخصیص → پرونده جلو می‌رود."""
    db = db_session
    sup_person = make_personnel(db, full_name="مسئولِ رفتنی", org_unit="واحد فروش")
    sup = make_user(db, "unit_supervisor", personnel_id=sup_person.id)
    replacement = make_user(db, "unit_supervisor")
    ceo = make_user(db, "ceo")
    hr = make_user(db, "hr", capabilities=[Capability.manage_personnel])
    subordinate = make_personnel(db, full_name="زیرمجموعه", org_unit="واحد فروش")
    make_access(db, subordinate, sup, None, ceo)
    db.commit()

    r = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": subordinate.id},
        headers=auth_header(sup),
    )
    assert r.status_code == 201, r.text
    eid = r.json()["id"]

    # ── ۱) خروج ───────────────────────────────────────────────────────────
    assert _leave(client, hr, sup_person).status_code == 200
    notices = [
        n
        for n in db.scalars(select(Notification).where(Notification.type == "seats_vacated"))
        if n.user_id == hr.id
    ]
    assert len(notices) == 1
    code = r.json()["evaluation_code"]
    assert code in notices[0].message
    # و لینک، مستقیم به همان فهرست — نه به یک صفحهٔ عمومی
    assert notices[0].link == f"/hr/queue?seat_user_id={sup.id}&tab=all", notices[0].link

    # ── ۲) پرونده حالا قفل است ────────────────────────────────────────────
    stuck = client.put(
        f"/api/evaluations/{eid}/scores",
        json={"scores": full_valid_scores(active_indicators(db))},
        headers=auth_header(sup),
    )
    assert stuck.status_code in (401, 403), (
        f"صاحبِ رفتهٔ صندلی نباید بتواند اقدام کند: {stuck.status_code} {stuck.text[:120]}"
    )
    # و جایگزینِ آیندهٔ او هم هنوز صندلی ندارد
    assert client.put(
        f"/api/evaluations/{eid}/scores",
        json={"scores": full_valid_scores(active_indicators(db))},
        headers=auth_header(replacement),
    ).status_code == 403

    # ── ۳) HR روی لینکِ اعلان می‌رود و *همان* پرونده‌ها را می‌بیند ──────────
    #
    # یک پروندهٔ بی‌ربط هم ساخته می‌شود، وگرنه این ادعا بی فیلتر هم درست
    # درمی‌آمد و چیزی را نمی‌سنجید.
    other_sup = make_user(db, "unit_supervisor")
    bystander = make_personnel(db, org_unit="واحد دیگر")
    make_access(db, bystander, other_sup, None, ceo)
    db.commit()
    other_eid = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": bystander.id},
        headers=auth_header(other_sup),
    ).json()["id"]

    found = client.get(
        f"/api/evaluations?seat_user_id={sup.id}", headers=auth_header(hr)
    )
    assert found.status_code == 200, found.text
    ids = [x["id"] for x in found.json()["items"]]
    assert ids == [eid], ids
    assert other_eid not in ids, "فیلتر باید پروندهٔ بی‌ربط را کنار بگذارد"
    # و کدِ داخلِ متن هم کار می‌کند (جست‌وجو `evaluation_code` را می‌گیرد)
    by_code = client.get(f"/api/evaluations?q={code}", headers=auth_header(hr))
    assert [x["id"] for x in by_code.json()["items"]] == [eid]

    # ── ۴) بازتخصیص ───────────────────────────────────────────────────────
    fixed = client.post(
        f"/api/evaluations/{eid}/reassign",
        json={
            "stage_field": "unit_supervisor_user_id",
            "new_user_id": replacement.id,
            "reason": "مسئول قبلی از سازمان خارج شد",
        },
        headers=auth_header(hr),
    )
    assert fixed.status_code == 200, fixed.text
    assert fixed.json()["unit_supervisor_user_id"] == replacement.id

    # ── ۵) و پرونده دوباره حرکت می‌کند ────────────────────────────────────
    assert client.put(
        f"/api/evaluations/{eid}/scores",
        json={"scores": full_valid_scores(active_indicators(db))},
        headers=auth_header(replacement),
    ).status_code in (200, 201)
    assert client.post(
        f"/api/evaluations/{eid}/submit", headers=auth_header(replacement)
    ).status_code == 200

    # دلیلِ تغییر در خودِ پرونده ثبت شده تا شش ماه بعد معلوم باشد چه شد
    comments = client.get(f"/api/evaluations/{eid}", headers=auth_header(hr)).json()["comments"]
    assert any("مسئول قبلی از سازمان خارج شد" in c["comment_text"] for c in comments), comments


def test_full_recovery_path_when_the_hr_owner_departs(client, db_session):
    """صندلیِ منابع انسانی مسیرِ نجاتِ خودش را دارد: «واگذاری»."""
    db = db_session
    leaver_person = make_personnel(db, full_name="کارشناسِ رفتنی")
    leaver = make_user(db, "hr", personnel_id=leaver_person.id)
    other_hr = make_user(db, "hr", capabilities=[Capability.manage_personnel])
    sup = make_user(db, "unit_supervisor")
    ceo = make_user(db, "ceo")
    subject = make_personnel(db)
    make_access(db, subject, sup, None, ceo)
    db.commit()

    r = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": subject.id},
        headers=auth_header(sup),
    )
    eid = r.json()["id"]
    assert client.put(
        f"/api/evaluations/{eid}/scores",
        json={"scores": full_valid_scores(active_indicators(db))},
        headers=auth_header(sup),
    ).status_code in (200, 201)
    assert client.post(f"/api/evaluations/{eid}/submit", headers=auth_header(sup)).status_code == 200
    assert client.post(
        f"/api/evaluations/{eid}/hr-claim", headers=auth_header(leaver)
    ).status_code == 200

    assert _leave(client, other_hr, leaver_person).status_code == 200

    # صندلیِ HR روی حسابِ رفته مانده، پس تأییدِ کارشناسِ دیگر رد می‌شود
    blocked = client.post(f"/api/evaluations/{eid}/hr-approve", headers=auth_header(other_hr))
    assert blocked.status_code == 403, blocked.text

    # واگذاری همان دری است که بازش می‌کند
    handover = client.post(
        f"/api/evaluations/{eid}/hr-handover",
        json={"new_hr_user_id": other_hr.id, "reason": "مسئول قبلی از سازمان خارج شد"},
        headers=auth_header(other_hr),
    )
    assert handover.status_code == 200, handover.text
    assert client.post(
        f"/api/evaluations/{eid}/hr-approve", headers=auth_header(other_hr)
    ).status_code == 200


def test_reassignment_cannot_pick_an_inactive_replacement(client, db_session):
    """جایگزینِ غیرفعال یعنی همان بن‌بست، با یک اسمِ تازه."""
    db = db_session
    sup = make_user(db, "unit_supervisor")
    dead = make_user(db, "unit_supervisor")
    dead.is_active = False
    ceo = make_user(db, "ceo")
    hr = make_user(db, "hr")
    person = make_personnel(db)
    make_access(db, person, sup, None, ceo)
    db.commit()

    eid = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": person.id},
        headers=auth_header(sup),
    ).json()["id"]

    r = client.post(
        f"/api/evaluations/{eid}/reassign",
        json={
            "stage_field": "unit_supervisor_user_id",
            "new_user_id": dead.id,
            "reason": "امتحان",
        },
        headers=auth_header(hr),
    )
    assert r.status_code == 400, r.text
    assert "غیرفعال" in r.json()["detail"]


def test_seat_filter_covers_all_four_seats(client, db_session):
    """فیلترِ صندلی هر چهار صندلی را می‌گیرد، از جمله صندلیِ برداشته‌شدهٔ HR."""
    db = db_session
    sup = make_user(db, "unit_supervisor")
    deputy = make_user(db, "deputy")
    ceo = make_user(db, "ceo")
    hr_owner = make_user(db, "hr")
    hr_admin = make_user(db, "hr")
    person = make_personnel(db)
    make_access(db, person, sup, deputy, ceo)
    db.commit()

    eid = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": person.id},
        headers=auth_header(sup),
    ).json()["id"]

    def seen_by(user_id):
        r = client.get(
            f"/api/evaluations?seat_user_id={user_id}", headers=auth_header(hr_admin)
        )
        assert r.status_code == 200, r.text
        return [x["id"] for x in r.json()["items"]]

    assert seen_by(sup.id) == [eid]
    assert seen_by(deputy.id) == [eid]
    assert seen_by(ceo.id) == [eid]
    # صندلیِ HR تا برداشته‌نشدن خالی است، پس این پرونده در فهرستِ او نیست
    assert seen_by(hr_owner.id) == []

    assert client.put(
        f"/api/evaluations/{eid}/scores",
        json={"scores": full_valid_scores(active_indicators(db))},
        headers=auth_header(sup),
    ).status_code in (200, 201)
    assert client.post(f"/api/evaluations/{eid}/submit", headers=auth_header(sup)).status_code == 200
    assert client.post(
        f"/api/evaluations/{eid}/hr-claim", headers=auth_header(hr_owner)
    ).status_code == 200

    assert seen_by(hr_owner.id) == [eid], "صندلیِ برداشته‌شده هم قفل‌شونده است"


def test_seat_filter_ignores_closed_records(client, db_session):
    """پروندهٔ بسته گذاری ندارد، پس در فهرستِ نجات جایی ندارد.

    فیلتر خودش وضعیت را محدود نمی‌کند — تبِ فهرست این کار را می‌کند — ولی
    ترکیبشان باید همان چیزی بدهد که منابع انسانی لازم دارد.
    """
    db = db_session
    sup = make_user(db, "unit_supervisor")
    ceo = make_user(db, "ceo")
    hr = make_user(db, "hr")
    person = make_personnel(db)
    make_access(db, person, sup, None, ceo)
    db.commit()

    eid = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": person.id},
        headers=auth_header(sup),
    ).json()["id"]
    assert client.put(
        f"/api/evaluations/{eid}/scores",
        json={"scores": full_valid_scores(active_indicators(db))},
        headers=auth_header(sup),
    ).status_code in (200, 201)
    assert client.post(f"/api/evaluations/{eid}/submit", headers=auth_header(sup)).status_code == 200
    assert client.post(f"/api/evaluations/{eid}/hr-approve", headers=auth_header(hr)).status_code == 200
    assert client.post(f"/api/evaluations/{eid}/ceo-finalize", headers=auth_header(ceo)).status_code == 200

    open_only = client.get(
        f"/api/evaluations?seat_user_id={sup.id}&status=draft", headers=auth_header(hr)
    )
    assert open_only.json()["items"] == []


def test_seat_filter_respects_the_visibility_scope(client, db_session):
    """فیلتر یک راهِ دور زدنِ دامنهٔ دید نیست.

    `scope_evaluations_for_role` پیش از فیلترها اعمال می‌شود، پس مسئولِ واحدی
    که این پرونده را نمی‌بیند، با دادنِ `seat_user_id` هم نمی‌بیندش.
    """
    db = db_session
    sup = make_user(db, "unit_supervisor")
    other_sup = make_user(db, "unit_supervisor")
    ceo = make_user(db, "ceo")
    person = make_personnel(db)
    make_access(db, person, sup, None, ceo)
    db.commit()

    eid = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": person.id},
        headers=auth_header(sup),
    ).json()["id"]

    r = client.get(f"/api/evaluations?seat_user_id={sup.id}", headers=auth_header(other_sup))
    assert r.status_code == 200, r.text
    assert eid not in [x["id"] for x in r.json()["items"]], r.json()
