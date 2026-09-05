"""پنج یافتهٔ تأییدشده از بازبینیِ چندزاویه‌ای.

هر کلاس یک یافته است و روی کدِ پیش از رفع می‌شکند.
"""
from datetime import UTC, datetime

import pytest
from sqlalchemy import event, text

from app.models.enums import Capability, UserRole
from app.models.evaluation import EvaluationRecord
from app.services.evaluation import applied_bonus
from app.services.scoring_scheme import LEGACY_RULES
from tests.helpers import (
    active_indicators,
    auth_header,
    full_valid_scores,
    make_access,
    make_personnel,
    make_user,
    set_module,
)


# ══════════════════════════════════════════════════════════════════════════
# R1 — خروجی اکسل: ساختِ فایل پس از commit یک N+1 می‌سازد
# ══════════════════════════════════════════════════════════════════════════
class TestExcelExportQueryCount:
    """`expire_on_commit` پیش‌فرضِ SQLAlchemy است، پس commit همهٔ ردیف‌های
    بارشده را باطل می‌کند. ساختنِ workbook *پس از* commit یعنی هر ستون یک
    SELECTِ تازه — N+1ی که از ترتیبِ فراخوانی می‌آید، نه از eager-loading.
    """

    @staticmethod
    def _count_selects(client, url, user):
        from app.db.session import engine

        seen = []

        def before(conn, cursor, statement, *a):
            if statement.lstrip().upper().startswith("SELECT"):
                seen.append(statement)

        event.listen(engine, "before_cursor_execute", before)
        try:
            r = client.get(url, headers=auth_header(user))
        finally:
            event.remove(engine, "before_cursor_execute", before)
        assert r.status_code == 200, r.text
        assert r.content[:2] == b"PK", "خروجی باید واقعاً یک فایل xlsx باشد"
        return len(seen)

    def _seed(self, client, db, n):
        ceo = make_user(db, "ceo")
        hr = make_user(db, "hr")
        for _ in range(n):
            person = make_personnel(db, org_unit="واحد خروجی")
            sup = make_user(db, "unit_supervisor")
            make_access(db, person, sup, None, ceo)
            db.commit()
            client.post(
                "/api/evaluations",
                json={"subject_personnel_id": person.id},
                headers=auth_header(sup),
            )
        db.commit()
        return hr

    def test_query_count_does_not_grow_with_rows(self, client, db_session):
        """قلبِ ماجرا: شمارِ کوئری باید *مستقل از تعداد ردیف* بماند."""
        db = db_session
        hr = self._seed(client, db, 2)
        few = self._count_selects(client, "/api/evaluations/export.xlsx", hr)

        for _ in range(6):
            person = make_personnel(db, org_unit="واحد خروجی")
            sup = make_user(db, "unit_supervisor")
            make_access(db, person, sup, None, make_user(db, "ceo"))
            db.commit()
            client.post(
                "/api/evaluations",
                json={"subject_personnel_id": person.id},
                headers=auth_header(sup),
            )
        db.commit()
        many = self._count_selects(client, "/api/evaluations/export.xlsx", hr)

        # با باگ، هر ردیفِ تازه دست‌کم یک SELECT اضافه می‌کند (در عمل چند تا).
        assert many - few <= 2, (
            f"شمارِ کوئری با تعدادِ ردیف رشد کرد: {few} → {many}. "
            "یعنی workbook پس از commit ساخته می‌شود."
        )

    @pytest.mark.parametrize(
        "url",
        [
            "/api/evaluations/export.xlsx",
            "/api/personnel/export.xlsx",
            "/api/users/export.xlsx",
            "/api/improvement-plans/export.xlsx",
        ],
    )
    def test_every_export_builds_before_commit(self, client, db_session, url):
        """چهار endpoint همین اشتباه را داشتند؛ هیچ‌کدام نباید عقب بماند."""
        import inspect

        from app.api.routers import evaluations, improvement_plans, personnel, users

        module = {
            "/api/evaluations/export.xlsx": evaluations,
            "/api/personnel/export.xlsx": personnel,
            "/api/users/export.xlsx": users,
            "/api/improvement-plans/export.xlsx": improvement_plans,
        }[url]
        src = inspect.getsource(module)
        for fn in [f for f in src.split("\ndef ") if "export.xlsx" in f or "_excel" in f]:
            if "build_" not in fn or "db.commit()" not in fn:
                continue
            build_at = fn.index("build_")
            commit_at = fn.index("db.commit()")
            assert build_at < commit_at, (
                f"{module.__name__}: workbook پس از commit ساخته می‌شود — "
                "هر ستون یک SELECTِ تازه می‌زند"
            )


