"""موضوعِ ارزیابی بودن به نقش کاری ندارد — و در چهار جا داشت.

`require_own_personnel` این تفکیک را برای مسیرهای `/api/me` انجام داد: «چه کسی
ارزیابی می‌شود» با «چه نقشی در زنجیره دارد» یکی نیست. ولی چهار جای دیگر همچنان
نقش را می‌سنجیدند، و نتیجه‌اش برای غیرِ کارمندها این بود:

* دانلودِ سندِ رسمیِ *خودش* ۴۰۳ می‌گرفت — با پیامی دربارهٔ «رسیدگی به پروندهٔ
  خود» که به درخواستش ربطی نداشت، چون کنترل به `ensure_not_deciding_about_oneself`
  می‌افتاد؛
* اعلانِ «ارزیابی شما نهایی شد» هرگز به او نمی‌رسید؛
* مسیرِ `/me` در رابط او را به خانه برمی‌گرداند؛
* و لینکِ «کارنامه من» در منویش نبود.

سخت‌ترین حالتش کارمندانِ منابع انسانی‌اند: کلِ ماشینِ `hr_review_skipped` و
`objection_resolver_field` برای ارزیابیِ همین آدم‌ها نوشته شده — و همان آدم‌ها
نه نتیجه را می‌دیدند، نه می‌توانستند رؤیت بزنند، نه از مسیرِ اعتراضی که کد
به‌دقت به معاونت یا مدیرعامل می‌بَرد استفاده کنند.
"""
import pytest

from app.models.enums import EvaluationStatus
from app.models.evaluation import EvaluationRecord
from app.models.notification import Notification
from tests.helpers import (
    active_indicators,
    auth_header,
    full_valid_scores,
    make_access,
    make_personnel,
    make_user,
)

#: نقش‌هایی که در زنجیره کار می‌کنند و *خودشان هم* ارزیابی می‌شوند. `support`
#: این‌جا نیست: حسابِ نگهداریِ سامانه پروندهٔ پرسنلی ندارد و موضوعِ ارزیابی نیست.
SUBJECT_ROLES = ["employee", "unit_supervisor", "deputy", "ceo", "hr"]


#: نمایِ خودِ کارمند پیش‌فرض خاموش است و این فایل رفتارِ *روشن* را می‌سنجد.
pytestmark = pytest.mark.usefixtures("employee_view_on")


def _finalized_case_for(client, db_session, role: str):
    """پروندهٔ نهایی‌شدهٔ یک نفر که خودش حسابی با نقشِ `role` دارد.

    زنجیره‌اش را کسانِ دیگری می‌گردانند، تا آنچه سنجیده می‌شود «سوژه بودن»
    باشد و نه «در زنجیره بودن».
    """
    sup = make_user(db_session, "unit_supervisor", capabilities=[])
    dep = make_user(db_session, "deputy", capabilities=[])
    ceo = make_user(db_session, "ceo", capabilities=[])
    hr = make_user(db_session, "hr")
    subject = make_personnel(db_session, full_name=f"سوژهٔ {role}")
    actor = make_user(db_session, role, personnel_id=subject.id, capabilities=[])
    make_access(db_session, subject, sup, dep, ceo)
    db_session.commit()

    record_id = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": subject.id},
        headers=auth_header(sup),
    ).json()["id"]
    client.put(
        f"/api/evaluations/{record_id}/scores",
        json={"scores": full_valid_scores(active_indicators(db_session))},
        headers=auth_header(sup),
    )
    for path, who in (("submit", sup), ("hr-approve", hr), ("deputy-approve", dep),
                      ("ceo-finalize", ceo)):
        done = client.post(f"/api/evaluations/{record_id}/{path}", headers=auth_header(who))
        assert done.status_code == 200, (role, path, done.text)
    db_session.expire_all()
    assert db_session.get(EvaluationRecord, record_id).status is EvaluationStatus.finalized
    return actor, record_id


@pytest.mark.parametrize("role", SUBJECT_ROLES)
def test_a_subject_of_any_role_can_read_its_own_result(client, db_session, role):
    actor, record_id = _finalized_case_for(client, db_session, role)
    listed = client.get("/api/me/evaluations", headers=auth_header(actor))
    assert listed.status_code == 200, (role, listed.text)
    assert [item["id"] for item in listed.json()["items"]] == [record_id]


@pytest.mark.parametrize("role", SUBJECT_ROLES)
def test_a_subject_of_any_role_can_download_its_own_document(client, db_session, role):
    """همان ۴۰۳ی که گزارش ممیزی با یک probe نشانش داد."""
    actor, record_id = _finalized_case_for(client, db_session, role)
    got = client.get(
        f"/api/evaluations/{record_id}/summary.pdf", headers=auth_header(actor)
    )
    # ۵۰۰ تنها حالتِ پذیرفتنی است و آن هم فقط وقتی WeasyPrint نصب نباشد؛
    # چیزی که این تست می‌سنجد ۴۰۳ *نبودن* است.
    assert got.status_code != 403, (role, got.text)
    if got.status_code == 500:
        pytest.skip("WeasyPrint روی این سرور نیست؛ گاردِ دسترسی سنجیده شد")
    assert got.status_code == 200, (role, got.text)
    assert got.content[:4] == b"%PDF"


@pytest.mark.parametrize("role", SUBJECT_ROLES)
def test_a_subject_of_any_role_can_acknowledge_and_object(client, db_session, role):
    actor, record_id = _finalized_case_for(client, db_session, role)
    acked = client.post(
        f"/api/me/evaluations/{record_id}/acknowledge", headers=auth_header(actor)
    )
    assert acked.status_code == 200, (role, acked.text)
    objected = client.post(
        f"/api/me/evaluations/{record_id}/object",
        json={"reason": "به وزنِ شاخص سوم اعتراض دارم و توضیح می‌خواهم"},
        headers=auth_header(actor),
    )
    assert objected.status_code == 200, (role, objected.text)


@pytest.mark.parametrize("role", SUBJECT_ROLES)
def test_a_subject_of_any_role_is_told_its_case_was_finalized(client, db_session, role):
    """اعلانِ «دربارهٔ خودت» — پیش از این `User.role == employee` فیلترش می‌کرد."""
    actor, record_id = _finalized_case_for(client, db_session, role)
    db_session.expire_all()
    mine = [
        n.type
        for n in db_session.query(Notification).filter(Notification.user_id == actor.id).all()
    ]
    assert "evaluation_finalized_self" in mine, (role, mine)


def test_a_case_the_person_is_not_the_subject_of_stays_closed(client, db_session):
    """گارد شل نشده: «سوژه بودن» یعنی همان پرسنل، نه «هر نقشی»."""
    actor, record_id = _finalized_case_for(client, db_session, "unit_supervisor")
    outsider_p = make_personnel(db_session, full_name="بیگانه")
    outsider = make_user(
        db_session, "unit_supervisor", personnel_id=outsider_p.id, capabilities=[]
    )
    db_session.commit()
    refused = client.get(
        f"/api/evaluations/{record_id}/summary.pdf", headers=auth_header(outsider)
    )
    assert refused.status_code in (403, 404), refused.text
