"""حسابِ مدیر سامانه: هست یا نه، و اگر نیست، ساختنش.

نکته‌ای که این ماژول برایش هست
------------------------------
سرویس در هر بالا آمدن خودش یک مدیر می‌سازد اگر هیچ مدیری نباشد
(`services/bootstrap_admin.py`). ولی رمزِ آن حساب یک رشتهٔ تصادفی است که فقط
**یک بار** در لاگ نوشته می‌شود — و تا امروز آن لاگ در پنجرهٔ cmd ی بود که کاربر
کمینه‌اش کرده بود. نتیجه: حسابی وجود داشت که رمزش را کسی نمی‌دانست، و از بیرون
این دقیقاً شبیهِ «هیچ حسابی نیست» بود.

پس دو چیز لازم است: دیدنِ این‌که چه حسابی هست، و ساختنِ یکی با رمزی که خودِ
کاربر انتخاب می‌کند. رمز از راهِ محیط به اسکریپت می‌رود و نه آرگومان، چون
آرگومان‌ها در فهرستِ پروسه‌ها دیده می‌شوند — همان قاعده‌ای که `create_admin.py`
خودش هم رعایتش می‌کند.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .environment import child_environment
from .shell import Result, json_probe, stream

#: همان حداقلی که `scripts/create_admin.py` و فرمِ کاربر اعمال می‌کنند.
PASSWORD_MIN_LENGTH = 10


@dataclass
class Status:
    admins: list[dict] = field(default_factory=list)
    has_active_admin: bool = False
    any_user: bool = False
    error: str = ""

    @property
    def summary(self) -> str:
        if self.error:
            return "could not be read"
        if not self.admins:
            return "none yet"
        names = ", ".join(entry.get("username", "?") for entry in self.admins[:3])
        more = f" +{len(self.admins) - 3}" if len(self.admins) > 3 else ""
        return f"{names}{more}"


def status(interpreter: Path, backend: Path) -> Status:
    report = json_probe([str(interpreter), "-m", "scripts.admin_status"], cwd=backend, env=child_environment())
    return Status(
        admins=list(report.get("admins") or []),
        has_active_admin=bool(report.get("has_active_admin")),
        any_user=bool(report.get("any_user")),
        error=str(report.get("error") or ""),
    )


def validate(username: str, full_name: str, password: str, confirmation: str) -> str:
    """پیامِ خطا، یا رشتهٔ خالی اگر همه‌چیز درست است.

    پیش از زدنِ اسکریپت سنجیده می‌شود تا کاربر برای یک رمزِ کوتاه، منتظرِ بالا
    آمدنِ کلِ برنامه و بعد یک `SystemExit` نماند.
    """
    if not username.strip():
        return "A username is required."
    if any(character.isspace() for character in username.strip()):
        return "The username cannot contain spaces."
    if not full_name.strip():
        return "A display name is required — it is what other people see."
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"The password must be at least {PASSWORD_MIN_LENGTH} characters."
    if password != confirmation:
        return "The two passwords do not match."
    return ""


def create(
    interpreter: Path,
    backend: Path,
    *,
    username: str,
    full_name: str,
    password: str,
    log: Callable[[str], None],
) -> Result:
    code = stream(
        [str(interpreter), "-m", "scripts.create_admin",
         "--username", username.strip(), "--full-name", full_name.strip()],
        cwd=backend,
        # رمز از راهِ محیط، نه خطِ فرمان.
        env=child_environment({"NEXAHR_ADMIN_PASSWORD": password}),
        log=log,
    )
    if code != 0:
        return Result(False, "The account was not created — the log has the reason.")
    return Result(True, f"Created “{username.strip()}” with every administrative capability.")
