"""بن‌بستِ پروندهٔ بازِ واحدِ منابع انسانی، و راهِ خروجش.

سناریو: علی کارشناسِ HR است و حسین (مدیرِ HR) مسئولِ مستقیمش. پروندهٔ علی باز
است. حسین از سازمان خارج می‌شود.

پیش از این رفع، *هیچ‌کس* نمی‌توانست کاری بکند:

    دیدنِ پرونده ۴۰۳ · بازتخصیص ۴۰۳ · لغو ۴۰۳ · تمدیدِ مهلت ۴۰۳
    صاحبِ رفتهٔ صندلی ۴۰۱ · پروندهٔ تازه برای علی ۴۰۰ (قیدِ یکتا)

یعنی علی برای همیشه غیرقابل‌ارزیابی می‌شد. سپر (`hr_panel_is_shielded`) درست
است و باید بماند — ولی پیامش از قبل می‌گفت «رسیدگی به آن با معاونت و مدیرعامل
است» و هیچ‌کدام از آن سه endpoint آن دو نقش را راه نمی‌داد.
"""

from sqlalchemy import select

from app.models.enums import Capability, SeparationReason
from app.models.evaluation import EvaluationRecord
from app.models.notification import Notification
from tests.helpers import auth_header, make_access, make_hr_unit, make_personnel, make_user


def _case(client, db):
    """پروندهٔ بازِ علی (کارشناسِ HR)، با حسین روی صندلیِ مسئولِ واحد."""
    hr_unit = make_hr_unit(db)
    ali_person = make_personnel(db, full_name="علی قاسمی", org_unit=hr_unit)
    hossein_person = make_personnel(
        db, full_name="حسین قاسمی", org_unit=hr_unit, is_manager=True
    )
    ali = make_user(db, "hr", personnel_id=ali_person.id)
    hossein = make_user(db, "unit_supervisor", personnel_id=hossein_person.id)
    other_hr = make_user(db, "hr", capabilities=[Capability.manage_personnel])
    replacement = make_user(db, "unit_supervisor")
    deputy = make_user(db, "deputy")
    ceo = make_user(db, "ceo", capabilities=[])
    make_access(db, ali_person, hossein, deputy, ceo)
    db.commit()

    created = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": ali_person.id},
        headers=auth_header(hossein),
    )
    assert created.status_code == 201, created.text
    record_id = created.json()["id"]
    assert db.get(EvaluationRecord, record_id).hr_review_skipped is True

    # حسین از سازمان خارج می‌شود — صندلیِ مسئولِ واحد بی‌صاحب می‌ماند.
    left = client.patch(
        f"/api/personnel/{hossein_person.id}",
        json={"status": "inactive", "separation_reason": SeparationReason.resignation.value},
        headers=auth_header(other_hr),
    )
    assert left.status_code == 200, left.text
    return {
        "record_id": record_id,
        "ali": ali,
        "ali_person": ali_person,
        "hossein": hossein,
        "other_hr": other_hr,
        "replacement": replacement,
        "deputy": deputy,
        "ceo": ceo,
    }


def _reassign(client, actor, record_id, new_user_id):
    return client.post(
        f"/api/evaluations/{record_id}/reassign",
        json={
            "stage_field": "unit_supervisor_user_id",
            "new_user_id": new_user_id,
            "reason": "خروج مسئول واحد از سازمان",
        },
        headers=auth_header(actor),
    )


# ── سپر سرِ جایش می‌ماند ────────────────────────────────────────────────


def test_hr_still_cannot_touch_the_shielded_case(client, db_session):
    """رفعِ بن‌بست نباید سپر را باز کند — همان دلیلی که سپر برایش ساخته شد."""
    case = _case(client, db_session)
    blocked = _reassign(
        client, case["other_hr"], case["record_id"], case["replacement"].id
    )
    assert blocked.status_code == 403, blocked.text
    assert (
        client.post(
            f"/api/evaluations/{case['record_id']}/cancel",
            json={"reason": "هر دلیلی"},
            headers=auth_header(case["other_hr"]),
        ).status_code
        == 403
    )


