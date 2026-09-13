"""چند کوئری، چند میلی‌ثانیه — برای مسیرهایی که فازِ ۳ب می‌خواهد عوضشان کند.

قاعدهٔ نقشهٔ راه: «۳ب بدونِ عدد انجام نشود.» این اسکریپت آن عدد را می‌دهد و
دوبار اجرا می‌شود — یک‌بار پیش از تغییر، یک‌بار پس از آن — تا بشود گفت بهتر شد
یا فقط عوض شد.

**شمارشِ کوئری مهم‌تر از زمان است.** زمان به ماشین، کشِ صفحه و شلوغیِ لحظه بند
است؛ شمارشِ کوئری به شکلِ کد. یک مسیری که با هزار پرونده هزار کوئری می‌زند،
روی این ماشین شاید سریع به‌نظر برسد و روی شبکهٔ واقعیِ دیتابیس فاجعه باشد.

اجرا، روی همان دیتابیسِ پرشدهٔ `seed_load_test`:

    DATABASE_URL=postgresql://nexahr:...@localhost:5432/nexahr_load \\
        python -m scripts.measure_hot_paths

هیچ‌چیز commit نمی‌شود: جاروها اعلان می‌سازند و هر اندازه‌گیری با rollback تمام
می‌شود، پس اجرای دوم همان شرایطِ اجرای اول را دارد.
"""
import argparse
import statistics
import time
from collections import Counter
from contextlib import contextmanager

from sqlalchemy import event, text

from app.core.config import settings
from app.db.session import SessionLocal, engine

REPEATS = 3


@contextmanager
def counting():
    """شمارندهٔ کوئری روی همان engineِ سامانه.

    متنِ کوئری هم شمرده می‌شود، چون عددِ کل می‌گوید «بد است» و نمی‌گوید
    «کجا»: ۶۲۵۱ کوئریِ جاروی SLA سه منبعِ کاملاً متفاوت داشت و بی این تفکیک
    هر سه‌تا یک عدد بودند.
    """
    counter = {"n": 0, "by_sql": Counter()}

    def before(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1
        counter["by_sql"][" ".join(statement.split())[:110]] += 1

    event.listen(engine, "before_cursor_execute", before)
    try:
        yield counter
    finally:
        event.remove(engine, "before_cursor_execute", before)


def measure(name: str, fn, repeats: int = REPEATS) -> dict:
    """`fn(db)` را چند بار اجرا می‌کند و کوئری و زمان را می‌گیرد.

    هر بار session تازه و rollback: جاروها می‌نویسند، و بارِ دوم روی دادهٔ
    دست‌خوردهٔ بارِ اول، عددِ دیگری می‌داد (`notify_once` دومی را رد می‌کند).
    """
    query_counts = []
    durations = []
    by_sql: Counter = Counter()
    for _ in range(repeats):
        db = SessionLocal()
        try:
            with counting() as counter:
                started = time.perf_counter()
                fn(db)
                # قراردادِ جاروها «commit با فراخواننده است»، پس درج‌های معوق
                # بخشی از کارِ همان مسیرند. بی این flush، تغییری که درج‌ها را
                # دسته‌ای می‌کند «رایگان» به‌نظر می‌رسید چون rollback آن‌ها را
                # اصلاً به دیتابیس نمی‌رساند.
                db.flush()
                durations.append((time.perf_counter() - started) * 1000)
            query_counts.append(counter["n"])
            if counter["n"] >= max(query_counts):
                by_sql = counter["by_sql"]
        finally:
            db.rollback()
            db.close()
    return {
        "name": name,
        "queries": max(query_counts),
        "ms": statistics.median(durations),
        "by_sql": by_sql,
    }


def _paths() -> list[tuple[str, object]]:
    from app.api.routers.analytics import executive_overview
    from app.api.routers.dashboard import overview, pipeline
    from app.api.routers.reports import _Filters, _summary_data
    from app.services.audit import verify_chain
    from app.services.scheduled import (
        run_contract_expiry_sweep,
        run_improvement_review_sweep,
        run_orphaned_case_sweep,
        run_sla_sweep,
    )
    from app.services.stage_stats import stage_stats

    return [
        ("جارو: هشدارِ انقضای قرارداد", run_contract_expiry_sweep),
        ("جارو: یادآوریِ تأخیر (SLA)", run_sla_sweep),
        ("جارو: پرونده‌های بی‌صاحب", run_orphaned_case_sweep),
        ("جارو: بازنگریِ برنامهٔ بهبود", run_improvement_review_sweep),
        ("داشبورد: نمای کلی", lambda db: overview(site=None, db=db, current_user=None)),
        ("داشبورد: قیف مراحل", lambda db: pipeline(db=db, current_user=None)),
        ("داشبورد: آمارِ مرحله‌ها", lambda db: stage_stats(db)),
        ("گزارش: خلاصه", lambda db: _summary_data(db, _Filters(personnel_status=None))),
        ("تحلیل: نمای مدیریتی", lambda db: executive_overview(db=db, current_user=None)),
        ("ممیزی: راستی‌آزماییِ کاملِ زنجیره", lambda db: verify_chain(db)),
        ("ممیزی: بررسیِ سریع (از لنگر)", lambda db: verify_chain(db, since_anchor=True)),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=REPEATS)
    parser.add_argument("--only", default=None, help="زیررشته‌ای از نامِ مسیر")
    parser.add_argument(
        "--trace", action="store_true", help="پرتکرارترین کوئری‌های هر مسیر را هم چاپ کن"
    )
    args = parser.parse_args()

    print(f"مقصد: {settings.database_url}")
    db = SessionLocal()
    try:
        sizes = db.execute(
            text(
                """
                select
                    (select count(*) from personnel),
                    (select count(*) from evaluation_records),
                    (select count(*) from evaluation_scores),
                    (select count(*) from audit_log)
                """
            )
        ).one()
    finally:
        db.close()
    print(
        f"اندازه: {sizes[0]} پرسنل، {sizes[1]} پرونده، "
        f"{sizes[2]} نمره، {sizes[3]} ردیفِ ممیزی\n"
    )

    rows = []
    for name, fn in _paths():
        if args.only and args.only not in name:
            continue
        rows.append(measure(name, fn, args.repeats))

    width = max(len(r["name"]) for r in rows)
    print(f"{'مسیر'.ljust(width)}  {'کوئری':>7}  {'میلی‌ثانیه':>11}")
    print("-" * (width + 24))
    for row in rows:
        print(f"{row['name'].ljust(width)}  {row['queries']:>7}  {row['ms']:>11.1f}")

    if args.trace:
        for row in rows:
            top = [(sql, n) for sql, n in row["by_sql"].most_common(5) if n > 1]
            if not top:
                continue
            print(f"\n— {row['name']}")
            for sql, n in top:
                print(f"   {n:>6} ×  {sql}")


if __name__ == "__main__":
    main()
