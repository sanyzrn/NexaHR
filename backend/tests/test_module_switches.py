"""سوییچِ ماژول باید *کاری* بکند.

گاردِ ماژول یک `Depends`ِ استفاده‌نشده در `api/deps.py` بود و هیچ روتی به آن
وصل نبود، پس همهٔ سوییچ‌ها ظاهری بودند: سازمانی که کانالِ اعتراض را عمداً باز
نکرده بود همچنان اعتراض می‌پذیرفت، و سازمانی که خودارزیابی را خاموش کرده بود
همچنان خودارزیابی ثبت می‌کرد. و چون `objections` و
`employee_evaluation_visibility` پیش‌فرض *خاموش*‌اند، این حالتِ پیش‌فرض بود و
نه یک گوشهٔ نادر.

سه ماژول هم اصلاً هیچ‌جای سرور خوانده نمی‌شدند (`role_analytics`،
`outbound_notifications`، `employee_overview_cards`) — یعنی سه سوییچ در پنلِ
مدیر که فقط رابط را عوض می‌کردند.

تستِ آخرِ این فایل همان چیزی است که نگذارد این وضع برگردد: هر کلیدِ ماژول باید
دستِ‌کم یک‌جا در سرور خوانده شود.
"""
import pytest

from app.core.modules import MODULE_KEYS
from tests.helpers import (
    active_indicators,
    auth_header,
    full_valid_scores,
    make_access,
    make_personnel,
    make_user,
    set_module,
)


@pytest.fixture()
def cast(db_session):
    people = {
        "hr": make_user(db_session, "hr"),
        "sup": make_user(db_session, "unit_supervisor"),
        "dep": make_user(db_session, "deputy"),
        "ceo": make_user(db_session, "ceo"),
    }
    personnel = make_personnel(db_session, full_name="موضوعِ سوییچ‌ها")
    people["employee"] = make_user(
        db_session, "employee", personnel_id=personnel.id, capabilities=[]
    )
    make_access(db_session, personnel, people["sup"], people["dep"], people["ceo"])
    db_session.commit()
    return {**people, "personnel": personnel}


def _open_case(client, db_session, cast) -> int:
    record_id = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": cast["personnel"].id},
        headers=auth_header(cast["sup"]),
    ).json()["id"]
    client.put(
        f"/api/evaluations/{record_id}/scores",
        json={"scores": full_valid_scores(active_indicators(db_session))},
        headers=auth_header(cast["sup"]),
    )
    return record_id


def _finalize(client, cast, record_id: int) -> None:
    for path, who in (("submit", "sup"), ("hr-approve", "hr"), ("deputy-approve", "dep"),
                      ("ceo-finalize", "ceo")):
        done = client.post(
            f"/api/evaluations/{record_id}/{path}", headers=auth_header(cast[who])
        )
        assert done.status_code == 200, (path, done.text)


# ── خودارزیابی ────────────────────────────────────────────────────────────


def test_self_assessment_off_refuses_the_submission(client, db_session, cast):
    record_id = _open_case(client, db_session, cast)
    set_module(db_session, "self_assessment", False)
    db_session.commit()
    refused = client.post(
        f"/api/me/evaluations/{record_id}/self-assessment",
        json={"scores": [], "note": "دیدگاه خودم"},
        headers=auth_header(cast["employee"]),
    )
    assert refused.status_code == 403, refused.text


def test_self_assessment_off_refuses_the_invitation_too(client, db_session, cast):
    """دعوت هم یک نوشتن است؛ سوییچی که فقط نیمی از یک جریان را ببندد، نبسته."""
    _open_case(client, db_session, cast)
    set_module(db_session, "self_assessment", False)
    db_session.commit()
    refused = client.post(
        f"/api/personnel/{cast['personnel'].id}/invite-self-assessment",
        headers=auth_header(cast["hr"]),
    )
    assert refused.status_code == 403, refused.text


# ── اعتراض و رؤیت ─────────────────────────────────────────────────────────


def test_objections_off_refuses_an_objection(client, db_session, cast):
    set_module(db_session, "employee_evaluation_visibility", True)
    set_module(db_session, "objections", False)
    db_session.commit()
    record_id = _open_case(client, db_session, cast)
    _finalize(client, cast, record_id)
    refused = client.post(
        f"/api/me/evaluations/{record_id}/object",
        json={"reason": "به وزنِ شاخص سوم اعتراض دارم"},
        headers=auth_header(cast["employee"]),
    )
    assert refused.status_code == 403, refused.text