def test_the_departed_seat_holder_cannot_act(client, db_session):
    case = _case(client, db_session)
    stuck = _reassign(client, case["hossein"], case["record_id"], case["replacement"].id)
    assert stuck.status_code in (401, 403)


def test_a_second_record_for_the_same_person_is_still_refused(client, db_session):
    """قیدِ یکتای جزئی سرِ جایش است؛ راهِ خروج «پروندهٔ دوم» نیست."""
    case = _case(client, db_session)
    again = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": case["ali_person"].id},
        headers=auth_header(case["deputy"]),
    )
    assert again.status_code == 400, again.text


# ── و درِ خروج باز است ──────────────────────────────────────────────────


def test_the_deputy_on_the_chain_can_reassign(client, db_session):
    """معاونتِ همان پرونده جایگزین می‌گذارد و پرونده دوباره راه می‌افتد."""
    case = _case(client, db_session)
    fixed = _reassign(
        client, case["deputy"], case["record_id"], case["replacement"].id
    )
    assert fixed.status_code == 200, fixed.text
    record = db_session.get(EvaluationRecord, case["record_id"])
    db_session.refresh(record)
    assert record.unit_supervisor_user_id == case["replacement"].id


def test_the_ceo_can_reassign(client, db_session):
    case = _case(client, db_session)
    fixed = _reassign(client, case["ceo"], case["record_id"], case["replacement"].id)
    assert fixed.status_code == 200, fixed.text


def test_the_deputy_can_cancel_as_a_last_resort(client, db_session):
    case = _case(client, db_session)
    cancelled = client.post(
        f"/api/evaluations/{case['record_id']}/cancel",
        json={"reason": "مسئول واحد رفت و جایگزینی تعیین نشد"},
        headers=auth_header(case["deputy"]),
    )
    assert cancelled.status_code == 200, cancelled.text

    # و حالا راهِ ادامه باز است — بن‌بست واقعاً شکسته، نه دور زده شده.
    #
    # زنجیرهٔ *دسترسی* هنوز صندلیِ مردهٔ حسین را دارد و پروندهٔ تازه را رد
    # می‌کند («صندلی‌های غیرفعال…»). آن گاردِ درستی است و سرِ جایش می‌ماند:
    # ردیفِ دسترسی سپر ندارد، پس منابع انسانی همیشه می‌تواند اصلاحش کند.
    fixed = client.put(
        f"/api/personnel/{case['ali_person'].id}/access",
        json={
            "unit_supervisor_user_id": case["replacement"].id,
            "deputy_user_id": case["deputy"].id,
            "ceo_user_id": case["ceo"].id,
        },
        headers=auth_header(case["other_hr"]),
    )
    assert fixed.status_code == 200, fixed.text
    again = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": case["ali_person"].id},
        headers=auth_header(case["replacement"]),
    )
    assert again.status_code == 201, again.text


def test_an_unrelated_deputy_gets_nothing(client, db_session):
    """رفعِ بن‌بست نباید به هر معاونتی حقِ لغوِ هر پرونده بدهد."""
    case = _case(client, db_session)
    outsider = make_user(db_session, "deputy")
    db_session.commit()
    refused = _reassign(
        client, outsider, case["record_id"], case["replacement"].id
    )
    assert refused.status_code == 403, refused.text


