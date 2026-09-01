"""پروندهٔ کارمندانِ منابع انسانی، مرحلهٔ منابع انسانی ندارد.

از یک تستِ واقعی آمد، با دو نفر که هر دو در واحد منابع انسانی‌اند:

* **علی، کارشناس منابع انسانی.** مسئولِ مستقیمش حسین است (مدیر HR). پروندهٔ علی
  پس از نمره‌دهیِ حسین در صفِ بررسیِ منابع انسانی می‌نشست — همان صفی که علی
  خودش عضوش است. یعنی نمرهٔ خودش را در پنل می‌دید، و تنها HR دیگری که
  می‌توانست داوری کند، همان حسینی بود که نمره را داده بود.

* **حسین، مدیر منابع انسانی.** مسیر «مدیر» را دارد (معاونتش نمره می‌دهد)، ولی
  پرونده‌اش بعد از نمرهٔ معاونت *برمی‌گشت* به صفِ منابع انسانی — یعنی روی میزِ
  زیردستِ خودش.

قاعدهٔ تازه یکی است و هر دو را می‌گیرد: اگر موضوعِ پرونده عضوِ واحدِ منابع انسانی
باشد، مرحلهٔ منابع انسانی از زنجیره حذف می‌شود. حذف، نه واگذاری — چون در تیمِ
کوچکِ HR کسی نمی‌ماند که هم‌زمان بی‌طرف باشد و نمره‌دهنده نباشد.

ملاک عضویتِ *واحد* است و نه نقشِ حساب، و این تصادفی نیست: `may_act_at` عمداً
نقشِ `hr` را از صندلی‌های زنجیره بیرون گذاشته، پس حسینی که مسئولِ مستقیمِ علی
است *نمی‌تواند* نقشِ `hr` داشته باشد. با ملاکِ نقشی، پروندهٔ خودِ او از قلم
می‌افتاد — یعنی مهم‌ترین نیمهٔ گزارش حل نمی‌شد.

سومین عضوِ خانواده‌ای است که از قبل بود: `is_manager_path` (مسئول واحد نیست) و
`skips_deputy` (معاونت نیست). مرحله‌ای که داورِ بی‌طرف ندارد، پرونده را نگه
نمی‌دارد.
"""
from app.models.enums import EvaluationStatus
from app.models.evaluation import EvaluationRecord
from app.models.evaluation_access import EvaluationAccess
from tests.helpers import (
    active_indicators,
    auth_header,
    full_valid_scores,
    make_access,
    make_hr_unit,
    make_personnel,
    make_user,
)


def _score_and_submit(client, db_session, record_id: int, scorer) -> None:
    client.put(
        f"/api/evaluations/{record_id}/scores",
        json={"scores": full_valid_scores(active_indicators(db_session))},
        headers=auth_header(scorer),
    )
    response = client.post(
        f"/api/evaluations/{record_id}/submit", headers=auth_header(scorer)
    )
    assert response.status_code == 200, response.text


def _specialist(client, db_session):
    """علی: کارشناس HR، با حسین (مدیرِ HR) به‌عنوان مسئولِ مستقیم.

    نقشِ حسابِ حسین `unit_supervisor` است و نه `hr` — چون `may_act_at` نقشِ
    `hr` را از صندلی‌های زنجیره بیرون گذاشته و بی این، حسین اصلاً نمی‌توانست
    نمره بدهد. عضویتش در واحدِ منابع انسانی از راهِ `personnel.org_unit` می‌آید.
    """
    hr_unit = make_hr_unit(db_session)
    ali_person = make_personnel(db_session, full_name="علی قاسمی", org_unit=hr_unit)
    hossein_person = make_personnel(
        db_session, full_name="حسین قاسمی", org_unit=hr_unit, is_manager=True
    )
    ali = make_user(db_session, "hr", personnel_id=ali_person.id)
    hossein = make_user(db_session, "unit_supervisor", personnel_id=hossein_person.id)
    other_hr = make_user(db_session, "hr")
    deputy = make_user(db_session, "deputy")
    ceo = make_user(db_session, "ceo", capabilities=[])
    make_access(db_session, ali_person, hossein, deputy, ceo)
    db_session.commit()

    record_id = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": ali_person.id},
        headers=auth_header(hossein),
    ).json()["id"]
    return {
        "record_id": record_id,
        "ali": ali,
        "hossein": hossein,
        "other_hr": other_hr,
        "supervisor": hossein,
        "deputy": deputy,
        "ceo": ceo,
        "person": ali_person,
        "hr_unit": hr_unit,
    }


