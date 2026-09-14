"""جلسهٔ طولانی نباید وسطش قطع شود.

پنجرهٔ تاریخچه دوازده پیام است. در جلسهٔ چهل‌پیامیِ اصلاحِ اکسل، مدل
پیام‌های ۱ تا ۲۸ را *اصلاً* نمی‌بیند: نه فایلی که اول کار معرفی شد، نه
تصمیمی که وسطِ راه گرفته شد. از بیرون این‌طور دیده می‌شود که «دستیار یادش
رفت».

بزرگ‌کردنِ پنجره جوابش نیست — هزینهٔ هر نوبت خطی بالا می‌رود. پس دوازده
پیامِ آخر دست‌نخورده می‌ماند و بیرون‌افتاده‌ها در یک پاراگراف جمع می‌شوند.

سه ادعایی که این فایل می‌سنجد و هیچ‌کدام ظاهری نیستند:

۱. **خلاصهٔ قبلی در درخواستِ بعدی می‌رود.** بی آن، هر بازسازی از صفر شروع
   می‌شود و نیمهٔ اولِ جلسه برای همیشه گم می‌شود.
۲. **هزینه‌اش شمرده می‌شود.** فراخوانیِ پنهانِ سامانه‌ای که در دفترِ هزینه
   نیاید، همان کم‌گوییِ دفتر است.
۳. **شکستِ خلاصه نوبت را نمی‌شکند.**
"""
import asyncio

from app.models.ai import AiConversation, AiMessage, AiUserAccess
from app.models.ai_usage import AiUsageLog
from app.services.ai import summary as summary_service
from tests.fake_llm import ScriptedAdapter, reset, response
from tests.helpers import auth_header, enable_ai_provider, make_user


def _refresh(db, convo, adapter, *, window=12):
    """`refresh` async است و این مجموعه پلاگینِ asyncio ندارد.

    همان الگوی `test_ai_error_reporting.py`: یک حلقهٔ کوتاه به‌جای یک
    وابستگیِ تازه برای چهار تست.
    """
    return asyncio.run(summary_service.refresh(db, convo, adapter, window=window))


def _convo_with(db, user, count: int, summary: str = "", through: int = 0) -> AiConversation:
    convo = AiConversation(
        user_id=user.id, title="جلسه", summary_text=summary, summary_through_message_id=through
    )
    db.add(convo)
    db.flush()
    for index in range(count):
        db.add(
            AiMessage(
                conversation_id=convo.id,
                role="user" if index % 2 == 0 else "assistant",
                content=f"پیام {index}",
            )
        )
    db.commit()
    return convo


# ── شکلِ درخواستِ خلاصه‌سازی، بی هیچ سرویسی ────────────────────────────────


def test_the_previous_summary_travels_with_the_new_chunk(db_session):
    """وگرنه هر بازسازی از صفر شروع می‌شود و نیمهٔ اول گم می‌شود."""
    user = make_user(db_session, "hr", capabilities=[])
    convo = _convo_with(db_session, user, 4, summary="قبلاً دربارهٔ فایل حرف زدیم.")
    pending = list(db_session.scalars(db_session.query(AiMessage).statement))

    messages = summary_service.build_prompt(convo, pending)

    body = messages[-1].content
    assert "قبلاً دربارهٔ فایل حرف زدیم." in body
    assert "پیام 0" in body
    assert messages[0].role == "system"


def test_the_first_summary_carries_no_empty_preamble(db_session):
    user = make_user(db_session, "hr", capabilities=[])
    convo = _convo_with(db_session, user, 2)
    pending = list(db_session.scalars(db_session.query(AiMessage).statement))

    body = summary_service.build_prompt(convo, pending)[-1].content
    assert "خلاصهٔ قبلی" not in body


# ── چه وقت به‌روز می‌شود ──────────────────────────────────────────────────


