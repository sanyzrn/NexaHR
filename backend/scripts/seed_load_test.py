"""دیتابیسِ پرشده برای اندازه‌گیری — نه برای دمو، نه برای تست.

نقشهٔ راه برای فازِ ۳ب یک قاعده گذاشت: «بدونِ عدد انجام نشود.» این اسکریپت آن
عدد را ممکن می‌کند. یک سازمانِ سه‌ساله با هزار پرسنل می‌سازد تا کوئری‌هایی که
امروز روی شانزده پرونده بی‌عیب به‌نظر می‌رسند، اندازهٔ واقعی‌شان دیده شود.

با `seed_demo_scenarios` اشتباه نشود: آن یکی سناریو می‌سازد (پرونده‌ای در هر
مرحله، یک اعتراض، یک قراردادِ رو به انقضا) تا رفتار دیده شود و عمداً کوچک است.
این یکی شکلِ درست را برای هیچ‌کس تضمین نمی‌کند و فقط *حجم* می‌سازد.

با SQLِ خام و `generate_series` پر می‌شود و نه با ORM: هزار پرسنل × شش دوره ×
بیست شاخص یعنی حدودِ صد و بیست هزار ردیفِ نمره، و ساختنِ صد و بیست هزار شیء
پایتونی برای دورانداختنشان، خودِ اسکریپت را به همان چیزی تبدیل می‌کند که
می‌خواهیم اندازه بگیریم.

اجرا (از پوشهٔ backend، با venv فعال) — **روی دیتابیسِ جدا**:

    DATABASE_URL=postgresql://nexahr:...@localhost:5432/nexahr_load \\
        python -m scripts.seed_load_test --personnel 1000 --years 3

دیتابیسِ مقصد باید از قبل ساخته و `alembic upgrade head` شده باشد و **خالی**
باشد؛ اسکریپت روی دیتابیسِ پرداده اجرا نمی‌شود تا کسی به‌اشتباه دادهٔ توسعه‌اش
را با صد هزار ردیفِ ساختگی قاطی نکند.
"""
import argparse
import json
import sys
import time
from datetime import timedelta

from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal

# شاخص‌ها را خودِ مایگریشن‌ها می‌سازند (چارچوبِ نسخهٔ ۱، بیست شاخص). این‌جا
# ساخته نمی‌شوند: چارچوبِ ساختگی، عددِ اندازه‌گیری را از واقعیت دور می‌کند.
UNITS = [
    ("ستاد", "منابع انسانی"),
    ("ستاد", "مالی"),
    ("ستاد", "حقوقی"),
    ("ستاد", "فناوری اطلاعات"),
    ("کارخانه", "تولید"),
    ("کارخانه", "کنترل کیفیت"),
    ("کارخانه", "نگهداری و تعمیرات"),
    ("کارخانه", "انبار"),
    ("فروش", "فروش داخلی"),
    ("فروش", "صادرات"),
    ("فروش", "بازاریابی"),
    ("فروش", "خدمات پس از فروش"),
]
DEPUTIES = 3
HR_USERS = 5
#: رشته‌ای در جایِ هشِ رمز — نه یک رمزِ ضعیف، بلکه هشی که هیچ رمزی به آن
#: نمی‌رسد: طولش با قالبِ bcrypt نمی‌خوانَد، پس راستی‌آزمایی همیشه رد می‌کند.
#:
#: عمداً هشِ یک رمزِ واقعی *نیست*. این اسکریپت هزار حساب می‌سازد و تنها کارِ
#: آن حساب‌ها پر کردنِ صندلی‌هاست؛ اگر رمزِ مشترکی داشتند، یک دیتابیسِ
#: آزمایشیِ فراموش‌شده می‌شد هزار درِ باز.
DEAD_HASH = "$2b$12$loadtestloadtestloadtestloadtestloadtestloadtestloadtestlo"


