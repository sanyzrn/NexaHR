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


def _module_of(filename: str):
    """خودِ فایلِ مایگریشن را بار می‌کند.

    مایگریشن‌ها عمداً خودبسنده‌اند و از کدِ برنامه چیزی وارد نمی‌کنند (وگرنه
    با تحولِ مدل‌ها می‌شکنند)، پس تست هم همان‌جا سراغِ گارد می‌رود و نه یک
    نسخهٔ دوم.
    """
    path = next(_VERSIONS.glob(filename))
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _guard_of(filename: str):
    """گاردِ «نسخه‌ها» — در هر دو مایگریشن با همین یک نام تکرار شده."""
    return _module_of(filename)._refuse_if_history_would_be_lost


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


# ── سه گاردِ دیگر، هرکدام با شکلِ زیانِ خودش ────────────────────────────────
#
# همان الگو، ولی نه همان کوئری: هر کدام چیزِ متفاوتی را از دست می‌دهند و
# پیامشان باید همان را بگوید. گاردی که فقط «داده هست» بگوید، خواننده‌اش
# نمی‌فهمد چه چیزی را دارد می‌بازد.


def test_the_verify_token_guard_is_silent_when_nothing_was_printed(db_session):
    guard = _module_of("b28cc6abdf2a_*.py")._refuse_if_printed_documents_would_stop_verifying
    assert (
        db_session.scalar(
            text("SELECT count(*) FROM evaluation_records WHERE verify_token IS NOT NULL")
        )
        == 0
    ), "پیش‌فرضِ تست: هنوز سندی نهایی نشده"
    guard(bind=db_session.connection())


def test_an_issued_verify_token_stops_the_downgrade(db_session):
    """توکن تصادفی است و بازساخته نمی‌شود؛ زیان روی کاغذِ بیرون می‌افتد."""
    from tests.helpers import make_personnel, make_user

    guard = _module_of("b28cc6abdf2a_*.py")._refuse_if_printed_documents_would_stop_verifying
    ceo = make_user(db_session, "ceo", capabilities=[])
    person = make_personnel(db_session)
    db_session.flush()
    db_session.execute(
        text(
            "INSERT INTO evaluation_records "
            "(evaluation_code, subject_personnel_id, ceo_user_id, status, verify_token) "
            "VALUES ('MG-1', :pid, :ceo, 'finalized', 'a-token')"
        ),
        {"pid": person.id, "ceo": ceo.id},
    )
    db_session.flush()

    with pytest.raises(RuntimeError) as raised:
        guard(bind=db_session.connection())
    assert "QR" in str(raised.value)


def test_a_populated_unit_catalogue_stops_the_downgrade(db_session):
    """نامِ واحد می‌ماند؛ پرچمِ «واحدِ منابع انسانی» می‌رود — و آن بی‌صداست."""
    guard = _module_of("ddafefc08701_*.py")._refuse_if_the_unit_catalogue_would_be_lost
    db_session.execute(
        text(
            "INSERT INTO org_units (site, name, is_active, display_order, is_hr_unit) "
            "VALUES ('ستاد', 'منابع انسانی', true, 1, true)"
        )
    )
    db_session.flush()

    with pytest.raises(RuntimeError) as raised:
        guard(bind=db_session.connection())
    assert "منابع انسانی" in str(raised.value)


def test_the_indicator_guard_is_silent_on_an_untouched_catalogue(db_session):
    """کاتالوگِ دست‌نخورده دقیقاً همان سید است — آن‌جا چیزی گم نمی‌شود."""
    guard = _module_of("65a700d744d4_*.py")._refuse_if_the_catalogue_is_no_longer_the_seed
    guard(bind=db_session.connection())


def test_an_added_indicator_stops_the_downgrade(db_session):
    """شاخصی که منابع انسانی خودش نوشته، با `DELETE`ِ مبتنی بر *بخش* می‌رفت."""
    guard = _module_of("65a700d744d4_*.py")._refuse_if_the_catalogue_is_no_longer_the_seed
    db_session.execute(
        text(
            "INSERT INTO indicators (section, category, description, display_order, is_active) "
            "VALUES ('general', 'دستهٔ خودمان', 'شاخصی که منابع انسانی اضافه کرده', 99, true)"
        )
    )
    db_session.flush()

    with pytest.raises(RuntimeError) as raised:
        guard(bind=db_session.connection())
    assert "downgrade متوقف شد" in str(raised.value)
