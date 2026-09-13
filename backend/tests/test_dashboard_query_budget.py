"""داشبورد جدولِ نمره‌ها را *یک‌بار* می‌خواند، و هزینه‌اش با داده رشد نمی‌کند.

دو قاعده، و هرکدام یک خرابیِ متفاوت را می‌گیرد:

* **یک اسکن.** «پنج شاخصِ ضعیف» و «پنج شاخصِ قوی»، در دو بخشِ فرم، چهار کوئریِ
  جدا بودند که تجمیعِ زیرشان در هر چهارتا یکی بود. روی دیتابیسِ هزارنفره همین
  چهار اسکنِ ۱۲۰ هزار ردیفی، ۵۳۶ میلی‌ثانیه از یک صفحهٔ داشبورد بود. عددِ
  «چهار» جایی نوشته نشده بود که کسی ببیندش؛ این‌جا نوشته می‌شود.
* **هزینهٔ ثابت.** با دو برابر شدنِ پرونده‌ها، شمارِ کوئری نباید تکان بخورد.

شمارِ کوئری و نه زمان: زمان به ماشین بند است و در CI نوسان دارد؛ شمارِ کوئری
به شکلِ کد.
"""
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.api.routers.dashboard import overview
from app.models.enums import EvaluationStatus
from app.models.evaluation import EvaluationRecord, EvaluationScore
from tests.helpers import active_indicators, make_access, make_personnel, make_user


def statements_of(fn) -> list[str]:
    """متنِ همهٔ کوئری‌های اجراشده در طول `fn`."""
    seen: list[str] = []

    def before(conn, cursor, statement, parameters, context, executemany):
        seen.append(" ".join(statement.split()))

    event.listen(Engine, "before_cursor_execute", before)
    try:
        fn()
    finally:
        event.remove(Engine, "before_cursor_execute", before)
    return seen


def _finalized_records(db, count: int) -> None:
    """`count` پروندهٔ نهایی‌شده با نمرهٔ همهٔ شاخص‌ها."""
    indicators = active_indicators(db)
    ceo = make_user(db, "ceo", capabilities=[])
    supervisor = make_user(db, "unit_supervisor")
    for _ in range(count):
        personnel = make_personnel(db)
        make_access(db, personnel, supervisor, None, ceo)
        record = EvaluationRecord(
            evaluation_code=f"DQ-{personnel.id}",
            subject_personnel_id=personnel.id,
            unit_supervisor_user_id=supervisor.id,
            ceo_user_id=ceo.id,
            status=EvaluationStatus.finalized,
            final_weighted_pct=80,
            general_score_pct=80,
            specialized_score_pct=80,
        )
        db.add(record)
        db.flush()
        db.add_all(
            EvaluationScore(
                evaluation_record_id=record.id, indicator_id=indicator.id, score=4
            )
            for indicator in indicators
        )
    db.flush()


def test_the_overview_reads_the_score_table_once(db_session):
    """جدولِ نمره‌ها بزرگ‌ترین جدولِ سامانه است و یک صفحه یک‌بار می‌خواندش."""
    _finalized_records(db_session, 3)
    statements = statements_of(
        lambda: overview(site=None, db=db_session, current_user=None)
    )
    scans = [s for s in statements if "evaluation_scores" in s]
    assert len(scans) == 1, (
        f"نمای کلیِ داشبورد {len(scans)} بار جدولِ نمره‌ها را اسکن می‌کند. "
        "همهٔ فهرست‌های شاخصی از یک تجمیع می‌آیند؛ اگر فهرستِ تازه‌ای لازم شد، "
        "از همان `indicator_rows` بِبُرید، نه با کوئریِ جدید.\n" + "\n".join(scans)
    )


def test_the_overview_costs_the_same_whatever_the_data_size(db_session):
    _finalized_records(db_session, 3)
    small = len(statements_of(lambda: overview(site=None, db=db_session, current_user=None)))

    _finalized_records(db_session, 6)
    large = len(statements_of(lambda: overview(site=None, db=db_session, current_user=None)))

    assert small == large, (
        f"با بیشتر شدنِ پرونده‌ها کوئری‌ها از {small} به {large} رفت — "
        "یعنی جایی در این نما کوئری به‌ازای هر ردیف زده می‌شود."
    )