def test_acknowledgement_off_refuses_the_acknowledgement(client, db_session, cast):
    set_module(db_session, "employee_evaluation_visibility", True)
    set_module(db_session, "employee_result_acknowledgement", False)
    db_session.commit()
    record_id = _open_case(client, db_session, cast)
    _finalize(client, cast, record_id)
    refused = client.post(
        f"/api/me/evaluations/{record_id}/acknowledge", headers=auth_header(cast["employee"])
    )
    assert refused.status_code == 403, refused.text


# ── نمایشِ نتیجه ──────────────────────────────────────────────────────────


def test_visibility_off_hides_the_result_from_its_subject(client, db_session, cast):
    """تنها سوییچی که روی *خواندن* هم می‌نشیند — چون کارِ خودش همین است.

    رابط از قبل بخش را پنهان می‌کرد و سرور نتیجه را می‌داد؛ یعنی نیمهٔ
    قابل‌اعتماد حرفِ شل‌تر را می‌زد و یک درخواستِ ناموفقِ `/my-permissions`
    کافی بود تا نتیجه لو برود.
    """
    set_module(db_session, "employee_evaluation_visibility", True)
    db_session.commit()
    record_id = _open_case(client, db_session, cast)
    _finalize(client, cast, record_id)

    shown = client.get("/api/me/evaluations", headers=auth_header(cast["employee"]))
    assert shown.status_code == 200
    assert shown.json()["total"] == 1, "پیش‌شرطِ تست: با سوییچِ روشن باید دیده شود"

    set_module(db_session, "employee_evaluation_visibility", False)
    db_session.commit()
    hidden = client.get("/api/me/evaluations", headers=auth_header(cast["employee"]))
    assert hidden.status_code == 200
    assert hidden.json() == {"total": 0, "items": []}

    # و دادهٔ پرونده پاک نشده: زنجیره و منابع انسانی همه‌چیز را می‌بینند.
    hr_view = client.get(
        f"/api/evaluations/{record_id}", headers=auth_header(cast["hr"])
    )
    assert hr_view.status_code == 200


def test_overview_cards_respect_both_switches(client, db_session, cast):
    set_module(db_session, "employee_evaluation_visibility", True)
    set_module(db_session, "employee_overview_cards", True)
    db_session.commit()
    record_id = _open_case(client, db_session, cast)
    _finalize(client, cast, record_id)

    def cards():
        return client.get(
            "/api/dashboard/role-overview",
            params={"scope": "self"},
            headers=auth_header(cast["employee"]),
        ).json()["cards"]

    assert cards(), "پیش‌شرطِ تست"
    set_module(db_session, "employee_overview_cards", False)
    db_session.commit()
    assert cards() == []

    set_module(db_session, "employee_overview_cards", True)
    set_module(db_session, "employee_evaluation_visibility", False)
    db_session.commit()
    assert cards() == [], "محتوای کاشی‌ها نتیجهٔ ارزیابی است، پس به آن سوییچ هم بند است"


# ── تحلیل نقش‌ها ──────────────────────────────────────────────────────────


def test_role_analytics_off_closes_both_analytics_views(client, db_session, cast):
    set_module(db_session, "role_analytics", False)
    db_session.commit()
    assert (
        client.get("/api/analytics/my-scoring", headers=auth_header(cast["sup"])).status_code
        == 403
    )
    assert (
        client.get("/api/analytics/executive", headers=auth_header(cast["ceo"])).status_code
        == 403
    )


# ── دوره‌ها و برنامهٔ بهبود ───────────────────────────────────────────────


