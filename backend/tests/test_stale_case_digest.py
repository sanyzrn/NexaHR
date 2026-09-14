"""یک جملهٔ روزانه در دستیار، به‌جای نُه ردیفِ زنگِ اعلان.

زنگِ اعلان به‌ازای *هر* پروندهٔ عقب‌افتاده یک ردیف می‌سازد. برای معاونتی با
نُه پروندهٔ گیرکرده، نُه ردیف یعنی هیچ — خوانده نمی‌شود و مثل نویز کنار
می‌رود. این جارو همان دادهٔ `run_sla_sweep` را *جمع* می‌بندد و در دستیارِ
خودِ آن آدم می‌گذارد.

دو تصمیمِ این فایل که ارزشِ تست دارند و ظاهری نیستند:

* **گفت‌وگوی جدا.** تاریخچهٔ هر گفت‌وگو در نوبتِ بعد به خودِ مدل داده می‌شود.
  تزریقِ گزارشِ خودکار وسطِ گفت‌وگوی جاری یعنی مدل آن فهرست را «حرفِ قبلیِ
  خودش» می‌بیند و از آن نتیجه می‌گیرد.
* **یک پیام در روز، با مرزِ روزِ محلی.** با UTC، اجرای ۰۱:۰۰ بامدادِ تهران
  پیامِ دومِ «دیروز» را می‌ساخت.
"""
from datetime import UTC, datetime, timedelta

import pytest

from app.models.ai import AiConversation, AiMessage, AiUserAccess
from app.models.enums import EvaluationStatus
from app.models.evaluation import EvaluationRecord
from app.services.scheduled import DIGEST_TITLE, run_stale_case_digest_sweep
from tests.helpers import enable_ai_provider, make_access, make_personnel, make_user


@pytest.fixture()
def stalled(db_session):
    """یک پروندهٔ باز که ده روز است در مرحلهٔ مسئولِ واحد مانده."""
    supervisor = make_user(db_session, "unit_supervisor", capabilities=[])
    deputy = make_user(db_session, "deputy", capabilities=[])
    ceo = make_user(db_session, "ceo", capabilities=[])
    person = make_personnel(db_session, full_name="کسی که پرونده‌اش مانده")
    make_access(db_session, person, supervisor, deputy, ceo)
    record = EvaluationRecord(
        evaluation_code="DG-1",
        subject_personnel_id=person.id,
        unit_supervisor_user_id=supervisor.id,
        deputy_user_id=deputy.id,
        ceo_user_id=ceo.id,
        status=EvaluationStatus.draft,
        stage_entered_at=datetime.now(UTC) - timedelta(days=10),
    )
    db_session.add(record)
    enable_ai_provider(db_session)
    db_session.add(AiUserAccess(user_id=supervisor.id, enabled=True))
    db_session.commit()
    return {"supervisor": supervisor, "record": record, "deputy": deputy}


def _digest_messages(db, user_id) -> list[AiMessage]:
    convo = db.scalar(
        db.query(AiConversation)
        .filter(AiConversation.user_id == user_id, AiConversation.title == DIGEST_TITLE)
        .statement
    )
    if convo is None:
        return []
    return list(db.scalars(db.query(AiMessage).filter(AiMessage.conversation_id == convo.id).statement))


def test_the_owner_of_a_stalled_case_gets_one_message(db_session, stalled):
    assert run_stale_case_digest_sweep(db_session) == 1
    db_session.commit()

    messages = _digest_messages(db_session, stalled["supervisor"].id)
    assert len(messages) == 1
    body = messages[0].content
    assert "DG-1" in body
    assert "کسی که پرونده‌اش مانده" in body
    assert "۱۰ روز" in body


def test_it_does_not_propose_anything(db_session, stalled):
    """گزارش می‌دهد؛ اقدام را آدم از دستیار می‌خواهد.

    پیامی که خودش کاری پیشنهاد کند، از قراردادِ «مدل پیشنهاد می‌دهد، کاربر
    تصمیم می‌گیرد» رد می‌شود — بی اینکه هیچ کارتِ تأییدی وسط باشد.
    """
    run_stale_case_digest_sweep(db_session)
    db_session.commit()

    body = _digest_messages(db_session, stalled["supervisor"].id)[0]
    assert body.actions_json == ""
    assert body.meta_json == ""


