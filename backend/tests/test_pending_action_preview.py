"""کارتِ تأیید باید بگوید *چه چیزی* عوض می‌شود.

«تنظیم مجوزهای حساب #۷ به ۲ مجوز» جمله‌ای است که کسی جلویش را نمی‌گیرد،
چون هیچ‌کس نمی‌داند آن دو کدام‌اند. تا امروز تنها راهِ فهمیدن، بازکردنِ
JSONِ خام بود — و آن هم فقط *خواسته* را می‌گفت، نه تفاوت را: مجوزی که
**حذف** می‌شود اصلاً در آرگومان‌ها نیست.

چرا این مهم است و یک تزئینِ رابط نیست: بازبینی ثابت کرد مدلِ کاملاً مطیع هم
پیش از ساختِ کارت ۴۰۳ می‌گیرد. ولی اگر روزی چیزی از آن گارد رد شود، تنها
چیزی که بینِ مهاجم و دیتابیس می‌ماند همین کارت است.
"""
import json

from app.models.ai import AiConversation, AiPendingAction
from app.models.capability import UserCapability
from app.models.enums import Capability
from app.schemas.auth import CurrentUser
from app.services.ai.tools import base as tools_base
from tests.helpers import auth_header, make_access, make_personnel, make_user


def _ctx(db, user, caps=()) -> tools_base.ToolContext:
    return tools_base.ToolContext(
        db=db,
        user=CurrentUser(
            id=user.id,
            username=user.username,
            role=user.role,
            personnel_id=user.personnel_id,
            must_change_password=False,
            display_name=user.display_name,
        ),
        caps=frozenset(caps),
        conversation_id=0,
    )


def _preview(db, user, tool: str, arguments: dict, caps=()) -> list[dict]:
    spec = tools_base.REGISTRY[tool]
    return spec.preview_of(_ctx(db, user, caps), arguments)


def _rows_by_label(rows: list[dict]) -> dict[str, dict]:
    return {row["label"]: row for row in rows}


# ── مجوزها: آن‌که می‌آید و آن‌که می‌رود ────────────────────────────────────


def test_the_card_names_both_the_added_and_the_removed_capability(db_session):
    """حذف‌شونده در آرگومان‌ها *نیست* و فقط از مقایسه با امروز پیدا می‌شود."""
    from app.services.ai.tools import people  # noqa: F401

    admin = make_user(db_session, "hr", capabilities=[Capability.manage_capabilities])
    target = make_user(db_session, "deputy", capabilities=[Capability.manage_scoring])
    db_session.commit()

    rows = _preview(
        db_session,
        admin,
        "grant_capabilities",
        {"user_id": target.id, "capabilities": ["manage_users"]},
    )
    by_label = _rows_by_label(rows)

    assert by_label["ساخت و ویرایش حساب کاربری"]["kind"] == "add"
    assert by_label["شاخص‌ها و طرح نمره‌دهی"]["kind"] == "remove"
    # و حساب به نامِ آدم، نه به شناسه
    assert by_label["حساب کاربری"]["after"] == target.display_name


def test_a_no_op_grant_says_so_instead_of_looking_like_a_change(db_session):
    from app.services.ai.tools import people  # noqa: F401

    admin = make_user(db_session, "hr", capabilities=[Capability.manage_capabilities])
    target = make_user(db_session, "deputy", capabilities=[Capability.manage_scoring])
    db_session.commit()

    rows = _preview(
        db_session,
        admin,
        "grant_capabilities",
        {"user_id": target.id, "capabilities": ["manage_scoring"]},
    )
    assert "تغییری در مجوزها" in _rows_by_label(rows)


def test_an_unknown_capability_does_not_break_the_card(db_session):
    """مجوزِ ناشناخته را خودِ endpoint رد می‌کند؛ کارت فقط باید *دیده* شود.

    استثنایی که از ساختنِ کارت بیرون بزند، کلِ نوبت را می‌شکند — و آن یعنی
    یک آرگومانِ بدِ مدل می‌تواند گفت‌وگو را از کار بیندازد.
    """
    from app.services.ai.tools import people  # noqa: F401

    admin = make_user(db_session, "hr", capabilities=[Capability.manage_capabilities])
    target = make_user(db_session, "deputy", capabilities=[])
    db_session.commit()

    rows = _preview(
        db_session,
        admin,
        "grant_capabilities",
        {"user_id": target.id, "capabilities": ["manage_everything_ever"]},
    )
    assert any("manage_everything_ever" in row["label"] for row in rows)


