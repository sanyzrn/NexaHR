"""اجرای یک دستور با خروجیِ خط‌به‌خط.

`subprocess.run` برای چیزی مثل `pip install` مناسب نیست: چند دقیقه طول می‌کشد و
تا لحظهٔ آخر هیچ خروجی‌ای نمی‌دهد، پس رابط کاربری در همان مدت به‌نظر هنگ‌کرده
می‌آید. این‌جا خروجی همان‌طور که تولید می‌شود به فراخوان تحویل داده می‌شود.

stderr عمداً با stdout ادغام می‌شود. دو جریانِ جدا یعنی خطاها در پنلِ گزارش
جای دیگری می‌افتند و ترتیبِ واقعیِ رخدادها گم می‌شود — و همان ترتیب است که
می‌گوید کدام خط باعثِ کدام خطا شد.
"""
from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from .ports import NO_WINDOW

Log = Callable[[str], None]


def stream(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    log: Log | None = None,
    timeout: float | None = None,
) -> int:
    """دستور را اجرا کن، هر خطش را به `log` بده، و کدِ خروج را برگردان.

    کدِ خروجِ ۱۲۷ یعنی خودِ دستور پیدا نشد — روی ویندوز این حالت به‌جای
    `FileNotFoundError` باید مثل یک شکستِ عادی دیده شود تا پیامِ راهنما را از
    دست ندهیم.
    """
    try:
        proc = subprocess.Popen(
            list(argv),
            cwd=str(cwd) if cwd else None,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            errors="replace",
            **NO_WINDOW,
        )
    except OSError as exc:
        if log:
            log(f"could not run {argv[0]}: {exc}")
        return 127

    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            if log:
                log(line.rstrip("\r\n"))
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        if log:
            log(f"{argv[0]} timed out")
        return 124
    finally:
        proc.stdout.close()


def quiet(argv: Sequence[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> int:
    """فقط کدِ خروج مهم است — خروجی دور ریخته می‌شود."""
    return stream(argv, cwd=cwd, env=env, log=None)
