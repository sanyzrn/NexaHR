"""لنگرِ زنجیرهٔ ممیزی — و اینکه خودش نقطهٔ کور نشود (فازِ ۳پ).

راستی‌آزماییِ زنجیره از ابتدای تاریخ حساب می‌کرد، و آن عدد هرگز کوچک نمی‌شود.
لنگر همان هزینه را از مسیرِ درخواست بیرون می‌بَرد: جاروی شبانه کامل می‌سنجد و
نقطه‌اش را ثبت می‌کند، و بررسیِ تعاملی از همان نقطه به بعد را می‌سنجد.

ولی یک لنگرِ بی‌مراقبت، بدتر از نداشتنش است: بررسیِ سریع فقط پس از لنگر را
می‌بیند، پس هر دست‌کاری *پیش از* آن نامرئی می‌شود — و نشانِ صفحه سبز می‌ماند.
این فایل دقیقاً همان مرزها را می‌سنجد:

* لنگر بی یک راستی‌آزماییِ کاملِ موفق جلو نمی‌رود
* لنگرِ دست‌کاری‌شده، بررسی را سبز نمی‌کند — قرمزش می‌کند
* دفترِ لنگر خودش append-only است
* شکستِ بررسیِ کامل به کسی خبر می‌دهد؛ کشفی که به کسی نرسد کشف نیست
"""
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import InternalError, ProgrammingError

from app.models.audit_chain_check import AuditChainCheck
from app.models.audit_log import AuditLog
from app.models.enums import Capability
from app.models.notification import Notification
from app.services.audit import (
    ANCHOR_MISMATCH,
    latest_anchor,
    log_event,
    record_full_verification,
    verify_chain,
)
from app.services.scheduled import run_audit_anchor_sweep
from tests.helpers import auth_header, make_user


def _log_some(db, actor, count: int = 3) -> None:
    for i in range(count):
        log_event(db, actor_user_id=actor.id, event_type="test_event", new_value={"n": i})
    db.flush()


def _head(db) -> AuditLog:
    return db.scalar(select(AuditLog).order_by(AuditLog.id.desc()).limit(1))


def _tamper(db, row_id: int, **columns) -> None:
    """ویرایشِ مستقیم، با خاموش‌کردنِ موقتِ تریگرِ append-only.

    این همان کاری است که یک مهاجمِ دارای دسترسیِ دیتابیس می‌کند، و تنها راهِ
    آزمودنِ چیزی که قرار است بگیردش.
    """
    assignments = ", ".join(f"{key} = :{key}" for key in columns)
    db.execute(text("ALTER TABLE audit_log DISABLE TRIGGER trg_audit_log_append_only"))
    db.execute(text(f"UPDATE audit_log SET {assignments} WHERE id = :id"), {**columns, "id": row_id})
    db.execute(text("ALTER TABLE audit_log ENABLE TRIGGER trg_audit_log_append_only"))
    db.expire_all()


# ── لنگر فقط پس از یک راستی‌آزماییِ کاملِ موفق جلو می‌رود ────────────────────


def test_a_healthy_chain_moves_the_anchor_to_the_head(db_session):
    actor = make_user(db_session, "hr")
    db_session.flush()
    _log_some(db_session, actor, 3)

    outcome = record_full_verification(db_session)

    assert outcome["ok"] is True
    assert outcome["advanced"] is True
    anchor = latest_anchor(db_session)
    head = _head(db_session)
    assert anchor.log_id == head.id
    assert anchor.entry_hash == head.entry_hash


