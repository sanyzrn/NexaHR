"""خروج از سازمان، صندلی‌های بی‌صاحب را همان لحظه به منابع انسانی می‌گوید.

تغییر نقش و غیرفعال‌کردنِ دستی با ۴۰۹ رد می‌شوند
(`evaluation.ensure_no_open_chain_seat`)، پس این تنها راهی است که یک صندلی
می‌تواند بی‌صاحب شود — و خروج را نمی‌شود رد کرد، طرف رفته.

مکملِ `run_orphaned_case_sweep` است و تکرارش نیست: آن جارو فقط پرونده‌ای را
می‌گیرد که صاحبِ *مرحلهٔ فعلی*‌اش مرده باشد، و شبانه اجرا می‌شود.
"""
import pytest
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


def _hr(db, **kw):
    return make_user(db, "hr", **kw)


def _leave(client, actor, personnel, reason=SeparationReason.resignation):
    return client.patch(
        f"/api/personnel/{personnel.id}",
        json={"status": "inactive", "separation_reason": reason.value},
        headers=auth_header(actor),
    )


def _notices(db, recipients, type_="seats_vacated"):
    """اعلان‌های این نوع، *فقط* برای حساب‌هایی که همین تست ساخته.

    دیتابیسِ تست ردیف‌های جامانده از تستِ همروندیِ `test_audit_fixes` را دارد
    (حساب‌های `af_race_*` که بیرون از rollback کامیت می‌شوند)، پس شمارشِ
    سراسریِ گیرندگان به ترتیبِ اجرا و به تاریخِ دیتابیس وابسته می‌شد — همان
    نوع سبزیِ دروغینی که یک‌بار در این پروژه گرفتار شد.
    """
    ids = {u.id for u in recipients}
    return [
        n
        for n in db.scalars(select(Notification).where(Notification.type == type_))
        if n.user_id in ids
    ]


def _open_record(client, db, subject, sup):
    r = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": subject.id},
        headers=auth_header(sup),
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def departing_supervisor(client, db_session):
    """مسئولِ واحدی که پروندهٔ بازِ زیرمجموعه‌اش رویش صندلی دارد."""
    db = db_session
    sup_person = make_personnel(db, full_name="مسئولِ رفتنی", org_unit="واحد فروش")
    sup = make_user(db, "unit_supervisor", personnel_id=sup_person.id)
    ceo = make_user(db, "ceo")
    hr = _hr(db, capabilities=[Capability.manage_personnel])
    subordinate = make_personnel(db, full_name="زیرمجموعه", org_unit="واحد فروش")
    make_access(db, subordinate, sup, None, ceo)
    db.commit()
    return sup_person, sup, subordinate, ceo, hr


def test_departure_notifies_hr_with_the_seat_list(client, db_session, departing_supervisor):
    db = db_session
    sup_person, sup, subordinate, ceo, hr = departing_supervisor
    record = _open_record(client, db, subordinate, sup)

    assert _leave(client, hr, sup_person).status_code == 200

    notices = _notices(db, [hr])
    assert len(notices) == 1, notices
    body = notices[0].message
    assert "مسئولِ رفتنی" in body
    assert record["evaluation_code"] in body, body
    assert "مسئول واحد" in body
    assert "تغییر مسئول مرحله" in body, "پیام باید راهِ رفع را بگوید"
    assert notices[0].user_id == hr.id


def test_no_notice_when_no_seats_are_left_behind(client, db_session):
    """کارمندی که در پروندهٔ کسی صندلی ندارد، اعلانِ بی‌مورد نمی‌سازد."""
    db = db_session
    person = make_personnel(db, full_name="کارمندِ ساده")
    hr = _hr(db, capabilities=[Capability.manage_personnel])
    db.commit()

    assert _leave(client, hr, person).status_code == 200
    assert _notices(db, [hr]) == []


