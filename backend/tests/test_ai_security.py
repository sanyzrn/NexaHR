"""گاردهای امنیتیِ دستیار — چیزهایی که اگر بشکنند بی‌صدا می‌شکنند.

این‌ها ادعاهای مستنداتِ همین زیرسیستم را می‌سنجند، نه جزئیاتِ پیاده‌سازی را:

* کارمندِ بی‌مجوز از راهِ دستیار به دادهٔ دیگران نمی‌رسد — نه از ابزارها و نه
  از زمینهٔ پرامپت (که بیرونِ مسیرِ گاردِ ابزارهاست و جداگانه سنجیده می‌شود).
* سوییچِ فقط-خواندنی در *لحظهٔ اجرا* می‌بندد، نه فقط در تبلیغِ ابزارها.
* هیچ ابزارِ تغییردهنده‌ای بدون کارتِ تأیید وجود ندارد.
* نقطهٔ تأیید مالِ صاحبش است، یک‌بار بیشتر اجرا نمی‌شود، و اگر دسترسی بینِ
  پیشنهاد و تأیید گرفته شود اجرا نمی‌شود.
"""


import json
from datetime import UTC, datetime

from fastapi import HTTPException

import app.services.ai.tools  # noqa: F401
from app.models.ai import AiConversation, AiPendingAction, AiUserAccess
from app.models.enums import Capability
from app.schemas.auth import CurrentUser
from app.services.ai.tools import base as tools_base
from tests.helpers import auth_header, make_access, make_personnel, make_user  # noqa: F401

SECRET_NAME = "محرمانهٔ کاملاً یکتا ۹۹۳۱"


def _ctx(db, user, caps=None, allow_writes=True):
    return tools_base.ToolContext(
        db=db,
        user=CurrentUser(
            id=user.id, username=user.username, role=user.role,
            personnel_id=user.personnel_id, must_change_password=False,
            display_name=user.username,
        ),
        caps=frozenset(caps or set()),
        conversation_id=0,
        allow_writes=allow_writes,
    )


def test_every_readonly_tool_denies_or_hides_other_peoples_data(client, db_session):
    # یک فردِ دیگر با نامِ یکتا، و یک پروندهٔ ارزیابی برایش
    sup = make_user(db_session, "unit_supervisor", username="probe_sup")
    dep = make_user(db_session, "deputy", username="probe_dep")
    ceo = make_user(db_session, "ceo", username="probe_ceo")
    victim = make_personnel(db_session, full_name=SECRET_NAME)
    make_access(db_session, victim, sup, dep, ceo)
    # کارمندِ مهاجم: بدون هیچ مجوزی، بدون هیچ زنجیره‌ای
    attacker_p = make_personnel(db_session, full_name="کارمندِ کنجکاو")
    attacker = make_user(db_session, "employee", username="probe_emp",
                         personnel_id=attacker_p.id, capabilities=[])
    db_session.commit()

    client.post("/api/evaluations", json={"subject_personnel_id": victim.id},
                headers=auth_header(sup))
    db_session.commit()

    ctx = _ctx(db_session, attacker)
    readonly = [s for s in tools_base.REGISTRY.values() if s.read_only]
    leaked, denied, ok = [], [], []
    for spec in readonly:
        try:
            outcome = tools_base.execute_tool(ctx, spec, {})
        except HTTPException as e:
            denied.append((spec.name, e.status_code))
            continue
        except Exception as e:  # ابزارهایی که آرگومانِ اجباری دارند
            denied.append((spec.name, type(e).__name__))
            continue
        blob = (outcome.content or "") + json.dumps(outcome.ui or {}, ensure_ascii=False)
        if SECRET_NAME in blob:
            leaked.append(spec.name)
        else:
            ok.append(spec.name)

    print(f"\nرد شد ({len(denied)}): {[d[0] for d in denied]}")
    print(f"اجرا شد و چیزی لو نداد ({len(ok)}): {ok}")
    print(f"!!! نشت ({len(leaked)}): {leaked}")
    assert not leaked, f"این ابزارها نامِ فردِ دیگر را به کارمندِ بی‌مجوز دادند: {leaked}"


def test_write_switch_off_blocks_every_mutating_tool(db_session):
    """سوییچِ فقط-خواندنی باید هر ابزارِ تغییردهنده را در لحظهٔ اجرا ببندد."""
    u = make_user(db_session, "hr", username="probe_hr_ro",
                  capabilities=list(Capability))
    db_session.commit()
    ctx = _ctx(db_session, u, caps=set(Capability), allow_writes=False)
    escaped = []
    for spec in tools_base.REGISTRY.values():
        if spec.read_only:
            continue
        try:
            tools_base.execute_tool(ctx, spec, {})
        except HTTPException as e:
            if e.status_code != 403:
                escaped.append((spec.name, e.status_code))
        except Exception as e:
            escaped.append((spec.name, type(e).__name__))
    assert not escaped, f"با سوییچِ خاموش، این‌ها ۴۰۳ نگرفتند: {escaped}"


