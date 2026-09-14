"""نشست‌های مرده پاک می‌شوند، و دو رقابتِ ساخت ۵۰۰ نمی‌دهند.

سه چیز از یک جنس: چیزهایی که در حالتِ عادی هیچ‌وقت دیده نمی‌شوند و وقتی دیده
شوند، توضیح‌دادنشان سخت است.

* **جدولِ نشست‌ها هیچ‌وقت پاک نمی‌شد.** هر چرخشِ توکن یک ردیفِ تازه می‌سازد و
  والد را نگه می‌دارد؛ توکنِ دسترسی کوتاه‌عمر است، پس یک کاربرِ فعال روزی
  ده‌ها ردیف می‌ساخت. جاروی شبانه `login_attempts` را پاک می‌کرد و این را نه —
  و `ip` و `user_agent`ِ هر نشست تا ابد می‌ماندند.
* **دو «بخوان، بعد بساز»** که قیدِ یکتای دیتابیس را ندیده می‌گرفتند: نامِ
  کاربریِ تکراریِ هم‌زمان، و اولین ثبتِ زنجیرهٔ یک پرسنل. `SELECT`ِ قبلی در
  برابرِ هم‌زمانی گارد نیست — دو درخواست هر دو «نیست» می‌بینند — و دومی ۵۰۰
  می‌گرفت.
"""
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import settings
from app.models.auth_session import AuthSession
from app.services.sessions import create_session, purge_dead_sessions
from tests.helpers import auth_header, make_personnel, make_user


def _age(db, jti: str, **columns) -> None:
    session = db.scalar(select(AuthSession).where(AuthSession.jti == jti))
    for key, value in columns.items():
        setattr(session, key, value)
    db.flush()


def _long_ago() -> datetime:
    return datetime.now(UTC) - timedelta(days=settings.session_retention_days + 1)


# ── جاروی نشست‌ها ──────────────────────────────────────────────────────────


def test_expired_sessions_are_swept(db_session):
    user = make_user(db_session, "hr")
    db_session.flush()
    jti = create_session(db_session, user.id)
    _age(db_session, jti, expires_at=_long_ago())

    assert purge_dead_sessions(db_session) == 1
    assert db_session.scalar(select(AuthSession).where(AuthSession.jti == jti)) is None


def test_revoked_sessions_are_swept(db_session):
    user = make_user(db_session, "hr")
    db_session.flush()
    jti = create_session(db_session, user.id)
    _age(db_session, jti, revoked_at=_long_ago())

    assert purge_dead_sessions(db_session) == 1


def test_a_live_session_is_never_swept(db_session):
    """گاردِ ارزان در برابر «تمیز شد چون همه‌چیز پاک شد»."""
    user = make_user(db_session, "hr")
    db_session.flush()
    jti = create_session(db_session, user.id)

    assert purge_dead_sessions(db_session) == 0
    assert db_session.scalar(select(AuthSession).where(AuthSession.jti == jti)) is not None


def test_a_recently_dead_session_is_kept_for_the_retention_window(db_session):
    """مهلتِ نگه‌داری برای *بعد از حادثه* است.

    وقتی هشدارِ «توکن دوباره استفاده شد» می‌آید، کسی که بررسی می‌کند باید
    بتواند زنجیرهٔ چرخش‌ها را عقب برود. پاک‌کردنِ فوری، همان هشدار را به یک خطِ
    بی‌زمینه تبدیل می‌کرد.
    """
    user = make_user(db_session, "hr")
    db_session.flush()
    jti = create_session(db_session, user.id)
    _age(db_session, jti, revoked_at=datetime.now(UTC) - timedelta(days=1))

    assert purge_dead_sessions(db_session) == 0


def test_a_rotated_but_still_valid_session_is_kept(db_session):
    """ردیفِ چرخیده همان چیزی است که مهلتِ grace را ممکن می‌کند.

    حذفش یک `refresh`ِ دوبارهٔ بی‌آزار — دو تب، یا یک تلاشِ دوباره پس از
    تایم‌اوت — را به «همهٔ نشست‌هایت باطل شد» تبدیل می‌کرد.
    """
    user = make_user(db_session, "hr")
    db_session.flush()
    jti = create_session(db_session, user.id)
    _age(db_session, jti, rotated_at=datetime.now(UTC))

    assert purge_dead_sessions(db_session) == 0


def test_the_nightly_sweep_reports_what_it_purged(db_session):
    from app.services.scheduled import run_all_sweeps

    user = make_user(db_session, "hr")
    db_session.flush()
    _age(db_session, create_session(db_session, user.id), expires_at=_long_ago())

    summary = run_all_sweeps(db_session)

    assert summary["dead_sessions_purged"] == 1


