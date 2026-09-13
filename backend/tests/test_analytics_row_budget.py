"""نمای مدیریتی خلاصه می‌خواهد، نه ردیف‌ها.

میانه و صدکِ ۹۰ِ «زمان چرخه» تا امروز در پایتون حساب می‌شدند، و برای همان دو
عدد *یک ردیف به‌ازای هر پروندهٔ نهایی‌شدهٔ تاریخِ سازمان* از دیتابیس خوانده
می‌شد. برخلافِ بقیهٔ این صفحه هیچ سقفی هم نداشت: نه پنجرهٔ زمانی، نه دوره —
فقط هر سال بزرگ‌تر می‌شد.

این تست *ردیف‌های خوانده‌شده* را می‌شمارد و نه کوئری‌ها را، چون خرابی از همان
جنس بود: تعدادِ کوئری‌ها درست بود و حجمشان نه. اگر فردا کسی برای عددِ تازه‌ای
دوباره فهرست بکشد بالا، همین‌جا می‌افتد.
"""
from datetime import UTC, datetime, timedelta

from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.api.routers.analytics import executive_overview
from app.models.enums import EvaluationStatus
from app.models.evaluation import EvaluationRecord
from tests.helpers import make_access, make_personnel, make_user


def rows_fetched(fn) -> int:
    """جمعِ ردیف‌هایی که در طول `fn` از دیتابیس برگشته‌اند."""
    total = {"n": 0}

    def after(conn, cursor, statement, parameters, context, executemany):
        if cursor.rowcount and cursor.rowcount > 0:
            total["n"] += cursor.rowcount

    event.listen(Engine, "after_cursor_execute", after)
    try:
        fn()
    finally:
        event.remove(Engine, "after_cursor_execute", after)
    return total["n"]


def _records(db, count: int) -> None:
    """`count` پروندهٔ نهایی‌شده و `count` پروندهٔ باز.

    هر دو لازم‌اند و هیچ‌کدام تزئینی نیست: «زمان چرخه» از پرونده‌های
    نهایی‌شده‌ای می‌آید که `finalized_at` دارند، و «قدیمی‌ترین پروندهٔ باز» از
    پرونده‌های باز. بی `finalized_at`، هر دو کوئری تهی برمی‌گشتند و این تست
    بی آن‌که کاری کند سبز می‌ماند.
    """
    ceo = make_user(db, "ceo", capabilities=[])
    supervisor = make_user(db, "unit_supervisor")
    finished = datetime.now(UTC)
    started = finished - timedelta(days=12)
    for index in range(count):
        for status in (EvaluationStatus.finalized, EvaluationStatus.draft):
            personnel = make_personnel(db)
            make_access(db, personnel, supervisor, None, ceo)
            db.add(
                EvaluationRecord(
                    evaluation_code=f"AR-{personnel.id}-{status.value}",
                    subject_personnel_id=personnel.id,
                    unit_supervisor_user_id=supervisor.id,
                    ceo_user_id=ceo.id,
                    status=status,
                    final_weighted_pct=80 if status is EvaluationStatus.finalized else None,
                    recommendation="تمدید" if status is EvaluationStatus.finalized else None,
                    created_at=started - timedelta(days=index),
                    stage_entered_at=started - timedelta(days=index),
                    finalized_at=(
                        finished if status is EvaluationStatus.finalized else None
                    ),
                )
            )
    db.flush()


def test_the_executive_overview_reads_a_constant_number_of_rows(db_session):
    _records(db_session, 4)
    small = rows_fetched(lambda: executive_overview(db=db_session, current_user=None))

    _records(db_session, 20)
    large = rows_fetched(lambda: executive_overview(db=db_session, current_user=None))

    assert small == large, (
        f"با بیشتر شدنِ پرونده‌ها، ردیف‌های خوانده‌شده از {small} به {large} رفت. "
        "این نما فقط تجمیع نشان می‌دهد؛ هر عددش باید از یک تابعِ تجمیعیِ SQL "
        "بیاید، نه از کشیدنِ فهرست بالا و حساب‌کردن در پایتون."
    )