# ══════════════════════════════════════════════════════════════════════════
# R2 — امتیازِ ویژه روی سندِ هش‌شده
# ══════════════════════════════════════════════════════════════════════════
class TestBonusOnTheDocument:
    """سند سه عدد کنار هم چاپ می‌کند و باید با هم جمع شوند."""

    def test_applied_bonus_is_clamped_to_the_ceiling(self):
        assert applied_bonus(5, LEGACY_RULES, 98.0) == 2.0
        assert applied_bonus(3, LEGACY_RULES, 80.0) == 3.0
        assert applied_bonus(99, LEGACY_RULES, 10.0) == LEGACY_RULES.bonus_max_points
        assert applied_bonus(None, LEGACY_RULES, 50.0) == 0.0

    def test_snapshot_prints_the_applied_bonus_not_the_raw_one(self, client, db_session):
        """پایهٔ نزدیک به ۱۰۰ با امتیازِ خامِ بزرگ — دقیقاً جایی که سقف می‌بُرد."""
        from app.services.snapshot import build_final_snapshot

        db = db_session
        person = make_personnel(db)
        sup = make_user(db, "unit_supervisor")
        ceo = make_user(db, "ceo")
        make_user(db, "hr")  # صفِ منابع انسانی باید خالی نباشد
        make_access(db, person, sup, None, ceo)
        db.commit()

        eid = client.post(
            "/api/evaluations",
            json={"subject_personnel_id": person.id},
            headers=auth_header(sup),
        ).json()["id"]
        indicators = active_indicators(db)
        assert client.put(
            f"/api/evaluations/{eid}/scores",
            json={
                "scores": [
                    # نمرهٔ ۵ شاهد لازم دارد؛ هدف رسیدن به پایهٔ ۱۰۰ است تا سقف
                    # حتماً امتیازِ ویژه را ببُرد — همان جایی که سند می‌شکست.
                    {"indicator_id": i.id, "score": 5,
                     "evidence_text": "شاهدِ آزمون برای این شاخص با واژگانِ کافی"}
                    for i in indicators
                ]
            },
            headers=auth_header(sup),
        ).status_code in (200, 201)
        # امتیازِ ویژه‌ای که با پایهٔ ۱۰۰ حتماً بریده می‌شود
        assert client.patch(
            f"/api/evaluations/{eid}/special-score",
            json={"bonus_points": 5, "bonus_reason": "دلیلِ آزمون برای امتیاز ویژه"},
            headers=auth_header(sup),
        ).status_code == 200
        assert client.post(f"/api/evaluations/{eid}/submit", headers=auth_header(sup)).status_code == 200

        record = db.get(EvaluationRecord, eid)
        snapshot = build_final_snapshot(db, record)

        base = snapshot["base_weighted_pct"]
        bonus = snapshot["bonus_points"] or 0.0
        final = snapshot["final_weighted_pct"]
        assert round(base + bonus, 1) == final, (
            f"سه عددِ سند با هم جمع نمی‌شوند: {base} + {bonus} ≠ {final}"
        )
        assert float(record.bonus_points) == 5.0, "مقدارِ خام باید در پرونده بماند"

    def test_unclamped_bonus_is_unchanged(self, client, db_session):
        """وقتی سقف نمی‌بُرد، سند باید همان عددِ ثبت‌شده را نشان بدهد."""
        from app.services.snapshot import build_final_snapshot

        db = db_session
        person = make_personnel(db)
        sup = make_user(db, "unit_supervisor")
        ceo = make_user(db, "ceo")
        make_access(db, person, sup, None, ceo)
        db.commit()
        eid = client.post(
            "/api/evaluations",
            json={"subject_personnel_id": person.id},
            headers=auth_header(sup),
        ).json()["id"]
        assert client.put(
            f"/api/evaluations/{eid}/scores",
            json={"scores": full_valid_scores(active_indicators(db))},
            headers=auth_header(sup),
        ).status_code in (200, 201)
        assert client.patch(
            f"/api/evaluations/{eid}/special-score",
            json={"bonus_points": 2, "bonus_reason": "دلیلِ آزمون برای امتیاز ویژه"},
            headers=auth_header(sup),
        ).status_code == 200
        assert client.post(f"/api/evaluations/{eid}/submit", headers=auth_header(sup)).status_code == 200

        snapshot = build_final_snapshot(db, db.get(EvaluationRecord, eid))
        assert snapshot["bonus_points"] == 2.0
        assert round(snapshot["base_weighted_pct"] + 2.0, 1) == snapshot["final_weighted_pct"]

    def test_no_bonus_leaves_the_block_out(self, client, db_session):
        """قالب با `{% if snapshot.bonus_points %}` شرط می‌گذارد."""
        from app.services.snapshot import build_final_snapshot

        db = db_session
        person = make_personnel(db)
        sup = make_user(db, "unit_supervisor")
        ceo = make_user(db, "ceo")
        make_access(db, person, sup, None, ceo)
        db.commit()
        eid = client.post(
            "/api/evaluations",
            json={"subject_personnel_id": person.id},
            headers=auth_header(sup),
        ).json()["id"]
        assert client.put(
            f"/api/evaluations/{eid}/scores",
            json={"scores": full_valid_scores(active_indicators(db))},
            headers=auth_header(sup),
        ).status_code in (200, 201)
        assert client.post(f"/api/evaluations/{eid}/submit", headers=auth_header(sup)).status_code == 200
        assert build_final_snapshot(db, db.get(EvaluationRecord, eid))["bonus_points"] is None