def test_a_short_conversation_is_left_alone(db_session):
    """دوازده پیامِ آخر همیشه دست‌نخورده‌اند؛ گفت‌وگوی کوتاه هیچ هزینه‌ای ندارد."""
    user = make_user(db_session, "hr", capabilities=[])
    convo = _convo_with(db_session, user, 10)
    reset(ScriptedAdapter)
    ScriptedAdapter.script = [response(content="نباید صدا زده شود")]

    result = _refresh(db_session, convo, ScriptedAdapter)

    assert result.updated is False
    assert result.calls == 0
    assert ScriptedAdapter.seen == []


def test_messages_that_fell_out_of_the_window_get_folded(db_session):
    user = make_user(db_session, "hr", capabilities=[])
    convo = _convo_with(db_session, user, 20)
    reset(ScriptedAdapter)
    ScriptedAdapter.script = [response(content="دربارهٔ اکسل پرسنل حرف زدند.")]

    result = _refresh(db_session, convo, ScriptedAdapter)

    assert result.updated is True
    assert convo.summary_text == "دربارهٔ اکسل پرسنل حرف زدند."
    # هشت پیامِ اول بیرون از پنجره‌اند و تا همان‌جا علامت می‌خورد
    assert convo.summary_through_message_id > 0
    folded = summary_service._pending_messages(db_session, convo, 12)
    assert folded == [], "دوباره خلاصه نمی‌شوند"


def test_a_failing_service_leaves_the_old_summary_alone(db_session):
    """بدترین حالتش این است که مدل همان چیزی را ببیند که تا دیروز می‌دید."""
    from tests.fake_llm import FailingAdapter

    user = make_user(db_session, "hr", capabilities=[])
    convo = _convo_with(db_session, user, 20, summary="خلاصهٔ دیروز")
    reset(FailingAdapter)
    FailingAdapter.script = [response(content="بی‌ربط")]

    result = _refresh(db_session, convo, FailingAdapter)

    assert result.updated is False
    assert convo.summary_text == "خلاصهٔ دیروز"


def test_an_empty_answer_is_not_stored_as_a_summary(db_session):
    user = make_user(db_session, "hr", capabilities=[])
    convo = _convo_with(db_session, user, 20, summary="خلاصهٔ دیروز")
    reset(ScriptedAdapter)
    ScriptedAdapter.script = [response(content="   ")]

    result = _refresh(db_session, convo, ScriptedAdapter)

    assert result.updated is False
    assert convo.summary_text == "خلاصهٔ دیروز"


# ── و از راهِ واقعیِ نوبت ──────────────────────────────────────────────────


def _enable(db, user):
    enable_ai_provider(db)
    db.add(AiUserAccess(user_id=user.id, enabled=True))
    db.commit()


def test_the_summary_reaches_the_model_and_its_cost_reaches_the_ledger(
    client, db_session, monkeypatch
):
    """دو ادعا در یک نوبت، چون یک چیزند: کارِ پنهان باید هم دیده شود هم شمرده.

    گفت‌وگو آن‌قدر بلند است که خلاصه‌سازی لازم شود، پس آداپتور دو بار صدا
    می‌خورَد: یک بار برای خودِ جواب و یک بار برای خلاصه. هر دو در یک ردیفِ
    دفتر می‌نشینند.
    """
    user = make_user(db_session, "hr", username="sm_user", capabilities=[])
    _enable(db_session, user)
    convo = _convo_with(db_session, user, 20)
    monkeypatch.setattr("app.api.routers.ai.OpenAiCompatibleAdapter", ScriptedAdapter)
    reset(ScriptedAdapter)
    ScriptedAdapter.script = [
        response(content="بله.", usage={"prompt_tokens": 50, "completion_tokens": 5}),
        response(content="خلاصهٔ تازه.", usage={"prompt_tokens": 200, "completion_tokens": 20}),
    ]

    body = client.post(
        "/api/ai/chat",
        json={"message": "ادامه بده", "conversation_id": convo.id},
        headers=auth_header(user),
    )
    assert body.status_code == 200, body.text

    db_session.expire_all()
    assert db_session.get(AiConversation, convo.id).summary_text == "خلاصهٔ تازه."

    row = db_session.scalars(db_session.query(AiUsageLog).statement).one()
    assert row.calls == 2, "فراخوانیِ خلاصه هم یک درخواست است"
    assert row.total_tokens == 275, "۵۵ نوبت + ۲۲۰ خلاصه"


