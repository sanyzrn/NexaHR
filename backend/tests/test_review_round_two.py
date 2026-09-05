"""دستهٔ ۲ بازبینی: بایپسِ اعتبارسنجیِ طرح، و شاخهٔ بی‌گاردِ داشبورد."""
import pytest
from fastapi import HTTPException

from app.models.enums import Capability, SchemeStatus
from app.models.scoring_scheme import ScoringScheme
from app.schemas.auth import CurrentUser
from app.services.ai.tools.base import ToolContext
from tests.helpers import auth_header, make_personnel, make_user, set_module


def _ctx(db, user, caps=frozenset()):
    return ToolContext(
        db=db,
        user=CurrentUser(
            id=user.id, username=user.username, role=user.role,
            personnel_id=user.personnel_id, full_name=user.username,
            must_change_password=False,
        ),
        caps=caps,
        conversation_id=0,
    )


# ══════════════════════════════════════════════════════════════════════════
# S1 — اعتبارسنجیِ طرحِ نمره‌دهی از راهِ دستیار
# ══════════════════════════════════════════════════════════════════════════
class TestSchemeDraftValidation:
    """همهٔ گاردها در `SchemeInput` بودند و مسیرِ دستیار از کنارشان می‌گذشت."""

    @staticmethod
    def _draft(db, hr, **kw):
        from app.services.ai.tools.framework import create_scoring_scheme_draft

        return create_scoring_scheme_draft(
            _ctx(db, hr, frozenset({Capability.manage_scoring})),
            name=kw.pop("name", "طرحِ آزمون"),
            **kw,
        )

    def test_weights_that_do_not_sum_to_one_are_rejected(self, db_session):
        db = db_session
        hr = make_user(db, "hr")
        db.commit()
        with pytest.raises(HTTPException) as exc:
            self._draft(db, hr, general_section_weight=0.9, specialized_section_weight=0.9)
        assert exc.value.status_code == 400
        assert "۱" in exc.value.detail or "جمع" in exc.value.detail

    def test_negative_weight_is_rejected(self, db_session):
        """`general=-0.5, specialized=1.5` جمعش ۱ است ولی وزنِ منفی است —
        و `base_pct` را به بازهٔ منفی تا ۱۵۰ می‌بَرد."""
        db = db_session
        hr = make_user(db, "hr")
        db.commit()
        with pytest.raises(HTTPException) as exc:
            self._draft(db, hr, general_section_weight=-0.5, specialized_section_weight=1.5)
        assert exc.value.status_code == 400

    def test_bonus_cap_above_the_limit_is_rejected(self, db_session):
        db = db_session
        hr = make_user(db, "hr")
        db.commit()
        with pytest.raises(HTTPException) as exc:
            self._draft(db, hr, bonus_max_points=99)
        assert exc.value.status_code == 400

    def test_negative_improvement_pct_is_rejected(self, db_session):
        """عددِ منفی این‌جا واجدبودنِ برنامهٔ بهبود را سراسری خاموش می‌کرد."""
        db = db_session
        hr = make_user(db, "hr")
        db.commit()
        with pytest.raises(HTTPException) as exc:
            self._draft(db, hr, improvement_plan_max_pct=-5)
        assert exc.value.status_code == 400

    def test_evidence_word_range_must_be_ordered(self, db_session):
        db = db_session
        hr = make_user(db, "hr")
        db.commit()
        with pytest.raises(HTTPException) as exc:
            self._draft(db, hr, evidence_min_words=40, evidence_max_words=3)
        assert exc.value.status_code == 400

    def test_a_valid_draft_still_works(self, db_session):
        """گارد نباید مسیرِ سالم را ببندد."""
        db = db_session
        hr = make_user(db, "hr")
        db.commit()
        out = self._draft(db, hr, general_section_weight=0.7, specialized_section_weight=0.3)
        assert '"created": true' in out.content.lower()
        scheme = db.scalar(
            ScoringScheme.__table__.select().order_by(ScoringScheme.version.desc()).limit(1)
        )
        assert scheme is not None

    def test_nothing_is_written_when_validation_fails(self, db_session):
        """۴۰۰ باید *پیش از* هر درجی بیفتد، نه بعدش."""
        db = db_session
        hr = make_user(db, "hr")
        db.commit()
        before = db.scalar(
            ScoringScheme.__table__.count() if hasattr(ScoringScheme.__table__, "count")
            else __import__("sqlalchemy").select(__import__("sqlalchemy").func.count()).select_from(ScoringScheme)
        )
        with pytest.raises(HTTPException):
            self._draft(db, hr, bonus_max_points=99)
        import sqlalchemy as sa

        after = db.scalar(sa.select(sa.func.count()).select_from(ScoringScheme))
        assert after == before, "پیش‌نویسِ نامعتبر نباید ردیفی بسازد"


