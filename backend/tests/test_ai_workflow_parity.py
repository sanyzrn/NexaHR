"""مسیرِ دستیار و مسیرِ رابط باید یک چیز باشند — نه دو نسخهٔ شبیه به هم.

`advance_evaluation` تا دیروز مستقیم `apply_transition` را صدا می‌زد. ماشین
حالت فقط *گذار* را می‌سنجد؛ هر چیز دیگری که یک تأیید لازم دارد در خودِ
endpoint است. نتیجه چهار خرابیِ جدا بود، همه از یک ریشه:

* `submit` بی `finalize_scoring` می‌گذشت: بی اعتبارسنجیِ شواهد، بی وارسیِ
  کاملِ شاخص‌ها، و بی محاسبهٔ نتیجه.
* `ceo_finalize` بی `final_snapshot` و `verify_token` نهایی می‌کرد — و
  `finalized` وضعیتِ پایانی است، پس آن پرونده *برای همیشه* بی‌کارنامه می‌ماند.
* `ensure_hr_may_handle` در روترها بود و نه در گذار، پس کارمندِ منابع انسانی
  از راهِ دستیار پروندهٔ خودش را تأیید یا لغو می‌کرد.
* و `return`/`hr_claim` اصلاً گذاری در `TRANSITIONS` ندارند؛ `KeyError` که به
  ۵۰۰ ترجمه می‌شد.

پس این فایل یک پرسش دارد و آن را برای *هر* اقدام می‌پرسد: پرونده‌ای که از راه
دستیار پیش رفته، با پرونده‌ای که از راه HTTP پیش رفته، آیا در همان حال است؟
و آن‌جا که رابط رد می‌کند، آیا دستیار هم رد می‌کند؟
"""
import pytest
from fastapi import HTTPException

from app.models.enums import EvaluationStatus, UserRole
from app.models.evaluation import EvaluationRecord
from app.schemas.auth import CurrentUser
from app.services.ai.tools import base as tools_base
from app.services.ai.tools.evaluations import _ADVANCE, _ADVANCE_ACTIONS
from tests.helpers import (
    active_indicators,
    auth_header,
    full_valid_scores,
    make_access,
    make_hr_unit,
    make_personnel,
    make_user,
)

#: حالتی که «پیش رفتنِ پرونده» را می‌سازد. اگر مسیر دستیار هر یک از این‌ها را
#: جا بگذارد، پرونده *به‌نظر* جلو رفته و در واقع خراب شده — همان چیزی که هیچ
#: گزارشی نشانش نمی‌داد.
_STATE_FIELDS = (
    "status",
    "base_weighted_pct",
    "general_score_pct",
    "specialized_score_pct",
    "final_weighted_pct",
    "recommendation",
    "hr_user_id",
)


def _snapshot(record: EvaluationRecord) -> dict:
    state = {name: getattr(record, name) for name in _STATE_FIELDS}
    # زمان و سند و توکن هرگز دقیقاً یکی نمی‌شوند؛ چیزی که مهم است «نشسته یا نه».
    state["finalized"] = record.finalized_at is not None
    state["has_snapshot"] = record.final_snapshot is not None
    state["has_verify_token"] = bool(record.verify_token)
    return state


def _ctx(db, user, caps=None) -> tools_base.ToolContext:
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
        caps=frozenset(caps or set()),
        conversation_id=0,
    )


def _advance_by_copilot(db, user, evaluation_id: int, action: str, reason: str = ""):
    """همان راهی که نقطهٔ تأیید می‌رود: `execute_tool`، با گاردِ کامل."""
    arguments = {"evaluation_id": evaluation_id, "action": action}
    if reason:
        arguments["reason"] = reason
    return tools_base.execute_tool(
        _ctx(db, user), tools_base.REGISTRY["advance_evaluation"], arguments
    )


# ── بازیگرها و ساختِ پرونده ────────────────────────────────────────────────


