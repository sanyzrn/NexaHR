"""تست‌های مرحله‌های آماده‌سازی و تشخیصِ ابزارها."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.launcher import steps
from tools.launcher.environment import Paths, Tool, node_version_ok, parse_version


def make_context(tmp_path: Path) -> steps.Context:
    paths = Paths(
        root=tmp_path,
        backend=tmp_path / "backend",
        frontend=tmp_path / "frontend",
        venv=tmp_path / "backend" / ".venv",
    )
    paths.backend.mkdir(parents=True)
    paths.frontend.mkdir(parents=True)
    return steps.Context(paths=paths, log=lambda source, line: None)


# ── نسخه‌ها ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "text, expected",
    [("v20.19.4", (20, 19, 4)), ("3.11.9", (3, 11, 9)), ("v22.12.0", (22, 12, 0)), ("", ())],
)
def test_version_strings_are_parsed_the_same_way_whatever_the_tool(text, expected):
    assert parse_version(text) == expected


@pytest.mark.parametrize(
    "version, ok",
    [
        ((20, 18), False),   # LTS قدیمی: npm install موفق می‌شود، npm run dev نه
        ((20, 19), True),
        ((21, 7), False),    # ۲۱ اصلاً در بازهٔ Vite 8 نیست
        ((22, 11), False),
        ((22, 12), True),
        ((24, 0), True),
        ((18, 20), False),
    ],
)
def test_the_node_rule_is_the_one_vite_actually_enforces(version, ok):
    # شرطِ Vite 8 «^20.19 || >=22.12» است، نه «>= 20». نسخهٔ ساده‌شده ۲۱ و ۲۲های
    # اولیه را قبول می‌کرد و خرابی تازه موقعِ `npm run dev` پیدا می‌شد.
    assert node_version_ok(version) is ok


# ── فایل تنظیمات ───────────────────────────────────────────────────────

def test_the_generated_env_file_is_pure_ascii(tmp_path):
    """کامنتِ فارسی در `backend/.env` بک‌اند را پیش از bind کردنِ پورت می‌کشد.

    starlette فایل را با انکودینگِ پیش‌فرضِ سیستم می‌خواند — روی ویندوزِ فارسی
    cp1252 — و یک بایتِ غیرِ ASCII یعنی UnicodeDecodeError موقعِ import. برای
    همین این فایل این‌جا نوشته می‌شود و از `.env.example`ِ فارسی کپی نمی‌شود.
    """
    ctx = make_context(tmp_path)
    assert steps.ensure_settings(ctx).ok
    assert all(byte < 128 for byte in ctx.paths.env_file.read_bytes())


def test_an_existing_env_file_is_never_overwritten(tmp_path):
    ctx = make_context(tmp_path)
    ctx.paths.env_file.write_text("DATABASE_URL=postgresql+psycopg://me:secret@db:6543/mine\n")
    assert steps.ensure_settings(ctx).ok
    assert "6543" in ctx.paths.env_file.read_text()


def test_a_non_ascii_env_file_is_reported_but_not_touched(tmp_path):
    ctx = make_context(tmp_path)
    ctx.paths.env_file.write_text("# توضیح فارسی\nENVIRONMENT=development\n", encoding="utf-8")
    assert steps.ensure_settings(ctx).ok
    assert any("non-ASCII" in note for note in ctx.notes)
    assert "توضیح" in ctx.paths.env_file.read_text(encoding="utf-8")


# ── نقطهٔ اتصالِ دیتابیس ────────────────────────────────────────────────

@pytest.mark.parametrize(
    "url, expected",
    [
        ("DATABASE_URL=postgresql+psycopg://nexahr:pw@localhost:5432/nexahr", ("localhost", 5432)),
        ("DATABASE_URL=postgresql+psycopg://nexahr:pw@db.internal:6543/nexahr", ("db.internal", 6543)),
        # بدونِ پورت، پیش‌فرضِ خودِ پستگرس.
        ("DATABASE_URL=postgresql+psycopg://nexahr:pw@localhost/nexahr", ("localhost", 5432)),
        # فایلِ بی‌ربط: نباید بترکد، فقط پیش‌فرض بدهد.
        ("ENVIRONMENT=development", ("localhost", 5432)),
    ],
)
def test_the_database_host_comes_from_the_settings_file(url, expected):
    # عدد ۵۴۳۲ ثابت نوشته نمی‌شد وگرنه کسی که پستگرسش روی پورتِ دیگری است، پیامِ
    # «چیزی روی ۵۴۳۲ گوش نمی‌دهد» را می‌گرفت که دربارهٔ سرورِ او صادق نیست.
    assert steps.database_endpoint(url) == expected


def test_a_password_containing_an_at_sign_does_not_confuse_the_host(tmp_path):
    url = "DATABASE_URL=postgresql+psycopg://nexahr:p@ss@localhost:5432/nexahr"
    assert steps.database_endpoint(url) == ("localhost", 5432)


# ── چکِ ابزارها ────────────────────────────────────────────────────────

def test_an_old_python_stops_the_run_with_an_explanation(tmp_path):
    ctx = make_context(tmp_path)
    ctx.python = Tool(ok=False, version=(3, 10), text="3.10")
    outcome = steps.check_toolchain(ctx)
    assert not outcome.ok
    assert outcome.remedy and "3.11" in outcome.remedy.title
    assert "datetime.UTC" in outcome.remedy.body


def test_a_missing_node_says_where_to_get_it(tmp_path):
    ctx = make_context(tmp_path)
    ctx.python = Tool(ok=True, version=(3, 12), text="3.12")
    ctx.node = Tool(ok=False)
    outcome = steps.check_toolchain(ctx)
    assert not outcome.ok
    assert outcome.remedy and outcome.remedy.url == "https://nodejs.org"


def test_every_failure_carries_something_the_user_can_act_on(tmp_path):
    """قاعدهٔ دومِ راه‌اندازِ قدیمی: هیچ توقفی بدونِ «حالا چه کار کنم» نباشد.

    نسخهٔ قبلی این را با `:fail` تضمین می‌کرد که دو آرگومان می‌گرفت. این‌جا
    معادلش این است که هر `Outcome`ِ ناموفق یک `Remedy` داشته باشد.
    """
    ctx = make_context(tmp_path)
    ctx.python = Tool(ok=False, version=(3, 9), text="3.9")
    failures = [steps.check_toolchain(ctx)]

    ctx.python = Tool(ok=True, version=(3, 12), text="3.12")
    ctx.node = Tool(ok=False)
    failures.append(steps.check_toolchain(ctx))

    for outcome in failures:
        assert not outcome.ok
        assert outcome.remedy is not None
        assert outcome.remedy.title
        assert outcome.remedy.body or outcome.remedy.commands or outcome.remedy.url