# ── دو رقابتِ ساخت ─────────────────────────────────────────────────────────
#
# هر دو از یک شکل‌اند: «بخوان، اگر نبود بساز». آن `SELECT` در حالتِ عادی کار
# می‌کند و پیامِ بهتری هم می‌دهد، ولی گاردِ *واقعی* نیست — دو درخواستِ هم‌زمان
# هر دو «نیست» می‌بینند، هر دو می‌سازند، و دومی روی قیدِ یکتای دیتابیس می‌خورَد.
#
# دو درخواستِ واقعاً هم‌زمان را نمی‌شود در یک تستِ تک‌تراکنشی ساخت. پس همان
# حالت از دیدِ کدِ پایین‌دست شبیه‌سازی می‌شود: بررسیِ بالا *کور* می‌شود و
# «نیست» می‌گوید، در حالی که ردیف واقعاً هست. از این نقطه به بعد، کد دقیقاً
# همان چیزی را می‌بیند که در رقابتِ واقعی می‌دید.


def _blind_the_lookup(monkeypatch, db, marker: str) -> None:
    """بررسیِ «آیا از قبل هست؟» را کور می‌کند و بقیهٔ پرس‌وجوها را دست نمی‌زند."""
    real_scalar = db.scalar

    def blind(statement, *args, **kwargs):
        if marker in str(statement):
            return None
        return real_scalar(statement, *args, **kwargs)

    monkeypatch.setattr(db, "scalar", blind)


def test_a_duplicate_username_is_a_clean_error(client, db_session):
    """مسیرِ عادی: بررسیِ بالا می‌گیردش."""
    admin = make_user(db_session, "hr")
    db_session.commit()
    body = {"username": "hamnam", "password": "Str0ng-Pass-9", "role": "unit_supervisor"}

    assert client.post("/api/users", json=body, headers=auth_header(admin)).status_code == 201

    again = client.post("/api/users", json=body, headers=auth_header(admin))
    assert again.status_code == 400
    assert again.json()["detail"] == "نام کاربری تکراری است"


def test_a_duplicate_username_race_is_a_clean_error_too(client, db_session, monkeypatch):
    """و مسیرِ رقابت: قیدِ یکتا باید به همان پیام ترجمه شود، نه ۵۰۰."""
    admin = make_user(db_session, "hr")
    db_session.commit()
    body = {"username": "hamzaman", "password": "Str0ng-Pass-9", "role": "unit_supervisor"}
    assert client.post("/api/users", json=body, headers=auth_header(admin)).status_code == 201

    _blind_the_lookup(monkeypatch, db_session, "users.username")
    again = client.post("/api/users", json=body, headers=auth_header(admin))

    assert again.status_code == 400, f"انتظار پیامِ تمیز بود، نه {again.status_code}"
    assert again.json()["detail"] == "نام کاربری تکراری است"


def test_a_second_chain_for_the_same_person_is_a_conflict_not_a_crash(
    client, db_session, monkeypatch
):
    """«هر پرسنل یک زنجیره» قیدِ یکتاست؛ رقابتش باید ۴۰۹ بدهد نه ۵۰۰."""
    hr = make_user(db_session, "hr")
    sup = make_user(db_session, "unit_supervisor")
    ceo = make_user(db_session, "ceo", capabilities=[])
    person = make_personnel(db_session)
    db_session.commit()

    body = {
        "unit_supervisor_user_id": sup.id,
        "deputy_user_id": None,
        "ceo_user_id": ceo.id,
    }
    url = f"/api/personnel/{person.id}/access"
    assert client.put(url, json=body, headers=auth_header(hr)).status_code == 200

    _blind_the_lookup(monkeypatch, db_session, "evaluation_access.personnel_id")
    again = client.put(url, json=body, headers=auth_header(hr))

    assert again.status_code == 409, f"انتظار ۴۰۹ بود، نه {again.status_code}"
    assert "هم‌زمان" in again.json()["detail"]


def test_the_ordinary_second_write_is_an_update_not_a_conflict(client, db_session):
    """گاردِ ارزان: ثبتِ دوبارهٔ زنجیره باید همچنان *به‌روزرسانی* باشد.

    بی این، تبدیلِ همان مسیر به ۴۰۹ هم تستِ بالا را سبز می‌کرد.
    """
    hr = make_user(db_session, "hr")
    sup = make_user(db_session, "unit_supervisor")
    other_sup = make_user(db_session, "unit_supervisor")
    ceo = make_user(db_session, "ceo", capabilities=[])
    person = make_personnel(db_session)
    db_session.commit()

    url = f"/api/personnel/{person.id}/access"
    base = {"deputy_user_id": None, "ceo_user_id": ceo.id}
    assert client.put(
        url, json={**base, "unit_supervisor_user_id": sup.id}, headers=auth_header(hr)
    ).status_code == 200

    changed = client.put(
        url, json={**base, "unit_supervisor_user_id": other_sup.id}, headers=auth_header(hr)
    )
    assert changed.status_code == 200
    assert changed.json()["unit_supervisor_user_id"] == other_sup.id