def _hr_manager(client, db_session):
    """حسین: مدیر HR — مسیر «مدیر»، معاونت خودش نمره می‌دهد."""
    hr_unit = make_hr_unit(db_session)
    person = make_personnel(
        db_session, full_name="حسین قاسمی", org_unit=hr_unit, is_manager=True
    )
    # نقشش `unit_supervisor` است چون کارشناسانش را نمره می‌دهد — و همین بود که
    # قاعدهٔ نقش‌محور را از کار می‌انداخت.
    hossein = make_user(db_session, "unit_supervisor", personnel_id=person.id)
    ali = make_user(db_session, "hr")
    deputy = make_user(db_session, "deputy")  # مهدی روحی
    ceo = make_user(db_session, "ceo", capabilities=[])
    db_session.add(
        EvaluationAccess(
            personnel_id=person.id,
            unit_supervisor_user_id=None,
            deputy_user_id=deputy.id,
            ceo_user_id=ceo.id,
        )
    )
    db_session.commit()

    record_id = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": person.id},
        headers=auth_header(deputy),
    ).json()["id"]
    return {
        "record_id": record_id,
        "hossein": hossein,
        "ali": ali,
        "deputy": deputy,
        "ceo": ceo,
        "person": person,
    }


# ── مهم ۱: کارشناس منابع انسانی ──────────────────────────────────────────


def test_the_specialist_s_case_goes_straight_to_the_deputy(client, db_session):
    """ثبتِ نمره، پرونده را از صفِ منابع انسانی *رد* می‌کند."""
    case = _specialist(client, db_session)

    _score_and_submit(client, db_session, case["record_id"], case["supervisor"])

    record = db_session.get(EvaluationRecord, case["record_id"])
    db_session.refresh(record)
    assert record.hr_review_skipped is True
    assert record.status is EvaluationStatus.hr_approved, "باید روی میزِ معاونت باشد"


def test_the_specialist_never_sees_their_own_case_in_the_hr_panel(client, db_session):
    """فهرست ستونِ نتیجه دارد؛ بستنِ صفحهٔ جزئیات به‌تنهایی کافی نبود.

    ریشهٔ گزارش همین بود: «نتیجه به علی نمایش داده نشود». پیش از این
    `_ensure_can_view` صفحهٔ جزئیات را می‌بست ولی `scope_evaluations_for_role`
    برای HR کلِ پرس‌وجو را بی‌قید برمی‌گرداند — یعنی نمرهٔ نهاییِ خودش را در
    فهرست می‌دید، فقط نمی‌توانست رویش کلیک کند.
    """
    case = _specialist(client, db_session)
    _score_and_submit(client, db_session, case["record_id"], case["supervisor"])

    listing = client.get("/api/evaluations", headers=auth_header(case["ali"])).json()
    assert all(row["id"] != case["record_id"] for row in listing["items"])

    # و همان پرونده برای HR دیگری دیده می‌شود — گاردی که همه را ببندد، قفل است.
    other = client.get("/api/evaluations", headers=auth_header(case["other_hr"])).json()
    assert any(row["id"] == case["record_id"] for row in other["items"])