def test_a_broken_chain_leaves_the_anchor_where_it_was(db_session):
    """قاعدهٔ اصلیِ کلِ این فاز، در یک تست.

    اگر لنگر روی زنجیرهٔ شکسته هم جلو می‌رفت، همان شکست برای همیشه *پشتِ* لنگر
    می‌ماند و بررسیِ سریع دیگر هیچ‌وقت نمی‌دیدش.
    """
    actor = make_user(db_session, "hr")
    db_session.flush()
    _log_some(db_session, actor, 3)
    record_full_verification(db_session)
    anchor_before = latest_anchor(db_session).log_id

    _log_some(db_session, actor, 2)
    victim = db_session.scalar(
        select(AuditLog).where(AuditLog.id > anchor_before).order_by(AuditLog.id)
    )
    _tamper(db_session, victim.id, event_type="something_else")

    outcome = record_full_verification(db_session)

    assert outcome["ok"] is False
    assert outcome["advanced"] is False
    assert latest_anchor(db_session).log_id == anchor_before


def test_a_failed_check_is_recorded_but_is_never_an_anchor(db_session):
    """شکست ثبت می‌شود — وگرنه رابط جز «سبزِ سریع» چیزی نمی‌دید."""
    actor = make_user(db_session, "hr")
    db_session.flush()
    _log_some(db_session, actor, 3)
    _tamper(db_session, _head(db_session).id, event_type="rewritten")

    record_full_verification(db_session)

    last = db_session.scalar(select(AuditChainCheck).order_by(AuditChainCheck.id.desc()).limit(1))
    assert last.ok is False
    assert last.reason is not None
    # و هشِ لنگر خالی می‌ماند تا هیچ‌وقت مبنای بررسیِ سریع نشود
    assert last.entry_hash is None
    assert latest_anchor(db_session) is None


def test_a_second_run_with_no_new_events_does_not_re_anchor(db_session):
    actor = make_user(db_session, "hr")
    db_session.flush()
    _log_some(db_session, actor, 2)

    assert record_full_verification(db_session)["advanced"] is True
    assert record_full_verification(db_session)["advanced"] is False


# ── بررسیِ سریع: ارزان، ولی نه ساده‌لوح ─────────────────────────────────────


def test_the_fast_check_costs_the_same_whatever_came_before_the_anchor(db_session):
    """کلِ دلیلِ وجودِ لنگر، در یک تست.

    هزینهٔ بررسیِ تعاملی باید به *فعالیتِ از آخرین جارو تا حالا* بند باشد و نه
    به سنِ سامانه. پس همان دو رویدادِ تازه، چه پشتِ سرشان پنج رویداد باشد چه
    پنجاه‌تا، باید همان دو ردیف را بسنجد.

    عددِ واقعی روی دیتابیسِ بیست‌وپنج‌هزار ردیفی: ۱۱۵۷ میلی‌ثانیه → ۳
    (`docs/perf-3b.md`).
    """
    actor = make_user(db_session, "hr")
    db_session.flush()

    _log_some(db_session, actor, 5)
    record_full_verification(db_session)
    _log_some(db_session, actor, 2)
    short_history = verify_chain(db_session, since_anchor=True)

    _log_some(db_session, actor, 50)
    record_full_verification(db_session)
    _log_some(db_session, actor, 2)
    long_history = verify_chain(db_session, since_anchor=True)

    assert short_history["ok"] is True
    assert long_history["ok"] is True
    assert short_history["full"] is False
    assert long_history["full"] is False
    assert short_history["anchor_log_id"] is not None
    assert short_history["checked"] == long_history["checked"] == 2, (
        "بررسیِ سریع باید فقط رویدادهای پس از لنگر را بشمارد؛ اگر با تاریخِ "
        "پیش از لنگر رشد کند، لنگر هیچ کاری نکرده است."
    )


def test_the_fast_check_still_catches_tampering_after_the_anchor(db_session):
    actor = make_user(db_session, "hr")
    db_session.flush()
    _log_some(db_session, actor, 3)
    record_full_verification(db_session)
    _log_some(db_session, actor, 2)
    _tamper(db_session, _head(db_session).id, new_value=json.dumps({"n": 999}))

    assert verify_chain(db_session, since_anchor=True)["ok"] is False


