"""زنجیره‌ای که معاونت ندارد — پرونده از منابع انسانی مستقیم به مدیرعامل می‌رود.

از ساختار واقعی یک سازمان آمد: ۹ نفر از ۴۲ نفرِ یک فایل پرسنلی هیچ معاونتی بالای
سرشان نداشتند. تا پیش از این ستون NOT NULL بود، یعنی تنها راه ثبتشان گذاشتن یک
معاونتِ ساختگی بود — نامی که بعداً پای تأیید پروندهٔ آن‌ها می‌نشست، در سندی که
امضا می‌شود.

قرینهٔ مسیر «مدیر» است که از قبل وجود داشت: مرحله‌ای که کسی در آن نایستاده،
نباید پرونده را نگه دارد.
"""
from app.models.enums import EvaluationStatus
from app.models.evaluation import EvaluationRecord
from app.models.evaluation_access import EvaluationAccess
from tests.helpers import (
    active_indicators,
    auth_header,
    full_valid_scores,
    make_personnel,
    make_user,
)


def _chain_without_deputy(db_session):
    hr = make_user(db_session, "hr")
    supervisor = make_user(db_session, "unit_supervisor", capabilities=[])
    ceo = make_user(db_session, "ceo", capabilities=[])
    personnel = make_personnel(db_session)
    db_session.add(
        EvaluationAccess(
            personnel_id=personnel.id,
            unit_supervisor_user_id=supervisor.id,
            deputy_user_id=None,
            ceo_user_id=ceo.id,
        )
    )
    db_session.commit()
    return hr, supervisor, ceo, personnel


def _run_to_hr_approved(client, db_session, hr, supervisor, personnel):
    created = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": personnel.id},
        headers=auth_header(supervisor),
    )
    assert created.status_code == 201, created.text
    record_id = created.json()["id"]

    scores = full_valid_scores(active_indicators(db_session))
    client.put(
        f"/api/evaluations/{record_id}/scores",
        json={"scores": scores},
        headers=auth_header(supervisor),
    )
    assert client.post(
        f"/api/evaluations/{record_id}/submit", headers=auth_header(supervisor)
    ).status_code == 200
    assert client.post(
        f"/api/evaluations/{record_id}/hr-approve", headers=auth_header(hr)
    ).status_code == 200
    return record_id


def test_the_ceo_finalises_straight_from_hr_approval(client, db_session):
    hr, supervisor, ceo, personnel = _chain_without_deputy(db_session)
    record_id = _run_to_hr_approved(client, db_session, hr, supervisor, personnel)

    response = client.post(
        f"/api/evaluations/{record_id}/ceo-finalize", headers=auth_header(ceo)
    )
    assert response.status_code == 200, response.text
    db_session.expire_all()
    assert db_session.get(EvaluationRecord, record_id).status is EvaluationStatus.finalized


def test_a_chain_with_a_deputy_still_has_to_go_through_them(client, db_session):
    """گاردِ اصلی این تغییر.

    گذارِ تازه (`hr_approved` → نهایی) نباید راهی بشود برای دورزدنِ تأیید معاونت
    در زنجیره‌هایی که معاونت *دارند*. اگر این تست بشکند، یک مرحلهٔ تأیید در کل
    سامانه اختیاری شده است.
    """
    hr = make_user(db_session, "hr")
    supervisor = make_user(db_session, "unit_supervisor", capabilities=[])
    deputy = make_user(db_session, "deputy", capabilities=[])
    ceo = make_user(db_session, "ceo", capabilities=[])
    personnel = make_personnel(db_session)
    db_session.add(
        EvaluationAccess(
            personnel_id=personnel.id,
            unit_supervisor_user_id=supervisor.id,
            deputy_user_id=deputy.id,
            ceo_user_id=ceo.id,
        )
    )
    db_session.commit()
    record_id = _run_to_hr_approved(client, db_session, hr, supervisor, personnel)

    blocked = client.post(
        f"/api/evaluations/{record_id}/ceo-finalize", headers=auth_header(ceo)
    )
    assert blocked.status_code == 403, blocked.text
    db_session.expire_all()
    assert db_session.get(EvaluationRecord, record_id).status is EvaluationStatus.hr_approved


def test_both_middle_stages_empty_is_now_a_chain_of_its_own(client, db_session):
    """قاعده عوض شد: خالی‌بودنِ هر دو صندلیِ میانی رد نمی‌شود.

    پیش از این ۴۰۰ می‌گرفت با استدلالِ «هیچ‌کس نمره نمی‌دهد» — استدلالی که
    درست بود و نتیجه‌گیری‌اش غلط: نمره‌دهنده وجود داشت (خودِ مدیرعامل)، فقط
    گذارش نوشته نشده بود. گردشِ کاملِ آن مسیر در `test_ceo_only_chain.py` است؛
    این‌جا فقط ثابت می‌شود که این فایل دیگر آن را ممنوع نمی‌داند.
    """
    hr = make_user(db_session, "hr")
    ceo = make_user(db_session, "ceo", capabilities=[])
    personnel = make_personnel(db_session)
    db_session.commit()

    response = client.put(
        f"/api/personnel/{personnel.id}/access",
        json={"unit_supervisor_user_id": None, "deputy_user_id": None, "ceo_user_id": ceo.id},
        headers=auth_header(hr),
    )
    assert response.status_code == 200, response.text


