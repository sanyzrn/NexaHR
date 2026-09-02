"""زنجیره‌ای که نه مسئول واحد دارد و نه معاونت — خودِ مدیرعامل نمره می‌دهد.

از ساختار واقعی آمد، مثل دو خویشاوندش: کسانی که مستقیم زیر نظرِ مدیرعامل کار
می‌کنند و بالای سرشان دیگر کسی *وجود ندارد*.

تا امروز این شکل قابل ثبت نبود. `upsert_access` خالی‌بودنِ هر دو صندلیِ میانی را
رد می‌کرد با این استدلال که «نمره‌دهنده‌ای وجود ندارد» — استدلالی که درست بود و
نتیجه‌گیری‌اش غلط: نمره‌دهنده وجود داشت، مدیرعامل بود، فقط گذارش نوشته نشده بود.
تنها راهِ باقی‌مانده نشاندنِ مدیرعامل در صندلیِ «مسئول واحد» بود؛ `may_act_at`
اجازه‌اش را می‌دهد، ولی در رابط قابل انتخاب نبود (فهرست فقط نقشِ
`unit_supervisor` را می‌داد) و در سند هم دروغ می‌گفت.

مرحلهٔ منابع انسانی عمداً می‌ماند
--------------------------------
حذفِ مرحله جایی است که داورِ بی‌طرفی برایش نمانده باشد (پروندهٔ خودِ کارکنانِ
منابع انسانی). این‌جا آن حالت نیست: منابع انسانی نه موضوع است و نه هم‌تیمیِ
موضوع. و چون تنها تصمیم‌گیرِ زنجیره یک نفر است، آن یک جفت‌چشمِ مستقل این‌جا
لازم‌تر از هر پروندهٔ دیگری است. تأییدِ نهاییِ مدیرعامل پایانِ زنجیره است چون
کسی بالای سرش نیست — نه چون بازبینی‌ای نشده.
"""
from app.models.enums import EvaluationStatus
from app.models.evaluation import EvaluationRecord
from app.models.evaluation_access import EvaluationAccess
from tests.helpers import (
    active_indicators,
    auth_header,
    full_valid_scores,
    make_hr_unit,
    make_personnel,
    make_user,
)


def _ceo_only(db_session, *, org_unit: str | None = None):
    hr = make_user(db_session, "hr")
    ceo = make_user(db_session, "ceo", capabilities=[])
    personnel = (
        make_personnel(db_session, org_unit=org_unit)
        if org_unit is not None
        else make_personnel(db_session)
    )
    db_session.add(
        EvaluationAccess(
            personnel_id=personnel.id,
            unit_supervisor_user_id=None,
            deputy_user_id=None,
            ceo_user_id=ceo.id,
        )
    )
    db_session.commit()
    return hr, ceo, personnel


def _open_and_score(client, db_session, ceo, personnel) -> int:
    created = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": personnel.id},
        headers=auth_header(ceo),
    )
    assert created.status_code == 201, created.text
    record_id = created.json()["id"]
    scored = client.put(
        f"/api/evaluations/{record_id}/scores",
        json={"scores": full_valid_scores(active_indicators(db_session))},
        headers=auth_header(ceo),
    )
    assert scored.status_code == 200, scored.text
    return record_id


# ── ثبتِ خودِ زنجیره ────────────────────────────────────────────────────────


