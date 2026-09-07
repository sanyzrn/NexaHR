"""متنی که سرور می‌نویسد هم فارسی است — رقم و تاریخ، هر دو.

سامانه دو استانداردِ عددی داشت: سند و رابط فارسی («۱۴۰۴/۰۶/۱۵»، «۸۲٫۵٪») و
متن‌هایی که *سرور* می‌سازد لاتین («3 روز دیگر»، «تا 2026-01-05 تمدید شد»).

و بدترین جایش روی خودِ سندِ رسمی می‌نشست: کامنتِ تمدیدِ مهلت با تاریخِ میلادی
ثبت می‌شد، `snapshot` همهٔ کامنت‌ها را بی‌قید برمی‌داشت، و قالب آن را کنارِ
تاریخ‌های شمسیِ خودش چاپ می‌کرد — روی مدرکی که هش می‌شود و QR تأیید دارد.

آن‌چه عمداً *ترجمه نمی‌شود* هم این‌جا قفل است: کلیدِ یکتاییِ اعلان و
`old_value`/`new_value`ِ لاگِ ممیزی داده‌اند، نه متن.
"""
import re
from datetime import date, datetime, timedelta

from app.core.persian import fa_date, fa_digits

LATIN_DIGIT = re.compile(r"[0-9]")


def test_fa_date_is_jalali_with_persian_digits():
    assert fa_date(date(2026, 1, 5)) == "۱۴۰۴/۱۰/۱۵"
    assert fa_date(None) == "—"


def test_fa_date_uses_the_org_day_and_not_the_utc_day():
    """۲۱:۰۰ UTC در تهران فردا است؛ سند باید روزِ سازمان را بگوید."""
    late = datetime(2025, 12, 31, 21, 0, tzinfo=__import__("datetime").UTC)
    assert fa_date(late) == fa_date(date(2026, 1, 1))


def test_fa_digits_leaves_identifiers_alone():
    # کدِ پرونده برچسب است، نه عدد — و همان‌طور جست‌وجو می‌شود.
    assert fa_digits(3) == "۳"
    assert fa_digits(82.5) == "۸۲٫۵"


def test_the_extension_comment_reaches_the_official_document_in_jalali(
    client, db_session
):
    """زنجیرهٔ کامل: تمدید → کامنت → snapshot → سند."""
    from tests.helpers import (
        active_indicators,
        auth_header,
        full_valid_scores,
        make_access,
        make_personnel,
        make_user,
    )

    personnel = make_personnel(db_session)
    hr = make_user(db_session, "hr")
    sup = make_user(db_session, "unit_supervisor")
    dep = make_user(db_session, "deputy")
    ceo = make_user(db_session, "ceo")
    make_access(db_session, personnel, sup, dep, ceo)
    db_session.commit()

    # تمدید فقط برای پرونده‌ای معنا دارد که به دوره‌ای وصل است — وگرنه از
    # ابتدا مهلتی ندارد. `closed` تا ایندکسِ «حداکثر یک دورهٔ باز» با
    # تست‌های موازی درنیفتد؛ مهلت از خودِ تاریخ می‌آید.
    from app.models.enums import PeriodStatus
    from app.models.evaluation import EvaluationRecord
    from app.models.evaluation_period import EvaluationPeriod

    today = date.today()
    period = EvaluationPeriod(
        name="دورهٔ تمدید",
        starts_on=today - timedelta(days=30),
        ends_on=today + timedelta(days=1),
        status=PeriodStatus.closed,
    )
    db_session.add(period)
    db_session.flush()
    db_session.commit()

    record_id = client.post(
        "/api/evaluations",
        json={"subject_personnel_id": personnel.id},
        headers=auth_header(sup),
    ).json()["id"]
    record = db_session.get(EvaluationRecord, record_id)
    record.period_id = period.id
    db_session.commit()

    until = today + timedelta(days=10)
    extended = client.post(
        f"/api/evaluations/{record_id}/extend-submission",
        json={"until": until.isoformat(), "reason": "غیبتِ موجهِ ارزیاب"},
        headers=auth_header(hr),
    )
    assert extended.status_code == 200, extended.text

    detail = client.get(
        f"/api/evaluations/{record_id}", headers=auth_header(hr)
    ).json()
    comment = next(
        c["comment_text"] for c in detail["comments"] if "تمدید مهلت" in c["comment_text"]
    )
    assert fa_date(until) in comment
    assert not LATIN_DIGIT.search(comment.split("دلیل:")[0]), comment

    # و پرونده تا آخر می‌رود، پس همان کامنت روی سند می‌نشیند.
    client.put(
        f"/api/evaluations/{record_id}/scores",
        json={"scores": full_valid_scores(active_indicators(db_session))},
        headers=auth_header(sup),
    )
    client.post(f"/api/evaluations/{record_id}/submit", headers=auth_header(sup))
    client.post(f"/api/evaluations/{record_id}/hr-approve", headers=auth_header(hr))
    client.post(f"/api/evaluations/{record_id}/deputy-approve", headers=auth_header(dep))
    assert client.post(
        f"/api/evaluations/{record_id}/ceo-finalize", headers=auth_header(ceo)
    ).status_code == 200

    db_session.refresh(record)
    texts = [c["comment_text"] for c in record.final_snapshot["comments"]]
    assert any(fa_date(until) in t for t in texts)


