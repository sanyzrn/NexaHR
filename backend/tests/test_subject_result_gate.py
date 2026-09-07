"""سوییچِ «نمایش نتیجه به کارمند» روی *هر* مسیرِ خواندن — نه فقط یکی.

چرا این فایل هست: سوییچ `employee_evaluation_visibility` عمداً خواندنِ سمتِ
سرور را می‌بندد و نه فقط رابط را. ولی «سمتِ سرور» چند مسیر است و تا امروز
فقط `/api/me/evaluations` می‌پرسید. دو مسیرِ دیگر نمی‌پرسیدند:

* `GET /api/evaluations` — پروندهٔ نهایی‌شدهٔ خودِ فرد با اسکیمای سمتِ زنجیره
  (شاملِ `evaluator_comment`).
* `GET /api/evaluations/{id}/summary.pdf` — کلِ سندِ رسمیِ هش‌شده.

و شناسهٔ پرونده از همان فهرستِ اول به‌دست می‌آمد، پس دومی خودبه‌خود باز می‌شد.

مهم‌تر از خودِ رفع، این است که رفع *سنجیده* باشد: پیش از این فایل، اعمالِ
همان گارد به‌عنوان یک جهش، هر ۱۱۳۱ تستِ بک‌اند را سبز رد می‌کرد — یعنی
مجموعهٔ تست «گارددار» را از «بی‌گارد» تشخیص نمی‌داد.

این فایل عمداً فیکسچرِ `employee_view_on` را *ندارد*: پیش‌فرضِ ماژول خاموش
است و همین حالتِ خاموش است که باید سنجیده شود.
"""
import pytest

from tests.helpers import (
    active_indicators,
    auth_header,
    full_valid_scores,
    make_access,
    make_personnel,
    make_user,
    set_module,
)

#: هر چیزی که کارمند از سرور می‌خواند و نتیجهٔ خودش را لو می‌دهد.
_CHAIN_SIDE_FIELDS = ("evaluator_comment", "hr_username", "hr_display_name")


@pytest.fixture
def finalized(client, db_session):
    """یک پروندهٔ نهایی‌شده، به‌همراه حسابِ کارمندِ سوژه و شناسهٔ پرونده."""
    personnel = make_personnel(db_session, full_name="سوژهٔ گارد")
    hr = make_user(db_session, "hr")
    sup = make_user(db_session, "unit_supervisor")
    dep = make_user(db_session, "deputy")
    ceo = make_user(db_session, "ceo")
    make_access(db_session, personnel, sup, dep, ceo)
    employee = make_user(db_session, "employee", personnel_id=personnel.id)
    indicators = active_indicators(db_session)

    evaluation_id = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": personnel.id},
        headers=auth_header(sup),
    ).json()["id"]
    client.put(
        f"/api/evaluations/{evaluation_id}/scores",
        json={"scores": full_valid_scores(indicators)},
        headers=auth_header(sup),
    )
    client.patch(
        f"/api/evaluations/{evaluation_id}/evaluator-comment",
        json={"evaluator_comment": "نظر محرمانهٔ ارزیاب"},
        headers=auth_header(sup),
    )
    client.post(f"/api/evaluations/{evaluation_id}/submit", headers=auth_header(sup))
    client.post(f"/api/evaluations/{evaluation_id}/hr-approve", headers=auth_header(hr))
    client.post(f"/api/evaluations/{evaluation_id}/deputy-approve", headers=auth_header(dep))
    assert (
        client.post(
            f"/api/evaluations/{evaluation_id}/ceo-finalize", headers=auth_header(ceo)
        ).status_code
        == 200
    )
    return {"id": evaluation_id, "employee": employee, "hr": hr, "personnel": personnel}


def test_with_the_switch_off_every_read_path_is_closed(client, db_session, finalized):
    """سه مسیر، یک جواب. تا امروز فقط اولی درست جواب می‌داد."""
    set_module(db_session, "employee_evaluation_visibility", False)
    employee = finalized["employee"]
    evaluation_id = finalized["id"]

    mine = client.get("/api/me/evaluations", headers=auth_header(employee))
    assert mine.status_code == 200
    assert mine.json() == {"total": 0, "items": []}

    listing = client.get("/api/evaluations", headers=auth_header(employee))
    assert listing.status_code == 200
    assert listing.json() == {"total": 0, "items": []}

    pdf = client.get(
        f"/api/evaluations/{evaluation_id}/summary.pdf", headers=auth_header(employee)
    )
    assert pdf.status_code == 403
    assert "فعال نیست" in pdf.json()["detail"]


def test_with_the_switch_on_the_person_gets_the_small_view_and_the_document(
    client, db_session, finalized
):
    """روشن‌بودن یعنی «نتیجه‌اش را ببیند»، نه «نمای زنجیره را ببیند»."""
    set_module(db_session, "employee_evaluation_visibility", True)
    employee = finalized["employee"]
    evaluation_id = finalized["id"]

    mine = client.get("/api/me/evaluations", headers=auth_header(employee)).json()
    assert [item["id"] for item in mine["items"]] == [evaluation_id]
    item = mine["items"][0]
    assert item["final_weighted_pct"] is not None
    for field in _CHAIN_SIDE_FIELDS:
        assert field not in item, f"نمای کارمند نباید {field} داشته باشد"

    # سندِ خودش را می‌گیرد — همان چیزی که H2 باز کرد و این گارد نبست.
    pdf = client.get(
        f"/api/evaluations/{evaluation_id}/summary.pdf", headers=auth_header(employee)
    )
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"

    # ولی فهرستِ سمتِ زنجیره برایش تهی می‌ماند، چون نمای دیگری دارد.
    assert client.get("/api/evaluations", headers=auth_header(employee)).json() == {
        "total": 0,
        "items": [],
    }


def test_hr_keeps_the_document_of_other_people_while_the_switch_is_off(
    client, db_session, finalized
):
    """سوییچ دربارهٔ دیدنِ *سوژه* است، نه دربارهٔ کارِ منابع انسانی."""
    set_module(db_session, "employee_evaluation_visibility", False)
    pdf = client.get(
        f"/api/evaluations/{finalized['id']}/summary.pdf",
        headers=auth_header(finalized["hr"]),
    )
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"


def test_a_subject_who_is_not_an_employee_is_gated_by_the_same_rule(
    client, db_session, finalized
):
    """قاعده به نقش کار ندارد.

    کارشناسِ منابع انسانی که *موضوعِ* پرونده است، در این درخواست ارزیابی‌شده
    است نه ارزیاب — پس همان‌جا می‌ایستد که کارمند. دسترسی‌اش به سندِ دیگران
    (تستِ بالا) دست‌نخورده است.
    """
    set_module(db_session, "employee_evaluation_visibility", False)
    hr_subject = make_user(db_session, "hr", personnel_id=finalized["personnel"].id)
    pdf = client.get(
        f"/api/evaluations/{finalized['id']}/summary.pdf", headers=auth_header(hr_subject)
    )
    assert pdf.status_code == 403
    assert "فعال نیست" in pdf.json()["detail"]