def test_the_specialist_gets_no_notification_about_their_own_case(client, db_session):
    """اعلانِ «پروندهٔ خودت در صفِ بررسی قرار گرفت» به همان کسی نرود که موضوع است."""
    case = _specialist(client, db_session)
    _score_and_submit(client, db_session, case["record_id"], case["supervisor"])

    notes = client.get("/api/notifications", headers=auth_header(case["ali"])).json()
    rows = notes["items"] if isinstance(notes, dict) else notes
    assert all(case["person"].full_name not in row["message"] for row in rows)


def test_the_specialist_s_case_finishes_through_deputy_and_ceo(client, db_session):
    case = _specialist(client, db_session)
    _score_and_submit(client, db_session, case["record_id"], case["supervisor"])

    assert (
        client.post(
            f"/api/evaluations/{case['record_id']}/deputy-approve",
            headers=auth_header(case["deputy"]),
        ).status_code
        == 200
    )
    final = client.post(
        f"/api/evaluations/{case['record_id']}/ceo-finalize",
        headers=auth_header(case["ceo"]),
    )
    assert final.status_code == 200, final.text
    assert final.json()["status"] == "finalized"


def test_the_ceo_cannot_finalize_before_the_deputy(client, db_session):
    """رد شدنِ مرحلهٔ HR نباید مرحلهٔ معاونت را هم باز کند.

    پرونده در `hr_approved` می‌نشیند و آن وضعیت برای مدیرعامل هم یک ورودیِ
    مجاز است — ولی فقط وقتی معاونتی در زنجیره نباشد. بی این تست، رد کردنِ یک
    مرحله بی‌صدا مرحلهٔ بعدی را هم می‌پراند.
    """
    case = _specialist(client, db_session)
    _score_and_submit(client, db_session, case["record_id"], case["supervisor"])

    early = client.post(
        f"/api/evaluations/{case['record_id']}/ceo-finalize",
        headers=auth_header(case["ceo"]),
    )
    assert early.status_code == 403, early.text


def test_a_deputy_return_goes_back_to_the_scorer_not_to_a_queue_that_is_gone(
    client, db_session
):
    """برگشتِ معاونت باید یک پله بیشتر عقب برود.

    مقصدِ عادیِ این برگشت `submitted` است، یعنی «صفِ منابع انسانی» — صفی که
    این پرونده ندارد. بی این گذارِ جدا، پرونده به وضعیتی می‌رفت که هیچ‌کس در آن
    اقدامی نمی‌تواند بکند و برای همیشه همان‌جا می‌ماند.
    """
    case = _specialist(client, db_session)
    _score_and_submit(client, db_session, case["record_id"], case["supervisor"])

    returned = client.post(
        f"/api/evaluations/{case['record_id']}/return",
        json={"reason": "شواهدِ شاخص سوم کافی نیست"},
        headers=auth_header(case["deputy"]),
    )
    assert returned.status_code == 200, returned.text
    assert returned.json()["status"] == "draft", "باید دستِ نمره‌دهنده برگردد"

    # و از همان‌جا دوباره جلو می‌رود — بن‌بست نیست.
    again = client.post(
        f"/api/evaluations/{case['record_id']}/submit",
        headers=auth_header(case["supervisor"]),
    )
    assert again.status_code == 200, again.text
    assert again.json()["status"] == "hr_approved"


# ── مهم ۲: مدیر منابع انسانی ─────────────────────────────────────────────


def test_the_hr_manager_s_case_goes_straight_to_the_ceo(client, db_session):
    """دو مرحلهٔ میانی هر دو غایب‌اند، پس نمرهٔ معاونت پرونده را روی میزِ مدیرعامل می‌گذارد."""
    case = _hr_manager(client, db_session)

    _score_and_submit(client, db_session, case["record_id"], case["deputy"])

    record = db_session.get(EvaluationRecord, case["record_id"])
    db_session.refresh(record)
    assert record.hr_review_skipped is True
    assert record.status is EvaluationStatus.deputy_approved


