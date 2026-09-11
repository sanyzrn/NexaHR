"""چرخشِ توکنِ refresh باید قفلِ ردیفی بگیرد.

کلِ کشفِ سرقت روی یک «بخوان، بسنج، بنویس» بنا شده: اگر `rotated_at` پر باشد
یعنی این توکن قبلاً مصرف شده و کسِ دوم دزد است — و پاسخش باطل‌کردنِ همهٔ
نشست‌های آن کاربر است.

بی قفل، آن تضمین فقط برای استفادهٔ *متوالی* برقرار بود: دو
`POST /api/auth/refresh`ِ هم‌زمان با یک کوکی، هر دو `rotated_at IS NULL`
می‌دیدند، هر دو نشستِ جانشین می‌ساختند و هر دو ۲۰۰ می‌گرفتند. دزدی که
هم‌زمان با قربانی refresh می‌کرد، دو شاخهٔ زندهٔ نشست می‌ساخت و هیچ‌وقت کشف
نمی‌شد.

مثل `test_score_write_lock`، این‌جا دو اتصالِ واقعی لازم است — پس داده باید
commit شده باشد و savepointِ conftest کافی نیست.
"""
import threading

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import hash_password
from app.models.auth_session import AuthSession
from app.models.user import User
from app.services.sessions import RefreshReuseError, create_session, rotate_session

LOCK_HOLD_SECONDS = 0.6


@pytest.fixture
def committed_session():
    engine = create_engine(settings.database_url)
    make_session = sessionmaker(bind=engine)

    with make_session() as setup:
        user = User(
            username="rot_lock",
            password_hash=hash_password("Rotate-Lock-1"),
            role="hr",
        )
        setup.add(user)
        setup.flush()
        user_id = user.id
        jti = create_session(setup, user_id, user_agent="probe", ip="10.0.0.1")
        setup.commit()

    yield {"make_session": make_session, "user_id": user_id, "jti": jti}

    with make_session() as teardown:
        teardown.execute(
            text("DELETE FROM auth_sessions WHERE user_id = :u"), {"u": user_id}
        )
        teardown.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
        teardown.commit()
    engine.dispose()


def _hold_lock_then_rotate(committed_session, lock_held: threading.Event) -> None:
    with committed_session["make_session"]() as session:
        rotate_session(
            session, committed_session["user_id"], committed_session["jti"]
        )
        lock_held.set()
        # قفل تا commit نگه داشته می‌شود.
        threading.Event().wait(LOCK_HOLD_SECONDS)
        session.commit()


def test_a_second_connection_cannot_take_the_session_lock(committed_session):
    """اثباتِ اینکه قفل بین دو اتصال مؤثر است، نه فقط در SQLِ تولیدشده."""
    lock_held = threading.Event()
    holder = threading.Thread(
        target=_hold_lock_then_rotate, args=(committed_session, lock_held)
    )
    holder.start()
    try:
        assert lock_held.wait(timeout=5), "چرخانندهٔ اول به‌موقع قفل را نگرفت"
        with committed_session["make_session"]() as reader:
            reader.execute(text("SET LOCAL lock_timeout = '100ms'"))
            with pytest.raises(OperationalError):
                reader.scalar(
                    select(AuthSession)
                    .where(AuthSession.jti == committed_session["jti"])
                    .with_for_update(of=AuthSession)
                )
    finally:
        holder.join(timeout=5)


def test_a_racing_refresh_sees_the_rotation_and_is_treated_as_reuse(committed_session):
    """مسابقهٔ واقعی: دو چرخشِ هم‌زمان با یک توکن.

    با قفل، دومی پشتِ اولی معطل می‌ماند و بعد `rotated_at`ِ پرشده را می‌بیند.
    چون مهلتِ grace تازه شروع شده، پاسخش «بی‌چرخش» (`None`) است و نه یک
    نشستِ جانشینِ دوم. بی قفل، هر دو نشستِ تازه می‌ساختند.
    """
    lock_held = threading.Event()
    holder = threading.Thread(
        target=_hold_lock_then_rotate, args=(committed_session, lock_held)
    )
    holder.start()
    try:
        assert lock_held.wait(timeout=5)
        with committed_session["make_session"]() as second:
            outcome = rotate_session(
                second, committed_session["user_id"], committed_session["jti"]
            )
            second.commit()
    finally:
        holder.join(timeout=5)

    assert outcome is None, "چرخشِ دوم نباید نشستِ تازه بسازد"

    # یک جانشین ساخته شد، نه دو تا.
    with committed_session["make_session"]() as check:
        rows = check.scalars(
            select(AuthSession).where(AuthSession.user_id == committed_session["user_id"])
        ).all()
        assert len(rows) == 2, [r.jti for r in rows]
        parent = next(r for r in rows if r.jti == committed_session["jti"])
        assert parent.rotated_at is not None
        assert parent.replaced_by_jti is not None


def test_reuse_outside_the_grace_window_still_revokes_everything(committed_session):
    """قاعدهٔ اصلی دست‌نخورده است: مصرفِ دوباره پس از مهلت یعنی سرقت."""
    from datetime import UTC, datetime, timedelta

    with committed_session["make_session"]() as session:
        rotate_session(session, committed_session["user_id"], committed_session["jti"])
        session.commit()

    with committed_session["make_session"]() as aged:
        row = aged.scalar(
            select(AuthSession).where(AuthSession.jti == committed_session["jti"])
        )
        row.rotated_at = datetime.now(UTC) - timedelta(hours=1)
        aged.commit()

    with committed_session["make_session"]() as thief:
        with pytest.raises(RefreshReuseError):
            rotate_session(
                thief, committed_session["user_id"], committed_session["jti"]
            )
        thief.commit()

    with committed_session["make_session"]() as check:
        rows = check.scalars(
            select(AuthSession).where(AuthSession.user_id == committed_session["user_id"])
        ).all()
        assert all(r.revoked_at is not None for r in rows), "همهٔ نشست‌ها باید باطل شوند"
