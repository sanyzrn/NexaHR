"""چیزی که `setup_and_run.bat` اجرا می‌کند.

پسوندِ `.pyw` یعنی ویندوز آن را با `pythonw.exe` باز می‌کند و هیچ پنجرهٔ کنسولی
نمی‌سازد — همان چیزی که کلِ این کار برایش انجام شده.

ولی «بدونِ کنسول» یک خطر دارد: اگر راه‌انداز پیش از ساختنِ پنجره بمیرد، کاربر
مطلقاً هیچ چیزی نمی‌بیند — نه پنجره‌ای، نه خطایی. پس هر استثنایی این‌جا گرفته
می‌شود، در فایل نوشته می‌شود، و با یک MessageBox ویندوزی (بدونِ نیاز به Tk، که
شاید خودش علتِ خرابی بوده) گزارش می‌شود.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _report(error: BaseException) -> None:
    report = ROOT / "launcher-error.log"
    text = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    try:
        report.write_text(text, encoding="utf-8")
    except OSError:
        pass
    message = (
        "NexaHR's launcher could not start.\n\n"
        f"{type(error).__name__}: {error}\n\n"
        f"The full details are in:\n{report}\n\n"
        "Running setup_and_run.bat --console shows the same run in a terminal."
    )
    if sys.platform.startswith("win"):
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "NexaHR", 0x10)
    else:
        print(message, file=sys.stderr)


def main() -> int:
    try:
        from tools.launcher.__main__ import main as launcher_main

        return launcher_main(sys.argv[1:])
    except SystemExit:
        raise
    except BaseException as error:  # noqa: BLE001 - آخرین توری که هست
        _report(error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