def test_own_cancelled_record_is_not_listed(client, db_session):
    """پروندهٔ خودِ فرد همین حالا لغو شده و دیگر باز نیست."""
    db = db_session
    person = make_personnel(db, full_name="موضوعِ پرونده")
    sup = make_user(db, "unit_supervisor")
    ceo = make_user(db, "ceo")
    hr = _hr(db, capabilities=[Capability.manage_personnel])
    make_access(db, person, sup, None, ceo)
    db.commit()
    own = _open_record(client, db, person, sup)

    assert _leave(client, hr, person).status_code == 200
    # این فرد در پروندهٔ خودش صندلی نداشت (موضوع بود، نه ارزیاب)، پس اعلانی
    # نیست؛ و اگر منطق پروندهٔ لغوشده را می‌شمرد، این‌جا پیدا می‌شد.
    for notice in _notices(db, [hr]):
        assert own["evaluation_code"] not in notice.message, notice.message


def test_every_active_hr_is_told(client, db_session, departing_supervisor):
    db = db_session
    sup_person, sup, subordinate, ceo, hr = departing_supervisor
    hr2 = _hr(db)
    inactive = _hr(db)
    inactive.is_active = False
    db.commit()
    _open_record(client, db, subordinate, sup)

    assert _leave(client, hr, sup_person).status_code == 200
    recipients = {n.user_id for n in _notices(db, [hr, hr2, inactive])}
    assert recipients == {hr.id, hr2.id}, "حسابِ غیرفعال اعلان نمی‌گیرد"


def test_departing_hr_is_not_a_recipient(client, db_session):
    """اگر خودِ رفتنی کارشناسِ HR بود، اعلانِ خروجِ خودش را نمی‌گیرد."""
    db = db_session
    leaver_person = make_personnel(db, full_name="کارشناسِ رفتنی")
    leaver = _hr(db, personnel_id=leaver_person.id)
    other_hr = _hr(db, capabilities=[Capability.manage_personnel])
    sup = make_user(db, "unit_supervisor")
    ceo = make_user(db, "ceo")
    subject = make_personnel(db)
    # این کارشناس روی پروندهٔ کسی دیگر مالکِ مرحلهٔ HR است
    make_access(db, subject, sup, None, ceo)
    db.commit()
    record = _open_record(client, db, subject, sup)
    eid = record["id"]
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

    notices = _notices(db, [leaver, other_hr])
    recipients = {n.user_id for n in notices}
    assert leaver.id not in recipients, "حسابش پیش از اعلان غیرفعال شده است"
    assert other_hr.id in recipients
    # و صندلیِ منابع انسانی هم در فهرست می‌آید
    assert "منابع انسانی" in notices[0].message, notices[0].message


def test_long_lists_are_truncated_with_a_count(client, db_session):
    """مدیرِ پرزیرمجموعه: پیام باید خواندنی بماند و مابقی شمرده شوند."""
    db = db_session
    sup_person = make_personnel(db, full_name="مدیرِ پرزیرمجموعه", org_unit="واحد بزرگ")
    sup = make_user(db, "unit_supervisor", personnel_id=sup_person.id)
    ceo = make_user(db, "ceo")
    hr = _hr(db, capabilities=[Capability.manage_personnel])
    db.commit()
    for i in range(12):
        person = make_personnel(db, full_name=f"نفر {i}", org_unit="واحد بزرگ")
        make_access(db, person, sup, None, ceo)
        db.commit()
        _open_record(client, db, person, sup)

    assert _leave(client, hr, sup_person).status_code == 200
    body = _notices(db, [hr])[0].message
    assert "۱۲ پروندهٔ باز" in body or "12 پروندهٔ باز" in body, body
    assert "و ۲ مورد دیگر" in body or "و 2 مورد دیگر" in body, body


def test_one_aggregated_notice_not_one_per_record(client, db_session):
    """صد اعلان صندوقِ HR را بی‌مصرف می‌کند؛ پیگیریِ تک‌تک کارِ جاروی شبانه است."""
    db = db_session
    sup_person = make_personnel(db, full_name="مدیر", org_unit="واحد چند")
    sup = make_user(db, "unit_supervisor", personnel_id=sup_person.id)
    ceo = make_user(db, "ceo")
    hr = _hr(db, capabilities=[Capability.manage_personnel])
    db.commit()
    for _ in range(4):
        person = make_personnel(db, org_unit="واحد چند")
        make_access(db, person, sup, None, ceo)
        db.commit()
        _open_record(client, db, person, sup)

    assert _leave(client, hr, sup_person).status_code == 200
    assert len(_notices(db, [hr])) == 1, "یک اعلانِ تجمیعی، به‌ازای هر کارشناسِ HR"


