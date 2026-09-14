"""دفترِ هزینهٔ دستیار: چیزی که سرویس گفت، همان‌جا بماند.

تا امروز `usage` از سرویس می‌آمد، به فرانت پاس داده می‌شد و با پایانِ
درخواست دور ریخته می‌شد. یعنی سامانه‌ای که هر پیامش پول خرج می‌کند،
نمی‌توانست بگوید این ماه چقدر و دستِ چه کسی — و آن عدد اولین بار در
صورت‌حسابِ سرویس دیده می‌شد.

سه چیزِ این فایل مهم‌تر از «ردیف ثبت شد» است، چون هر سه *بی‌صدا* غلط
می‌شدند:

۱. **جمع، نه جایگزین.** حلقهٔ ابزار در یک نوبت چند بار به سرویس می‌رود و کدِ
   قبلی فقط مصرفِ آخرین پله را نگه می‌داشت.
۲. **نوبتِ شکست‌خورده هم هزینه دارد.** درخواست‌های موفقِ پیش از خطا پول
   خرج کرده‌اند.
۳. **دو خانوادهٔ نام‌گذاری.** سرویس‌های سازگار با OpenAI
   `prompt_tokens` می‌دهند و خانوادهٔ Anthropic `input_tokens`. دفتری که
   یکی را نشناسد، برای نیمی از سرویس‌ها صفر می‌ماند.
"""
import pytest

from app.models.ai import AiUserAccess
from app.models.ai_usage import AiUsageLog
from app.models.enums import Capability
from app.services.ai.usage import normalize
from tests.fake_llm import FailingAdapter, ScriptedAdapter, reset, response, tool_call
from tests.helpers import auth_header, enable_ai_provider, make_personnel, make_user


def _enable_for(db, user, **access_kwargs):
    enable_ai_provider(db)
    db.add(AiUserAccess(user_id=user.id, enabled=True, **access_kwargs))
    db.commit()


def _rows(db) -> list[AiUsageLog]:
    return list(db.scalars(db.query(AiUsageLog).order_by(AiUsageLog.id).statement))


# ── نرمال‌سازی: همان یک تابع، بی دیتابیس ───────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # سازگار با OpenAI
        (
            {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
            (10, 4, 14),
        ),
        # خانوادهٔ Anthropic — همان چیز، نامِ دیگر
        ({"input_tokens": 10, "output_tokens": 4}, (10, 4, 14)),
        # جمع داده نشده: از دو تای دیگر ساخته می‌شود
        ({"prompt_tokens": 7, "completion_tokens": 3}, (7, 3, 10)),
        # جمع داده شده ولی تفکیک نه: حدس زده نمی‌شود
        ({"total_tokens": 9}, (0, 0, 9)),
        # آشغال، به هر شکلی
        ({}, (0, 0, 0)),
        (None, (0, 0, 0)),
        ("نه یک دیکشنری", (0, 0, 0)),
        ({"prompt_tokens": "چند"}, (0, 0, 0)),
        # `True` عددِ ۱ نیست؛ دادهٔ خراب است
        ({"prompt_tokens": True, "completion_tokens": 5}, (0, 5, 5)),
        # عددِ منفی از سرویس معنا ندارد و نباید جمع را کم کند
        ({"prompt_tokens": -3, "completion_tokens": 5}, (0, 5, 5)),
    ],
)
def test_normalize_speaks_both_dialects(raw, expected):
    numbers = normalize(raw)
    assert (
        numbers["prompt_tokens"],
        numbers["completion_tokens"],
        numbers["total_tokens"],
    ) == expected


# ── و همان چیز، از راهِ واقعیِ endpoint ────────────────────────────────────


def test_a_multi_step_turn_adds_up_instead_of_overwriting(client, db_session, monkeypatch):
    """مهم‌ترین تستِ این فایل.

    کدِ قبلی `usage = response.usage or usage` بود: مصرفِ *آخرین* پله می‌ماند
    و بقیه دور ریخته می‌شد. در نوبتی با سه درخواست، آن یعنی دفتر یک‌سومِ
    واقعیت را می‌گفت — و دفتری که کم‌تر از واقعیت بگوید، از نداشتنش بدتر
    است، چون به آن اعتماد می‌شود.
    """
    from app.services.ai.tools import people  # noqa: F401  (ثبت ابزارها)

    user = make_user(
        db_session, "hr", username="led_multi", capabilities=[Capability.manage_personnel]
    )
    make_personnel(db_session, full_name="کارمند تست")
    _enable_for(db_session, user)
    monkeypatch.setattr("app.api.routers.ai.OpenAiCompatibleAdapter", ScriptedAdapter)
    reset(ScriptedAdapter)
    ScriptedAdapter.script = [
        response(
            content="می‌جستم…",
            calls=[tool_call("c1", "search_personnel", {"q": "تست"})],
            usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        ),
        response(
            content="پیدا شد.",
            usage={"prompt_tokens": 300, "completion_tokens": 10, "total_tokens": 310},
        ),
    ]

    body = client.post(
        "/api/ai/chat", json={"message": "کارمند تست کیست؟"}, headers=auth_header(user)
    )
    assert body.status_code == 200, body.text

    rows = _rows(db_session)
    assert len(rows) == 1, "هر نوبت یک ردیف، نه یکی به‌ازای هر درخواست"
    row = rows[0]
    assert (row.prompt_tokens, row.completion_tokens, row.total_tokens) == (400, 30, 430)
    assert row.calls == 2, "دو درخواست به سرویس رفت"
    assert row.failed is False
    # و همان عدد به خودِ کاربر هم برمی‌گردد
    assert body.json()["usage"]["total_tokens"] == 430


