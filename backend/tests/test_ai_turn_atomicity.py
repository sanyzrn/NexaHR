"""نوبتی که شکست، هیچ ردی در گفت‌وگو نمی‌گذارد.

کاربر این را این‌طور دید: پیامش را می‌فرستاد، خطای سرویس می‌گرفت، دوباره
می‌فرستاد — و همان پرسش دو بار پشتِ سرِ هم در گفت‌وگو می‌نشست. زشتی‌اش
مهم‌ترین بخشش نبود.

مهم‌ترش این بود: پرسشِ بی‌جواب هم *پیامِ تاریخچه* حساب می‌شد. پنجرهٔ تاریخچه
دوازده‌تایی است، پس چند تلاشِ ناموفق کافی بود تا پیام‌های واقعی از پنجره
بیرون بروند. یعنی هرچه کاربر بیشتر تلاش می‌کرد، دستیار کمتر می‌دانست — و از
بیرون این دقیقاً شبیهِ «حافظه‌اش پاک شد» است.

پس قاعده: پیامِ کاربر فقط وقتی در گفت‌وگو می‌ماند که *جوابی* هم کنارش باشد.
اما دفترِ هزینه می‌ماند: نوبتِ شکسته الزاماً رایگان نبوده.
"""
import pytest
from sqlalchemy import func, select

from app.models.ai import AiConversation, AiMessage, AiUserAccess
from app.models.ai_usage import AiUsageLog
from app.models.enums import Capability
from tests.fake_llm import FailingAdapter, ScriptedAdapter, reset, response
from tests.helpers import auth_header, enable_ai_provider, make_user


@pytest.fixture
def hr(db_session):
    user = make_user(
        db_session, "hr", username="atomic_hr", capabilities=[Capability.manage_personnel]
    )
    enable_ai_provider(db_session)
    db_session.add(AiUserAccess(user_id=user.id, enabled=True))
    db_session.commit()
    return user


def _messages(db, user_id: int) -> list[AiMessage]:
    return list(
        db.scalars(
            select(AiMessage)
            .join(AiConversation, AiConversation.id == AiMessage.conversation_id)
            .where(AiConversation.user_id == user_id)
            .order_by(AiMessage.id)
        )
    )


def test_a_failed_turn_leaves_no_question_behind(client, db_session, hr, monkeypatch):
    monkeypatch.setattr("app.api.routers.ai.OpenAiCompatibleAdapter", FailingAdapter)
    reset(FailingAdapter)

    failed = client.post(
        "/api/ai/chat", json={"message": "پرسنل را وارد کن"}, headers=auth_header(hr)
    )
    assert failed.status_code == 502

    db_session.expire_all()
    assert _messages(db_session, hr.id) == []


def test_two_failed_attempts_do_not_stack_up(client, db_session, hr, monkeypatch):
    """همان چیزی که کاربر در تصویر نشان داد: یک پرسش، دو بار."""
    monkeypatch.setattr("app.api.routers.ai.OpenAiCompatibleAdapter", FailingAdapter)
    reset(FailingAdapter)

    for _ in range(2):
        assert (
            client.post(
                "/api/ai/chat", json={"message": "چه کارهایی می‌توانی بکنی؟"}, headers=auth_header(hr)
            ).status_code
            == 502
        )

    db_session.expire_all()
    assert [m.content for m in _messages(db_session, hr.id)] == []


def test_the_empty_conversation_does_not_survive_either(client, db_session, hr, monkeypatch):
    """وگرنه هر خطای سرویس یک «گفت‌وگوی بی‌نامِ» خالی در ستونِ تاریخچه می‌گذاشت."""
    monkeypatch.setattr("app.api.routers.ai.OpenAiCompatibleAdapter", FailingAdapter)
    reset(FailingAdapter)

    client.post("/api/ai/chat", json={"message": "سلام"}, headers=auth_header(hr))

    db_session.expire_all()
    left = db_session.scalar(
        select(func.count()).select_from(AiConversation).where(AiConversation.user_id == hr.id)
    )
    assert left == 0