@pytest.fixture()
def chain(db_session):
    """یک زنجیرهٔ کاملِ چهار مرحله‌ای — همان شکلِ رایج."""
    hr = make_user(db_session, "hr")
    sup = make_user(db_session, "unit_supervisor")
    dep = make_user(db_session, "deputy")
    ceo = make_user(db_session, "ceo")
    db_session.commit()
    return {"hr": hr, "sup": sup, "dep": dep, "ceo": ceo}


def _fresh_case(client, db_session, chain) -> int:
    """پروندهٔ تازه در مرحلهٔ نمره‌دهی، با امتیازهای کاملِ معتبر."""
    personnel = make_personnel(db_session, full_name="موضوع همسنجی")
    make_access(db_session, personnel, chain["sup"], chain["dep"], chain["ceo"])
    db_session.commit()
    created = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": personnel.id},
        headers=auth_header(chain["sup"]),
    )
    assert created.status_code == 201, created.text
    record_id = created.json()["id"]
    scored = client.put(
        f"/api/evaluations/{record_id}/scores",
        json={"scores": full_valid_scores(active_indicators(db_session))},
        headers=auth_header(chain["sup"]),
    )
    assert scored.status_code == 200, scored.text
    return record_id


#: برای هر اقدام: مراحلی که باید *پیش* از آن از راه HTTP طی شود، بازیگرش، و
#: دلیلی که لازم دارد.
_PRECONDITIONS: dict[str, tuple[list[tuple[str, str]], str, str]] = {
    "submit": ([], "sup", ""),
    "hr_approve": ([("submit", "sup")], "hr", ""),
    "deputy_approve": ([("submit", "sup"), ("hr-approve", "hr")], "dep", ""),
    "ceo_finalize": (
        [("submit", "sup"), ("hr-approve", "hr"), ("deputy-approve", "dep")],
        "ceo",
        "",
    ),
    "return": ([("submit", "sup")], "hr", "شواهد یکی از شاخص‌ها کافی نیست"),
    "cancel": ([], "hr", "تأییدکنندهٔ این پرونده از سازمان رفته است"),
    "hr_claim": ([("submit", "sup")], "hr", ""),
}

#: مسیرِ HTTPِ هر اقدام — قرینهٔ دقیقِ همان اقدام در رابط.
_HTTP_PATH = {
    "submit": "submit",
    "hr_approve": "hr-approve",
    "deputy_approve": "deputy-approve",
    "ceo_finalize": "ceo-finalize",
    "return": "return",
    "cancel": "cancel",
    "hr_claim": "hr-claim",
}


def _prepare(client, db_session, chain, action: str) -> int:
    steps, _, _ = _PRECONDITIONS[action]
    record_id = _fresh_case(client, db_session, chain)
    for path, actor in steps:
        done = client.post(
            f"/api/evaluations/{record_id}/{path}", headers=auth_header(chain[actor])
        )
        assert done.status_code == 200, (action, path, done.text)
    return record_id


# ── جدولِ اقدام‌ها ─────────────────────────────────────────────────────────


def test_every_advertised_action_has_a_real_runner():
    """`enum`ِ شِما و جدولِ اجرا یک چیزند.

    این تست همان خرابیِ H4 را می‌گیرد: دو اکشن در `enum` بودند که هیچ مسیرِ
    اجرایی نداشتند و روی `TRANSITIONS[action]` با `KeyError` می‌افتادند.
    حالا `enum` *از* جدول ساخته می‌شود، پس واگرایی ساختاراً ناممکن است — و
    این تست همان تضمین را قفل می‌کند تا کسی دوباره دستی رونویسی‌شان نکند.
    """
    schema_enum = tools_base.REGISTRY["advance_evaluation"].parameters["properties"]["action"]["enum"]
    assert set(schema_enum) == set(_ADVANCE)
    assert set(_ADVANCE_ACTIONS) == set(_ADVANCE)
    # و هر اقدام باید در این فایل هم پیش‌شرط و مسیرِ HTTP داشته باشد، وگرنه
    # اقدامِ تازه بی‌آنکه سنجیده شود اضافه می‌شود.
    assert set(_PRECONDITIONS) == set(_ADVANCE)
    assert set(_HTTP_PATH) == set(_ADVANCE)