def test_a_tampered_anchor_turns_the_fast_check_red(db_session):
    """لنگری که با لاگ نخوانَد، راهِ دور زدنِ کلِ بررسی بود.

    بی این وارسی، کسی که به دیتابیس دست دارد `log_id` را روی سرِ زنجیره
    می‌گذاشت و بررسیِ سریع صفر ردیف می‌سنجید و همیشه سبز می‌شد.
    """
    actor = make_user(db_session, "hr")
    db_session.flush()
    _log_some(db_session, actor, 3)
    record_full_verification(db_session)
    _log_some(db_session, actor, 2)

    # لنگرِ جعلی: به سرِ زنجیره اشاره می‌کند ولی هشش مالِ جای دیگری است
    db_session.add(
        AuditChainCheck(
            ok=True,
            log_id=_head(db_session).id,
            entry_hash="0" * 64,
            verified_rows=0,
        )
    )
    db_session.flush()

    fast = verify_chain(db_session, since_anchor=True)

    assert fast["ok"] is False
    assert fast["reason"] == ANCHOR_MISMATCH


def test_with_no_anchor_the_fast_check_verifies_everything(db_session):
    """«سریع ولی ناقص» هیچ‌وقت پیش‌فرضِ خاموش نیست.

    روی سامانه‌ای که جارو هنوز اجرا نشده، بررسیِ پیش‌فرض باید همان بررسیِ کامل
    باشد — نه یک سبزِ بی‌محتوا.
    """
    actor = make_user(db_session, "hr")
    db_session.flush()
    _log_some(db_session, actor, 3)

    result = verify_chain(db_session, since_anchor=True)

    assert result["full"] is True
    assert result["checked"] >= 3


def test_the_two_windows_cannot_be_combined(db_session):
    """`limit` و `since_anchor` دو پنجرهٔ متفاوت با دو معنی‌اند.

    پذیرفتنِ هر دو یعنی یکی بی‌صدا نادیده گرفته شود، و بعد کسی سنجشی بگیرد که
    فکر می‌کند چیزِ دیگری را سنجیده.
    """
    with pytest.raises(ValueError):
        verify_chain(db_session, limit=3, since_anchor=True)


def test_an_anchor_with_no_row_id_is_ignored(db_session):
    """لنگرِ بی‌شناسه باید نادیده گرفته شود، نه اینکه بررسی را خالی کند.

    `id > NULL` در SQL برای *هیچ* ردیفی درست نیست. یعنی چنین لنگری بررسیِ سریع
    را به صفر ردیف می‌رساند و همیشه سبز می‌کرد — بدترین شکلِ خرابی، چون شبیهِ
    سلامت است. ساختِ چنین ردیفی از قبل جلوگیری شده؛ این تست گاردِ دومش است.
    """
    actor = make_user(db_session, "hr")
    db_session.flush()
    _log_some(db_session, actor, 3)
    db_session.add(AuditChainCheck(ok=True, log_id=None, entry_hash=None, verified_rows=0))
    db_session.flush()

    result = verify_chain(db_session, since_anchor=True)

    assert result["full"] is True, "لنگرِ بی‌شناسه نباید مبنای بررسی شود"
    assert result["checked"] >= 3


def test_an_empty_log_is_never_anchored(db_session):
    """لاگِ خالی چیزی برای لنگر انداختن ندارد، و لنگرِ تهی همان دامِ بالاست."""
    outcome = record_full_verification(db_session)

    assert outcome["advanced"] is False
    assert latest_anchor(db_session) is None
    # قاعدهٔ عمومی‌ترش: هیچ لنگری هرگز به هیچ‌جا اشاره نمی‌کند
    assert db_session.scalar(
        select(AuditChainCheck).where(AuditChainCheck.log_id.is_(None)).limit(1)
    ) is None


