"""«نیست» و «مالِ تو نیست» باید یک جوابِ یکسان بدهند.

شناسهٔ پرونده‌ها ترتیبی است (۱، ۲، ۳ …). تا امروز شناسهٔ ناموجود ۴۰۴ می‌گرفت و
پروندهٔ *دیگران* ۴۰۳ — یعنی هر کاربرِ واردشده می‌توانست شناسه‌ها را بشمارد و
نقشهٔ کاملی از «چند پرونده وجود دارد و کدام شناسه‌ها زنده‌اند» بسازد، بی آنکه
هیچ‌کدام را ببیند.

همین استدلال یک بار قبلاً در همین سامانه پذیرفته شده: صفحهٔ تأیید سند عمداً از
`evaluation_code`ِ ترتیبی استفاده نمی‌کند و توکنِ تصادفی می‌گیرد. و `me.py` هم
از ابتدا ۴۰۴ می‌داد («پرونده دیگران عمداً 404 برمی‌گردد، نه 403، تا وجودش هم لو
نرود»). این فایل همان قاعده را برای پنلِ ارزیابی قفل می‌کند.

**بدنهٔ پاسخ هم سنجیده می‌شود، نه فقط کد.** دو جوابِ ۴۰۴ با دو متنِ متفاوت،
دقیقاً همان چیزی را لو می‌دهند که کدِ یکسان پنهانش کرده بود.
"""
import pytest

from tests.helpers import (
    active_indicators,
    auth_header,
    full_valid_scores,
    make_access,
    make_personnel,
    make_user,
)


@pytest.fixture()
def a_case_that_is_not_yours(client, db_session):
    """یک پروندهٔ واقعی، و یک بیگانه که هیچ نسبتی با آن ندارد."""
    make_user(db_session, "hr")
    sup = make_user(db_session, "unit_supervisor")
    ceo = make_user(db_session, "ceo", capabilities=[])
    person = make_personnel(db_session)
    make_access(db_session, person, sup, None, ceo)

    outsider_person = make_personnel(db_session)
    outsider = make_user(db_session, "unit_supervisor", personnel_id=outsider_person.id)
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
    return {"id": record_id, "outsider": outsider}


def test_an_outsider_cannot_tell_an_existing_case_from_a_missing_one(
    client, a_case_that_is_not_yours
):
    headers = auth_header(a_case_that_is_not_yours["outsider"])
    real = a_case_that_is_not_yours["id"]

    existing = client.get(f"/api/evaluations/{real}", headers=headers)
    missing = client.get(f"/api/evaluations/{real + 10_000}", headers=headers)

    assert existing.status_code == missing.status_code == 404
    assert existing.json() == missing.json(), (
        "دو پاسخ باید حرف‌به‌حرف یکی باشند؛ متنِ متفاوت همان چیزی را لو می‌دهد "
        "که کدِ یکسان پنهانش کرده بود."
    )


def test_the_same_holds_for_the_official_document(client, a_case_that_is_not_yours):
    """سندِ رسمی هم همان در است، و همان جواب را باید بدهد."""
    headers = auth_header(a_case_that_is_not_yours["outsider"])
    real = a_case_that_is_not_yours["id"]

    existing = client.get(f"/api/evaluations/{real}/summary.pdf", headers=headers)
    missing = client.get(f"/api/evaluations/{real + 10_000}/summary.pdf", headers=headers)

    assert existing.status_code == missing.status_code == 404
    assert existing.json() == missing.json()


def test_someone_on_the_chain_still_gets_in(client, db_session, a_case_that_is_not_yours):
    """گاردِ ارزان در برابر «امن شد چون همه‌چیز ۴۰۴ است».

    اگر این تست نبود، بستنِ کاملِ endpoint هم تست‌های بالا را سبز می‌کرد.
    """
    from app.models.evaluation import EvaluationRecord
    from app.models.user import User

    record = db_session.get(EvaluationRecord, a_case_that_is_not_yours["id"])
    owner = db_session.get(User, record.unit_supervisor_user_id)

    assert client.get(
        f"/api/evaluations/{record.id}", headers=auth_header(owner)
    ).status_code == 200