def test_an_unknown_action_is_a_bad_request_not_a_crash(client, db_session, chain):
    record_id = _fresh_case(client, db_session, chain)
    with pytest.raises(HTTPException) as err:
        _advance_by_copilot(db_session, chain["sup"], record_id, "finalize_now")
    assert err.value.status_code == 400


# ── همسنجیِ حالت: دو پرونده، دو مسیر، یک نتیجه ─────────────────────────────


@pytest.mark.parametrize("action", sorted(_ADVANCE))
def test_the_copilot_path_lands_in_the_same_state_as_the_http_path(
    client, db_session, chain, action
):
    _, actor_key, reason = _PRECONDITIONS[action]
    actor = chain[actor_key]

    via_http = _prepare(client, db_session, chain, action)
    response = client.post(
        f"/api/evaluations/{via_http}/{_HTTP_PATH[action]}",
        json={"reason": reason} if reason else None,
        headers=auth_header(actor),
    )
    assert response.status_code == 200, (action, response.text)
    db_session.expire_all()
    expected = _snapshot(db_session.get(EvaluationRecord, via_http))

    via_copilot = _prepare(client, db_session, chain, action)
    outcome = _advance_by_copilot(db_session, actor, via_copilot, action, reason)
    assert outcome.summary
    db_session.expire_all()
    actual = _snapshot(db_session.get(EvaluationRecord, via_copilot))

    assert actual == expected, action


# ── هر خرابی، جدا ─────────────────────────────────────────────────────────


def test_submit_through_the_copilot_computes_the_result(client, db_session, chain):
    """C1 — پرونده‌ای که بی `finalize_scoring` ثبت شود، بی‌نتیجه جلو می‌رود."""
    record_id = _fresh_case(client, db_session, chain)
    _advance_by_copilot(db_session, chain["sup"], record_id, "submit")
    db_session.expire_all()
    record = db_session.get(EvaluationRecord, record_id)
    assert record.status is EvaluationStatus.submitted
    assert record.final_weighted_pct is not None
    assert record.base_weighted_pct is not None


def test_submit_through_the_copilot_enforces_the_evidence_rule(client, db_session, chain):
    """و همان اعتبارسنجی‌ای که فرمِ رابط دارد: امتیازِ بالا شواهد می‌خواهد."""
    personnel = make_personnel(db_session, full_name="بی‌شواهد")
    make_access(db_session, personnel, chain["sup"], chain["dep"], chain["ceo"])
    db_session.commit()
    record_id = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": personnel.id},
        headers=auth_header(chain["sup"]),
    ).json()["id"]
    indicators = active_indicators(db_session)
    client.put(
        f"/api/evaluations/{record_id}/scores",
        json={"scores": [{"indicator_id": ind.id, "score": 5} for ind in indicators]},
        headers=auth_header(chain["sup"]),
    )

    with pytest.raises(HTTPException) as err:
        _advance_by_copilot(db_session, chain["sup"], record_id, "submit")
    assert err.value.status_code == 400
    db_session.expire_all()
    assert db_session.get(EvaluationRecord, record_id).status is EvaluationStatus.draft


def test_ceo_finalize_through_the_copilot_leaves_a_document(client, db_session, chain):
    """C2 — بی اسنپ‌شات، پرونده برای همیشه بی‌کارنامه می‌ماند."""
    record_id = _prepare(client, db_session, chain, "ceo_finalize")
    _advance_by_copilot(db_session, chain["ceo"], record_id, "ceo_finalize")
    db_session.expire_all()
    record = db_session.get(EvaluationRecord, record_id)
    assert record.status is EvaluationStatus.finalized
    assert record.final_snapshot is not None
    assert record.verify_token
    assert record.finalized_at is not None


