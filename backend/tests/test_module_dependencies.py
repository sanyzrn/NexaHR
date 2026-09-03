"""زنجیرهٔ وابستگیِ ماژول‌ها (B-H1).

توضیحِ خودِ ماژولِ «اعتراض به نتیجه» می‌گفت «این گزینه با نمایش نتایج کارمند
معنا پیدا می‌کند» — ولی هیچ‌چیز اجرایش نمی‌کرد. سه ماژول به
`employee_evaluation_visibility` وابسته‌اند و هر سه مستقل روشن/خاموش می‌شدند،
پس پیکربندیِ بی‌معنا ممکن بود و ظاهرِ سالم داشت: کارمند دکمهٔ اعتراض دارد به
عددی که سرور از نشان‌دادنش امتناع می‌کند.
"""
import pytest

from app.core.modules import MODULES, MODULES_BY_KEY, dependents_of
from app.models.enums import Capability
from app.services.authorization import (
    ensure_module_enabled,
    is_module_enabled,
    stored_module_state,
    unmet_requirements,
)
from tests.helpers import auth_header, make_user, set_module

PARENT = "employee_evaluation_visibility"
CHILD = "objections"


def test_every_declared_requirement_is_a_real_key():
    for module in MODULES:
        for required in module.requires:
            assert required in MODULES_BY_KEY, f"{module.key} → {required}"


def test_the_three_employee_modules_declare_the_parent():
    assert set(dependents_of(PARENT)) == {
        "objections",
        "employee_overview_cards",
        "employee_result_acknowledgement",
    }


def test_child_on_parent_off_is_effectively_off(db_session):
    """قلبِ ماجرا."""
    db = db_session
    set_module(db, PARENT, False)
    set_module(db, CHILD, True)
    db.commit()

    assert stored_module_state(db, CHILD) is True, "سوییچِ خودش روشن است"
    assert is_module_enabled(db, CHILD) is False, "ولی واقعاً کار نمی‌کند"
    assert unmet_requirements(db, CHILD) == (PARENT,)


def test_child_works_once_parent_is_on(db_session):
    db = db_session
    set_module(db, PARENT, True)
    set_module(db, CHILD, True)
    db.commit()
    assert is_module_enabled(db, CHILD) is True
    assert unmet_requirements(db, CHILD) == ()


def test_guard_message_names_the_blocking_parent(db_session):
    """مدیری که سوییچ را روشن می‌بیند نباید دنبال خطای نامربوط بگردد."""
    from fastapi import HTTPException

    db = db_session
    set_module(db, PARENT, False)
    set_module(db, CHILD, True)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        ensure_module_enabled(db, CHILD)
    detail = exc.value.detail
    assert MODULES_BY_KEY[PARENT].label in detail, detail
    assert "نیاز دارد" in detail


def test_guard_message_is_the_plain_one_when_child_itself_is_off(db_session):
    """اگر خودِ سوییچ خاموش است، پیامِ وابستگی گیج‌کننده می‌شد."""
    from fastapi import HTTPException

    db = db_session
    set_module(db, PARENT, False)
    set_module(db, CHILD, False)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        ensure_module_enabled(db, CHILD)
    assert "غیرفعال شده است" in exc.value.detail
    assert "نیاز دارد" not in exc.value.detail


def test_api_exposes_the_blockers(client, db_session):
    """رابط با همین، سوییچ را غیرفعال می‌کند و دلیلش را می‌گوید."""
    db = db_session
    set_module(db, PARENT, False)
    set_module(db, CHILD, True)
    hr = make_user(db, "hr", capabilities=[Capability.manage_modules])
    db.commit()

    r = client.get("/api/administration/modules", headers=auth_header(hr))
    assert r.status_code == 200, r.text
    rows = {m["key"]: m for m in r.json()}

    child = rows[CHILD]
    assert child["enabled"] is True, "سوییچِ ذخیره‌شده نمایش داده می‌شود"
    assert child["requires"] == [PARENT]
    assert child["blocked_by"] == [PARENT]

    parent = rows[PARENT]
    assert parent["blocked_by"] == []
    assert set(parent["dependents"]) == set(dependents_of(PARENT))


def test_parent_on_clears_the_blockers_in_the_api(client, db_session):
    db = db_session
    set_module(db, PARENT, True)
    set_module(db, CHILD, True)
    hr = make_user(db, "hr", capabilities=[Capability.manage_modules])
    db.commit()

    rows = {
        m["key"]: m
        for m in client.get("/api/administration/modules", headers=auth_header(hr)).json()
    }
    assert rows[CHILD]["blocked_by"] == []


def test_toggle_response_carries_the_same_fields(client, db_session):
    db = db_session
    set_module(db, PARENT, False)
    hr = make_user(db, "hr", capabilities=[Capability.manage_modules])
    db.commit()

    r = client.put(
        f"/api/administration/modules/{CHILD}",
        json={"enabled": True},
        headers=auth_header(hr),
    )
    assert r.status_code == 200, r.text
    assert r.json()["blocked_by"] == [PARENT]