#: گذارهای هر وضعیت، از تولد تا همان‌جا. `stage_stats` مدتِ ماندن را از همین
#: ردیف‌ها بیرون می‌آورد، پس بی این‌ها نیمی از کارش اصلاً اندازه‌گیری نمی‌شد.
_PATH = ["draft", "submitted", "hr_approved", "deputy_approved", "finalized"]


def _seed_audit_chain(db) -> None:
    """لاگِ ممیزی با زنجیرهٔ هشِ **معتبر**.

    هشِ ساختگی وسوسه‌انگیز بود و غلط: فازِ ۳پ دربارهٔ همین زنجیره است، و
    دیتابیسی که زنجیره‌اش از پیش شکسته باشد، برای اندازه‌گیریِ `verify_chain`
    بی‌فایده است. پس با همان `compute_hash`ِ خودِ سامانه ساخته می‌شود — یک بار،
    ترتیبی، در پایتون؛ چیزی که در SQL نمی‌شود چون هر ردیف به هشِ ردیفِ قبلی
    بند است.
    """
    from app.services.audit import GENESIS_HASH, compute_hash

    actor_id = db.scalar(text("select id from users where username = 'load_ceo_1'"))
    rows = db.execute(
        text(
            """
            select id, status::text as status, created_at
            from evaluation_records
            order by id
            """
        )
    ).all()

    prev_hash = GENESIS_HASH
    payloads = []
    for record_id, status, created_at in rows:
        steps = _PATH[: _PATH.index(status) + 1] if status in _PATH else _PATH[:1]
        at = created_at
        for step_index in range(1, len(steps)):
            old_value = {"status": steps[step_index - 1]}
            new_value = {"status": steps[step_index]}
            at = at + timedelta(days=2, hours=step_index)
            entry_hash = compute_hash(
                actor_user_id=actor_id,
                event_type="status_changed",
                evaluation_record_id=record_id,
                old_value=old_value,
                new_value=new_value,
                prev_hash=prev_hash,
            )
            payloads.append(
                {
                    "record_id": record_id,
                    "actor_id": actor_id,
                    "old_value": json.dumps(old_value),
                    "new_value": json.dumps(new_value),
                    "created_at": at,
                    "prev_hash": prev_hash,
                    "entry_hash": entry_hash,
                }
            )
            prev_hash = entry_hash

    db.connection().exec_driver_sql(
        """
        insert into audit_log (
            evaluation_record_id, actor_user_id, event_type,
            old_value, new_value, created_at, prev_hash, entry_hash
        ) values (%(record_id)s, %(actor_id)s, 'status_changed',
                  %(old_value)s, %(new_value)s, %(created_at)s, %(prev_hash)s, %(entry_hash)s)
        """,
        payloads,
    )


def _require_non_production() -> None:
    if settings.environment == "production":
        sys.exit("این اسکریپت دادهٔ ساختگی می‌سازد و هرگز نباید روی production اجرا شود.")


def _require_empty(db) -> None:
    existing = db.scalar(text("select count(*) from personnel"))
    if existing:
        sys.exit(
            f"دیتابیسِ مقصد {existing} پرسنل دارد. این اسکریپت فقط روی دیتابیسِ خالی "
            "اجرا می‌شود — یک دیتابیسِ جدا بسازید و `alembic upgrade head` بزنید."
        )