def test_hr_can_register_a_chain_with_both_middle_seats_empty(client, db_session):
    """همان چیزی که در تستِ واقعی «ثبت نمی‌شد»."""
    hr = make_user(db_session, "hr")
    ceo = make_user(db_session, "ceo", capabilities=[])
    personnel = make_personnel(db_session)
    db_session.commit()

    saved = client.put(
        f"/api/personnel/{personnel.id}/access",
        json={
            "unit_supervisor_user_id": None,
            "deputy_user_id": None,
            "ceo_user_id": ceo.id,
        },
        headers=auth_header(hr),
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["unit_supervisor_user_id"] is None
    assert body["deputy_user_id"] is None
    assert body["ceo_user_id"] == ceo.id


def test_the_personnel_list_says_who_scores_this_person(client, db_session):
    """رابط باید بتواند این شکل را *ببیند*، وگرنه دکمهٔ نمره‌دهی جایی نمی‌نشیند.

    پیش از این تنها سرنخِ موجود `is_manager` بود — پرچمی روی خودِ پرسنل که
    قرار نیست شکلِ زنجیره را بگوید، و برای این مسیر هیچ می‌گفت.
    """
    hr, ceo, personnel = _ceo_only(db_session)

    rows = client.get(
        "/api/personnel", params={"accessible_to_me": True}, headers=auth_header(ceo)
    ).json()["items"]
    mine = [r for r in rows if r["id"] == personnel.id]
    assert mine and mine[0]["scored_by"] == "ceo"

    # و قرینه‌اش: زنجیرهٔ معمولی همان «مسئول واحد» را می‌گوید.
    supervisor = make_user(db_session, "unit_supervisor", capabilities=[])
    other = make_personnel(db_session)
    db_session.add(
        EvaluationAccess(
            personnel_id=other.id,
            unit_supervisor_user_id=supervisor.id,
            deputy_user_id=None,
            ceo_user_id=ceo.id,
        )
    )
    db_session.commit()
    rows = client.get("/api/personnel", headers=auth_header(hr)).json()["items"]
    by_id = {r["id"]: r["scored_by"] for r in rows}
    assert by_id[other.id] == "unit_supervisor"


# ── گردشِ کار ──────────────────────────────────────────────────────────────


def test_the_ceo_scores_and_the_case_reaches_hr(client, db_session):
    hr, ceo, personnel = _ceo_only(db_session)
    record_id = _open_and_score(client, db_session, ceo, personnel)

    submitted = client.post(
        f"/api/evaluations/{record_id}/submit", headers=auth_header(ceo)
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"

    record = db_session.get(EvaluationRecord, record_id)
    db_session.refresh(record)
    assert record.final_weighted_pct is not None, "نتیجه باید سرِ ثبت حساب شود"


def test_hr_review_then_the_ceo_signature_ends_the_chain(client, db_session):
    """پس از منابع انسانی، تأییدِ مدیرعامل تأییدِ نهایی است — مرحلهٔ معاونتی نیست."""
    hr, ceo, personnel = _ceo_only(db_session)
    record_id = _open_and_score(client, db_session, ceo, personnel)
    client.post(f"/api/evaluations/{record_id}/submit", headers=auth_header(ceo))

    approved = client.post(
        f"/api/evaluations/{record_id}/hr-approve", headers=auth_header(hr)
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "deputy_approved"

    final = client.post(
        f"/api/evaluations/{record_id}/ceo-finalize", headers=auth_header(ceo)
    )
    assert final.status_code == 200, final.text
    assert final.json()["status"] == "finalized"


def test_nobody_else_can_score_or_submit_this_case(client, db_session):
    """صندلیِ خالی یعنی «مرحله‌ای نیست»، نه «هر کسی می‌تواند»."""
    hr, ceo, personnel = _ceo_only(db_session)
    record_id = _open_and_score(client, db_session, ceo, personnel)
    outsider = make_user(db_session, "unit_supervisor", capabilities=[])
    deputy = make_user(db_session, "deputy", capabilities=[])
    db_session.commit()

    for actor in (outsider, deputy, hr):
        refused = client.post(
            f"/api/evaluations/{record_id}/submit", headers=auth_header(actor)
        )
        assert refused.status_code in (403, 404), (actor.username, refused.text)


def test_a_ceo_return_goes_back_to_scoring_not_to_the_hr_queue(client, db_session):
    """برگشت به «صفِ منابع انسانی» بی‌معناست: چیزی که باید عوض شود نمرهٔ خودِ اوست.

    بی این گذار، پرونده به `submitted` برمی‌گشت — یعنی همان جایی که منابع
    انسانی از آن تأییدش کرده بود، و مدیرعامل باید منتظرِ تأییدِ دومِ او می‌ماند
    تا بتواند نمره‌اش را عوض کند.
    """
    hr, ceo, personnel = _ceo_only(db_session)
    record_id = _open_and_score(client, db_session, ceo, personnel)
    client.post(f"/api/evaluations/{record_id}/submit", headers=auth_header(ceo))
    client.post(f"/api/evaluations/{record_id}/hr-approve", headers=auth_header(hr))

    returned = client.post(
        f"/api/evaluations/{record_id}/return",
        json={"reason": "نمره را باید بازبینی کنم"},
        headers=auth_header(ceo),
    )
    assert returned.status_code == 200, returned.text
    assert returned.json()["status"] == "draft"

    # و از همان‌جا دوباره جلو می‌رود.
    assert (
        client.post(
            f"/api/evaluations/{record_id}/submit", headers=auth_header(ceo)
        ).status_code
        == 200
    )


def test_hr_can_still_return_the_case_to_the_ceo(client, db_session):
    """برگشتِ منابع انسانی به «نمره‌دهنده» می‌رود، و نمره‌دهنده این‌جا مدیرعامل است."""
    hr, ceo, personnel = _ceo_only(db_session)
    record_id = _open_and_score(client, db_session, ceo, personnel)
    client.post(f"/api/evaluations/{record_id}/submit", headers=auth_header(ceo))

    returned = client.post(
        f"/api/evaluations/{record_id}/return",
        json={"reason": "شواهد یکی از شاخص‌ها کافی نیست"},
        headers=auth_header(hr),
    )
    assert returned.status_code == 200, returned.text
    assert returned.json()["status"] == "draft"


def test_the_deputy_return_message_names_the_real_scorer(client, db_session):
    """پیامِ «معاونت خودش نمره‌دهنده اول است» برای این مسیر دروغ بود."""
    hr, ceo, personnel = _ceo_only(db_session)
    record_id = _open_and_score(client, db_session, ceo, personnel)
    client.post(f"/api/evaluations/{record_id}/submit", headers=auth_header(ceo))
    client.post(f"/api/evaluations/{record_id}/hr-approve", headers=auth_header(hr))
    deputy = make_user(db_session, "deputy", capabilities=[])
    db_session.commit()

    refused = client.post(
        f"/api/evaluations/{record_id}/return",
        json={"reason": "دلیلی برای برگشت"},
        headers=auth_header(deputy),
    )
    assert refused.status_code in (400, 403), refused.text


# ── تلاقی با پروندهٔ اعضای واحدِ منابع انسانی ───────────────────────────────


def test_an_hr_member_reporting_to_the_ceo_has_only_the_ceo(client, db_session):
    """هر سه مرحلهٔ میانی غایب: تنها داورِ پرونده مدیرعامل است.

    حالتِ نادری است و راهِ بهتری هم ندارد — منابع انسانی این‌جا خودش طرفِ
    ماجراست و بالای سرِ مدیرعامل کسی نیست. مهم این است که پرونده *قفل نشود*:
    بی گذارِ `ceo_submit_hr_subject` در `draft` می‌ماند و فقط لغو از آن
    خارجش می‌کرد.
    """
    hr_unit = make_hr_unit(db_session)
    hr, ceo, personnel = _ceo_only(db_session, org_unit=hr_unit)
    record_id = _open_and_score(client, db_session, ceo, personnel)

    record = db_session.get(EvaluationRecord, record_id)
    db_session.refresh(record)
    assert record.hr_review_skipped is True

    submitted = client.post(
        f"/api/evaluations/{record_id}/submit", headers=auth_header(ceo)
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "deputy_approved"

    refused = client.post(
        f"/api/evaluations/{record_id}/hr-approve", headers=auth_header(hr)
    )
    assert refused.status_code in (400, 403), refused.text

    final = client.post(
        f"/api/evaluations/{record_id}/ceo-finalize", headers=auth_header(ceo)
    )
    assert final.status_code == 200, final.text
    assert db_session.get(EvaluationRecord, record_id).status is EvaluationStatus.finalized
