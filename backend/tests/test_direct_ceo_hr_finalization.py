"""زنجیرهٔ «مستقیمِ مدیرعامل»: تأییدِ نهایی با منابع انسانی است، نه با نمره‌دهنده.

سیاستِ قبلی این بود که همان مدیرعامل پرونده را هم نمره بدهد و هم نهایی کند، و
سند با یک جملهٔ افشا اعلامش کند. مجاز بود ولی تفکیکِ وظایف نبود. حالا کسی که
نمره داده امضاکنندهٔ نهایی نیست.

استثنا: پروندهٔ خودِ واحدِ منابع انسانی، که به‌عمد مرحلهٔ HR ندارد.
"""
import pytest
from sqlalchemy import select

from app.models.enums import EvaluationStatus
from app.models.evaluation import EvaluationRecord
from app.models.evaluation_access import EvaluationAccess
from app.models.notification import Notification
from tests.helpers import (
    active_indicators,
    auth_header,
    full_valid_scores,
    make_hr_unit,
    make_personnel,
    make_user,
)


@pytest.fixture(autouse=True)
def _no_pdf(monkeypatch):
    """آرشیوِ PDF در پس‌زمینه اجرا می‌شود و به WeasyPrint نیاز دارد؛ کارِ این
    فایل گردشِ کار است، نه رندر."""
    monkeypatch.setattr(
        "app.api.routers.evaluations.archive_final_pdf_detached", lambda _id: None
    )


def _direct_ceo(db, *, hr_unit=False):
    """پرسنلی که مستقیم زیر نظر مدیرعامل است: نه مسئولِ واحد، نه معاونت."""
    unit = make_hr_unit(db) if hr_unit else "واحد تست"
    person = make_personnel(db, full_name="زیرمجموعهٔ مدیرعامل", org_unit=unit)
    hr = make_user(db, "hr")
    ceo = make_user(db, "ceo", capabilities=[])
    db.add(
        EvaluationAccess(
            personnel_id=person.id,
            unit_supervisor_user_id=None,
            deputy_user_id=None,
            ceo_user_id=ceo.id,
        )
    )
    db.commit()
    return hr, ceo, person


def _score_and_submit(client, db, ceo, person):
    created = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": person.id},
        headers=auth_header(ceo),
    )
    assert created.status_code == 201, created.text
    record_id = created.json()["id"]
    scored = client.put(
        f"/api/evaluations/{record_id}/scores",
        json={"scores": full_valid_scores(active_indicators(db))},
        headers=auth_header(ceo),
    )
    assert scored.status_code == 200, scored.text
    submitted = client.post(f"/api/evaluations/{record_id}/submit", headers=auth_header(ceo))
    assert submitted.status_code == 200, submitted.text
    return record_id


def test_hr_approval_finalizes_the_case(client, db_session):
    hr, ceo, person = _direct_ceo(db_session)
    record_id = _score_and_submit(client, db_session, ceo, person)

    done = client.post(f"/api/evaluations/{record_id}/hr-approve", headers=auth_header(hr))
    assert done.status_code == 200, done.text
    assert done.json()["status"] == EvaluationStatus.finalized.value


def test_the_document_is_built_by_the_same_stamp(client, db_session):
    """مسیرِ تازه باید همان مهرِ نهایی‌سازی را بزند، نه نسخهٔ نصفه‌ای از آن."""
    hr, ceo, person = _direct_ceo(db_session)
    record_id = _score_and_submit(client, db_session, ceo, person)
    client.post(f"/api/evaluations/{record_id}/hr-approve", headers=auth_header(hr))

    record = db_session.get(EvaluationRecord, record_id)
    db_session.refresh(record)
    assert record.finalized_at is not None
    assert record.verify_token, "بی توکن، صفحهٔ تأیید عمومی وجود ندارد"
    assert record.final_snapshot is not None, "بی سند، پرونده هیچ‌وقت کارنامه ندارد"
    # و سند، امضاکنندگانِ واقعی را دارد: مدیرعامل و منابع انسانی، نه بیشتر.
    labels = [row["label"] for row in record.final_snapshot["signatories"]]
    assert labels == ["مدیرعامل", "منابع انسانی"], labels


def test_the_case_is_no_longer_a_single_decider(client, db_session):
    hr, ceo, person = _direct_ceo(db_session)
    record_id = _score_and_submit(client, db_session, ceo, person)
    done = client.post(f"/api/evaluations/{record_id}/hr-approve", headers=auth_header(hr))

    assert done.json()["single_decider"] is False
    record = db_session.get(EvaluationRecord, record_id)
    db_session.refresh(record)
    assert record.final_approver_user_id == hr.id
    assert record.final_snapshot["single_decider"] is False