# ── دفترِ لنگر هم append-only است ───────────────────────────────────────────


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_chain_checks SET ok = false WHERE id = :id",
        "DELETE FROM audit_chain_checks WHERE id = :id",
    ],
)
def test_the_anchor_ledger_cannot_be_edited(db_session, statement):
    actor = make_user(db_session, "hr")
    db_session.flush()
    _log_some(db_session, actor, 2)
    record_full_verification(db_session)
    check_id = latest_anchor(db_session).id

    with pytest.raises((InternalError, ProgrammingError), match="append-only"):
        db_session.execute(text(statement), {"id": check_id})


# ── جارو ────────────────────────────────────────────────────────────────────


def test_the_sweep_does_not_verify_again_within_the_interval(db_session):
    """بررسیِ کامل گران است و زمان‌بند هر پنج دقیقه اجرا می‌شود."""
    actor = make_user(db_session, "hr")
    db_session.flush()
    _log_some(db_session, actor, 2)

    assert run_audit_anchor_sweep(db_session) == 1
    _log_some(db_session, actor, 2)
    assert run_audit_anchor_sweep(db_session) == 0
    assert db_session.scalar(select(AuditChainCheck.id).order_by(AuditChainCheck.id.desc())) is not None
    assert len(list(db_session.scalars(select(AuditChainCheck)))) == 1


def test_the_sweep_runs_again_once_the_interval_has_passed(db_session):
    actor = make_user(db_session, "hr")
    db_session.flush()
    _log_some(db_session, actor, 2)
    run_audit_anchor_sweep(db_session)

    stale = db_session.scalar(select(AuditChainCheck).order_by(AuditChainCheck.id.desc()).limit(1))
    db_session.execute(
        text("ALTER TABLE audit_chain_checks DISABLE TRIGGER trg_audit_chain_checks_append_only")
    )
    db_session.execute(
        text("UPDATE audit_chain_checks SET verified_at = :at WHERE id = :id"),
        {"at": datetime.now(UTC) - timedelta(days=3), "id": stale.id},
    )
    db_session.execute(
        text("ALTER TABLE audit_chain_checks ENABLE TRIGGER trg_audit_chain_checks_append_only")
    )
    db_session.expire_all()

    _log_some(db_session, actor, 2)
    assert run_audit_anchor_sweep(db_session) == 1


def test_a_broken_chain_reaches_a_human(db_session):
    """کشفی که به کسی نرسد، کشف نیست.

    از این پس بررسیِ تعاملی فقط پس از لنگر را می‌بیند، پس دست‌کاریِ پیش از لنگر
    در رابط دیده نمی‌شود. اگر جارو هم سکوت کند، این تغییر وضع را *بدتر* کرده
    است، نه بهتر.
    """
    watcher = make_user(db_session, "hr", capabilities=[Capability.view_audit_log])
    db_session.flush()
    _log_some(db_session, watcher, 3)
    _tamper(db_session, _head(db_session).id, event_type="rewritten")

    assert run_audit_anchor_sweep(db_session) == 0

    alerts = list(
        db_session.scalars(
            select(Notification).where(
                Notification.user_id == watcher.id,
                Notification.type == "audit_chain_broken",
            )
        )
    )
    assert len(alerts) == 1
    assert "شکست خورد" in alerts[0].message


# ── endpoint ────────────────────────────────────────────────────────────────


def test_the_endpoint_is_anchored_by_default_and_full_on_request(client, db_session):
    hr = make_user(db_session, "hr", capabilities=[Capability.view_audit_log])
    db_session.flush()
    _log_some(db_session, hr, 3)
    record_full_verification(db_session)
    _log_some(db_session, hr, 2)
    db_session.commit()

    fast = client.get("/api/audit-log/integrity", headers=auth_header(hr)).json()
    assert fast["ok"] is True
    assert fast["full"] is False
    assert fast["anchor_verified_at"] is not None

    whole = client.get("/api/audit-log/integrity?full=true", headers=auth_header(hr)).json()
    assert whole["ok"] is True
    assert whole["full"] is True
    assert whole["checked"] > fast["checked"]
