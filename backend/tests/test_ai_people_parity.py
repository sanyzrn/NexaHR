"""ابزارهای پرسنل و حساب هم باید از همان درِ رابط رد شوند.

سه ابزار در `ai/tools/people.py` سرویس یا مدل را مستقیم دست می‌زدند. دو تای
اول *همیشه* می‌شکستند و سومی گاردهای رابط را نداشت — و هیچ تستی از آن مسیرها
نمی‌گذشت.

* `revoke_all_for_user(account.id)` بی `db` صدا زده می‌شد. امضا
  `(db, user_id)` است، پس هر بار `TypeError` → ۵۰۰ و برگشتِ تراکنش. یعنی
  غیرفعال‌کردنِ حساب، بازنشانیِ رمز، و خروجِ پرسنلِ حساب‌دار از راه دستیار
  هرگز کار نمی‌کردند.
* `update_user`ِ ابزار `must_change_password` را روی رمزی که *دیگری* گذاشته
  ست نمی‌کرد، و گاردهای «نقشِ منابع انسانی را از خودت نگیر» و «کارمند بی
  پروندهٔ پرسنلی نمی‌شود» را نداشت.
* `grant_capabilities` گاردِ «آخرین دارندهٔ manage_capabilities» و «کارمند
  مجوز اداری نمی‌گیرد» را نداشت.

و یک دامنهٔ دید: `ORG_WIDE_ROLES` این فایل `support`/`deputy`/`ceo` را
«سازمان‌گستر» می‌شمرد، در حالی که `list_personnel` هیچ‌کدام را کامل نشان
نمی‌دهد. همان خرابیِ `ai/context.py` بود، در نسخهٔ دومش.
"""
import pytest
from fastapi import HTTPException

from app.models.capability import UserCapability
from app.models.enums import Capability, PersonnelStatus, UserRole
from app.models.evaluation import EvaluationRecord
from app.models.user import User
from app.schemas.auth import CurrentUser
from app.services.ai.tools import base as tools_base
from tests.helpers import (
    auth_header,
    make_access,
    make_personnel,
    make_user,
)


def _ctx(db, user, caps=()) -> tools_base.ToolContext:
    return tools_base.ToolContext(
        db=db,
        user=CurrentUser(
            id=user.id,
            username=user.username,
            role=user.role,
            personnel_id=user.personnel_id,
            must_change_password=False,
            display_name=user.username,
        ),
        caps=frozenset(caps),
        conversation_id=0,
    )


def _run(db, user, tool: str, arguments: dict, caps=()):
    return tools_base.execute_tool(
        _ctx(db, user, caps), tools_base.REGISTRY[tool], arguments
    )


# ── حسابِ کاربری ───────────────────────────────────────────────────────────


def test_deactivating_an_account_through_the_copilot_works_at_all(db_session):
    """پیش از این `TypeError` بود، پس این تست حتی به گاردها هم نمی‌رسید."""
    admin = make_user(db_session, "hr", capabilities=[Capability.manage_users])
    target = make_user(db_session, "unit_supervisor", capabilities=[])
    db_session.commit()

    _run(db_session, admin, "update_user", {"user_id": target.id, "is_active": False},
         caps=[Capability.manage_users])
    db_session.expire_all()
    assert db_session.get(User, target.id).is_active is False


def test_a_password_set_by_someone_else_must_be_changed_on_first_login(db_session):
    """همان قاعده‌ای که مسیر اکسل و بازنشانیِ رابط دارند.

    رمزی که کسِ دیگری انتخاب کرده و از راه تلفن یا پیام رسیده، نباید در
    استفاده بماند — استدلالش در `personnel_import` نوشته شده.
    """
    admin = make_user(db_session, "hr", capabilities=[Capability.manage_users])
    target = make_user(db_session, "unit_supervisor", capabilities=[])
    before_version = target.token_version
    db_session.commit()

    _run(db_session, admin, "update_user",
         {"user_id": target.id, "password": "A-New-Password-9"},
         caps=[Capability.manage_users])
    db_session.expire_all()
    fresh = db_session.get(User, target.id)
    assert fresh.must_change_password is True
    # و نشست‌های قبلی باطل شده‌اند.
    assert fresh.token_version > before_version


