"""یافته‌های دستهٔ یکِ ادغامِ سه گزارش — هر کدام با قرینهٔ منفیِ خودش.

این‌ها گاردها و برچسب‌هایی‌اند که یک‌جا درست بودند و جای دیگر نه؛ هیچ‌کدام
تصمیمِ محصولی ندارند و همه‌شان با کدِ همین سامانه قابلِ اثباتند.
"""

from app.core.constants import IMPROVEMENT_PLAN_MAX_PCT
from app.models.enums import Capability
from app.models.user import User
from tests.helpers import auth_header, make_user

# ── N7: رمزی که دیگری گذاشته، موقت است ─────────────────────────────────────


def test_an_account_created_by_hr_must_change_its_password(client, db_session):
    """مسیر اکسل از ابتدا این را می‌گذاشت و ساختِ حساب جا افتاده بود.

    استدلالش در `personnel_import.py:69` نوشته شده: «رمزی که در یک فایلِ اکسلِ
    دست‌به‌دست‌شده نوشته شده نباید در استفاده بماند». رمزی که منابع انسانی در
    یک فرمِ وب تایپ می‌کند و با تلفن می‌فرستد، همان ردهٔ خطر است.
    """
    hr = make_user(db_session, "hr", capabilities=[Capability.manage_users])
    db_session.commit()

    created = client.post(
        "/api/users",
        json={
            "username": "tempuser1",
            "password": "Hr-Chosen-Pass-1",
            "role": "unit_supervisor",
        },
        headers=auth_header(hr),
    )
    assert created.status_code == 201, created.text
    db_session.expire_all()
    fresh = db_session.get(User, created.json()["id"])
    assert fresh.must_change_password is True

    # و گاردِ سرور واقعاً می‌بندد: ورود می‌شود، ولی کارِ دیگری نه.
    logged_in = client.post(
        "/api/auth/login",
        json={"username": "tempuser1", "password": "Hr-Chosen-Pass-1"},
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["must_change_password"] is True


# ── N8: «مجوز ندارید»ِ دروغین پس از تغییر اجباری ───────────────────────────


def test_my_permissions_answers_during_a_forced_password_change(client, db_session):
    """اولین صفحه‌ای که مدیرِ سامانه پس از تغییر رمزش می‌بیند، دروغ می‌گفت.

    گاردِ تغییر اجباری یک allowlist است و `my-permissions` در آن نبود، پس
    ۴۰۳ برمی‌گشت؛ `PermissionsContext` روی خطا همه‌چیز را «ندارد» می‌خواند و
    صفحهٔ مدیریت به حسابی که *همهٔ* اختیارات را دارد می‌گفت «شما مجوز مدیریت
    سامانه را ندارید». تنها درمانش یک رفرشِ دستی بود.

    این مسیر چیزی جز مجوزهای خودِ فراخوان لو نمی‌دهد.
    """
    admin = make_user(
        db_session,
        "support",
        capabilities=[Capability.manage_capabilities, Capability.manage_users],
    )
    admin.must_change_password = True
    db_session.commit()

    mine = client.get("/api/administration/my-permissions", headers=auth_header(admin))
    assert mine.status_code == 200, mine.text
    assert "manage_capabilities" in mine.json()["capabilities"]

    # و بقیهٔ مسیرهای اداری همچنان بسته‌اند — معافیت فقط برای همین یکی است.
    assert (
        client.get("/api/administration/capabilities", headers=auth_header(admin)).status_code
        == 403
    )


# ── N10: مرزِ دقیقِ آستانهٔ برنامهٔ بهبود ──────────────────────────────────


def test_the_dashboard_and_plan_eligibility_agree_on_the_exact_threshold(
    client, db_session, no_cohort_suppression
):
    """پروندهٔ دقیقاً روی آستانه در قیفِ «نیازمند بهبود» شمرده می‌شد و بعد
    ساختنِ همان برنامه‌ای که آن قیف وعده می‌دهد ۴۰۰ می‌گرفت."""
    from app.models.evaluation import EvaluationRecord

    hr = make_user(db_session, "hr")
    sup = make_user(db_session, "unit_supervisor", capabilities=[])
    dep = make_user(db_session, "deputy", capabilities=[])
    ceo = make_user(db_session, "ceo", capabilities=[])
    from tests.helpers import (
        active_indicators,
        full_valid_scores,
        make_access,
        make_personnel,
    )

    person = make_personnel(db_session, full_name="دقیقاً روی مرز")
    make_access(db_session, person, sup, dep, ceo)
    db_session.commit()

    record_id = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": person.id},
        headers=auth_header(sup),
    ).json()["id"]
    client.put(
        f"/api/evaluations/{record_id}/scores",
        json={"scores": full_valid_scores(active_indicators(db_session))},
        headers=auth_header(sup),
    )
    for path, who in (("submit", sup), ("hr-approve", hr), ("deputy-approve", dep),
                      ("ceo-finalize", ceo)):
        client.post(f"/api/evaluations/{record_id}/{path}", headers=auth_header(who))

    # نتیجه را دقیقاً روی آستانه می‌نشانیم — همان لبه‌ای که دو طرف اختلاف داشتند.
    db_session.expire_all()
    record = db_session.get(EvaluationRecord, record_id)
    record.final_weighted_pct = IMPROVEMENT_PLAN_MAX_PCT
    db_session.commit()

    # سمتِ برنامهٔ بهبود: رد می‌کند (`>= آستانه`).
    refused = client.post(
        "/api/improvement-plans",
        json={
            "evaluation_record_id": record_id,
            "title": "برنامه",
            "review_date": "2027-01-01",
            "goals": ["هدف"],
        },
        headers=auth_header(hr),
    )
    assert refused.status_code == 400, refused.text

    # پس داشبورد هم نباید در قیفِ «نیازمند بهبود» بشماردش.
    mix = client.get("/api/dashboard/overview", headers=auth_header(hr)).json()["outcome_mix"]
    assert mix["people_counted"] >= 1
    assert mix["needs_improvement_pct"] == 0.0, mix


