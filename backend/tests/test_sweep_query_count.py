"""هزینهٔ جاروهای شبانه نباید با تعدادِ پرونده‌ها رشد کند.

این تست عددِ امروز را قفل نمی‌کند — قاعده را می‌سنجد: همان جارو را یک‌بار با
`K` پرونده و یک‌بار با `۲K` پرونده اجرا می‌کند و می‌خواهد **شمارِ کوئری یکی
بماند**. هر N+1ی که فردا برگردد، همین‌جا می‌افتد، چه در `scheduled.py` باشد چه
در `notifications.py` یا در بررسیِ ماژول‌ها.

چرا شمارِ کوئری و نه زمان: زمان به ماشینِ اجراکننده بند است و در CI نوسان
دارد؛ شمارِ کوئری به شکلِ کد. و شکلِ کد همان چیزی است که خراب می‌شود.

عددی که این تست از آن آمد (`scripts/measure_hot_paths.py` روی دیتابیسِ
هزارنفره): جاروی SLA ۶۲۵۱ کوئری می‌زد و حالا ۶ تا؛ جاروی پرونده‌های بی‌صاحب
۱۰۰۲ و حالا ۴ تا. سه منبعِ جدا داشت — فهرستِ HR در هر پرونده، بررسیِ ماژول در
هر اعلان، و `count(*)`ِ dedup در هر اعلان — و هر سه از یک جنس بودند.
"""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.models.enums import EvaluationStatus
from app.models.evaluation import EvaluationRecord
from app.services.scheduled import (
    run_contract_expiry_sweep,
    run_orphaned_case_sweep,
    run_sla_sweep,
)
from tests.helpers import make_access, make_personnel, make_user


def count_queries(fn) -> int:
    """کوئری‌های واقعیِ روی سیم در طول اجرای `fn`."""
    counter = {"n": 0}

    def before(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1

    event.listen(Engine, "before_cursor_execute", before)
    try:
        fn()
    finally:
        event.remove(Engine, "before_cursor_execute", before)
    return counter["n"]


def _stalled_records(db, count: int, *, status: EvaluationStatus, active_seats: bool) -> None:
    """`count` پروندهٔ گیرکرده، هرکدام با پرسنل و زنجیرهٔ خودش.

    زنجیره‌ها عمداً یکسان نیستند: اگر همهٔ پرونده‌ها یک صندلی داشتند، کشِ
    identity map هر N+1ی را پنهان می‌کرد و تست همیشه سبز می‌ماند.
    """
    long_ago = datetime.now(UTC) - timedelta(days=365)
    for _ in range(count):
        supervisor = make_user(db, "unit_supervisor")
        deputy = make_user(db, "deputy")
        ceo = make_user(db, "ceo", capabilities=[])
        if not active_seats:
            for seat in (supervisor, deputy, ceo):
                seat.is_active = False
        personnel = make_personnel(db)
        make_access(db, personnel, supervisor, deputy, ceo)
        db.add(
            EvaluationRecord(
                evaluation_code=f"QC-{personnel.id}",
                subject_personnel_id=personnel.id,
                unit_supervisor_user_id=supervisor.id,
                deputy_user_id=deputy.id,
                ceo_user_id=ceo.id,
                status=status,
                created_at=long_ago,
                stage_entered_at=long_ago,
            )
        )
    db.flush()


def _flat_cost(db, sweep, *, build) -> tuple[int, int]:
    """هزینهٔ همان جارو با `K` و با `۲K` ردیف.

    `db.info.clear()` پیش از هر اندازه‌گیری لازم است، وگرنه خودِ تست دروغ
    می‌گوید: عکسِ ماژول‌ها در `Session.info` می‌نشیند و `rollback` پاکش
    نمی‌کند، پس اجرای دوم یک کوئری *کمتر* می‌زد — و مقایسه بی‌معنا می‌شد.
    هر دو اجرا باید از یک نقطه شروع کنند.
    """
    build(db, 3)
    db.info.clear()
    small = count_queries(lambda: (sweep(db), db.flush()))
    db.rollback()

    build(db, 6)
    db.info.clear()
    large = count_queries(lambda: (sweep(db), db.flush()))
    db.rollback()
    return small, large


def test_the_sla_sweep_does_not_query_per_record(db_session):
    """یادآوریِ تأخیر: سه منبعِ N+1 داشت و هر سه این‌جا سنجیده می‌شوند."""
    make_user(db_session, "hr")
    small, large = _flat_cost(
        db_session,
        run_sla_sweep,
        build=lambda db, n: _stalled_records(
            db, n, status=EvaluationStatus.draft, active_seats=True
        ),
    )
    assert small == large, (
        f"با دو برابر شدنِ پرونده‌ها، کوئری‌ها از {small} به {large} رفت — "
        "یعنی جایی در مسیر، کوئری به‌ازای هر پرونده (یا هر اعلان) زده می‌شود."
    )


def test_the_sla_sweep_does_not_query_per_hr_user(db_session):
    """صفِ مشترکِ HR برای *همهٔ* پرونده‌ها یکی است و یک‌بار خوانده می‌شود."""
    for _ in range(3):
        make_user(db_session, "hr")
    small, large = _flat_cost(
        db_session,
        run_sla_sweep,
        build=lambda db, n: _stalled_records(
            db, n, status=EvaluationStatus.submitted, active_seats=True
        ),
    )
    assert small == large


def test_the_orphaned_case_sweep_does_not_query_per_record(db_session):
    """«آیا صاحبِ این مرحله هنوز فعال است» یک کوئری برای همه است، نه یکی برای هرکدام."""
    make_user(db_session, "hr")
    small, large = _flat_cost(
        db_session,
        run_orphaned_case_sweep,
        build=lambda db, n: _stalled_records(
            db, n, status=EvaluationStatus.draft, active_seats=False
        ),
    )
    assert small == large


def test_the_contract_expiry_sweep_does_not_query_per_person(db_session):
    make_user(db_session, "hr")

    def build(db, n):
        soon = datetime.now(UTC).date() + timedelta(days=5)
        for _ in range(n):
            make_personnel(db, contract_end_date=soon)
        db.flush()

    small, large = _flat_cost(db_session, run_contract_expiry_sweep, build=build)
    assert small == large


@pytest.mark.parametrize("sweep", [run_sla_sweep, run_orphaned_case_sweep])
def test_the_sweeps_still_do_their_job(db_session, sweep):
    """گاردِ ارزان در برابر «سریع شد چون دیگر کاری نمی‌کند».

    تست‌های بالا فقط *شمارِ* کوئری را می‌بینند؛ جاروی خالی هم در آن‌ها سبز
    می‌شود. این‌جا فقط یک چیز خواسته می‌شود: هنوز اعلان می‌سازد.
    """
    make_user(db_session, "hr")
    _stalled_records(
        db_session,
        2,
        status=EvaluationStatus.draft,
        active_seats=sweep is run_sla_sweep,
    )
    assert sweep(db_session) > 0