def test_a_turn_that_reports_nothing_leaves_no_row(client, db_session, monkeypatch):
    """دفتری که پر از صفر باشد، خواندنش سخت‌تر از نداشتنش است."""
    user = make_user(db_session, "hr", username="led_silent", capabilities=[])
    _enable_for(db_session, user)
    monkeypatch.setattr("app.api.routers.ai.OpenAiCompatibleAdapter", ScriptedAdapter)
    reset(ScriptedAdapter)
    ScriptedAdapter.script = [response(content="سلام.")]  # بی `usage`

    assert client.post(
        "/api/ai/chat", json={"message": "سلام"}, headers=auth_header(user)
    ).status_code == 200
    assert _rows(db_session) == []


def test_a_failed_turn_is_still_written_down(client, db_session, monkeypatch):
    """شکست رایگان نیست — و ردیفِ شکست‌خورده همان چیزی است که تفاوتِ جمعِ
    دفتر با جمعِ صورت‌حساب را توضیح می‌دهد."""
    user = make_user(db_session, "hr", username="led_fail", capabilities=[])
    _enable_for(db_session, user)
    monkeypatch.setattr("app.api.routers.ai.OpenAiCompatibleAdapter", FailingAdapter)
    reset(FailingAdapter)
    FailingAdapter.script = [response(content="بی‌ربط")]

    assert client.post(
        "/api/ai/chat", json={"message": "سلام"}, headers=auth_header(user)
    ).status_code == 502

    rows = _rows(db_session)
    assert len(rows) == 1
    assert rows[0].failed is True
    assert rows[0].username == "led_fail"


# ── گزارش ─────────────────────────────────────────────────────────────────


def test_the_report_groups_by_user_and_by_day(client, db_session):
    admin = make_user(db_session, "hr", username="led_admin", capabilities=[Capability.manage_ai])
    db_session.add_all(
        [
            AiUsageLog(
                user_id=admin.id, username="پرخرج", prompt_tokens=90,
                completion_tokens=10, total_tokens=100, calls=2,
            ),
            AiUsageLog(
                user_id=admin.id, username="پرخرج", prompt_tokens=40,
                completion_tokens=10, total_tokens=50, calls=1,
            ),
            AiUsageLog(
                user_id=None, username="کم‌خرج", prompt_tokens=5,
                completion_tokens=5, total_tokens=10, calls=1, failed=True,
            ),
        ]
    )
    db_session.commit()

    body = client.get("/api/ai/usage?days=7", headers=auth_header(admin)).json()

    assert body["totals"]["total_tokens"] == 160
    assert body["totals"]["turns"] == 3
    assert body["totals"]["calls"] == 4
    assert body["totals"]["failed_turns"] == 1
    # پرخرج‌ترین اول — همان چیزی که کسی که گزارش را باز می‌کند دنبالش است
    assert [u["username"] for u in body["by_user"]] == ["پرخرج", "کم‌خرج"]
    assert body["by_user"][0]["total_tokens"] == 150
    assert body["by_user"][0]["turns"] == 2
    # هر سه ردیف امروز نوشته شدند
    assert len(body["by_day"]) == 1
    assert body["by_day"][0]["total_tokens"] == 160


def test_the_window_really_cuts(client, db_session):
    """گزارشِ «۷ روزِ اخیر» که ردیفِ ۹۰ روز پیش را بیاورد، گزارش نیست."""
    from datetime import UTC, datetime, timedelta

    admin = make_user(db_session, "hr", username="led_window", capabilities=[Capability.manage_ai])
    old = AiUsageLog(user_id=admin.id, username="قدیمی", total_tokens=999, calls=1)
    old.created_at = datetime.now(UTC) - timedelta(days=90)
    db_session.add(old)
    db_session.commit()

    body = client.get("/api/ai/usage?days=7", headers=auth_header(admin)).json()
    assert body["totals"]["total_tokens"] == 0
    assert body["by_user"] == []

    wide = client.get("/api/ai/usage?days=120", headers=auth_header(admin)).json()
    assert wide["totals"]["total_tokens"] == 999


def test_the_ledger_is_not_public(client, db_session):
    """«چه کسی چقدر با دستیار حرف زده» دادهٔ مدیریتی است، نه عمومی."""
    plain = make_user(db_session, "deputy", username="led_plain", capabilities=[])
    db_session.commit()

    assert client.get("/api/ai/usage", headers=auth_header(plain)).status_code == 403


def test_deleting_the_account_does_not_erase_its_spending(client, db_session):
    """هزینه اتفاق افتاده؛ حذفِ حساب برش نمی‌گرداند.

    کلیدِ خارجی عمداً `SET NULL` است و نه `CASCADE`. با `CASCADE`، حذفِ یک
    حسابِ اشتباه‌ساخته‌شده خرجش را هم از دفتر پاک می‌کرد و جمعِ ماه دیگر با
    صورت‌حساب نمی‌خواند — بی هیچ نشانه‌ای.
    """
    admin = make_user(db_session, "hr", username="led_keeper", capabilities=[Capability.manage_users])
    doomed = make_user(db_session, "deputy", username="led_doomed", capabilities=[])
    db_session.add(
        AiUsageLog(user_id=doomed.id, username=doomed.username, total_tokens=77, calls=1)
    )
    db_session.commit()

    assert client.delete(
        f"/api/users/{doomed.id}", headers=auth_header(admin)
    ).status_code == 204

    rows = _rows(db_session)
    assert len(rows) == 1
    assert rows[0].user_id is None
    assert rows[0].username == "led_doomed", "عکسِ نام می‌ماند تا ردیف خوانا بماند"
    assert rows[0].total_tokens == 77
