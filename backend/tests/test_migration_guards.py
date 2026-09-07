"""`downgrade`ی که تاریخ را بازنویسی می‌کند باید بلند بشکند، نه بی‌صدا.

مسئله حذفِ جدول نیست؛ *بازگشت* است. `downgrade` جدولِ نسخه‌ها را می‌ریزد و
`upgrade`ِ بعدی فقط v1 را می‌سازد و همهٔ پرونده‌های بی‌نسخه را به آن مهر
می‌زند. پس پرونده‌ای که واقعاً زیرِ v2 نمره گرفته، پس از یک چرخهٔ
رفت‌وبرگشت به v1 اشاره می‌کند — و همان تضمینی می‌شکند که وجودِ آن ستون
برایش ساخته شده: «محاسبه از نسخهٔ خودِ پرونده می‌خواند، نه از طرحِ فعال».

پروندهٔ باز با وزن‌های اشتباه دوباره محاسبه می‌شود؛ پروندهٔ نهایی‌شده
snapshotِ خودش را نگه می‌دارد ولی آستانه و توصیه‌اش عوض می‌شود. و هیچ
هشداری در هیچ مرحله‌ای چاپ نمی‌شد.

**چه چیزی این‌جا سنجیده *نمی‌شود*:** خودِ چرخهٔ `downgrade`/`upgrade` اجرا
نمی‌شود — روی دیتابیسِ مشترکِ تست ویرانگر است. آن‌چه سنجیده می‌شود همان
منطقی است که گارد را می‌سازد: کوئریِ تشخیص و خودِ raise.
"""
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text

_VERSIONS = Path(__file__).resolve().parent.parent / "alembic" / "versions"


def _guard_of(filename: str):
    """تابعِ گارد را از خودِ فایلِ مایگریشن برمی‌دارد.

    مایگریشن‌ها عمداً خودبسنده‌اند و از کدِ برنامه چیزی وارد نمی‌کنند (وگرنه
    با تحولِ مدل‌ها می‌شکنند)، پس گارد در هر دو فایل تکرار شده. این تست هم
    همان‌جا سراغش می‌رود و نه یک نسخهٔ سوم.
    """
    path = next(_VERSIONS.glob(filename))
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._refuse_if_history_would_be_lost


SCHEME_GUARD = ("e2b4a71c8d35_*.py", "scoring_schemes", "scoring_scheme_id", "طرحِ نمره‌دهی", "طرح")
FRAMEWORK_GUARD = (
    "b7d4e2a91c68_*.py",
    "indicator_frameworks",
    "indicator_framework_id",
    "چارچوبِ شاخص",
    "چارچوب",
)


@pytest.mark.parametrize("case", [SCHEME_GUARD, FRAMEWORK_GUARD], ids=["scheme", "framework"])
def test_the_guard_is_silent_when_only_version_one_exists(case, db_session):
    """نصبِ تازه فقط v1 دارد — `downgrade` آن‌جا چیزی را از دست نمی‌دهد."""
    filename, table, column, label, singular = case
    guard = _guard_of(filename)
    assert (
        db_session.scalar(text(f"SELECT count(*) FROM {table} WHERE version <> 1")) == 0
    ), "پیش‌فرضِ تست: هنوز نسخهٔ دومی ساخته نشده"
    guard(table, column, label, singular, bind=db_session.connection())


@pytest.mark.parametrize("case", [SCHEME_GUARD, FRAMEWORK_GUARD], ids=["scheme", "framework"])
def test_a_second_version_stops_the_downgrade(case, db_session):
    """و به‌محضِ وجودِ نسخهٔ دوم، بلند می‌شکند."""
    filename, table, column, label, singular = case
    guard = _guard_of(filename)
    # نسخهٔ دوم با `INSERT ... SELECT` از خودِ v1 ساخته می‌شود و نه با مقادیرِ
    # دستی: این جدول‌ها ستونِ `jsonb` و enum دارند و بازسازیِ دستی‌شان یعنی
    # تست به *شکلِ* آن‌ها بند می‌شود، در حالی که موضوعش شمارشِ نسخه‌هاست.
    row = (
        db_session.execute(text(f"SELECT * FROM {table} WHERE version = 1 LIMIT 1"))
        .mappings()
        .one()
    )
    columns = [c for c in row.keys() if c != "id"]
    # و `status` هم عوض می‌شود: ایندکسِ «حداکثر یک طرحِ فعال» اجازهٔ دومی
    # نمی‌دهد — و طرحِ تازه هم در واقعیت `draft` ساخته می‌شود، نه `active`.
    projected = ", ".join(
        "2" if c == "version" else ("'draft'" if c == "status" else c) for c in columns
    )
    db_session.execute(
        text(
            f"INSERT INTO {table} ({', '.join(columns)}) "
            f"SELECT {projected} FROM {table} WHERE version = 1"
        )
    )
    db_session.flush()

    with pytest.raises(RuntimeError) as raised:
        guard(table, column, label, singular, bind=db_session.connection())
    assert label in str(raised.value)
    assert "downgrade متوقف شد" in str(raised.value)
