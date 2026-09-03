"""تست‌های مدیریت شاخص‌ها: افزودن خودکار به انتهای ترتیب، تغییر ترتیب (drag) و حذف."""
from app.models.enums import Capability
from tests.helpers import (
    active_indicators,
    auth_header,
    full_valid_scores,
    make_access,
    make_personnel,
    make_user,
)


def _create(client, hr, category: str, section: str = "general", display_order: int = 999):
    # display_order عمداً مقدار «اشتباه» می‌فرستیم تا ثابت شود سرور آن را نادیده می‌گیرد.
    return client.post(
        "/api/indicators",
        json={
            "section": section,
            "category": category,
            "description": "شرح",
            "display_order": display_order,
        },
        headers=auth_header(hr),
    )


def test_create_ignores_client_order_and_appends_to_end(client, db_session):
    hr = make_user(db_session, "hr")
    db_session.commit()

    # بیشترین ترتیب فعلی بخش general را می‌گیریم تا افزودنی‌ها بعد از آن باشند
    existing = client.get(
        "/api/indicators", params={"section": "general", "include_inactive": True}, headers=auth_header(hr)
    ).json()
    base_max = max((i["display_order"] for i in existing), default=0)

    a = _create(client, hr, "شاخص الف").json()
    b = _create(client, hr, "شاخص ب").json()
    assert a["display_order"] == base_max + 1
    assert b["display_order"] == base_max + 2


def test_reorder_persists_new_order(client, db_session):
    hr = make_user(db_session, "hr")
    db_session.commit()

    a = _create(client, hr, "الف", section="specialized").json()
    b = _create(client, hr, "ب", section="specialized").json()
    c = _create(client, hr, "ج", section="specialized").json()

    all_ids = [
        i["id"]
        for i in client.get(
            "/api/indicators",
            params={"section": "specialized", "include_inactive": True},
            headers=auth_header(hr),
        ).json()
    ]
    # c را به ابتدا می‌بریم، بقیه به همان ترتیب
    new_order = [c["id"]] + [i for i in all_ids if i != c["id"]]

    r = client.patch(
        "/api/indicators/reorder",
        json={"section": "specialized", "ordered_ids": new_order},
        headers=auth_header(hr),
    )
    assert r.status_code == 204, r.text

    after = client.get(
        "/api/indicators",
        params={"section": "specialized", "include_inactive": True},
        headers=auth_header(hr),
    ).json()
    assert [i["id"] for i in after] == new_order
    assert after[0]["id"] == c["id"] and after[0]["display_order"] == 1
    assert {a["id"], b["id"]}.issubset({i["id"] for i in after})


def test_reorder_rejects_mismatched_id_set(client, db_session):
    hr = make_user(db_session, "hr")
    db_session.commit()
    a = _create(client, hr, "الف", section="specialized").json()

    # فهرست ناقص/اضافه → ۴۰۰
    r = client.patch(
        "/api/indicators/reorder",
        json={"section": "specialized", "ordered_ids": [a["id"], 999999]},
        headers=auth_header(hr),
    )
    assert r.status_code == 400


def test_delete_unused_indicator_succeeds(client, db_session):
    hr = make_user(db_session, "hr")
    db_session.commit()
    ind = _create(client, hr, "قابل حذف", section="specialized").json()

    r = client.delete(f"/api/indicators/{ind['id']}", headers=auth_header(hr))
    assert r.status_code == 204, r.text

    remaining = client.get(
        "/api/indicators",
        params={"section": "specialized", "include_inactive": True},
        headers=auth_header(hr),
    ).json()
    assert ind["id"] not in {i["id"] for i in remaining}


def test_delete_scored_indicator_conflicts(client, db_session):
    """شاخصی که در یک ارزیابی امتیاز خورده قابل حذف نیست (۴۰۹) — باید غیرفعال شود."""
    hr = make_user(db_session, "hr")
    sup = make_user(db_session, "unit_supervisor")
    dep = make_user(db_session, "deputy")
    ceo = make_user(db_session, "ceo")
    personnel = make_personnel(db_session)
    make_access(db_session, personnel, sup, dep, ceo)
    db_session.commit()

    indicators = active_indicators(db_session)
    eid = client.post(
        "/api/evaluations", json={"subject_personnel_id": personnel.id}, headers=auth_header(sup)
    ).json()["id"]
    client.put(
        f"/api/evaluations/{eid}/scores",
        json={"scores": full_valid_scores(indicators)},
        headers=auth_header(sup),
    )
    client.post(f"/api/evaluations/{eid}/submit", headers=auth_header(sup))

    scored_id = indicators[0].id
    r = client.delete(f"/api/indicators/{scored_id}", headers=auth_header(hr))
    assert r.status_code == 409, r.text