# ══════════════════════════════════════════════════════════════════════════
# R3 — نشتِ زنجیرهٔ ارزیابی از راهِ دستیار
# ══════════════════════════════════════════════════════════════════════════
class TestEvaluationAccessLeak:
    """`guarded_inline=True` ادعای گاردِ درون‌بدنه بود و بدنه نداشتش."""

    @staticmethod
    def _ctx(db, user):
        from app.schemas.auth import CurrentUser
        from app.services.ai.tools.base import ToolContext

        return ToolContext(
            db=db,
            user=CurrentUser(
                id=user.id,
                username=user.username,
                role=user.role,
                personnel_id=user.personnel_id,
                full_name=user.username,
                must_change_password=False,
            ),
            caps=frozenset(),
            conversation_id=0,
        )

    def test_employee_cannot_read_an_unrelated_chain(self, client, db_session):
        from fastapi import HTTPException

        from app.services.ai.tools.people import get_evaluation_access

        db = db_session
        stranger = make_personnel(db, full_name="پرسنلِ بی‌ربط")
        sup = make_user(db, "unit_supervisor")
        ceo = make_user(db, "ceo")
        make_access(db, stranger, sup, None, ceo)
        onlooker_person = make_personnel(db)
        onlooker = make_user(db, "employee", personnel_id=onlooker_person.id)
        db.commit()

        with pytest.raises(HTTPException) as exc:
            get_evaluation_access(self._ctx(db, onlooker), personnel_id=stranger.id)
        assert exc.value.status_code == 403

    def test_hr_still_reads_it(self, client, db_session):
        from app.schemas.auth import CurrentUser
        from app.services.ai.tools.base import ToolContext
        from app.services.ai.tools.people import get_evaluation_access

        db = db_session
        person = make_personnel(db)
        sup = make_user(db, "unit_supervisor")
        ceo = make_user(db, "ceo")
        make_access(db, person, sup, None, ceo)
        hr = make_user(db, "hr")
        db.commit()

        ctx = ToolContext(
            db=db,
            user=CurrentUser(
                id=hr.id, username=hr.username, role=UserRole.hr, personnel_id=None,
                full_name=hr.username, must_change_password=False,
            ),
            caps=frozenset({Capability.manage_personnel}),
            conversation_id=0,
        )
        out = get_evaluation_access(ctx, personnel_id=person.id)
        assert sup.username in out.content

    def test_the_subject_reads_their_own_chain(self, client, db_session):
        """قاعده همان `_can_view_personnel` است و پروندهٔ خودِ فرد را می‌بندد."""
        from app.services.ai.tools.people import get_evaluation_access

        db = db_session
        person = make_personnel(db)
        sup = make_user(db, "unit_supervisor")
        ceo = make_user(db, "ceo")
        make_access(db, person, sup, None, ceo)
        subject = make_user(db, "employee", personnel_id=person.id)
        db.commit()
        out = get_evaluation_access(self._ctx(db, subject), personnel_id=person.id)
        assert sup.username in out.content


