"""«با ویندوز بالا بیا» — یک میان‌بر در پوشهٔ Startup.

چرا میان‌بر و نه یک ورودیِ رجیستری
----------------------------------
هر دو کار می‌کنند، ولی میان‌بر را کاربر می‌بیند و می‌تواند خودش پاکش کند
(`shell:startup` در Run). یک کلید در `HKCU\\...\\Run` نامرئی است و برنامه‌ای که
بی‌اجازه در آن می‌نشیند، درست همان‌طور رفتار می‌کند که بدافزار.

چرا `.lnk` و نه `.bat`
----------------------
فایلِ دسته‌ای در Startup یک پنجرهٔ کنسول باز می‌کند — دقیقاً همان چیزی که این
راه‌انداز آمده که از بین ببرد، و بدتر: در هر بوت. میان‌بر مستقیم به
`pythonw.exe` اشاره می‌کند و هیچ کنسولی نمی‌سازد.

ساختِ `.lnk` از پایتون بدونِ `pywin32` ممکن نیست، ولی PowerShell همان COM را
دارد و روی هر ویندوزی هست. روی لینوکس و مک این ماژول فقط «پشتیبانی نمی‌شود»
می‌گوید؛ آن‌جا سرویسِ کاربر (systemd/launchd) راهِ درست است و ساختنش بدونِ
درخواستِ صریح، دخالت است.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .ports import NO_WINDOW, WINDOWS

SHORTCUT_NAME = "NexaHR.lnk"


def supported() -> bool:
    return WINDOWS


def startup_folder() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not WINDOWS or not appdata:
        return None
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def shortcut_path() -> Path | None:
    folder = startup_folder()
    return folder / SHORTCUT_NAME if folder else None


def enabled() -> bool:
    path = shortcut_path()
    return bool(path and path.exists())


def _powershell(script: str) -> bool:
    try:
        done = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=30, errors="replace", **NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def enable(interpreter: Path, launcher: Path) -> bool:
    """میان‌بر را بساز. `interpreter` باید `pythonw.exe` باشد، وگرنه کنسول می‌آید."""
    path = shortcut_path()
    if path is None:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    # نقلِ قولِ تکی در PowerShell با دوبرابر کردنِ خودش escape می‌شود. مسیرها
    # می‌توانند فاصله داشته باشند (`Program Files`)، پس نقلِ قول اجباری است.
    def quoted(value: str) -> str:
        return "'" + str(value).replace("'", "''") + "'"

    script = (
        "$s = (New-Object -COM WScript.Shell).CreateShortcut(" + quoted(path) + ");"
        "$s.TargetPath = " + quoted(interpreter) + ";"
        "$s.Arguments = " + quoted(f'"{launcher}"') + ";"
        "$s.WorkingDirectory = " + quoted(launcher.parent.parent) + ";"
        "$s.Description = 'Start NexaHR for local development';"
        "$s.Save()"
    )
    return _powershell(script) and path.exists()


def disable() -> bool:
    path = shortcut_path()
    if path is None:
        return False
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return False
    return not path.exists()


def describe() -> str:
    """چرا این گزینه در دسترس نیست — برای وقتی که نیست."""
    if not WINDOWS:
        return "Only available on Windows."
    if startup_folder() is None:
        return "The Windows Startup folder could not be located (APPDATA is not set)."
    return ""