def seed(personnel_count: int, years: int) -> None:
    db = SessionLocal()
    try:
        _require_empty(db)
        started = time.monotonic()

        values = ", ".join(
            f"('{site}', '{name}', {order})" for order, (site, name) in enumerate(UNITS, start=1)
        )
        db.execute(
            text(
                f"""
                insert into org_units (site, name, is_active, display_order, is_hr_unit)
                select s, n, true, ord, n = 'منابع انسانی'
                from (values {values}) as u(s, n, ord)
                """
            )
        )

        # نقش‌ها: یک مدیرعامل، سه معاونت، یک مسئول به ازای هر واحد، پنج HR.
        db.execute(
            text(
                """
                insert into users (username, password_hash, role, is_active, token_version, full_name)
                select 'load_' || tag || '_' || i, :hash, tag::user_role, true, 1,
                       'کاربر بارِ ' || tag || ' ' || i
                from (
                    select 'ceo' as tag, generate_series(1, 1) as i
                    union all select 'deputy', generate_series(1, :deputies)
                    union all select 'unit_supervisor', generate_series(1, :units)
                    union all select 'hr', generate_series(1, :hr)
                ) roles
                """
            ),
            {
                "hash": DEAD_HASH,
                "deputies": DEPUTIES,
                "units": len(UNITS),
                "hr": HR_USERS,
            },
        )

        db.execute(
            text(
                """
                insert into personnel (
                    personnel_code, full_name, job_title, org_unit,
                    contract_start_date, contract_end_date, status, is_manager
                )
                select
                    'LT-' || lpad(i::text, 6, '0'),
                    'پرسنلِ آزمونِ بار ' || i,
                    'سمتِ ' || (i % 40),
                    (select name from org_units order by display_order offset (i % :units) limit 1),
                    current_date - (400 + (i % 900)),
                    -- بخشی از قراردادها عمداً رو به انقضا، تا جاروی تمدید کار داشته باشد
                    current_date + ((i % 400) - 30),
                    'active'::personnel_status,
                    i % 25 = 0
                from generate_series(1, :n) as i
                """
            ),
            {"units": len(UNITS), "n": personnel_count},
        )

        # زنجیرهٔ دسترسی: هر واحد یک مسئول، معاونت به‌گردش، مدیرعاملِ یگانه.
        db.execute(
            text(
                """
                with seats as (
                    select
                        (select id from users where username = 'load_ceo_1') as ceo_id,
                        array(select id from users where role = 'deputy' order by id) as deputies,
                        array(select id from users where role = 'unit_supervisor' order by id) as supervisors
                )
                insert into evaluation_access (personnel_id, unit_supervisor_user_id, deputy_user_id, ceo_user_id)
                select
                    p.id,
                    -- یکی از هر بیست نفر «مدیر» است و مسئولِ واحد ندارد (مسیرِ مدیر)
                    case when p.is_manager then null else s.supervisors[1 + (p.id % :units)] end,
                    s.deputies[1 + (p.id % :deputies)],
                    s.ceo_id
                from personnel p cross join seats s
                """
            ),
            {"units": len(UNITS), "deputies": DEPUTIES},
        )

        # پرونده‌های نهایی‌شده: دو دوره در سال، در همان بازهٔ سه‌ساله پخش شده.
        periods = years * 2
        db.execute(
            text(
                """
                with seats as (
                    select
                        (select id from users where username = 'load_ceo_1') as ceo_id,
                        array(select id from users where role = 'deputy' order by id) as deputies,
                        array(select id from users where role = 'unit_supervisor' order by id) as supervisors,
                        array(select id from users where role = 'hr' order by id) as hrs
                )
                insert into evaluation_records (
                    evaluation_code, subject_personnel_id,
                    unit_supervisor_user_id, deputy_user_id, ceo_user_id, hr_user_id,
                    status, base_weighted_pct, general_score_pct, specialized_score_pct,
                    final_weighted_pct, created_at, stage_entered_at, finalized_at,
                    scoring_scheme_id, indicator_framework_id
                )
                select
                    'LT-' || p.id || '-' || k,
                    p.id,
                    case when p.is_manager then null else s.supervisors[1 + (p.id % :units)] end,
                    s.deputies[1 + (p.id % :deputies)],
                    s.ceo_id,
                    s.hrs[1 + (p.id % :hrs)],
                    'finalized'::evaluation_status,
                    55 + ((p.id * 7 + k * 13) % 40),
                    55 + ((p.id * 5 + k) % 40),
                    55 + ((p.id * 11 + k) % 40),
                    55 + ((p.id * 7 + k * 13) % 40),
                    now() - make_interval(days => 30 + k * 180 + (p.id % 60)),
                    now() - make_interval(days => 30 + k * 180 + (p.id % 60)),
                    now() - make_interval(days => 20 + k * 180 + (p.id % 60)),
                    (select id from scoring_schemes order by version desc limit 1),
                    (select id from indicator_frameworks order by version desc limit 1)
                from personnel p
                cross join seats s
                cross join generate_series(1, :periods) as k
                """
            ),
            {"units": len(UNITS), "deputies": DEPUTIES, "hrs": HR_USERS, "periods": periods},
        )

        # پرونده‌های باز: یکی به ازای هر پرسنل (قیدِ یکتای جزئی بیش از این نمی‌دهد)،
        # پخش‌شده روی چهار وضعیتِ باز، و همه از آستانهٔ SLA گذشته تا جاروها کار کنند.
        db.execute(
            text(
                """
                with seats as (
                    select
                        (select id from users where username = 'load_ceo_1') as ceo_id,
                        array(select id from users where role = 'deputy' order by id) as deputies,
                        array(select id from users where role = 'unit_supervisor' order by id) as supervisors,
                        array(select id from users where role = 'hr' order by id) as hrs
                )
                insert into evaluation_records (
                    evaluation_code, subject_personnel_id,
                    unit_supervisor_user_id, deputy_user_id, ceo_user_id, hr_user_id,
                    status, created_at, stage_entered_at,
                    scoring_scheme_id, indicator_framework_id
                )
                select
                    'LT-' || p.id || '-open',
                    p.id,
                    case when p.is_manager then null else s.supervisors[1 + (p.id % :units)] end,
                    s.deputies[1 + (p.id % :deputies)],
                    s.ceo_id,
                    case when p.id % 4 = 1 then null else s.hrs[1 + (p.id % :hrs)] end,
                    (array['draft', 'submitted', 'hr_approved', 'deputy_approved'])[1 + (p.id % 4)]::evaluation_status,
                    now() - make_interval(days => 40 + (p.id % 30)),
                    now() - make_interval(days => 40 + (p.id % 30)),
                    (select id from scoring_schemes order by version desc limit 1),
                    (select id from indicator_frameworks order by version desc limit 1)
                from personnel p cross join seats s
                """
            ),
            {"units": len(UNITS), "deputies": DEPUTIES, "hrs": HR_USERS},
        )

        db.execute(
            text(
                """
                insert into evaluation_scores (evaluation_record_id, indicator_id, score)
                select r.id, i.id, 1 + ((r.id + i.id) % 5)
                from evaluation_records r cross join indicators i
                """
            )
        )

        _seed_audit_chain(db)

        db.commit()
        elapsed = time.monotonic() - started

        counts = db.execute(
            text(
                """
                select
                    (select count(*) from personnel),
                    (select count(*) from users),
                    (select count(*) from evaluation_records),
                    (select count(*) from evaluation_records where status not in ('finalized','cancelled')),
                    (select count(*) from evaluation_scores),
                    (select count(*) from audit_log)
                """
            )
        ).one()
        print(
            f"پر شد در {elapsed:.1f} ثانیه: "
            f"{counts[0]} پرسنل، {counts[1]} کاربر، {counts[2]} پرونده "
            f"({counts[3]} باز)، {counts[4]} نمره، {counts[5]} ردیفِ ممیزی."
        )
        print("حالا `ANALYZE` بزنید تا برنامه‌ریزِ کوئری آمارِ درست داشته باشد:")
        db.execute(text("analyze"))
        db.commit()
        print("ANALYZE انجام شد.")
    finally:
        db.close()


def main() -> None:
    _require_non_production()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--personnel", type=int, default=1000)
    parser.add_argument("--years", type=int, default=3)
    args = parser.parse_args()
    print(f"مقصد: {settings.database_url}")
    seed(args.personnel, args.years)


if __name__ == "__main__":
    main()