def test_the_deputy_is_still_refused_on_an_ordinary_case(client, db_session):
    """پروندهٔ غیرِ سپرشده هیچ چیزش عوض نمی‌شود: کار با منابع انسانی است."""
    ceo = make_user(db_session, "ceo", capabilities=[])
    deputy = make_user(db_session, "deputy")
    sup = make_user(db_session, "unit_supervisor")
    person = make_personnel(db_session, full_name="کارمند عادی")
    make_access(db_session, person, sup, deputy, ceo)
    db_session.commit()
    record_id = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": person.id},
        headers=auth_header(sup),
    ).json()["id"]

    refused = client.post(
        f"/api/evaluations/{record_id}/cancel",
        json={"reason": "بی‌دلیل"},
        headers=auth_header(deputy),
    )
    assert refused.status_code == 403, refused.text


# ── و اعلان به کسی می‌رود که می‌تواند کاری بکند ─────────────────────────


def test_the_vacated_seat_notice_goes_to_the_chain_not_to_hr(client, db_session):
    """HR نباید بشنود «جایگزین تعیین کن» برای کاری که برایش ۴۰۳ است."""
    case = _case(client, db_session)
    notices = list(
        db_session.scalars(
            select(Notification).where(Notification.type == "seats_vacated")
        )
    )
    recipients = {n.user_id for n in notices}
    assert case["deputy"].id in recipients
    assert case["ceo"].id in recipients
    assert case["other_hr"].id not in recipients, (
        "پروندهٔ سپرشده نباید به منابع انسانی گزارش شود"
    )
    mine = [n for n in notices if n.user_id == case["deputy"].id]
    assert len(mine) == 1
    assert mine[0].link == f"/evaluations/{case['record_id']}", mine[0].link


# ── و صورتِ سومِ همان بن‌بست ────────────────────────────────────────────


def test_an_hr_member_with_an_open_case_can_still_be_separated(client, db_session):
    """کارشناسِ HR با پروندهٔ بازِ *خودش* باید قابلِ خارج‌کردن باشد.

    این را حین رفعِ بن‌بست پیدا کردم و بدترین صورتش بود: لغوِ خودکارِ لحظهٔ خروج
    از همان سپر رد نمی‌شد، پس *کلِ* اقدامِ خروج ۴۰۳ می‌گرفت — نه حساب بسته
    می‌شد، نه نشست باطل، نه پرونده لغو. یعنی عضوِ واحدِ منابع انسانی که پروندهٔ
    باز داشت، اصلاً از سازمان خارج نمی‌شد.
    """
    db = db_session
    hr_unit = make_hr_unit(db)
    ali_person = make_personnel(db, full_name="علی رفتنی", org_unit=hr_unit)
    hossein_person = make_personnel(
        db, full_name="حسین مدیر", org_unit=hr_unit, is_manager=True
    )
    ali = make_user(db, "hr", personnel_id=ali_person.id)
    hossein = make_user(db, "unit_supervisor", personnel_id=hossein_person.id)
    other_hr = make_user(db, "hr", capabilities=[Capability.manage_personnel])
    deputy = make_user(db, "deputy")
    ceo = make_user(db, "ceo", capabilities=[])
    make_access(db, ali_person, hossein, deputy, ceo)
    db.commit()

    record_id = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": ali_person.id},
        headers=auth_header(hossein),
    ).json()["id"]

    left = client.patch(
        f"/api/personnel/{ali_person.id}",
        json={"status": "inactive", "separation_reason": SeparationReason.resignation.value},
        headers=auth_header(other_hr),
    )
    assert left.status_code == 200, left.text

    record = db.get(EvaluationRecord, record_id)
    db.refresh(record)
    assert record.status.value == "cancelled"
    db.refresh(ali)
    assert ali.is_active is False, "حساب هم باید بسته شده باشد"


def test_the_separation_exemption_does_not_open_the_manual_path(client, db_session):
    """استثنا فقط روی لغوِ خودکار است؛ لغوِ دستیِ HR همچنان ۴۰۳ می‌گیرد."""
    case = _case(client, db_session)
    refused = client.post(
        f"/api/evaluations/{case['record_id']}/cancel",
        json={"reason": "دستی"},
        headers=auth_header(case["other_hr"]),
    )
    assert refused.status_code == 403, refused.text