def test_the_copilot_cannot_strip_hr_from_its_own_account(db_session):
    """گاردِ روتر که در ابزار نبود."""
    admin = make_user(db_session, "hr", capabilities=[Capability.manage_users])
    db_session.commit()
    with pytest.raises(HTTPException) as err:
        _run(db_session, admin, "update_user",
             {"user_id": admin.id, "role": "unit_supervisor"},
             caps=[Capability.manage_users])
    assert err.value.status_code == 400
    db_session.rollback()
    db_session.expire_all()
    assert db_session.get(User, admin.id).role is UserRole.hr


def test_an_employee_account_still_needs_a_personnel_record(db_session):
    admin = make_user(db_session, "hr", capabilities=[Capability.manage_users])
    target = make_user(db_session, "unit_supervisor", capabilities=[])
    db_session.commit()
    with pytest.raises(HTTPException) as err:
        _run(db_session, admin, "update_user", {"user_id": target.id, "role": "employee"},
             caps=[Capability.manage_users])
    assert err.value.status_code == 400
    db_session.rollback()


# ── مجوزهای اداری ─────────────────────────────────────────────────────────


def test_the_last_capability_holder_cannot_strip_itself_through_the_copilot(db_session):
    """«تنها راه خروج، SQL دستی روی پروداکشن است» — کامنتِ خودِ روتر.

    از راه دستیار همان یک کلیک ممکن بود.
    """
    db_session.query(UserCapability).filter(
        UserCapability.capability == Capability.manage_capabilities
    ).delete()
    sole = make_user(db_session, "hr", capabilities=[Capability.manage_capabilities])
    db_session.commit()

    with pytest.raises(HTTPException) as err:
        _run(db_session, sole, "grant_capabilities",
             {"user_id": sole.id, "capabilities": ["manage_users"]},
             caps=[Capability.manage_capabilities])
    assert err.value.status_code == 400
    db_session.rollback()
    db_session.expire_all()
    from app.services.authorization import capabilities_of

    assert Capability.manage_capabilities in capabilities_of(db_session, sole.id)


def test_a_plain_employee_gets_no_administrative_capability(db_session):
    admin = make_user(db_session, "hr", capabilities=[Capability.manage_capabilities])
    person = make_personnel(db_session)
    worker = make_user(db_session, "employee", personnel_id=person.id, capabilities=[])
    db_session.commit()
    with pytest.raises(HTTPException) as err:
        _run(db_session, admin, "grant_capabilities",
             {"user_id": worker.id, "capabilities": ["manage_users"]},
             caps=[Capability.manage_capabilities])
    assert err.value.status_code == 400
    db_session.rollback()


# ── خروجِ پرسنل ───────────────────────────────────────────────────────────


def test_separating_personnel_with_an_account_works_and_leaves_a_trail(client, db_session):
    """سه چیز که بدنهٔ رونویسی‌شده جا می‌گذاشت — و اولش کلاً می‌شکست."""
    hr = make_user(db_session, "hr")
    sup = make_user(db_session, "unit_supervisor", capabilities=[])
    dep = make_user(db_session, "deputy", capabilities=[])
    ceo = make_user(db_session, "ceo", capabilities=[])
    person = make_personnel(db_session, full_name="کسی که می‌رود")
    account = make_user(db_session, "employee", personnel_id=person.id, capabilities=[])
    make_access(db_session, person, sup, dep, ceo)
    db_session.commit()
    record_id = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": person.id},
        headers=auth_header(sup),
    ).json()["id"]
    db_session.commit()

    _run(db_session, hr, "separate_personnel",
         {"personnel_id": person.id, "separation_reason": "resignation"})
    db_session.expire_all()

    assert db_session.get(EvaluationRecord, record_id).status.value == "cancelled"
    assert db_session.get(User, account.id).is_active is False
    from app.models.personnel import Personnel

    assert db_session.get(Personnel, person.id).status is PersonnelStatus.inactive

    # کامنتِ توضیحِ لغو و دو رویدادِ ممیزی، که رونویسی نداشتشان.
    detail = client.get(
        f"/api/evaluations/{record_id}", headers=auth_header(hr)
    ).json()
    assert any("خارج شد" in c["comment_text"] for c in detail["comments"]), detail["comments"]
    events = client.get(
        "/api/audit-log", params={"limit": 200},
        headers=auth_header(make_user(db_session, "hr", capabilities=[Capability.view_audit_log])),
    )
    kinds = {row["event_type"] for row in events.json()["items"]}
    assert "evaluation_cancelled_on_separation" in kinds, sorted(kinds)
    assert "user_deactivated_on_separation" in kinds, sorted(kinds)