# ══════════════════════════════════════════════════════════════════════════
# R4 — مرزِ روزِ محلی در فیلترهای گزارش و ابزارِ ممیزیِ دستیار
# ══════════════════════════════════════════════════════════════════════════
class TestReportDateBoundaries:
    """`created_at` از نوع `timestamptz` است؛ مقایسهٔ مستقیمِ `date` مرز را روی
    نیمه‌شبِ UTC می‌گذارد و سه‌ونیم ساعتِ اولِ هر روزِ تهران را جا می‌اندازد."""

    def _record_at(self, db, when: datetime):
        person = make_personnel(db, org_unit="واحد مرزی")
        sup = make_user(db, "unit_supervisor")
        ceo = make_user(db, "ceo")
        make_access(db, person, sup, None, ceo)
        record = EvaluationRecord(
            subject_personnel_id=person.id,
            unit_supervisor_user_id=sup.id,
            ceo_user_id=ceo.id,
            status="finalized",
            final_weighted_pct=70.0,
            evaluation_code=f"EVL-BND-{when:%H%M%S%f}",
        )
        db.add(record)
        db.flush()
        db.execute(
            text("UPDATE evaluation_records SET created_at = :ts WHERE id = :i"),
            {"ts": when, "i": record.id},
        )
        db.flush()
        return record

    def test_first_local_hours_are_inside_the_filter(self, client, db_session, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "org_timezone", "Asia/Tehran")
        db = db_session
        # ۰۰:۳۰ بامدادِ ۷ اکتبرِ تهران = ۲۱:۰۰ ششمِ اکتبر به‌وقت UTC
        self._record_at(db, datetime(2025, 10, 6, 21, 0, tzinfo=UTC))
        hr = make_user(db, "hr")
        db.commit()

        r = client.get(
            "/api/dashboard/report/summary",
            params={"created_from": "2025-10-07", "created_to": "2025-10-07",
                    "org_unit": "واحد مرزی"},
            headers=auth_header(hr),
        )
        assert r.status_code == 200, r.text
        assert r.json()["total_evaluations"] == 1, "ردیفِ ۰۰:۳۰ تهران باید داخلِ همان روز باشد"

    def test_day_after_is_outside(self, client, db_session, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "org_timezone", "Asia/Tehran")
        db = db_session
        # ۰۰:۳۰ بامدادِ ۸ اکتبرِ تهران — یک روز *بعد* از پایانِ بازه
        self._record_at(db, datetime(2025, 10, 7, 21, 0, tzinfo=UTC))
        hr = make_user(db, "hr")
        db.commit()

        r = client.get(
            "/api/dashboard/report/summary",
            params={"created_from": "2025-10-07", "created_to": "2025-10-07",
                    "org_unit": "واحد مرزی"},
            headers=auth_header(hr),
        )
        assert r.json()["total_evaluations"] == 0, "ردیفِ فردا نباید داخلِ بازه بیاید"

    def test_the_assistant_audit_search_uses_the_same_boundary(self):
        """همان جست‌وجو از دو راه نباید دو نتیجه بدهد."""
        import inspect

        from app.services.ai.tools import analytics

        src = inspect.getsource(analytics)
        assert "local_day_start(from_dt)" in src
        assert "local_day_end(to_dt)" in src


