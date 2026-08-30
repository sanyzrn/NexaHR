"""تست‌های قابلیت‌های اختیاری، حسابِ مدیر، و خواندنِ خروجیِ اسکریپت‌ها."""
from __future__ import annotations

import pytest

from tools.launcher import admin, prerequisites
from tools.launcher.shell import find_json

# ── دسته‌بندیِ خطای PDF ─────────────────────────────────────────────────
#
# این تنها جایی است که تعیین می‌کند کاربر کدام ساعت را هدر می‌دهد. «بسته نیست»
# با یک `pip install` حل می‌شود؛ «کتابخانهٔ بومی نیست» با pip *اصلاً* حل
# نمی‌شود. پیامِ درهم یعنی کسی نیم‌روز pip می‌زند برای چیزی که pip درستش
# نمی‌کند.

def test_a_missing_package_is_something_the_launcher_can_fix_itself():
    fix = prerequisites.classify_pdf_failure(
        "Traceback (most recent call last):\nModuleNotFoundError: No module named 'weasyprint'"
    )
    assert fix.package == "weasyprint"
    assert not fix.url


@pytest.mark.parametrize(
    "error",
    [
        "OSError: cannot load library 'libgobject-2.0-0': error 0x7e",
        "OSError: cannot load library 'libpango-1.0-0.dll'",
        "ImportError: DLL load failed while importing _ffi",
    ],
)
def test_a_missing_native_library_is_never_offered_as_a_pip_install(error):
    fix = prerequisites.classify_pdf_failure(error)
    assert not fix.package
    assert fix.url
    assert "GTK" in fix.body


def test_an_unrecognised_error_still_points_somewhere_useful():
    fix = prerequisites.classify_pdf_failure("weasyprint exploded for reasons unknown")
    assert not fix.package
    assert fix.url.startswith("https://")


# ── اعتبارسنجیِ حسابِ مدیر ──────────────────────────────────────────────

def test_a_valid_admin_form_passes():
    assert admin.validate("admin", "System administrator", "a-long-enough-pw", "a-long-enough-pw") == ""


@pytest.mark.parametrize(
    "username, full_name, password, confirm, expected",
    [
        ("", "Name", "a-long-enough-pw", "a-long-enough-pw", "username"),
        ("two words", "Name", "a-long-enough-pw", "a-long-enough-pw", "spaces"),
        ("admin", "", "a-long-enough-pw", "a-long-enough-pw", "display name"),
        ("admin", "Name", "short", "short", "10 characters"),
        ("admin", "Name", "a-long-enough-pw", "something-else", "do not match"),
    ],
)
def test_the_form_is_checked_before_anything_is_launched(username, full_name, password, confirm, expected):
    # پیش از زدنِ اسکریپت سنجیده می‌شود، وگرنه کاربر برای یک رمزِ کوتاه منتظرِ
    # بالا آمدنِ کلِ برنامه می‌ماند و بعد یک `SystemExit` می‌گیرد.
    problem = admin.validate(username, full_name, password, confirm)
    assert expected in problem


def test_the_minimum_password_length_matches_what_the_backend_enforces():
    # اگر این دو از هم دور بیفتند، راه‌انداز رمزی را قبول می‌کند که اسکریپت
    # بعداً ردش می‌کند — و پیامِ خطا جای دیگری ظاهر می‌شود.
    source = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "backend" / "scripts" / "create_admin.py"
    ).read_text(encoding="utf-8")
    assert f"PASSWORD_MIN_LENGTH = {admin.PASSWORD_MIN_LENGTH}" in source


# ── خلاصهٔ وضعیتِ مدیر ─────────────────────────────────────────────────

def test_no_admin_yet_is_said_plainly():
    assert admin.Status().summary == "none yet"


def test_a_handful_of_admins_are_listed_and_the_rest_counted():
    status = admin.Status(admins=[{"username": name} for name in ("a", "b", "c", "d", "e")])
    assert status.summary == "a, b, c +2"


def test_a_probe_that_failed_does_not_pretend_there_are_none():
    # «هیچ مدیری نیست» و «نتوانستیم بپرسیم» دو چیزند: اولی دعوت به ساختن است،
    # دومی نشانهٔ خرابیِ دیگری.
    assert admin.Status(error="connection refused").summary == "could not be read"


# ── خواندنِ JSON از خروجیِ پرحرف ────────────────────────────────────────

def test_json_is_found_even_when_the_script_printed_other_things_first():
    # اسکریپت‌های بک‌اند ممکن است هشدارِ SQLAlchemy یا خطِ لاگ چاپ کنند.
    noisy = 'warning: something\nINFO started\n{"has_active_admin": true}\n'
    assert find_json(noisy) == {"has_active_admin": True}


def test_the_last_object_wins_when_there_is_more_than_one():
    assert find_json('{"round": 1}\n{"round": 2}\n') == {"round": 2}


def test_output_with_no_json_at_all_is_an_empty_answer_not_a_crash():
    assert find_json("Traceback (most recent call last):\n  ValueError\n") == {}
    assert find_json("") == {}