def test_the_stored_summary_is_shown_to_the_model_next_turn(client, db_session, monkeypatch):
    user = make_user(db_session, "hr", username="sm_reader", capabilities=[])
    _enable(db_session, user)
    convo = _convo_with(db_session, user, 4, summary="پیش‌تر دربارهٔ واحدِ مالی حرف زدیم.")
    monkeypatch.setattr("app.api.routers.ai.OpenAiCompatibleAdapter", ScriptedAdapter)
    reset(ScriptedAdapter)
    ScriptedAdapter.script = [response(content="باشد.")]

    client.post(
        "/api/ai/chat",
        json={"message": "خب؟", "conversation_id": convo.id},
        headers=auth_header(user),
    )

    system_prompt = ScriptedAdapter.seen[0][0].content
    assert "پیش‌تر دربارهٔ واحدِ مالی حرف زدیم." in system_prompt
    # و زیرِ همان پوششِ «دادهٔ نامطمئن» که بقیهٔ متنِ کاربر دارد
    assert "خلاصهٔ بخشِ قبلیِ همین گفت‌وگو" in system_prompt


# ── و همان مسئله، یک لایه پایین‌تر: پیوست‌ها ───────────────────────────────


def _upload(db, convo, name: str):
    from app.models.ai import AiUpload

    row = AiUpload(
        conversation_id=convo.id,
        user_id=convo.user_id,
        filename=name,
        mime_type="application/vnd.ms-excel",
        size_bytes=10,
        content=b"x",
        structure_json='{"kind": "excel"}',
    )
    db.add(row)
    db.flush()
    return row


def test_every_attachment_of_the_conversation_is_introduced(db_session):
    """سقفِ سه‌تایی، ارجاعِ «همان فایلِ اول» را بی‌جواب می‌گذاشت.

    در جلسهٔ اصلاحِ اکسل، چهارمین فایل که بارگذاری می‌شد اولی از یادِ مدل
    می‌رفت — و کاربر فقط می‌دید که دستیار فایلی را که خودش معرفی کرده بود
    نمی‌شناسد.
    """
    from app.services.ai.orchestrator import _attachments_note

    user = make_user(db_session, "hr", capabilities=[])
    convo = _convo_with(db_session, user, 0)
    for index in range(5):
        _upload(db_session, convo, f"فایل-{index}.xlsx")
    db_session.commit()

    note = _attachments_note(db_session, convo.id)
    for index in range(5):
        assert f"فایل-{index}.xlsx" in note


def test_a_flood_of_attachments_is_capped_and_says_so(db_session):
    """سقفِ ایمنی می‌ماند — ولی ساکت نیست.

    فهرستی که بی‌صدا بریده شود، همان خرابیِ قبلی است با عددِ بزرگ‌تر: مدل
    فکر می‌کند همهٔ فایل‌ها را دیده.
    """
    from app.services.ai.orchestrator import _ATTACHMENT_LIMIT, _attachments_note

    user = make_user(db_session, "hr", capabilities=[])
    convo = _convo_with(db_session, user, 0)
    for index in range(_ATTACHMENT_LIMIT + 3):
        _upload(db_session, convo, f"ف-{index}.xlsx")
    db_session.commit()

    note = _attachments_note(db_session, convo.id)
    assert note.count("\n- ") + 1 == _ATTACHMENT_LIMIT + 1
    assert "۳ فایلِ قدیمی‌تر" in note or "3 فایلِ قدیمی‌تر" in note