# ── دامنهٔ دیدِ پرسنل ──────────────────────────────────────────────────────


SECRET = "پرسنلِ محرمانهٔ ۷۷۲۱"


@pytest.mark.parametrize("role", ["support", "deputy", "ceo"])
def test_a_role_outside_the_chain_sees_no_personnel_through_the_tools(db_session, role):
    """قرینهٔ همان تستِ `test_ai_security` برای متنِ پرامپت، این‌بار برای ابزارها."""
    import json

    sup = make_user(db_session, "unit_supervisor", capabilities=[])
    dep = make_user(db_session, "deputy", capabilities=[])
    ceo = make_user(db_session, "ceo", capabilities=[])
    victim = make_personnel(db_session, full_name=SECRET)
    make_access(db_session, victim, sup, dep, ceo)
    outsider_person = make_personnel(db_session, full_name="خودِ " + role)
    outsider = make_user(db_session, role, personnel_id=outsider_person.id, capabilities=[])
    db_session.commit()

    found = json.loads(
        _run(db_session, outsider, "search_personnel", {"q": SECRET}).content
    )
    assert found["matches"] == 0, found

    with pytest.raises(HTTPException) as err:
        _run(db_session, outsider, "get_personnel", {"personnel_id": victim.id})
    assert err.value.status_code == 403


def test_the_chain_still_sees_its_own_people(db_session):
    """وگرنه تست فقط «هیچ‌کس هیچ نمی‌بیند» را می‌سنجید."""
    import json

    sup = make_user(db_session, "unit_supervisor", capabilities=[])
    dep = make_user(db_session, "deputy", capabilities=[])
    ceo = make_user(db_session, "ceo", capabilities=[])
    person = make_personnel(db_session, full_name=SECRET + " زنجیره")
    make_access(db_session, person, sup, dep, ceo)
    db_session.commit()

    for actor in (sup, dep, ceo):
        found = json.loads(
            _run(db_session, actor, "search_personnel", {"q": SECRET}).content
        )
        assert found["matches"] == 1, (actor.username, found)
        assert _run(db_session, actor, "get_personnel", {"personnel_id": person.id})


def test_manage_personnel_still_opens_the_whole_roster(db_session):
    """آن مجوز در رابط هم کلِ فهرست را می‌دهد (`personnel/export.xlsx`)."""
    import json

    sup = make_user(db_session, "unit_supervisor", capabilities=[])
    dep = make_user(db_session, "deputy", capabilities=[])
    ceo = make_user(db_session, "ceo", capabilities=[])
    person = make_personnel(db_session, full_name=SECRET + " مجوزدار")
    make_access(db_session, person, sup, dep, ceo)
    keeper = make_user(db_session, "support", capabilities=[Capability.manage_personnel])
    db_session.commit()

    found = json.loads(
        _run(db_session, keeper, "search_personnel", {"q": SECRET},
             caps=[Capability.manage_personnel]).content
    )
    assert found["matches"] == 1, found
    assert _run(db_session, keeper, "get_personnel", {"personnel_id": person.id},
                caps=[Capability.manage_personnel])