def test_only_one_message_a_day(db_session, stalled):
    assert run_stale_case_digest_sweep(db_session) == 1
    db_session.commit()
    assert run_stale_case_digest_sweep(db_session) == 0
    db_session.commit()

    assert len(_digest_messages(db_session, stalled["supervisor"].id)) == 1


def test_it_uses_a_conversation_of_its_own(db_session, stalled):
    """وگرنه گزارش به متنِ زمینهٔ گفت‌وگوی جاری قاچاق می‌شود."""
    ongoing = AiConversation(user_id=stalled["supervisor"].id, title="بحثِ دیروز")
    db_session.add(ongoing)
    db_session.commit()

    run_stale_case_digest_sweep(db_session)
    db_session.commit()

    in_ongoing = db_session.scalars(
        db_session.query(AiMessage).filter(AiMessage.conversation_id == ongoing.id).statement
    ).all()
    assert list(in_ongoing) == [], "گفت‌وگوی کاربر باید دست‌نخورده بماند"
    assert len(_digest_messages(db_session, stalled["supervisor"].id)) == 1


def test_someone_without_the_assistant_gets_nothing(db_session, stalled):
    """پیامی در پنجره‌ای که کاربر نمی‌بیند، ردیفِ مرده است."""
    db_session.query(AiUserAccess).filter(
        AiUserAccess.user_id == stalled["supervisor"].id
    ).delete()
    db_session.commit()

    assert run_stale_case_digest_sweep(db_session) == 0
    db_session.commit()
    assert _digest_messages(db_session, stalled["supervisor"].id) == []


def test_the_global_switch_wins(db_session, stalled):
    from app.models.ai import AiSettings

    db_session.merge(AiSettings(id=1, enabled=False))
    db_session.commit()

    assert run_stale_case_digest_sweep(db_session) == 0


def test_a_fresh_case_is_not_reported(db_session, stalled):
    """معیار، «مدتِ ماندن در همین مرحله» است — نه سنِ پرونده."""
    stalled["record"].stage_entered_at = datetime.now(UTC)
    db_session.commit()

    assert run_stale_case_digest_sweep(db_session) == 0


def test_it_goes_to_the_owner_of_the_current_stage_only(db_session, stalled):
    """معاونت در مرحلهٔ `draft` صاحبِ پرونده نیست و نباید گزارش بگیرد."""
    db_session.add(AiUserAccess(user_id=stalled["deputy"].id, enabled=True))
    db_session.commit()

    assert run_stale_case_digest_sweep(db_session) == 1
    db_session.commit()
    assert _digest_messages(db_session, stalled["deputy"].id) == []


def test_a_long_list_is_summarised_not_dumped(db_session, stalled):
    """فهرستِ چهل‌ردیفی خوانده نمی‌شود و هدفِ «یک نگاه» را از بین می‌برد."""
    supervisor = stalled["supervisor"]
    ceo = make_user(db_session, "ceo", capabilities=[])
    for index in range(8):
        person = make_personnel(db_session, full_name=f"نفر {index}")
        db_session.add(
            EvaluationRecord(
                evaluation_code=f"DG-X{index}",
                subject_personnel_id=person.id,
                unit_supervisor_user_id=supervisor.id,
                ceo_user_id=ceo.id,
                status=EvaluationStatus.draft,
                # همه چهار روزه: تنها پروندهٔ ده‌روزه همان DG-1 است، پس
                # ترتیبِ «پیرترین اول» یک ادعای بی‌ابهام می‌شود.
                stage_entered_at=datetime.now(UTC) - timedelta(days=4),
            )
        )
    db_session.commit()

    run_stale_case_digest_sweep(db_session)
    db_session.commit()

    body = _digest_messages(db_session, supervisor.id)[0].content
    assert body.count("\n- ") <= 6, "حداکثر پنج پرونده به‌علاوهٔ سطرِ «و n پروندهٔ دیگر»"
    assert "پروندهٔ دیگر" in body
    # پیرترین اول: کسی که یک نگاه می‌کند باید بدترین را اول ببیند
    assert body.index("DG-1") < body.index("DG-X"), "پیرترین باید اولِ فهرست باشد"