def test_finalising_without_a_document_is_refused_at_the_transition(client, db_session, chain):
    """گاردِ دومِ همان خرابی — برای فراخوانندهٔ بعدی که یادش برود.

    `apply_transition` را مستقیم صدا می‌زنیم؛ همان کاری که مسیرِ دستیار
    می‌کرد. حالا خودِ گذار جلویش را می‌گیرد، پس هیچ فراخوانندهٔ آینده‌ای
    نمی‌تواند پروندهٔ بی‌سند را با امضای «نهایی‌شده» ببندد.
    """
    from app.services.workflow import apply_transition

    record_id = _prepare(client, db_session, chain, "ceo_finalize")
    record = db_session.get(EvaluationRecord, record_id)
    assert record.final_snapshot is None
    with pytest.raises(HTTPException) as err:
        apply_transition(db_session, record, "ceo_finalize", _ctx(db_session, chain["ceo"]).user)
    assert err.value.status_code == 400
    db_session.rollback()


def test_return_through_the_copilot_works_and_records_the_reason(client, db_session, chain):
    """H4 — رایج‌ترین اقدامِ اصلاحیِ گردش‌کار، از راه دستیار ۵۰۰ می‌داد."""
    record_id = _prepare(client, db_session, chain, "return")
    _advance_by_copilot(
        db_session, chain["hr"], record_id, "return", "شواهد شاخص سوم کافی نیست"
    )
    db_session.expire_all()
    record = db_session.get(EvaluationRecord, record_id)
    assert record.status is EvaluationStatus.draft

    comments = client.get(
        f"/api/evaluations/{record_id}", headers=auth_header(chain["hr"])
    ).json()["comments"]
    assert any("شواهد شاخص سوم کافی نیست" in c["comment_text"] for c in comments), (
        "دلیلِ برگشت باید در پرونده دیده شود؛ پیش از این گرفته می‌شد و هیچ‌جا نمی‌نشست"
    )


def test_a_return_without_a_reason_is_refused(client, db_session, chain):
    record_id = _prepare(client, db_session, chain, "return")
    with pytest.raises(HTTPException) as err:
        _advance_by_copilot(db_session, chain["hr"], record_id, "return", "   ")
    assert err.value.status_code == 400


def test_cancel_through_the_copilot_records_the_reason(client, db_session, chain):
    record_id = _fresh_case(client, db_session, chain)
    _advance_by_copilot(
        db_session, chain["hr"], record_id, "cancel", "تأییدکننده از سازمان رفت"
    )
    db_session.expire_all()
    assert db_session.get(EvaluationRecord, record_id).status is EvaluationStatus.cancelled
    comments = client.get(
        f"/api/evaluations/{record_id}", headers=auth_header(chain["hr"])
    ).json()["comments"]
    assert any("تأییدکننده از سازمان رفت" in c["comment_text"] for c in comments)


def test_hr_claim_through_the_copilot_works(client, db_session, chain):
    """H4، نیمهٔ دوم — این هم گذاری در `TRANSITIONS` ندارد."""
    record_id = _prepare(client, db_session, chain, "hr_claim")
    _advance_by_copilot(db_session, chain["hr"], record_id, "hr_claim")
    db_session.expire_all()
    assert db_session.get(EvaluationRecord, record_id).hr_user_id == chain["hr"].id


# ── همان ردهایی که رابط می‌دهد ─────────────────────────────────────────────


def test_hr_cannot_handle_its_own_case_through_the_copilot(client, db_session, chain):
    """C3 — `ensure_hr_may_handle` در روترها بود، پس مسیرِ دستیار از کنارش می‌گذشت."""
    hr_unit = make_hr_unit(db_session)
    subject = make_personnel(db_session, full_name="خودِ منابع انسانی", org_unit=hr_unit)
    hr_self = make_user(db_session, "hr", personnel_id=subject.id)
    make_access(db_session, subject, chain["sup"], chain["dep"], chain["ceo"])
    db_session.commit()
    record_id = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": subject.id},
        headers=auth_header(chain["sup"]),
    ).json()["id"]
    client.put(
        f"/api/evaluations/{record_id}/scores",
        json={"scores": full_valid_scores(active_indicators(db_session))},
        headers=auth_header(chain["sup"]),
    )
    client.post(f"/api/evaluations/{record_id}/submit", headers=auth_header(chain["sup"]))
    db_session.expire_all()

    for action, reason in (("hr_approve", ""), ("cancel", "دلیلی"), ("hr_claim", "")):
        with pytest.raises(HTTPException) as err:
            _advance_by_copilot(db_session, hr_self, record_id, action, reason)
        assert err.value.status_code in (400, 403), action
        db_session.rollback()


