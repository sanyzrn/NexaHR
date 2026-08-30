"""اجرای یک دستور با خروجیِ خط‌به‌خط.

`subprocess.run` برای چیزی مثل `pip install` مناسب نیست: چند دقیقه طول می‌کشد و
تا لحظهٔ آخر هیچ خروجی‌ای نمی‌دهد، پس رابط کاربری در همان مدت به‌نظر هنگ‌کرده
می‌آید. این‌جا خروجی همان‌طور که تولید می‌شود به فراخوان تحویل داده می‌شود.

stderr عمداً با stdout ادغام می‌شود. دو جریانِ جدا یعنی خطاها در پنلِ گزارش
جای دیگری می‌افتند و ترتیبِ واقعیِ رخدادها گم می‌شود — و همان ترتیب است که
می‌گوید کدام خط باعثِ کدام خطا شد.
"""
from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .ports import NO_WINDOW

Log = Callable[[str], None]


@dataclass
class Result:
    """نتیجهٔ یک کارِ تک‌مرحله‌ای که کاربر خودش شروعش کرده.

    یک نوعِ مشترک برای همهٔ کارهای نگهداری (پشتیبان، بازگردانی، ساختِ حساب،
    نصبِ بسته) تا رابط کاربری برای هرکدام مسیرِ جداگانه نداشته باشد. `path` فقط
    وقتی پر می‌شود که کار فایلی ساخته باشد.
    """

    ok: bool
    message: str
    path: Path | None = None


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


def find_json(text: str) -> dict:
    """آخرین شیءِ JSON در خروجی.

    اسکریپت‌هایی که JSON می‌دهند ممکن است پیش از آن چیزِ دیگری هم چاپ کنند —
    هشدارِ SQLAlchemy، خطِ لاگِ آغازِ برنامه. گرفتنِ کلِ خروجی به‌عنوان JSON
    آن‌جا می‌شکند، پس دنبالِ آخرین سطری می‌گردیم که خودش یک شیء کامل باشد.
    """
    for line in reversed((text or "").splitlines()):
        stripped = line.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    return {}


def json_probe(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 90.0,
) -> dict:
    """اسکریپتی را اجرا کن که وضعیت را به‌صورت JSON چاپ می‌کند.

    شکستِ اجرا هم یک *جواب* است و به همان شکل برمی‌گردد (`error`)، تا فراخوان
    مجبور نباشد دو مسیرِ خطای جدا داشته باشد.
    """
    try:
        done = subprocess.run(
            list(argv), cwd=str(cwd) if cwd else None, env=env,
            capture_output=True, text=True, timeout=timeout, errors="replace", **NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"error": str(exc)}
    report = find_json(done.stdout)
    if report:
        return report
    return {"error": (done.stderr or done.stdout or "no output").strip()[-800:]}