def test_the_system_prompt_context_is_scoped_too(client, db_session):
    """زمینهٔ پرامپت بیرون از مسیرِ گاردِ ابزارهاست — پس جداگانه سنجیده می‌شود."""
    from app.services.ai import context as ai_context

    sup = make_user(db_session, "unit_supervisor", username="ctx_sup")
    dep = make_user(db_session, "deputy", username="ctx_dep")
    ceo = make_user(db_session, "ceo", username="ctx_ceo")
    victim = make_personnel(db_session, full_name=SECRET_NAME + " ctx")
    make_access(db_session, victim, sup, dep, ceo)
    attacker_p = make_personnel(db_session, full_name="کنجکاوِ زمینه")
    attacker = make_user(db_session, "employee", username="ctx_emp",
                         personnel_id=attacker_p.id, capabilities=[])
    db_session.commit()
    client.post("/api/evaluations", json={"subject_personnel_id": victim.id},
                headers=auth_header(sup))
    db_session.commit()

    ctx_user = _ctx(db_session, attacker).user
    text = ai_context.build(db_session, ctx_user, set(), limit=50)
    assert SECRET_NAME not in text, "زمینهٔ پرامپت نامِ فردِ دیگر را به کارمند داد"

    # و برای کسی که واقعاً دسترسی دارد، دیده می‌شود — وگرنه تست بی‌معناست
    sup_user = _ctx(db_session, sup).user
    sup_text = ai_context.build(db_session, sup_user, set(), limit=50)
    assert SECRET_NAME in sup_text, "برای ارزیابِ همان فرد باید دیده شود"


# ── نقطهٔ تأیید ────────────────────────────────────────────────────────────


def _seed(db, user, tool_name, arguments):
    conv = AiConversation(user_id=user.id, title="t")
    db.add(conv)
    db.flush()
    row = AiPendingAction(
        conversation_id=conv.id, user_id=user.id, tool_name=tool_name,
        arguments_json=json.dumps(arguments, ensure_ascii=False),
        summary="کارِ آزمایشی", status="pending", created_at=datetime.now(UTC),
    )
    db.add(row)
    db.flush()
    return row


def _enable_ai(db, user):
    _enable_globally(db)
    db.add(AiUserAccess(user_id=user.id, enabled=True, allow_write_actions=True))
    db.flush()


def _enable_globally(db):
    from tests.helpers import enable_ai_provider

    # آدرسِ بسته و عمدی: این فایل گاردها را می‌سنجد، نه یک تماسِ موفق.
    enable_ai_provider(db, base_url="http://127.0.0.1:1", allow_write_actions=True)


def test_one_user_cannot_confirm_another_users_pending_action(client, db_session):
    owner = make_user(db_session, "hr", username="cf_owner", capabilities=list(Capability))
    other = make_user(db_session, "hr", username="cf_other", capabilities=list(Capability))
    _enable_ai(db_session, owner)
    _enable_ai(db_session, other)
    p = make_personnel(db_session, full_name="هدفِ آزمون")
    row = _seed(db_session, owner, "separate_personnel",
                {"personnel_id": p.id, "separation_date": "2026-01-01", "reason": "x"})
    db_session.commit()

    r = client.post(f"/api/ai/pending/{row.id}/confirm", headers=auth_header(other))
    assert r.status_code == 404, f"کاربر دیگر نباید بتواند تأیید کند، ولی {r.status_code} گرفت"

    rej = client.post(f"/api/ai/pending/{row.id}/reject", headers=auth_header(other))
    assert rej.status_code == 404, f"رد کردن هم نباید ممکن باشد، ولی {rej.status_code}"

    db_session.expire_all()
    assert db_session.get(AiPendingAction, row.id).status == "pending"


def test_a_pending_action_executes_at_most_once(client, db_session):
    owner = make_user(db_session, "hr", username="cf_once", capabilities=list(Capability))
    _enable_ai(db_session, owner)
    p = make_personnel(db_session, full_name="یک‌بارِ آزمون")
    row = _seed(db_session, owner, "update_personnel",
                {"personnel_id": p.id, "job_title": "عنوانِ تازه"})
    db_session.commit()

    first = client.post(f"/api/ai/pending/{row.id}/confirm", headers=auth_header(owner))
    second = client.post(f"/api/ai/pending/{row.id}/confirm", headers=auth_header(owner))
    print("first:", first.status_code, "second:", second.status_code)
    assert first.status_code == 200, first.text
    assert second.status_code in (400, 409), f"تأیید دوم باید رد شود، نه {second.status_code}"


def test_confirm_is_refused_once_write_access_is_revoked(client, db_session):
    owner = make_user(db_session, "hr", username="cf_revoked", capabilities=list(Capability))
    _enable_globally(db_session)
    access = AiUserAccess(user_id=owner.id, enabled=True, allow_write_actions=True)
    db_session.add(access)
    db_session.flush()
    p = make_personnel(db_session, full_name="لغوِ دسترسی")
    row = _seed(db_session, owner, "update_personnel",
                {"personnel_id": p.id, "job_title": "نباید اعمال شود"})
    db_session.commit()

    # پیشنهاد ساخته شد، بعد اجازهٔ نوشتن گرفته شد
    access.allow_write_actions = False
    db_session.add(access)
    db_session.commit()

    r = client.post(f"/api/ai/pending/{row.id}/confirm", headers=auth_header(owner))
    assert r.status_code == 403, f"باید ۴۰۳ می‌گرفت، نه {r.status_code}: {r.text[:200]}"
    db_session.expire_all()
    assert db_session.get(AiPendingAction, row.id).status == "pending"