def test_the_expired_window_message_is_jalali(client, db_session):
    import pytest
    from fastapi import HTTPException

    from app.models.enums import PeriodStatus
    from app.models.evaluation import EvaluationRecord
    from app.models.evaluation_period import EvaluationPeriod
    from app.services.evaluation_window import ensure_open

    period = EvaluationPeriod(
        name="دورهٔ گذشته",
        status=PeriodStatus.closed,
        starts_on=date(2025, 1, 1),
        ends_on=date(2025, 3, 1),
    )
    db_session.add(period)
    db_session.flush()
    record = EvaluationRecord()
    record.period_id = period.id

    with pytest.raises(HTTPException) as raised:
        ensure_open(db_session, record, activity="ثبت")
    assert fa_date(period.ends_on) in raised.value.detail


def test_the_audit_log_keeps_machine_values_latin(client, db_session):
    """`old_value`/`new_value` داده‌اند، نه متن — نباید فارسی شوند.

    قاعده‌اش در داکِ `core/persian` نوشته است و این تست همان را قفل می‌کند:
    ترجمهٔ ارقام فقط برای *متنِ* آدم‌خوان است. کلیدِ یکتاییِ اعلان هم همین
    حکم را دارد.
    """
    from sqlalchemy import select

    from app.models.audit_log import AuditLog
    from tests.helpers import auth_header, make_personnel, make_user

    hr = make_user(db_session, "hr")
    personnel = make_personnel(db_session)
    db_session.commit()

    created = client.post(
        "/api/users",
        json={
            "username": "probe.latin",
            "password": "Probe-Latin-1234",
            "role": "employee",
            "personnel_id": personnel.id,
        },
        headers=auth_header(hr),
    )
    assert created.status_code == 201, created.text

    row = db_session.scalars(
        select(AuditLog)
        .where(AuditLog.event_type == "user_created")
        .order_by(AuditLog.id.desc())
    ).first()
    assert row is not None
    assert LATIN_DIGIT.search(str(row.new_value["id"])), row.new_value
    assert row.new_value["username"] == "probe.latin"


def test_one_person_gets_one_active_account(client, db_session):
    """هیچ قیدی روی `users.personnel_id` نبود — نه در مدل، نه در مایگریشن.

    و هر حسابِ وصل‌شده در *همهٔ* مسیرهای `/api/me` همان فرد به‌حساب می‌آمد:
    خودارزیابیِ یک‌بارمصرفش را ثبت می‌کرد، «نتیجه را دیدم» را به نامش ثبت
    می‌کرد، و پنجرهٔ اعتراضش را مصرف می‌کرد. هر که زودتر اقدام می‌کرد، فرصتِ
    خودِ فرد را برداشته بود — بی هیچ خطا و بی هیچ نشانه‌ای.

    این‌جا در همین فایل است چون هر دو گارد یک جنس دارند: چیزی که باید
    *ساختاری* می‌بود و در کد جا افتاده بود.
    """
    from tests.helpers import auth_header, make_personnel, make_user

    hr = make_user(db_session, "hr")
    personnel = make_personnel(db_session, full_name="یک آدم")
    db_session.commit()

    first = client.post(
        "/api/users",
        json={
            "username": "person.one",
            "password": "Person-One-1234",
            "role": "employee",
            "personnel_id": personnel.id,
        },
        headers=auth_header(hr),
    )
    assert first.status_code == 201, first.text

    second = client.post(
        "/api/users",
        json={
            "username": "person.two",
            "password": "Person-Two-1234",
            "role": "employee",
            "personnel_id": personnel.id,
        },
        headers=auth_header(hr),
    )
    assert second.status_code == 400, second.text
    assert "person.one" in second.json()["detail"]

    # و مسیرِ دوم: حسابِ موجودی که روی همان پرسنل *نشانه‌گیری* می‌شود.
    other_person = make_personnel(db_session, full_name="آدمِ دیگر")
    db_session.commit()
    third = client.post(
        "/api/users",
        json={
            "username": "person.three",
            "password": "Person-Three-1234",
            "role": "employee",
            "personnel_id": other_person.id,
        },
        headers=auth_header(hr),
    ).json()
    repointed = client.patch(
        f"/api/users/{third['id']}",
        json={"personnel_id": personnel.id},
        headers=auth_header(hr),
    )
    assert repointed.status_code == 400, repointed.text

    # ولی ویرایشِ خودِ حسابِ متصل (بی تغییرِ اتصال) نباید رد شود.
    same = client.patch(
        f"/api/users/{first.json()['id']}",
        json={"personnel_id": personnel.id, "full_name": "یک آدم"},
        headers=auth_header(hr),
    )
    assert same.status_code == 200, same.text


def test_a_deactivated_account_does_not_block_a_new_one(client, db_session):
    """کسی که رفته و برگشته باید حسابِ تازه بگیرد.

    حسابِ غیرفعال به `/api/me` نمی‌رسد (احراز هویت زودتر ردش می‌کند)، پس
    مانعِ ساختنِ حسابِ تازه هم نباید باشد.
    """
    from tests.helpers import auth_header, make_personnel, make_user

    hr = make_user(db_session, "hr")
    personnel = make_personnel(db_session, full_name="بازگشته")
    db_session.commit()

    old = client.post(
        "/api/users",
        json={
            "username": "returner.old",
            "password": "Returner-Old-1234",
            "role": "employee",
            "personnel_id": personnel.id,
        },
        headers=auth_header(hr),
    ).json()
    assert (
        client.patch(
            f"/api/users/{old['id']}",
            json={"is_active": False},
            headers=auth_header(hr),
        ).status_code
        == 200
    )

    fresh = client.post(
        "/api/users",
        json={
            "username": "returner.new",
            "password": "Returner-New-1234",
            "role": "employee",
            "personnel_id": personnel.id,
        },
        headers=auth_header(hr),
    )
    assert fresh.status_code == 201, fresh.text