def test_the_scorer_cannot_sign_their_own_work(client, db_session):
    """درِ قبلی بسته است: مدیرعامل نمی‌تواند پرونده‌ای را که خودش نمره داده ببندد."""
    hr, ceo, person = _direct_ceo(db_session)
    record_id = _score_and_submit(client, db_session, ceo, person)

    refused = client.post(
        f"/api/evaluations/{record_id}/ceo-finalize", headers=auth_header(ceo)
    )
    assert refused.status_code == 403, refused.text


def test_the_hr_seat_is_recorded_on_the_case(client, db_session):
    """صفِ HR بی‌مالک شروع می‌شود؛ اقدام باید مالکش را ثبت کند، وگرنه بعداً
    معلوم نیست *کی* امضا کرده."""
    hr, ceo, person = _direct_ceo(db_session)
    record_id = _score_and_submit(client, db_session, ceo, person)
    assert db_session.get(EvaluationRecord, record_id).hr_user_id is None

    client.post(f"/api/evaluations/{record_id}/hr-approve", headers=auth_header(hr))
    record = db_session.get(EvaluationRecord, record_id)
    db_session.refresh(record)
    assert record.hr_user_id == hr.id


def test_the_ceo_hears_that_hr_closed_it(client, db_session):
    """برخلافِ `ceo_finalize`، این‌جا خبرِ تازه‌ای هست: کارِ او تمام شده."""
    hr, ceo, person = _direct_ceo(db_session)
    record_id = _score_and_submit(client, db_session, ceo, person)
    client.post(f"/api/evaluations/{record_id}/hr-approve", headers=auth_header(hr))

    mine = [
        n
        for n in db_session.scalars(select(Notification).where(Notification.user_id == ceo.id))
        if n.evaluation_record_id == record_id and n.type.startswith("workflow_")
    ]
    assert mine, "مدیرعامل باید بداند پرونده‌اش بسته شد"
    assert "منابع انسانی" in mine[-1].message


def test_a_full_chain_still_ends_with_the_ceo(client, db_session):
    """رفعِ این یکی نباید زنجیرهٔ عادی را عوض کند."""
    hr = make_user(db_session, "hr")
    sup = make_user(db_session, "unit_supervisor")
    dep = make_user(db_session, "deputy")
    ceo = make_user(db_session, "ceo", capabilities=[])
    person = make_personnel(db_session, full_name="کارمند عادی")
    db_session.add(
        EvaluationAccess(
            personnel_id=person.id,
            unit_supervisor_user_id=sup.id,
            deputy_user_id=dep.id,
            ceo_user_id=ceo.id,
        )
    )
    db_session.commit()

    record_id = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": person.id},
        headers=auth_header(sup),
    ).json()["id"]
    client.put(
        f"/api/evaluations/{record_id}/scores",
        json={"scores": full_valid_scores(active_indicators(db_session))},
        headers=auth_header(sup),
    )
    client.post(f"/api/evaluations/{record_id}/submit", headers=auth_header(sup))

    approved = client.post(f"/api/evaluations/{record_id}/hr-approve", headers=auth_header(hr))
    assert approved.json()["status"] == EvaluationStatus.hr_approved.value
    client.post(f"/api/evaluations/{record_id}/deputy-approve", headers=auth_header(dep))
    final = client.post(f"/api/evaluations/{record_id}/ceo-finalize", headers=auth_header(ceo))
    assert final.status_code == 200, final.text
    assert final.json()["status"] == EvaluationStatus.finalized.value


def test_an_hr_unit_subject_still_ends_with_the_ceo(client, db_session):
    """استثنای ناگزیر: آن پرونده مرحلهٔ HR ندارد، پس کسی جز مدیرعامل نمانده."""
    hr, ceo, person = _direct_ceo(db_session, hr_unit=True)
    record_id = _score_and_submit(client, db_session, ceo, person)

    record = db_session.get(EvaluationRecord, record_id)
    db_session.refresh(record)
    assert record.hr_review_skipped is True
    # ثبت، پرونده را مستقیم روی میزِ مدیرعامل می‌گذارد — نه در صفِ HR.
    assert record.status is EvaluationStatus.deputy_approved
    assert client.post(
        f"/api/evaluations/{record_id}/hr-approve", headers=auth_header(hr)
    ).status_code in (400, 403)

    final = client.post(f"/api/evaluations/{record_id}/ceo-finalize", headers=auth_header(ceo))
    assert final.status_code == 200, final.text
    assert final.json()["single_decider"] is True, "این‌جا افشا لازم است"
