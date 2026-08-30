"""وضعیت دیتابیس، به شکلی که یک برنامهٔ دیگر بتواند بخواندش.

چرا این فایل هست
----------------
راه‌انداز (`tools/launcher`) با پایتونِ سیستم اجرا می‌شود، نه با venv — چون
خودش همان venv را می‌سازد. پس `psycopg` ندارد و نمی‌تواند مستقیم به دیتابیس وصل
شود. هر چیزی که پرسیدنش کتابخانهٔ دیتابیس می‌خواهد، باید از این‌جا رد شود.

خروجی JSON است و نه متنِ آدمیزاد، چون خواننده‌اش برنامه است. کدِ خروج هم همیشه
صفر می‌ماند مگر آرگومان‌ها غلط باشند: «نشد وصل شوم» یک *جواب* است، نه یک خطای
اجرا، و باید در همان JSON بیاید تا فراخوان بتواند بگوید چه شد.

تفاوتِ «سرور بالا نیست» و «دیتابیس نیست» عمداً نگه داشته شده: راه‌حلشان یکی
نیست — اولی سرویس می‌خواهد، دومی یک `CREATE DATABASE`.

اجرا (از پوشهٔ backend)::

    python -m scripts.db_info [--url postgresql+psycopg://...]
"""
from __future__ import annotations

import argparse
import json
import sys

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover - فقط وقتی venv ناقص است
    print(json.dumps({"error": "psycopg is not installed", "server_reachable": False}))
    raise SystemExit(0) from None

from scripts.ensure_database import Target

#: دیتابیسی که همیشه روی هر سرور PostgreSQL هست. برای سؤال‌هایی لازم است که
#: باید پرسیده شوند حتی وقتی دیتابیسِ خودمان هنوز ساخته نشده.
MAINTENANCE_DB = "postgres"


def _connect(target: Target, dbname: str):
    optional = {"password": target.password} if target.password else {}
    return psycopg.connect(
        user=target.user, host=target.host, port=target.port,
        dbname=dbname, connect_timeout=5, **optional,
    )


def _list_databases(target: Target) -> tuple[list[str], str]:
    """نامِ دیتابیس‌هایی که می‌شود به آن‌ها وصل شد.

    قالب‌ها (`template0` و `template1`) کنار گذاشته می‌شوند: در فهرست ظاهر
    می‌شوند ولی انتخابشان معنا ندارد.
    """
    try:
        with _connect(target, MAINTENANCE_DB) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT datname FROM pg_database "
                "WHERE datallowconn AND NOT datistemplate ORDER BY datname"
            )
            return [row[0] for row in cur.fetchall()], ""
    except psycopg.Error as exc:
        return [], str(exc).strip()


def inspect(url: str) -> dict:
    try:
        target = Target(url)
    except ValueError as exc:
        return {"error": str(exc), "server_reachable": False, "database_exists": False}

    report = {
        "url": url,
        "host": target.host,
        "port": target.port,
        "database": target.database,
        "user": target.user,
        "server_reachable": False,
        "database_exists": False,
        "databases": [],
        "error": "",
    }

    try:
        with _connect(target, target.database):
            report["server_reachable"] = True
            report["database_exists"] = True
    except psycopg.OperationalError as exc:
        message = str(exc).strip()
        report["error"] = message
        # پیامِ احراز هویت یعنی سرور جواب داده — پس بالاست، فقط ما نتوانستیم
        # وارد شویم. این را با «هیچ‌کس آن‌جا نیست» یکی گرفتن، کاربر را دنبال
        # راه‌اندازیِ سرویسی می‌فرستد که از قبل بالاست.
        lowered = message.lower()
        if "authentication" in lowered or "password" in lowered or "does not exist" in lowered:
            report["server_reachable"] = True

    names, listing_error = _list_databases(target)
    report["databases"] = names
    if names:
        report["server_reachable"] = True
        report["database_exists"] = target.database in names
    elif listing_error and not report["error"]:
        report["error"] = listing_error

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="وضعیت دیتابیس، به صورت JSON")
    parser.add_argument("--url", default=None, help="پیش‌فرض: DATABASE_URL از تنظیمات")
    args = parser.parse_args()

    url = args.url
    if not url:
        from app.core.config import settings

        url = settings.database_url

    json.dump(inspect(url), sys.stdout, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