# ── زنجیرهٔ ارزیابی: سه صندلی، «از که به که» ───────────────────────────────


def test_the_chain_card_shows_the_seat_being_replaced(db_session):
    """تعویضِ بی‌صدای یک صندلی همان چیزی است که کارت باید جلویش را بگیرد."""
    from app.services.ai.tools import people  # noqa: F401

    admin = make_user(db_session, "hr", capabilities=[Capability.manage_personnel])
    old_sup = make_user(db_session, "unit_supervisor", capabilities=[])
    new_sup = make_user(db_session, "unit_supervisor", capabilities=[])
    ceo = make_user(db_session, "ceo", capabilities=[])
    person = make_personnel(db_session, full_name="کسی که زنجیره‌اش عوض می‌شود")
    make_access(db_session, person, old_sup, None, ceo)
    db_session.commit()

    rows = _rows_by_label(
        _preview(
            db_session,
            admin,
            "set_evaluation_access",
            {"personnel_id": person.id, "unit_supervisor": new_sup.username, "ceo": ceo.username},
        )
    )

    assert rows["پرسنل"]["after"] == "کسی که زنجیره‌اش عوض می‌شود"
    assert rows["مسئول مستقیم"]["before"] == old_sup.display_name
    assert rows["مسئول مستقیم"]["after"] == new_sup.display_name
    assert rows["مسئول مستقیم"]["kind"] == "change"
    # صندلیِ دست‌نخورده باید *دست‌نخورده* دیده شود، نه «خالی می‌شود»
    assert rows["مدیرعامل"]["kind"] == "info"
    assert rows["معاونت"]["after"] == "—"


# ── حساب کاربری: غیرفعال‌سازی و رمز ───────────────────────────────────────


def test_deactivation_gets_its_own_line(db_session):
    from app.services.ai.tools import people  # noqa: F401

    admin = make_user(db_session, "hr", capabilities=[Capability.manage_users])
    target = make_user(db_session, "deputy", capabilities=[])
    db_session.commit()

    rows = _rows_by_label(
        _preview(db_session, admin, "update_user", {"user_id": target.id, "is_active": False})
    )
    assert rows["وضعیت حساب"]["before"] == "فعال"
    assert rows["وضعیت حساب"]["after"] == "غیرفعال"
    assert rows["وضعیت حساب"]["kind"] == "remove"


def test_the_password_never_reaches_the_card(db_session):
    """کارتِ تأیید در تاریخچهٔ گفت‌وگو می‌ماند و تاریخچه بعداً هم خوانده می‌شود."""
    from app.services.ai.tools import people  # noqa: F401

    admin = make_user(db_session, "hr", capabilities=[Capability.manage_users])
    target = make_user(db_session, "deputy", capabilities=[])
    db_session.commit()

    rows = _preview(
        db_session, admin, "update_user", {"user_id": target.id, "password": "Str0ng-Pass-9"}
    )
    blob = json.dumps(rows, ensure_ascii=False)
    assert "Str0ng-Pass-9" not in blob
    assert "بازنشانی می‌شود" in blob


def test_the_generic_card_also_hides_secrets(db_session):
    """ابزارِ بی‌`preview` جدولِ پیش‌فرض می‌گیرد — و آن هم نباید رمز چاپ کند."""
    rows = tools_base.generic_preview(
        {"username": "kasi", "password": "Str0ng-Pass-9", "role": "hr"}
    )
    by_label = _rows_by_label(rows)
    assert by_label["نام کاربری"]["after"] == "kasi"
    assert "Str0ng-Pass-9" not in json.dumps(rows, ensure_ascii=False)
    assert by_label["رمز عبور"]["after"] == "••••••"