def test_reorder_and_delete_forbidden_for_non_hr(client, db_session):
    hr = make_user(db_session, "hr")
    sup = make_user(db_session, "unit_supervisor")
    db_session.commit()
    ind = _create(client, hr, "الف", section="specialized").json()

    assert (
        client.patch(
            "/api/indicators/reorder",
            json={"section": "specialized", "ordered_ids": [ind["id"]]},
            headers=auth_header(sup),
        ).status_code
        == 403
    )
    assert client.delete(f"/api/indicators/{ind['id']}", headers=auth_header(sup)).status_code == 403


# ── وزنِ شاخص و جایگزینی (M-4) ─────────────────────────────────────────────


def test_the_list_says_what_each_indicator_weighs_in_the_active_scheme(client, db_session):
    """بی این عدد، «جایگزینی» یک ضررِ نامرئی داشت.

    `ScoringScheme.indicator_weights` با *شناسه* کلید خورده و جایگزینی شناسهٔ
    تازه می‌سازد؛ طرحِ فعال هم تغییرناپذیر است. پس شاخصی با وزن ۳، جایگزینش
    وزن ۱ می‌گیرد — و تا امروز هیچ‌جا گفته نمی‌شد. منابع انسانی که فکر می‌کرد
    یک اصلاح نگارشی می‌کند، وزنِ سؤال را برای همهٔ پرونده‌های بعدی عوض می‌کرد.
    """
    from app.models.scoring_scheme import ScoringScheme
    from app.services.scoring_scheme import active_scheme

    hr = make_user(db_session, "hr", capabilities=[Capability.manage_scoring])
    db_session.commit()
    target = active_indicators(db_session)[0]

    rows = client.get("/api/indicators", headers=auth_header(hr)).json()
    assert next(r for r in rows if r["id"] == target.id)["scheme_weight"] == 1.0

    scheme = active_scheme(db_session)
    assert scheme is not None
    db_session.get(ScoringScheme, scheme.id).indicator_weights = {str(target.id): 3.0}
    db_session.commit()

    rows = client.get("/api/indicators", headers=auth_header(hr)).json()
    assert next(r for r in rows if r["id"] == target.id)["scheme_weight"] == 3.0


def test_replacing_an_indicator_records_the_weight_it_drops(client, db_session):
    """بستنِ کار راه نیست (شناسهٔ تازه پیش از جایگزینی وجود ندارد، پس
    پیش‌نویسی که وزنش را داشته باشد هم ساخته نمی‌شود). پس عدد باید *ثبت* شود."""
    from app.models.scoring_scheme import ScoringScheme
    from app.services.scoring_scheme import active_scheme

    hr = make_user(
        db_session, "hr", capabilities=[Capability.manage_scoring, Capability.view_audit_log]
    )
    db_session.commit()
    target = active_indicators(db_session)[0]
    scheme = active_scheme(db_session)
    db_session.get(ScoringScheme, scheme.id).indicator_weights = {str(target.id): 2.5}
    db_session.commit()

    replaced = client.post(
        f"/api/indicators/{target.id}/replace",
        json={
            "category": target.category,
            "description": "متنِ تازه با معنای تازه",
            "reason": "سؤال دو مفهوم را با هم می‌پرسید",
        },
        headers=auth_header(hr),
    )
    assert replaced.status_code == 201, replaced.text
    assert replaced.json()["scheme_weight"] == 1.0

    events = client.get(
        "/api/audit-log", params={"event_type": "indicator_replaced"}, headers=auth_header(hr)
    ).json()["items"]
    assert events[0]["new_value"]["weight_before"] == 2.5
    assert events[0]["new_value"]["weight_after"] == 1.0
