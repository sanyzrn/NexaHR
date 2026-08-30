"""تست‌های سیم‌کشیِ نهایی: آنچه به هر سرور گفته می‌شود.

این‌جا همان جایی است که «پورت ۸۰۰۰ اجباری نیست» یا واقعاً درست است، یا فقط یک
ادعای داخلِ کامنت. اگر پورت جابه‌جا شود و فرانت‌اند خبردار نشود، نتیجه‌اش بدتر
از قبل است: همه‌چیز سبز گزارش می‌شود و هیچ درخواستی به مقصد نمی‌رسد.
"""
from __future__ import annotations

import pytest

from tools.launcher.session import Session


@pytest.fixture
def session() -> Session:
    made = Session(log=lambda source, line: None)
    made.ctx.backend_port = 8003
    made.ctx.frontend_port = 5177
    return made


def spec(session: Session, name: str):
    return next(item for item in session._specs() if item.name == name)


def test_the_frontend_is_told_where_the_backend_actually_landed(session):
    # تنها چیزی که پورتِ بک‌اند را قفل کرده بود، مقصدِ ثابتِ پروکسی در
    # `vite.config.ts` بود. حالا از همین متغیر خوانده می‌شود.
    assert spec(session, "frontend").env["NEXAHR_BACKEND_URL"] == "http://127.0.0.1:8003"


def test_the_backend_binds_the_port_that_was_chosen(session):
    argv = list(spec(session, "backend").argv)
    assert argv[argv.index("--port") + 1] == "8003"


def test_the_web_server_is_pinned_to_its_port_rather_than_drifting(session):
    # بدونِ `--strictPort`، اگر پورت گرفته باشد Vite بی‌صدا می‌رود روی پورتِ
    # بعدی. آن‌وقت آدرسی که راه‌انداز نشان می‌دهد به جایی می‌رود که کسی آن‌جا
    # نیست — و این دقیقاً همان گیج‌شدنی است که قرار بود از بین برود.
    argv = list(spec(session, "frontend").argv)
    assert "--strictPort" in argv
    assert argv[argv.index("--port") + 1] == "5177"


def test_the_backend_is_reachable_from_the_network_but_the_link_is_local(session):
    assert "0.0.0.0" in spec(session, "backend").argv
    assert "--host" in spec(session, "frontend").argv


def test_addresses_the_backend_builds_use_the_real_frontend_port(session):
    # `PUBLIC_BASE_URL` داخلِ QRِ کارنامه می‌نشیند. اگر روی ۵۱۷۳ ثابت بماند و
    # فرانت‌اند جای دیگری بالا آمده باشد، سندی تولید می‌شود که لینکِ تأییدش
    # هیچ‌وقت باز نمی‌شود.
    assert spec(session, "backend").env["PUBLIC_BASE_URL"] == "http://localhost:5177"


def test_cors_covers_wherever_the_frontend_ended_up(session):
    origins = spec(session, "backend").env["CORS_ORIGINS"]
    assert "http://localhost:5177" in origins
    assert "http://127.0.0.1:5177" in origins


def test_both_servers_run_with_utf8_forced(session):
    # همان تنظیمی که بدونش یک کامنتِ فارسی در `backend/.env` بک‌اند را پیش از
    # bind کردنِ پورت می‌کشد.
    for name in ("backend", "frontend"):
        assert spec(session, name).env["PYTHONUTF8"] == "1"


def test_output_is_unbuffered_so_the_log_panel_is_not_empty_for_minutes(session):
    assert spec(session, "backend").env["PYTHONUNBUFFERED"] == "1"


def test_the_backend_is_only_called_ready_when_the_api_answers(session):
    # `/` روی بک‌اند هم جواب می‌دهد. اگر معیارِ آمادگی آن بود، سروری که
    # روت‌هایش را بالا نیاورده «سالم» شمرده می‌شد.
    assert spec(session, "backend").ready_path == "/api/health"


def test_the_servers_start_from_their_own_folders(session):
    assert spec(session, "backend").cwd.name == "backend"
    assert spec(session, "frontend").cwd.name == "frontend"