def test_the_hr_manager_s_case_never_returns_to_hr(client, db_session):
    """«به محضِ بررسی توسط معاونت، دیگر نباید به منابع انسانی برگردد.»"""
    case = _hr_manager(client, db_session)
    _score_and_submit(client, db_session, case["record_id"], case["deputy"])

    refused = client.post(
        f"/api/evaluations/{case['record_id']}/hr-approve",
        headers=auth_header(case["ali"]),
    )
    assert refused.status_code == 400, refused.text

    final = client.post(
        f"/api/evaluations/{case['record_id']}/ceo-finalize",
        headers=auth_header(case["ceo"]),
    )
    assert final.status_code == 200, final.text


def test_a_ceo_return_on_the_manager_path_goes_back_to_the_deputy(client, db_session):
    """تنها پلهٔ عقب‌ترِ این پرونده، خودِ نمره‌دهی است."""
    case = _hr_manager(client, db_session)
    _score_and_submit(client, db_session, case["record_id"], case["deputy"])

    returned = client.post(
        f"/api/evaluations/{case['record_id']}/return",
        json={"reason": "نتیجه با گفت‌وگوی شفاهی نمی‌خواند"},
        headers=auth_header(case["ceo"]),
    )
    assert returned.status_code == 200, returned.text
    assert returned.json()["status"] == "draft"


def test_the_hr_manager_s_finalized_case_reaches_the_hr_panel(client, db_session):
    """«بعد از ثبت نهایی به پنل مدیریت HR برود» — برای بقیهٔ تیم، نه برای خودش."""
    case = _hr_manager(client, db_session)
    _score_and_submit(client, db_session, case["record_id"], case["deputy"])
    client.post(
        f"/api/evaluations/{case['record_id']}/ceo-finalize",
        headers=auth_header(case["ceo"]),
    )

    for_the_team = client.get("/api/evaluations", headers=auth_header(case["ali"])).json()
    assert any(row["id"] == case["record_id"] for row in for_the_team["items"])

    # حسین نقشِ `hr` ندارد، پس فهرستِ پنل HR را از راهِ دیگری هم نمی‌بیند؛
    # پروندهٔ خودش را از مسیرِ خودش می‌بیند (`/api/me/evaluations`).
    for_himself = client.get(
        "/api/evaluations", headers=auth_header(case["hossein"])
    ).json()
    assert all(row["id"] != case["record_id"] for row in for_himself["items"])


# ── قاعده به نقشِ *موضوع* بند است، نه به اسم کسی ─────────────────────────


def test_a_subject_outside_the_hr_unit_keeps_its_hr_review_stage(client, db_session):
    """قرینهٔ همهٔ تست‌های بالا: زنجیرهٔ بقیهٔ کارمندان دست‌نخورده می‌ماند."""
    make_hr_unit(db_session)  # واحد HR وجود دارد، ولی این فرد در آن نیست
    person = make_personnel(db_session, full_name="کارمند عادی")
    make_user(db_session, "employee", personnel_id=person.id)
    hr = make_user(db_session, "hr")
    supervisor = make_user(db_session, "unit_supervisor")
    deputy = make_user(db_session, "deputy")
    ceo = make_user(db_session, "ceo", capabilities=[])
    make_access(db_session, person, supervisor, deputy, ceo)
    db_session.commit()

    record_id = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": person.id},
        headers=auth_header(supervisor),
    ).json()["id"]
    _score_and_submit(client, db_session, record_id, supervisor)

    record = db_session.get(EvaluationRecord, record_id)
    db_session.refresh(record)
    assert record.hr_review_skipped is False
    assert record.status is EvaluationStatus.submitted
    assert (
        client.post(
            f"/api/evaluations/{record_id}/hr-approve", headers=auth_header(hr)
        ).status_code
        == 200
    )