# ── N19: نرمال‌سازیِ نویسه‌های نامرئی ──────────────────────────────────────


def test_invisible_characters_are_stripped_but_the_half_space_survives():
    """خطِ قبلی `replace("‌", "‌")` بود — هر دو طرف *همان* نیم‌فاصله.

    یعنی جایگزینی‌ای که کامنتش وعدهٔ پاک‌کردنِ نامرئی‌ها می‌داد، هیچ نویسه‌ای
    را عوض نمی‌کرد. و نیم‌فاصله باید بماند: حذفش «علی‌رضا» را «علیرضا»
    می‌کند، یعنی بازنویسیِ نامِ آدم.
    """
    from app.services.personnel_import import _text

    messy = "‏﻿علی‌رضا​ نوری ‍"
    assert _text(messy) == "علی‌رضا نوری"
    assert "‌" in _text(messy), "نیم‌فاصله نویسهٔ معناداری است و باید بماند"
    for invisible in ("​", "‍", "﻿", "‎", "‏", "­"):
        assert invisible not in _text(f"نام{invisible}خانوادگی")


# ── N20: برچسب‌های خام ────────────────────────────────────────────────────


def test_a_cancelled_evaluation_is_persian_in_the_excel_export():
    """`.get(x, x)` یعنی کلیدِ جاافتاده *خام* بیرون می‌رود."""
    from app.models.enums import EvaluationStatus
    from app.services.excel import _STATUS_LABELS

    missing = [
        s.value for s in EvaluationStatus if s.value not in _STATUS_LABELS
    ]
    assert not missing, missing
    assert _STATUS_LABELS["cancelled"] == "لغوشده"


def test_the_pdf_names_every_comment_stage_in_persian():
    """ستونِ «مرحله» در سندِ رسمی `hr_review` خام چاپ می‌کرد."""
    from app.models.enums import CommentStage
    from app.services.pdf import _STAGE_LABELS

    missing = [s.value for s in CommentStage if s.value not in _STAGE_LABELS]
    assert not missing, missing
    assert "{{ c.stage }}" not in (
        __import__("pathlib").Path("app/templates/evaluation_summary.html").read_text()
    ), "قالب باید از نگاشتِ برچسب رد شود، نه مقدارِ خام"