def test_periods_off_refuses_creation_but_still_lets_an_open_period_close(
    client, db_session, cast
):
    created = client.post(
        "/api/periods",
        json={"name": "دورهٔ آزمایشی", "starts_on": "2026-01-01", "ends_on": "2026-06-01"},
        headers=auth_header(cast["hr"]),
    )
    assert created.status_code == 201, created.text
    period_id = created.json()["id"]

    set_module(db_session, "periods", False)
    db_session.commit()
    refused = client.post(
        "/api/periods",
        json={"name": "دورهٔ دوم", "starts_on": "2026-07-01", "ends_on": "2026-12-01"},
        headers=auth_header(cast["hr"]),
    )
    assert refused.status_code == 403, refused.text

    # ولی دوره‌ای که باز مانده باید بسته شود، وگرنه سوییچ آن را برای همیشه
    # باز نگه می‌دارد — گارد روی *افزودن* است، نه روی خروج.
    closed = client.post(
        f"/api/periods/{period_id}/close", params={"force": True}, headers=auth_header(cast["hr"])
    )
    assert closed.status_code == 200, closed.text


def test_improvement_plans_off_refuses_a_new_plan(client, db_session, cast):
    set_module(db_session, "improvement_plans", False)
    db_session.commit()
    record_id = _open_case(client, db_session, cast)
    _finalize(client, cast, record_id)
    refused = client.post(
        "/api/improvement-plans",
        json={
            "evaluation_record_id": record_id,
            "title": "برنامهٔ بهبود",
            "review_date": "2026-12-01",
            "goals": ["هدف اول"],
        },
        headers=auth_header(cast["hr"]),
    )
    assert refused.status_code == 403, refused.text


# ── اعلانِ بیرونی ─────────────────────────────────────────────────────────


def test_outbound_notifications_off_queues_nothing(db_session, monkeypatch, cast):
    """نقطهٔ خاموشی *صف نریختن* است.

    اگر ردیف‌ها ساخته می‌شدند و فرستنده ردشان می‌کرد، خاموش‌کردن سوییچ یک صفِ
    روبه‌رشدِ ردیف‌های مرده می‌ساخت که روزی که کسی سوییچ را برگرداند همه‌شان
    یک‌جا بیرون می‌رفتند.
    """
    from app.models.enums import DeliveryChannel
    from app.models.notification import Notification
    from app.models.notification_delivery import NotificationDelivery
    from app.services import channels
    from app.services.channels.console import ConsoleChannel
    from app.services.notifications import notify

    # بی یک کانالِ تنظیم‌شده و یک گیرندهٔ قابل‌تماس، `enqueue_for` در هر حالتی
    # صفر ردیف می‌سازد و تست بی‌معنا می‌شود.
    monkeypatch.setattr(
        channels, "_all_channels", lambda: [ConsoleChannel(DeliveryChannel.email)]
    )
    target = cast["hr"]
    target.email = "kaveh@example.com"
    target.notify_by_email = True
    db_session.commit()

    def _send(type_: str = "evaluation_finalized_self") -> None:
        notify(db_session, [target.id], type_=type_, message="پیام آزمایشی", link="/me")
        db_session.flush()

    set_module(db_session, "outbound_notifications", True)
    db_session.commit()
    _send()
    assert db_session.query(NotificationDelivery).count() == 1, "پیش‌شرطِ تست"

    set_module(db_session, "outbound_notifications", False)
    db_session.commit()
    before = db_session.query(Notification).count()
    _send()
    assert db_session.query(NotificationDelivery).count() == 1, "ردیفِ تازه‌ای نباید ساخته شود"
    # ولی اعلانِ درون‌برنامه‌ای هسته است و باید باشد.
    assert db_session.query(Notification).count() == before + 1


# ── نگهبانِ خودِ قاعده ────────────────────────────────────────────────────


def test_every_module_key_is_enforced_somewhere_on_the_server():
    """هر سوییچ باید دستِ‌کم یک‌جا در سرور خوانده شود.

    این تست همان چیزی است که نگذارد وضعِ قبلی برگردد: کلیدی که هیچ‌جای سرور
    خوانده نشود، سوییچی است که فقط رابط را عوض می‌کند — و رابط قابلِ
    دست‌کاری است.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "app"
    sources = [
        path.read_text(encoding="utf-8")
        for path in root.rglob("*.py")
        # `core/modules.py` خودِ تعریف است، پس شمردنش تست را بی‌معنا می‌کند.
        if path.name != "modules.py"
    ]
    blob = "\n".join(sources)
    missing = sorted(key for key in MODULE_KEYS if f'"{key}"' not in blob)
    assert not missing, f"این ماژول‌ها هیچ‌جای سرور اعمال نمی‌شوند: {missing}"