class TestActivationRevalidates:
    """کمربندِ دوم: پیش‌نویسِ نامعتبرِ از قبل ساخته‌شده هم فعال نشود."""

    def test_an_invalid_draft_cannot_be_activated(self, db_session):
        from app.services.scoring_scheme import activate, next_version

        db = db_session
        author = make_user(db, "hr")
        activator = make_user(db, "hr")
        db.commit()
        # پیش‌نویسی که *مستقیم* ساخته می‌شود — همان کاری که ابزار پیش از این
        # می‌کرد و ردیف‌هایش ممکن است در دیتابیس مانده باشند.
        bad = ScoringScheme(
            version=next_version(db),
            name="طرحِ نامعتبر",
            status=SchemeStatus.draft,
            general_section_weight=0.9,
            specialized_section_weight=0.9,
            evidence_required_scores=[1, 5],
            evidence_min_words=3,
            evidence_max_words=40,
            bonus_max_points=5.0,
            improvement_plan_max_pct=75.0,
            thresholds=[{"upper_exclusive": 101, "label": "تمدید"}],
            indicator_weights={},
            created_by_user_id=author.id,
        )
        db.add(bad)
        db.flush()

        with pytest.raises(HTTPException) as exc:
            activate(db, bad, actor_user_id=activator.id)
        assert exc.value.status_code == 400
        assert "معتبر" in exc.value.detail
        assert bad.status is SchemeStatus.draft, "طرحِ ردشده باید پیش‌نویس بماند"

    def test_a_valid_draft_still_activates(self, db_session):
        from app.services.scoring_scheme import activate, next_version

        db = db_session
        author = make_user(db, "hr")
        activator = make_user(db, "hr")
        db.commit()
        good = ScoringScheme(
            version=next_version(db),
            name="طرحِ سالم",
            status=SchemeStatus.draft,
            general_section_weight=0.6,
            specialized_section_weight=0.4,
            evidence_required_scores=[1, 5],
            evidence_min_words=3,
            evidence_max_words=40,
            bonus_max_points=5.0,
            improvement_plan_max_pct=75.0,
            thresholds=[{"upper_exclusive": 101, "label": "تمدید"}],
            indicator_weights={},
            created_by_user_id=author.id,
        )
        db.add(good)
        db.flush()
        activate(db, good, actor_user_id=activator.id)
        assert good.status is SchemeStatus.active


# ══════════════════════════════════════════════════════════════════════════
# S2 — شاخهٔ بی‌گاردِ role-overview
# ══════════════════════════════════════════════════════════════════════════
class TestRoleOverviewEmployeeBranch:
    """یک تابع، دو شاخه — و تا امروز فقط یکی گاردشده بود."""

    @staticmethod
    def _employee(db):
        person = make_personnel(db)
        user = make_user(db, "employee", personnel_id=person.id)
        db.commit()
        return user

    def test_no_cards_when_visibility_is_off(self, client, db_session):
        """پیش‌فرضِ محصول: هر دو سوییچ خاموش‌اند."""
        db = db_session
        employee = self._employee(db)
        for key in ("employee_overview_cards", "employee_evaluation_visibility"):
            set_module(db, key, False)
        db.commit()

        r = client.get("/api/dashboard/role-overview", headers=auth_header(employee))
        assert r.status_code == 200, r.text
        assert r.json()["cards"] == [], "شاخهٔ نقش هم باید سوییچ را بسنجد"

    def test_scope_self_and_the_role_branch_agree(self, client, db_session):
        """دو مسیر به یک داده، پس نباید دو جواب بدهند."""
        db = db_session
        employee = self._employee(db)
        for key in ("employee_overview_cards", "employee_evaluation_visibility"):
            set_module(db, key, False)
        db.commit()

        default = client.get("/api/dashboard/role-overview", headers=auth_header(employee))
        explicit = client.get(
            "/api/dashboard/role-overview?scope=self", headers=auth_header(employee)
        )
        assert default.json()["cards"] == explicit.json()["cards"] == []

    def test_cards_appear_when_both_switches_are_on(self, client, db_session):
        db = db_session
        employee = self._employee(db)
        for key in ("employee_overview_cards", "employee_evaluation_visibility"):
            set_module(db, key, True)
        db.commit()

        r = client.get("/api/dashboard/role-overview", headers=auth_header(employee))
        assert r.status_code == 200, r.text
        assert len(r.json()["cards"]) > 0, "با هر دو سوییچِ روشن باید کاشی بیاید"

    def test_one_switch_is_not_enough(self, client, db_session):
        """محتوای کاشی‌ها *نتیجهٔ* ارزیابی است، پس به سوییچِ نمایشِ نتیجه هم بند است."""
        db = db_session
        employee = self._employee(db)
        set_module(db, "employee_overview_cards", True)
        set_module(db, "employee_evaluation_visibility", False)
        db.commit()

        r = client.get("/api/dashboard/role-overview", headers=auth_header(employee))
        assert r.json()["cards"] == []

    def test_other_roles_are_unaffected(self, client, db_session):
        """این اصلاح نباید داشبوردِ نقش‌های دیگر را خاموش کند."""
        db = db_session
        hr = make_user(db, "hr")
        for key in ("employee_overview_cards", "employee_evaluation_visibility"):
            set_module(db, key, False)
        db.commit()

        r = client.get("/api/dashboard/role-overview", headers=auth_header(hr))
        assert r.status_code == 200, r.text
        assert r.json()["role"] == "hr"