def test_hr_can_save_a_chain_without_a_deputy(client, db_session):
    hr = make_user(db_session, "hr")
    supervisor = make_user(db_session, "unit_supervisor", capabilities=[])
    ceo = make_user(db_session, "ceo", capabilities=[])
    personnel = make_personnel(db_session)
    db_session.commit()

    response = client.put(
        f"/api/personnel/{personnel.id}/access",
        json={
            "unit_supervisor_user_id": supervisor.id,
            "deputy_user_id": None,
            "ceo_user_id": ceo.id,
        },
        headers=auth_header(hr),
    )
    assert response.status_code == 200, response.text
    assert response.json()["deputy_user_id"] is None


def test_the_ceo_can_send_it_back_instead_of_only_signing(client, db_session):
    """روی این میز تا امروز فقط یک دکمه بود: امضا.

    `ceo_finalize` از `hr_approved` مجاز بود (تستِ بالا)، ولی هیچ گذارِ
    برگشتی از آن وضعیت وجود نداشت — نه `ceo_return` که فقط `deputy_approved`
    را می‌پذیرد و نه چیزِ دیگری. یعنی مدیرعاملی که با نمره موافق نبود، تنها
    راهش تلفن‌زدن به منابع انسانی بود.

    مقصد `submitted` است: مرحلهٔ HR در این زنجیره وجود دارد و پرونده به صفِ
    همان مرحله برمی‌گردد — قرینهٔ دقیقِ `ceo_return_manager`.
    """
    hr, supervisor, ceo, personnel = _chain_without_deputy(db_session)
    record_id = _run_to_hr_approved(client, db_session, hr, supervisor, personnel)

    returned = client.post(
        f"/api/evaluations/{record_id}/return",
        json={"reason": "شواهدِ شاخصِ سوم کافی نیست"},
        headers=auth_header(ceo),
    )
    assert returned.status_code == 200, returned.text
    assert returned.json()["status"] == EvaluationStatus.submitted.value

    # و از آن‌جا مسیر دوباره باز است: HR تأیید می‌کند و مدیرعامل نهایی.
    assert client.post(
        f"/api/evaluations/{record_id}/hr-approve", headers=auth_header(hr)
    ).status_code == 200
    assert client.post(
        f"/api/evaluations/{record_id}/ceo-finalize", headers=auth_header(ceo)
    ).status_code == 200


def test_the_deputy_seat_is_not_a_return_target_that_nobody_sits_in(client, db_session):
    """معاونتی که وجود ندارد، نباید مقصدِ برگشت باشد.

    اگر `ceo_return` (که مقصدش `hr_approved` است) در این زنجیره اجرا می‌شد،
    پرونده از `hr_approved` به `hr_approved` می‌رفت — یک برگشتِ بی‌حرکت.
    """
    hr, supervisor, ceo, personnel = _chain_without_deputy(db_session)
    record_id = _run_to_hr_approved(client, db_session, hr, supervisor, personnel)

    # معاونت در این زنجیره صندلی ندارد، پس تأییدش هم بی‌معناست.
    deputy = make_user(db_session, "deputy", capabilities=[])
    refused = client.post(
        f"/api/evaluations/{record_id}/deputy-approve", headers=auth_header(deputy)
    )
    assert refused.status_code in (400, 403)


def test_the_ceo_queue_shows_the_case_that_is_waiting_for_them(client, db_session):
    """تبِ «در انتظار تأیید نهایی» تا امروز فقط `deputy_approved` را می‌گرفت.

    یعنی پروندهٔ زنجیرهٔ بی‌معاونت — که روی `hr_approved` منتظرِ امضای همان
    مدیرعامل است — در هیچ صفی دیده نمی‌شد. `IS_ON_CEO_DESK` قرینهٔ کوئریِ
    گاردِ `ceo_finalize` است و این تست هر دو را کنارِ هم می‌سنجد.
    """
    hr, supervisor, ceo, personnel = _chain_without_deputy(db_session)
    record_id = _run_to_hr_approved(client, db_session, hr, supervisor, personnel)

    old_way = client.get(
        "/api/evaluations?status=deputy_approved", headers=auth_header(ceo)
    ).json()
    assert old_way["total"] == 0

    desk = client.get("/api/evaluations?on_ceo_desk=true", headers=auth_header(ceo)).json()
    assert [item["id"] for item in desk["items"]] == [record_id]

    # و همان پرونده واقعاً قابلِ نهایی‌کردن است — صف و گذار یک چیز می‌گویند.
    assert client.post(
        f"/api/evaluations/{record_id}/ceo-finalize", headers=auth_header(ceo)
    ).status_code == 200
    assert (
        client.get("/api/evaluations?on_ceo_desk=true", headers=auth_header(ceo)).json()[
            "total"
        ]
        == 0
    )
