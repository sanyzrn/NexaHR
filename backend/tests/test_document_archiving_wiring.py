"""هر مسیری که پرونده را نهایی می‌کند، ساختِ سند را هم زمان‌بندی می‌کند.

رندرِ PDF عمداً از مسیرِ درخواست بیرون رفته: WeasyPrint یک کتابخانهٔ بومیِ
سنگین است و تا پیش از این *داخلِ* درخواستِ نهایی‌سازی اجرا می‌شد، یعنی کند
شدنش به «نهایی‌سازی ناموفق» ترجمه می‌شد — روی مهم‌ترین اقدامِ سامانه.

ولی خودِ آن جابه‌جایی یک خطرِ تازه ساخت و هیچ تستی نداشت: `add_task` یک خطِ
ساده است و حذف یا جا انداختنش در یک مسیرِ *دیگر* هیچ‌جا دیده نمی‌شود. پرونده
نهایی می‌شود، پاسخ ۲۰۰ است، همه‌چیز سالم به‌نظر می‌رسد — و سند فقط وقتی ساخته
می‌شود که یا جاروی شبانه برسد یا کسی دانلودش کند.

این فایل *زمان‌بندی* را می‌سنجد و نه خودِ رندر را: رندر به نصب‌بودنِ
WeasyPrint بند است و در CI ممکن است نباشد، ولی سیمِ بینِ «نهایی شد» و «سند
بساز» باید همیشه وصل باشد.

و هر دو شکلِ نهایی‌سازی سنجیده می‌شوند، چون دو endpointِ جدا هستند: زنجیرهٔ
کامل (مدیرعامل می‌بندد) و زنجیرهٔ مستقیمِ مدیرعامل (منابع انسانی می‌بندد).
"""
import pytest

from app.models.enums import Capability
from tests.helpers import (
    active_indicators,
    auth_header,
    full_valid_scores,
    make_access,
    make_personnel,
    make_user,
)


@pytest.fixture()
def scheduled(monkeypatch):
    """شناسه‌های پرونده‌ای که برایشان ساختِ سند زمان‌بندی شد."""
    from app.api.routers import evaluations

    recorded: list[int] = []
    monkeypatch.setattr(
        evaluations, "archive_final_pdf_detached", lambda record_id: recorded.append(record_id)
    )
    return recorded


def _score_and_submit(client, db_session, evaluation_id, scorer) -> None:
    client.put(
        f"/api/evaluations/{evaluation_id}/scores",
        json={"scores": full_valid_scores(active_indicators(db_session))},
        headers=auth_header(scorer),
    )
    client.post(f"/api/evaluations/{evaluation_id}/submit", headers=auth_header(scorer))


def test_the_full_chain_schedules_the_document(client, db_session, scheduled):
    hr = make_user(db_session, "hr")
    sup = make_user(db_session, "unit_supervisor")
    dep = make_user(db_session, "deputy")
    ceo = make_user(db_session, "ceo")
    person = make_personnel(db_session)
    make_access(db_session, person, sup, dep, ceo)
    db_session.commit()

    evaluation_id = client.post(
        "/api/evaluations", json={"subject_personnel_id": person.id}, headers=auth_header(sup)
    ).json()["id"]
    _score_and_submit(client, db_session, evaluation_id, sup)
    client.post(f"/api/evaluations/{evaluation_id}/hr-approve", headers=auth_header(hr))
    client.post(f"/api/evaluations/{evaluation_id}/deputy-approve", headers=auth_header(dep))

    assert scheduled == [], "تا پیش از نهایی‌سازی نباید چیزی زمان‌بندی شود"
    final = client.post(
        f"/api/evaluations/{evaluation_id}/ceo-finalize", headers=auth_header(ceo)
    )

    assert final.status_code == 200, final.text
    assert scheduled == [evaluation_id]


def test_the_direct_ceo_chain_schedules_it_too(client, db_session, scheduled):
    """زنجیرهٔ مستقیمِ مدیرعامل endpointِ دیگری دارد — و همان سیم را لازم دارد.

    این همان شکلی است که در آن *منابع انسانی* پرونده را می‌بندد، نه مدیرعامل.
    یک مسیرِ جدا یعنی یک `add_task`ِ جدا، و یعنی جایی که می‌شود جا انداختش.
    """
    hr = make_user(db_session, "hr", capabilities=[Capability.manage_users])
    ceo = make_user(db_session, "ceo")
    person = make_personnel(db_session)
    # نه مسئولِ واحد و نه معاونت: مدیرعامل خودش نمره می‌دهد.
    make_access(db_session, person, None, None, ceo)
    db_session.commit()

    evaluation_id = client.post(
        "/api/evaluations", json={"subject_personnel_id": person.id}, headers=auth_header(ceo)
    ).json()["id"]
    _score_and_submit(client, db_session, evaluation_id, ceo)

    assert scheduled == []
    final = client.post(
        f"/api/evaluations/{evaluation_id}/hr-approve", headers=auth_header(hr)
    )

    assert final.status_code == 200, final.text
    assert scheduled == [evaluation_id], (
        "زنجیرهٔ مستقیمِ مدیرعامل با تأییدِ منابع انسانی *نهایی* می‌شود؛ "
        "ساختِ سند باید همان‌جا زمان‌بندی شود."
    )


def test_a_mere_approval_schedules_nothing(client, db_session, scheduled):
    """گاردِ ارزان: اگر هر گذاری سند بسازد، تستِ بالا هم سبز می‌ماند."""
    hr = make_user(db_session, "hr")
    sup = make_user(db_session, "unit_supervisor")
    dep = make_user(db_session, "deputy")
    ceo = make_user(db_session, "ceo")
    person = make_personnel(db_session)
    make_access(db_session, person, sup, dep, ceo)
    db_session.commit()

    evaluation_id = client.post(
        "/api/evaluations", json={"subject_personnel_id": person.id}, headers=auth_header(sup)
    ).json()["id"]
    _score_and_submit(client, db_session, evaluation_id, sup)
    client.post(f"/api/evaluations/{evaluation_id}/hr-approve", headers=auth_header(hr))

    assert scheduled == []