# ══════════════════════════════════════════════════════════════════════════
# R5 — گاردِ ماژول روی پاسخ به اعتراض
# ══════════════════════════════════════════════════════════════════════════
class TestObjectionModuleGuard:
    """سوییچی که فقط نیمی از مسیر را می‌بندد، سوییچ نیست."""

    def _record_with_objection(self, client, db):
        person = make_personnel(db)
        sup = make_user(db, "unit_supervisor")
        ceo = make_user(db, "ceo")
        hr = make_user(db, "hr")
        employee = make_user(db, "employee", personnel_id=person.id)
        make_access(db, person, sup, None, ceo)
        db.commit()

        eid = client.post(
            "/api/evaluations",
            json={"subject_personnel_id": person.id},
            headers=auth_header(sup),
        ).json()["id"]
        assert client.put(
            f"/api/evaluations/{eid}/scores",
            json={"scores": full_valid_scores(active_indicators(db))},
            headers=auth_header(sup),
        ).status_code in (200, 201)
        assert client.post(f"/api/evaluations/{eid}/submit", headers=auth_header(sup)).status_code == 200
        assert client.post(f"/api/evaluations/{eid}/hr-approve", headers=auth_header(hr)).status_code == 200
        assert client.post(f"/api/evaluations/{eid}/ceo-finalize", headers=auth_header(ceo)).status_code == 200

        for key in ("employee_evaluation_visibility", "objections",
                    "employee_result_acknowledgement"):
            set_module(db, key, True)
        db.commit()
        # اعتراض بدونِ ثبتِ «نتیجه را دیدم» ممکن نیست — همان قاعدهٔ محصول
        assert client.post(
            f"/api/me/evaluations/{eid}/acknowledge", headers=auth_header(employee)
        ).status_code == 200
        r = client.post(
            f"/api/me/evaluations/{eid}/object",
            json={"reason": "متنِ اعتراضِ آزمون که به‌قدر کافی بلند است"},
            headers=auth_header(employee),
        )
        assert r.status_code in (200, 201), r.text
        return eid, hr

    def test_resolving_is_blocked_when_the_module_is_off(self, client, db_session):
        db = db_session
        eid, hr = self._record_with_objection(client, db)
        set_module(db, "objections", False)
        db.commit()

        r = client.post(
            f"/api/evaluations/{eid}/resolve-objection",
            json={"resolution": "پاسخِ آزمون به اعتراضِ ثبت‌شده"},
            headers=auth_header(hr),
        )
        assert r.status_code == 403, r.text
        assert "اعتراض" in r.json()["detail"]

    def test_resolving_works_when_the_module_is_on(self, client, db_session):
        db = db_session
        eid, hr = self._record_with_objection(client, db)
        r = client.post(
            f"/api/evaluations/{eid}/resolve-objection",
            json={"resolution": "پاسخِ آزمون به اعتراضِ ثبت‌شده"},
            headers=auth_header(hr),
        )
        assert r.status_code == 200, r.text