def test_an_existing_conversation_is_never_deleted_by_a_failure(
    client, db_session, hr, monkeypatch
):
    """مرزِ پاک‌کردن: فقط گفت‌وگویی که *همین نوبت* ساخته و خالی مانده.

    بی این مرز، یک خطای سرویس می‌توانست گفت‌وگوی دیروزِ کاربر را ببرد.
    """
    monkeypatch.setattr("app.api.routers.ai.OpenAiCompatibleAdapter", ScriptedAdapter)
    reset(ScriptedAdapter)
    ScriptedAdapter.script = [response(content="سلام، در خدمتم.")]
    first = client.post("/api/ai/chat", json={"message": "سلام"}, headers=auth_header(hr))
    assert first.status_code == 200
    convo_id = first.json()["conversation_id"]

    monkeypatch.setattr("app.api.routers.ai.OpenAiCompatibleAdapter", FailingAdapter)
    reset(FailingAdapter)
    client.post(
        "/api/ai/chat",
        json={"conversation_id": convo_id, "message": "حالا کاری بکن"},
        headers=auth_header(hr),
    )

    db_session.expire_all()
    assert db_session.get(AiConversation, convo_id) is not None
    # و فقط همان جفتِ سالمِ نوبتِ اول مانده است.
    assert [m.role for m in _messages(db_session, hr.id)] == ["user", "assistant"]


def test_an_empty_but_pre_existing_conversation_survives_a_failure(
    client, db_session, hr, monkeypatch
):
    """مرزِ واقعی، و دلیلِ اینکه `conversation_was_new` لازم است.

    گفت‌وگوی *خالی* لزوماً «تازه‌ساختهٔ همین نوبت» نیست: رابط پیش از بارگذاری
    فایل یک گفت‌وگو می‌سازد و پیوست را به آن می‌چسباند، پس گفت‌وگویی وجود
    دارد که هیچ پیامی ندارد ولی یک فایل دارد. اگر شرطِ پاک‌کردن فقط
    «پیامی ندارد» بود، اولین خطای سرویس آن گفت‌وگو را می‌برد — و پیوستش را
    هم با خودش (کلیدِ خارجی CASCADE است). یعنی کاربر فایلِ بارگذاری‌شده‌اش را
    از دست می‌داد.
    """
    made = client.post("/api/ai/conversations", headers=auth_header(hr))
    assert made.status_code == 201
    convo_id = made.json()["id"]

    monkeypatch.setattr("app.api.routers.ai.OpenAiCompatibleAdapter", FailingAdapter)
    reset(FailingAdapter)
    client.post(
        "/api/ai/chat",
        json={"conversation_id": convo_id, "message": "این فایل را بررسی کن"},
        headers=auth_header(hr),
    )

    db_session.expire_all()
    assert db_session.get(AiConversation, convo_id) is not None


def test_the_cost_of_a_failed_turn_is_still_recorded(client, db_session, hr, monkeypatch):
    """مرزِ دیگر: پاک‌کردنِ پیام نباید دفترِ هزینه را هم ببرد.

    نوبتی که در پلهٔ چهارم می‌شکند، سه درخواستِ موفق پشتِ سرش دارد و هر سه
    پول خرج کرده‌اند.
    """
    monkeypatch.setattr("app.api.routers.ai.OpenAiCompatibleAdapter", FailingAdapter)
    reset(FailingAdapter)

    client.post("/api/ai/chat", json={"message": "سلام"}, headers=auth_header(hr))

    db_session.expire_all()
    rows = list(db_session.scalars(select(AiUsageLog).where(AiUsageLog.user_id == hr.id)))
    assert len(rows) == 1
    assert rows[0].failed is True


def test_a_successful_turn_still_keeps_both_sides(client, db_session, hr, monkeypatch):
    """قاعده نباید آن‌قدر پهن شود که نوبتِ سالم را هم پاک کند."""
    monkeypatch.setattr("app.api.routers.ai.OpenAiCompatibleAdapter", ScriptedAdapter)
    reset(ScriptedAdapter)
    ScriptedAdapter.script = [response(content="بله.")]

    assert (
        client.post(
            "/api/ai/chat", json={"message": "هستی؟"}, headers=auth_header(hr)
        ).status_code
        == 200
    )

    db_session.expire_all()
    rows = _messages(db_session, hr.id)
    assert [m.role for m in rows] == ["user", "assistant"]
    assert rows[0].content == "هستی؟"