def test_the_generic_card_labels_what_it_can(db_session):
    """حتی بی `preview`، «user_id: 7» نباید روی کارت بیاید."""
    rows = _rows_by_label(tools_base.generic_preview({"personnel_id": 7, "reason": "استعفا"}))
    assert set(rows) == {"پرسنل", "دلیل"}


# ── و از راهِ واقعی: ردیفِ دیتابیس و پاسخِ API ─────────────────────────────


def test_the_preview_is_frozen_on_the_row_at_decision_time(client, db_session):
    """کارت باید همان چیزی را نگه دارد که کاربر *موقعِ تصمیم* دید.

    اگر زنده حساب می‌شد، کارتِ یک پیشنهادِ تأییدشده بعداً چیزِ دیگری می‌گفت —
    و ردِ ممیزی دقیقاً همان لحظه را می‌خواهد، نه امروز را.
    """
    from app.services.ai.tools import people  # noqa: F401

    admin = make_user(db_session, "hr", capabilities=[Capability.manage_capabilities])
    target = make_user(db_session, "deputy", capabilities=[])
    db_session.commit()

    convo = AiConversation(user_id=admin.id, title="کارت")
    db_session.add(convo)
    db_session.flush()
    spec = tools_base.REGISTRY["grant_capabilities"]
    arguments = {"user_id": target.id, "capabilities": ["manage_users"]}
    row = AiPendingAction(
        conversation_id=convo.id,
        user_id=admin.id,
        tool_name=spec.name,
        arguments_json=json.dumps(arguments, ensure_ascii=False),
        summary=spec.summary_of(arguments),
        preview_json=json.dumps(
            spec.preview_of(_ctx(db_session, admin), arguments), ensure_ascii=False
        ),
        status="pending",
    )
    db_session.add(row)
    db_session.commit()

    # وضعیتِ دنیا بعد از ساختِ کارت عوض می‌شود…
    db_session.add(UserCapability(user_id=target.id, capability=Capability.view_audit_log))
    db_session.commit()

    body = client.get("/api/ai/pending", headers=auth_header(admin)).json()
    card = next(item for item in body if item["id"] == row.id)
    labels = {c["label"] for c in card["changes"]}
    assert "ساخت و ویرایش حساب کاربری" in labels
    assert "خواندن کامل گزارش رویدادها" not in labels, "کارت نباید با دنیا جلو برود"


def test_an_old_row_without_a_preview_still_renders(client, db_session):
    """ردیف‌های پیش از این نسخه `preview_json` خالی دارند و نباید بشکنند."""
    admin = make_user(db_session, "hr", capabilities=[Capability.manage_users])
    convo = AiConversation(user_id=admin.id, title="قدیمی")
    db_session.add(convo)
    db_session.flush()
    row = AiPendingAction(
        conversation_id=convo.id,
        user_id=admin.id,
        tool_name="update_user",
        arguments_json='{"user_id": 1}',
        summary="قدیمی",
        status="pending",
    )
    db_session.add(row)
    db_session.commit()

    body = client.get("/api/ai/pending", headers=auth_header(admin)).json()
    card = next(item for item in body if item["id"] == row.id)
    assert card["changes"] == []
    assert card["summary"] == "قدیمی"


def test_every_risky_tool_produces_a_card_with_at_least_one_row(db_session):
    """قاعده، نه فهرست: هیچ ابزارِ پرخطری نباید کارتِ خالی بدهد.

    ابزارِ تازه‌ای که فردا اضافه شود هم زیرِ همین قاعده می‌آید — بی اینکه کسی
    یادش بماند این فایل را به‌روز کند.
    """
    from app.services.ai.tools import evaluations, framework, people, uploads  # noqa: F401

    admin = make_user(db_session, "hr", capabilities=list(Capability))
    db_session.commit()
    ctx = _ctx(db_session, admin, list(Capability))

    for name, spec in sorted(tools_base.REGISTRY.items()):
        if not spec.risky:
            continue
        rows = spec.preview_of(ctx, {"user_id": 0, "personnel_id": 0, "reason": "آزمایش"})
        assert rows, f"ابزار پرخطر «{name}» کارتِ خالی داد"
        assert all({"label", "before", "after", "kind"} <= set(row) for row in rows), name