def test_a_role_that_the_ui_would_refuse_is_refused_here_too(client, db_session, chain):
    """گاردِ نقشِ endpoint در `Depends` است و مسیرِ دستیار آن را اجرا نمی‌کند.

    برای اقدام‌هایی که گذار دارند، `ensure_transition_allowed` همان سنجش را
    تکرار می‌کند. `hr_claim` اما هیچ گذاری ندارد — تنها گاردِ نقشش همان
    `Depends` بود، پس بی جدولِ `_ADVANCE` هر نقشی می‌توانست پروندهٔ صفِ
    منابع انسانی را «تحویل بگیرد».
    """
    record_id = _prepare(client, db_session, chain, "hr_claim")
    for actor in (chain["sup"], chain["dep"], chain["ceo"]):
        with pytest.raises(HTTPException) as err:
            _advance_by_copilot(db_session, actor, record_id, "hr_claim")
        assert err.value.status_code == 403, actor.username
        db_session.rollback()
    db_session.expire_all()
    assert db_session.get(EvaluationRecord, record_id).hr_user_id is None


def test_an_outsider_with_the_right_role_still_cannot_act(client, db_session, chain):
    """نقشِ درست کافی نیست؛ باید در زنجیرهٔ *همین* پرونده نشسته باشد."""
    record_id = _fresh_case(client, db_session, chain)
    stranger = make_user(db_session, "unit_supervisor", capabilities=[])
    db_session.commit()
    with pytest.raises(HTTPException) as err:
        _advance_by_copilot(db_session, stranger, record_id, "submit")
    assert err.value.status_code in (403, 404)


def test_the_copilot_cannot_skip_a_stage(client, db_session, chain):
    """گذار از `draft` مستقیم به تأیید نهایی — همان چیزی که رابط دکمه‌اش را ندارد."""
    record_id = _fresh_case(client, db_session, chain)
    for action, actor in (
        ("hr_approve", chain["hr"]),
        ("deputy_approve", chain["dep"]),
        ("ceo_finalize", chain["ceo"]),
    ):
        with pytest.raises(HTTPException) as err:
            _advance_by_copilot(db_session, actor, record_id, action)
        assert err.value.status_code in (400, 403, 409), action
        db_session.rollback()
    db_session.expire_all()
    assert db_session.get(EvaluationRecord, record_id).status is EvaluationStatus.draft


def test_a_read_only_copilot_cannot_advance_anything(client, db_session, chain):
    """سوییچِ نوشتن در لحظهٔ اجرا سنجیده می‌شود، نه فقط در تبلیغِ ابزار."""
    record_id = _fresh_case(client, db_session, chain)
    ctx = _ctx(db_session, chain["sup"])
    read_only = tools_base.ToolContext(
        db=ctx.db, user=ctx.user, caps=ctx.caps, conversation_id=0, allow_writes=False
    )
    with pytest.raises(HTTPException) as err:
        tools_base.execute_tool(
            read_only,
            tools_base.REGISTRY["advance_evaluation"],
            {"evaluation_id": record_id, "action": "submit"},
        )
    assert err.value.status_code == 403


def test_unused_role_import_is_referenced():
    """نگهبانِ کوچک: جدول باید با `UserRole`ها نوشته شده باشد، نه رشته."""
    assert all(callable(entry.may) for entry in _ADVANCE.values())
    assert _ADVANCE["hr_approve"].may(UserRole.hr)
    assert not _ADVANCE["hr_approve"].may(UserRole.ceo)
    # و قرینه‌اش: مافوق می‌تواند کارِ مرحلهٔ پایین‌تر را بکند.
    assert _ADVANCE["submit"].may(UserRole.ceo)
