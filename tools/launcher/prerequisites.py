"""چیزهایی که نبودنشان برنامه را زمین نمی‌زند، ولی یک قابلیت را خاموش می‌کند.

اینها با پیش‌نیازهای `steps.py` فرق دارند: آن‌ها اجرا را متوقف می‌کنند، اینها
فقط بخشی از کار را بی‌صدا از دسترس خارج می‌کنند — و «بی‌صدا» همان مشکل است.
خروجی PDF نمونهٔ دقیقش است: بسته در `requirements.txt` هست و pip نصبش می‌کند،
ولی روی ویندوز `import weasyprint` بدونِ کتابخانه‌های بومیِ GTK می‌ترکد. برنامه
بالا می‌آید، همه‌چیز سالم به‌نظر می‌رسد، و فقط وقتی کسی «دریافت PDF» را می‌زند
معلوم می‌شود چیزی کم است.

دو حالتِ شکست عمداً از هم جدا نگه داشته می‌شوند چون راه‌حلشان یکی نیست:
نبودنِ بسته با یک `pip install` حل می‌شود، نبودنِ کتابخانهٔ بومی با نصبِ GTK.
پیامِ درهم، کاربر را ساعت‌ها دنبال `pip install` می‌فرستد برای چیزی که pip
اصلاً درستش نمی‌کند.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .database import MISSING_TOOLS, find_tool
from .ports import NO_WINDOW

WEASYPRINT_DOCS = "https://doc.courtbouillon.org/weasyprint/stable/first_steps.html"
GTK_INSTALLER = "https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases"


@dataclass(frozen=True)
class Fix:
    """کاری که می‌شود برایش کرد — یا خودمان، یا با راهنمایی."""

    label: str
    body: str = ""
    #: بسته‌ای که راه‌انداز می‌تواند خودش با pip نصب کند. خالی یعنی دستی است.
    package: str = ""
    url: str = ""


@dataclass(frozen=True)
class Feature:
    key: str
    title: str
    available: bool
    detail: str = ""
    fix: Fix | None = None


@dataclass
class Report:
    features: list[Feature] = field(default_factory=list)

    @property
    def missing(self) -> list[Feature]:
        return [feature for feature in self.features if not feature.available]


def _probe_import(interpreter: Path, module: str) -> tuple[bool, str]:
    """آیا این ماژول در venv وارد می‌شود؟ اگر نه، با چه پیامی؟

    خودِ پیام مهم است و نه فقط موفق/ناموفق — تشخیصِ «بسته نیست» از «کتابخانهٔ
    بومی نیست» تنها از روی همان ممکن است.
    """
    try:
        done = subprocess.run(
            [str(interpreter), "-c", f"import {module}"],
            capture_output=True, text=True, timeout=60, errors="replace", **NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    if done.returncode == 0:
        return True, ""
    return False, (done.stderr or done.stdout or "").strip()


def classify_pdf_failure(error: str) -> Fix:
    """از متنِ خطا به راهِ حل.

    جدا از فراخوانی نگه داشته شده تا بشود بدونِ ویندوز و بدونِ venv سنجیدش —
    و چون همین دسته‌بندی است که تعیین می‌کند کاربر کدام ساعت را هدر می‌دهد.
    """
    lowered = error.lower()
    if "no module named" in lowered:
        return Fix(
            "Install the PDF package",
            "The weasyprint package is missing from the virtual environment. This one the "
            "launcher can fix by itself.",
            package="weasyprint",
        )
    native = ("libgobject", "libpango", "libcairo", "libgtk", "cannot load library", "oserror", "dll load failed")
    if any(marker in lowered for marker in native):
        return Fix(
            "How to enable PDF export",
            "The Python package is installed, but the native GTK libraries it draws with are "
            "not — this is the usual state on a fresh Windows machine, and pip cannot fix it. "
            "Install the GTK3 runtime, then close this window and start NexaHR again. "
            "Everything else keeps working meanwhile; only PDF export is off.",
            url=GTK_INSTALLER,
        )
    return Fix(
        "How to enable PDF export",
        "weasyprint did not import. The exact error is in the log; the setup steps for this "
        "platform are on the WeasyPrint site.",
        url=WEASYPRINT_DOCS,
    )


def inspect(interpreter: Path) -> Report:
    features: list[Feature] = []

    ok, error = _probe_import(interpreter, "weasyprint")
    features.append(
        Feature(
            key="pdf",
            title="PDF export",
            available=ok,
            detail="" if ok else error.splitlines()[-1] if error else "weasyprint did not import",
            fix=None if ok else classify_pdf_failure(error),
        )
    )

    dump = find_tool("pg_dump")
    features.append(
        Feature(
            key="pg_tools",
            title="Database backup",
            available=bool(dump),
            detail=dump or "pg_dump not found",
            fix=None if dump else Fix("Where to get pg_dump", MISSING_TOOLS),
        )
    )

    return Report(features=features)