def test_the_chain_shape_is_stamped_at_creation_not_read_live(client, db_session):
    """اگر زنده خوانده می‌شد، جابه‌جاییِ یک نفر پروندهٔ در جریان را می‌شکست.

    پروندهٔ نشسته در صفِ HR با انتقالِ همان فرد به واحدِ منابع انسانی، بی‌صدا
    غیرقابل‌تأیید می‌شد: گاردِ `hr_approve` ردش می‌کرد و هیچ گذارِ دیگری هم از
    `submitted` بیرون نمی‌برد.
    """
    hr_unit = make_hr_unit(db_session)
    person = make_personnel(db_session, full_name="کارمندی که جابه‌جا می‌شود")
    make_user(db_session, "employee", personnel_id=person.id)
    hr = make_user(db_session, "hr")
    supervisor = make_user(db_session, "unit_supervisor")
    deputy = make_user(db_session, "deputy")
    ceo = make_user(db_session, "ceo", capabilities=[])
    make_access(db_session, person, supervisor, deputy, ceo)
    db_session.commit()

    record_id = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": person.id},
        headers=auth_header(supervisor),
    ).json()["id"]
    _score_and_submit(client, db_session, record_id, supervisor)

    # وسطِ چرخه به واحدِ منابع انسانی منتقل می‌شود.
    person.org_unit = hr_unit
    db_session.commit()

    record = db_session.get(EvaluationRecord, record_id)
    db_session.refresh(record)
    assert record.hr_review_skipped is False, "شکلِ زنجیره وسط راه عوض نمی‌شود"
    assert (
        client.post(
            f"/api/evaluations/{record_id}/hr-approve", headers=auth_header(hr)
        ).status_code
        == 200
    ), "پروندهٔ در جریان باید همان مسیری را تمام کند که زیرش باز شده"


def test_the_flag_is_what_decides_not_the_unit_s_name(client, db_session):
    """واحدی به نامِ «منابع انسانی» که پرچم نخورده، مرحلهٔ HR را نگه می‌دارد.

    مهاجرت واحدهای هم‌نام را به‌عنوان *نقطهٔ شروع* پرچم می‌زند، ولی قاعده خودِ
    پرچم است. بی این تست، تطبیقِ نام می‌توانست بی‌سروصدا به شرطِ واقعی تبدیل
    شود — و سازمانی که واحدش «سرمایهٔ انسانی» نام دارد از قلم می‌افتاد، یا
    واحدی که عمداً پرچمش را برداشته‌اند دوباره مشمول می‌شد.
    """
    from app.models.org_unit import OrgUnit

    unnamed = OrgUnit(site=None, name="منابع انسانی (بدون پرچم)", is_hr_unit=False)
    db_session.add(unnamed)
    db_session.flush()
    person = make_personnel(db_session, full_name="کارمند", org_unit=unnamed.full_name)
    make_user(db_session, "employee", personnel_id=person.id)
    supervisor = make_user(db_session, "unit_supervisor")
    deputy = make_user(db_session, "deputy")
    ceo = make_user(db_session, "ceo", capabilities=[])
    make_access(db_session, person, supervisor, deputy, ceo)
    db_session.commit()

    record_id = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": person.id},
        headers=auth_header(supervisor),
    ).json()["id"]
    _score_and_submit(client, db_session, record_id, supervisor)

    record = db_session.get(EvaluationRecord, record_id)
    db_session.refresh(record)
    assert record.hr_review_skipped is False
    assert record.status is EvaluationStatus.submitted


def test_hr_can_flag_a_unit_from_the_panel(client, db_session):
    """قاعده باید *قابل تنظیم* باشد، وگرنه فقط مهاجرت می‌تواند تعیینش کند."""
    from app.models.org_unit import OrgUnit

    # نقشِ `hr` خودش گاردِ این مسیر را می‌گذراند (`require_role_or_capability`).
    admin = make_user(db_session, "hr")
    unit = OrgUnit(site=None, name="سرمایهٔ انسانی")
    db_session.add(unit)
    db_session.commit()

    response = client.patch(
        f"/api/org-units/{unit.id}",
        json={"is_hr_unit": True},
        headers=auth_header(admin),
    )
    assert response.status_code == 200, response.text
    assert response.json()["is_hr_unit"] is True
