"""قفلِ حساب زیرِ درخواستِ هم‌زمان.

`record_failure` یک «بخوان، جمع کن، بنویس» بود. با دو اتصالِ واقعی و
درهم‌آمیزیِ اجباری، دو خرابی داشت: شمارشِ گم‌شده (۱ به‌جای ۲) و
`UniqueViolation` که تا endpointِ ورود بالا می‌آمد و ۵۰۰ می‌داد.

آزمون‌ها با *دو اتصالِ جدا* کار می‌کنند و نه با session تست، چون رقابت فقط
بین دو تراکنشِ واقعی معنا دارد؛ `db_session` تست همه‌چیز را در یک تراکنشِ
rollback‌شونده نگه می‌دارد و اصلاً به آن نمی‌رسد.
"""
import threading

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import engine
from app.models.login_attempt import LoginAttempt
from app.services.login_guard import record_failure


def _fresh(username: str) -> None:
    with Session(engine) as session:
        session.execute(delete(LoginAttempt).where(LoginAttempt.username == username))
        session.commit()


def _count(username: str) -> int | None:
    with Session(engine) as session:
        row = session.get(LoginAttempt, username)
        return None if row is None else row.failed_count


def _race(username: str, workers: int) -> list[BaseException]:
    """هر کارگر در تراکنشِ خودش یک شکست ثبت می‌کند؛ همه با یک مانع هم‌زمان می‌شوند."""
    barrier = threading.Barrier(workers)
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            with Session(engine) as session:
                # تراکنش پیش از مانع باز می‌شود تا درهم‌آمیزی واقعاً رخ بدهد.
                session.execute(select(LoginAttempt).limit(1))
                barrier.wait(timeout=15)
                record_failure(session, username)
                session.commit()
        except BaseException as exc:  # noqa: BLE001 — هر شکستی باید دیده شود
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return errors


def test_no_failure_is_lost_on_an_existing_row():
    """دو شکستِ هم‌زمان باید دو بار شمرده شوند، نه یک بار."""
    username = "race-existing"
    _fresh(username)
    with Session(engine) as session:
        record_failure(session, username)
        session.commit()
    assert _count(username) == 1

    assert _race(username, workers=2) == []
    assert _count(username) == 3, "یک شکستِ هم‌زمان گم شده است"


def test_a_missing_row_does_not_raise_on_concurrent_inserts():
    """ردیفِ نبوده + دو INSERT هم‌زمان = پیش از این UniqueViolation و ۵۰۰."""
    username = "race-missing"
    _fresh(username)

    errors = _race(username, workers=4)
    assert errors == [], f"ثبتِ شکست نباید خطا بدهد: {errors!r}"
    assert _count(username) == 4


def test_the_lock_threshold_is_not_stretched_by_parallel_requests():
    """سقفِ قفل باید با درخواستِ موازی هم همان سقف بماند."""
    username = "race-threshold"
    _fresh(username)
    threshold = settings.login_max_failed_attempts

    assert _race(username, workers=threshold) == []
    with Session(engine) as session:
        row = session.get(LoginAttempt, username)
        assert row.locked_until is not None, (
            f"با {threshold} شکستِ هم‌زمان باید قفل شده باشد"
        )
    _fresh(username)
