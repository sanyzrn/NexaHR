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
import pytest

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


def _finish(client, record_id: int, deputy, ceo) -> None:
    """پرونده را تا `finalized` جلو می‌برد — از هر مرحله‌ای که هست.

    مرحلهٔ معاونت در مسیرِ «مدیر» وجود ندارد، پس ۴۰۳ گرفتن از آن اشکال نیست؛
    شرطِ واقعی همان تأیید نهایی است.
    """
    client.post(f"/api/evaluations/{record_id}/deputy-approve", headers=auth_header(deputy))
    final = client.post(f"/api/evaluations/{record_id}/ceo-finalize", headers=auth_header(ceo))
    assert final.status_code == 200, final.text


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

    و برخلاف بقیهٔ پرونده‌ها، *نهایی‌شدن* هم این در را باز نمی‌کند: مسیر خودش
    (`/api/me/evaluations`) جداست و همان است که باید نتیجه را به او بدهد.
    """
    case = _specialist(client, db_session)
    _score_and_submit(client, db_session, case["record_id"], case["supervisor"])

    listing = client.get("/api/evaluations", headers=auth_header(case["ali"])).json()
    assert all(row["id"] != case["record_id"] for row in listing["items"])

    _finish(client, case["record_id"], case["deputy"], case["ceo"])
    after = client.get("/api/evaluations", headers=auth_header(case["ali"])).json()
    assert all(row["id"] != case["record_id"] for row in after["items"])


def test_a_colleague_in_hr_sees_the_case_only_after_it_is_final(client, db_session):
    """قاعدهٔ دوم: پروندهٔ در جریانِ واحدِ HR را هم‌تیمی‌ها هم نمی‌بینند.

    دو خواستهٔ ظاهراً متضاد در یک جمله جا می‌شوند وقتی مرزشان *زمان* باشد و نه
    شخص: «علی پروندهٔ حسین را اصلاً نبیند» دربارهٔ پروندهٔ در جریان است، و
    «بعد از تأیید نهایی به پنل مدیریت HR برود» دربارهٔ همان پرونده پس از بسته
    شدنش. تا وقتی باز است، منابع انسانی ابزارِ اثرگذاری دارد (لغو، تمدید مهلت،
    تغییر مسئولِ مرحله) و شواهدِ ارزیاب هم روی پرونده است؛ پس از آن، هیچ‌کدام.
    """
    case = _specialist(client, db_session)
    _score_and_submit(client, db_session, case["record_id"], case["supervisor"])
    other_hr = auth_header(case["other_hr"])

    listing = client.get("/api/evaluations", headers=other_hr).json()
    assert all(row["id"] != case["record_id"] for row in listing["items"])
    detail = client.get(f"/api/evaluations/{case['record_id']}", headers=other_hr)
    assert detail.status_code == 403, detail.text
    assert "پیش از ثبت نهایی" in detail.json()["detail"]

    _finish(client, case["record_id"], case["deputy"], case["ceo"])

    listing = client.get("/api/evaluations", headers=other_hr).json()
    assert any(row["id"] == case["record_id"] for row in listing["items"])
    assert (
        client.get(f"/api/evaluations/{case['record_id']}", headers=other_hr).status_code
        == 200
    )


def test_the_excel_export_hides_what_the_list_hides(client, db_session):
    """دامنهٔ دید باید در «دریافت خروجی» هم همان باشد که در صفحه است.

    خروجیِ Excel همان فیلترهای فهرست را می‌پذیرد ولی
    `scope_evaluations_for_role` را صدا نمی‌زد — یعنی هر کاربر HR می‌توانست
    ستونِ نتیجهٔ پروندهٔ خودش و پروندهٔ در جریانِ واحدش را از همان صفحه‌ای که
    آن‌ها را پنهان می‌کند دانلود کند.
    """
    case = _specialist(client, db_session)
    _score_and_submit(client, db_session, case["record_id"], case["supervisor"])
    code = (
        db_session.get(EvaluationRecord, case["record_id"]).evaluation_code.encode()
    )

    for actor in (case["ali"], case["other_hr"]):
        response = client.get("/api/evaluations/export.xlsx", headers=auth_header(actor))
        assert response.status_code == 200, response.text
        # کدِ پرونده در xlsx به‌صورت رشته می‌نشیند؛ zip فشرده است، پس همین که
        # جایی در بایت‌ها نباشد کافی نیست — فایل را باز می‌کنیم.
        assert code not in _xlsx_text(response.content)


def _xlsx_text(content: bytes) -> bytes:
    """متنِ همهٔ برگه‌های یک xlsx، بی‌آنکه به کتابخانهٔ خواندن نیاز باشد."""
    import io as _io
    import zipfile

    with zipfile.ZipFile(_io.BytesIO(content)) as book:
        return b"".join(book.read(name) for name in book.namelist())


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("cancel", {"reason": "دلیلِ دلخواه برای لغو"}),
        ("extend-submission", {"until": "2099-01-01", "reason": "دلیلِ دلخواه برای تمدید"}),
        ("hr-claim", None),
    ],
)
def test_a_colleague_in_hr_cannot_touch_the_open_case(client, db_session, path, payload):
    """ابزارهای بیرونِ زنجیره هم بسته‌اند، نه فقط پنجرهٔ دیدن.

    این سه، تنها راه‌هایی هستند که نقشِ `hr` بی‌آنکه صندلی‌ای در زنجیره داشته
    باشد روی یک پروندهٔ باز اثر می‌گذارد. بستنِ فهرست بدون بستنِ این‌ها، گاردی
    است که فقط چشم را می‌بندد.
    """
    case = _specialist(client, db_session)
    _score_and_submit(client, db_session, case["record_id"], case["supervisor"])

    response = client.post(
        f"/api/evaluations/{case['record_id']}/{path}",
        json=payload,
        headers=auth_header(case["other_hr"]),
    )
    assert response.status_code == 403, response.text
    assert "پیش از ثبت نهایی" in response.json()["detail"]


def test_a_colleague_in_hr_cannot_pick_the_judges_of_an_open_case(client, db_session):
    """بازتخصیص از این هم مؤثرتر است: انتخابِ داورِ یک مرحله.

    و تا پیش از این، *هیچ* گاردی نداشت — نه حتی همان «پروندهٔ خودت» که بقیهٔ
    مسیرهای HR داشتند.
    """
    case = _specialist(client, db_session)
    _score_and_submit(client, db_session, case["record_id"], case["supervisor"])
    stand_in = make_user(db_session, "deputy")
    db_session.commit()

    response = client.post(
        f"/api/evaluations/{case['record_id']}/reassign",
        json={
            "stage_field": "deputy_user_id",
            "new_user_id": stand_in.id,
            "reason": "تلاش برای انتخاب داورِ دلخواه",
        },
        headers=auth_header(case["other_hr"]),
    )
    assert response.status_code == 403, response.text


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

    # ۴۰۳ و نه ۴۰۰: گاردِ دسترسی پیش از گاردِ وضعیت می‌ایستد. ترتیبش معنا دارد —
    # پیام باید بگوید «این پرونده به تو ربطی ندارد»، نه «هنوز نوبتش نشده»؛
    # دومی درست ولی گمراه‌کننده است و انگار روزی نوبتش می‌شود.
    refused = client.post(
        f"/api/evaluations/{case['record_id']}/hr-approve",
        headers=auth_header(case["ali"]),
    )
    assert refused.status_code == 403, refused.text
    assert "پیش از ثبت نهایی" in refused.json()["detail"]

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


# ── رسیدگی به اعتراض ────────────────────────────────────────────────────


def _object_to(client, db_session, record_id: int, person) -> None:
    """کارمند نتیجه را می‌بیند و به آن اعتراض می‌کند.

    حسابِ `employee` جداست از حسابِ کاریِ همان فرد در واحد منابع انسانی —
    مسیرِ «کارنامهٔ من» فقط با آن کار می‌کند، و همین جدایی است که به موضوعِ
    پرونده اجازه می‌دهد نتیجهٔ خودش را ببیند بی‌آنکه به پنلِ HR راه پیدا کند.
    """
    employee = make_user(db_session, "employee", personnel_id=person.id)
    db_session.commit()
    client.post(
        f"/api/me/evaluations/{record_id}/acknowledge", headers=auth_header(employee)
    )
    filed = client.post(
        f"/api/me/evaluations/{record_id}/object",
        json={"reason": "با این نتیجه موافق نیستم"},
        headers=auth_header(employee),
    )
    assert filed.status_code == 200, filed.text


def _resolve(client, record_id: int, actor):
    return client.post(
        f"/api/evaluations/{record_id}/resolve-objection",
        json={"resolution": "بررسی شد و پاسخ در پرونده ثبت شد"},
        headers=auth_header(actor),
    )


def test_the_specialist_s_objection_goes_to_the_deputy_not_to_hr(client, db_session):
    """اعتراض به نخستین سطحی می‌رود که در تهیهٔ همان ارزیابی دست نداشته.

    نمره‌دهندهٔ علی، حسین است (مسئولِ واحد)؛ پس معاونت نخستین سطحِ بی‌طرف است.
    منابع انسانی این‌جا اصلاً گزینه نیست: یا خودِ معترض است یا هم‌تیمی‌اش.

    بی این مسیر، اعتراضِ این پرونده‌ها *هیچ رسیدگی‌کننده‌ای نداشت* — مسیر پاسخ
    نقشِ `hr` می‌خواست و گاردِ «دربارهٔ خودت تصمیم نگیر» تنها HRِ ممکن را رد
    می‌کرد. اعتراضی که کسی موظف به پاسخش نباشد، تشریفات است.
    """
    case = _specialist(client, db_session)
    _score_and_submit(client, db_session, case["record_id"], case["supervisor"])
    _finish(client, case["record_id"], case["deputy"], case["ceo"])
    _object_to(client, db_session, case["record_id"], case["person"])

    refused = _resolve(client, case["record_id"], case["other_hr"])
    assert refused.status_code == 403, refused.text
    assert "معاونت" in refused.json()["detail"]

    answered = _resolve(client, case["record_id"], case["deputy"])
    assert answered.status_code == 200, answered.text
    assert answered.json()["objection_resolved_at"] is not None


def test_the_hr_manager_s_objection_goes_to_the_ceo(client, db_session):
    """یک پله بالاتر، چون نمره‌دهندهٔ حسین خودِ معاونت است.

    همان قاعده، همان تابع؛ فقط شکلِ زنجیره فرق دارد. اگر رسیدگی به معاونت
    می‌رسید، ارزیاب به اعتراضِ ارزیابیِ خودش پاسخ می‌داد.
    """
    case = _hr_manager(client, db_session)
    _score_and_submit(client, db_session, case["record_id"], case["deputy"])
    _finish(client, case["record_id"], case["deputy"], case["ceo"])
    _object_to(client, db_session, case["record_id"], case["person"])

    scorer = _resolve(client, case["record_id"], case["deputy"])
    assert scorer.status_code == 403, scorer.text
    assert "مدیرعامل" in scorer.json()["detail"]

    answered = _resolve(client, case["record_id"], case["ceo"])
    assert answered.status_code == 200, answered.text


def test_the_resolver_is_the_one_who_gets_the_notification(client, db_session):
    """اعلان به صفی که اجازهٔ پاسخ ندارد، یعنی اعتراض بی‌صدا می‌ماند."""
    case = _specialist(client, db_session)
    _score_and_submit(client, db_session, case["record_id"], case["supervisor"])
    _finish(client, case["record_id"], case["deputy"], case["ceo"])
    _object_to(client, db_session, case["record_id"], case["person"])

    def objection_notices(actor):
        notes = client.get("/api/notifications", headers=auth_header(actor)).json()
        rows = notes["items"] if isinstance(notes, dict) else notes
        return [row for row in rows if row["type"] == "evaluation_objection_filed"]

    assert objection_notices(case["deputy"])
    assert not objection_notices(case["other_hr"])


# ── مهم ۵: دستهٔ «مستقیمِ مدیرعامل» مرحلهٔ منابع انسانی را نگه می‌دارد ──


def test_a_direct_report_of_the_ceo_still_passes_through_hr(client, db_session):
    """کسی که مدیرعامل هم نمره‌دهنده‌اش است و هم تأییدکنندهٔ نهایی.

    این‌جا تضاد منافعی نیست که مرحله‌ای را حذف کند — منابع انسانی نه موضوع
    است و نه هم‌تیمیِ موضوع — و چون تنها تصمیم‌گیرِ زنجیره یک نفر است، آن یک
    جفت‌چشمِ مستقل از هر پروندهٔ دیگری این‌جا لازم‌تر است. حذفِ مرحله فقط جایی
    است که داورِ بی‌طرفی برایش نمانده باشد.
    """
    make_hr_unit(db_session)  # واحد HR هست، ولی این فرد در آن نیست
    person = make_personnel(db_session, full_name="دستیار مدیرعامل")
    ceo = make_user(db_session, "ceo", capabilities=[])
    hr = make_user(db_session, "hr")
    db_session.add(
        EvaluationAccess(
            personnel_id=person.id,
            # مدیرعامل خودش در صندلیِ نمره‌دهنده می‌نشیند (`may_act_at`)، و
            # معاونتی در کار نیست.
            unit_supervisor_user_id=ceo.id,
            deputy_user_id=None,
            ceo_user_id=ceo.id,
        )
    )
    db_session.commit()

    record_id = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": person.id},
        headers=auth_header(ceo),
    ).json()["id"]
    _score_and_submit(client, db_session, record_id, ceo)

    record = db_session.get(EvaluationRecord, record_id)
    db_session.refresh(record)
    assert record.hr_review_skipped is False
    assert record.status is EvaluationStatus.submitted

    approved = client.post(
        f"/api/evaluations/{record_id}/hr-approve", headers=auth_header(hr)
    )
    assert approved.status_code == 200, approved.text

    final = client.post(
        f"/api/evaluations/{record_id}/ceo-finalize", headers=auth_header(ceo)
    )
    assert final.status_code == 200, final.text