def test_copilot_separation_takes_the_same_path(client, db_session, departing_supervisor):
    """ابزارِ همکار هم `_close_out_departure` را صدا می‌زند، پس اعلان می‌آید."""
    from app.api.routers.personnel import _close_out_departure
    from app.models.enums import UserRole
    from app.schemas.auth import CurrentUser

    db = db_session
    sup_person, sup, subordinate, ceo, hr = departing_supervisor
    _open_record(client, db, subordinate, sup)
    sup_person.separation_reason = SeparationReason.resignation
    db.flush()

    actor = CurrentUser(
        id=hr.id, username=hr.username, role=UserRole.hr, personnel_id=None,
        full_name=hr.username, must_change_password=False,
    )
    _close_out_departure(db, sup_person, actor)
    db.commit()

    assert len(_notices(db, [hr])) == 1


def test_dedup_key_fits_the_column(client, db_session):
    """کلیدِ dedup ستونی ۱۲۰ نویسه‌ای است و باید در آن جا شود.

    نسخهٔ اول کدهای پرونده را در کلید فهرست می‌کرد؛ مدیرِ دوازده‌زیرمجموعه‌ای
    از ستون بیرون می‌زد و `DataError` می‌داد — یعنی خودِ اقدامِ خروجِ پرسنل
    شکست می‌خورد، نه فقط اعلانش.
    """
    db = db_session
    sup_person = make_personnel(db, full_name="مدیرِ خیلی‌پرزیرمجموعه", org_unit="واحد عظیم")
    sup = make_user(db, "unit_supervisor", personnel_id=sup_person.id)
    ceo = make_user(db, "ceo")
    hr = _hr(db, capabilities=[Capability.manage_personnel])
    db.commit()
    for _ in range(25):
        person = make_personnel(db, org_unit="واحد عظیم")
        make_access(db, person, sup, None, ceo)
        db.commit()
        _open_record(client, db, person, sup)

    assert _leave(client, hr, sup_person).status_code == 200
    notice = _notices(db, [hr])[0]
    assert notice.dedup_key is not None
    assert len(notice.dedup_key) <= 120, len(notice.dedup_key)


def test_a_different_seat_set_notifies_again(client, db_session, departing_supervisor):
    """کلیدِ dedup به مجموعهٔ پرونده‌ها گره خورده، نه فقط به فرد.

    اگر فقط شناسهٔ فرد در کلید بود، پروندهٔ تازه‌ای که فردا روی همان صندلیِ
    مردهٔ باز می‌شود هیچ خبری نمی‌ساخت.
    """
    from app.services.notifications import notify_vacated_seats

    db = db_session
    sup_person, sup, subordinate, ceo, hr = departing_supervisor
    _open_record(client, db, subordinate, sup)

    assert _leave(client, hr, sup_person).status_code == 200
    first = len(_notices(db, [hr]))
    assert first == 1

    # همان مجموعه، دوباره → چیزی اضافه نمی‌شود
    notify_vacated_seats(db, user_id=sup.id, person_label=sup_person.full_name)
    db.flush()
    assert len(_notices(db, [hr])) == 1, "مجموعهٔ یکسان نباید اعلانِ تکراری بسازد"

    # پروندهٔ تازه روی همان صندلیِ مرده → مجموعه عوض شد → اعلانِ تازه
    another = make_personnel(db, org_unit="واحد فروش")
    make_access(db, another, sup, None, ceo)
    db.flush()
    from app.models.evaluation import EvaluationRecord, EvaluationStatus

    db.add(
        EvaluationRecord(
            subject_personnel_id=another.id,
            unit_supervisor_user_id=sup.id,
            ceo_user_id=ceo.id,
            status=EvaluationStatus.draft,
            evaluation_code="EVL-SEATS-NEW",
        )
    )
    db.flush()
    notify_vacated_seats(db, user_id=sup.id, person_label=sup_person.full_name)
    db.flush()
    assert len(_notices(db, [hr])) == 2, "مجموعهٔ عوض‌شده باید دوباره خبر بدهد"
