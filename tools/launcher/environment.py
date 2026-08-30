"""جای فایل‌ها، و این‌که ابزارهای لازم واقعاً کار می‌کنند یا نه.

قاعدهٔ همیشگیِ این پروژه این‌جا هم برقرار است: چک‌ها می‌سنجند که چیزی **کار
می‌کند**، نه این‌که **هست**. روی ویندوز ۱۱ تازه‌نصب، `python` معمولاً یک
میان‌برِ فروشگاه مایکروسافت است؛ `where python` پیدایش می‌کند، اجرا که بشود
فروشگاه باز می‌شود و چیزی چاپ نمی‌کند. پس تنها سنجهٔ درست، اجرا کردن و خواندنِ
نسخه از خروجی است.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .ports import NO_WINDOW, WINDOWS

# پایتون ۳٫۱۱: کدِ برنامه `datetime.UTC` را import می‌کند که از همان نسخه اضافه شد.
MIN_PYTHON = (3, 11)
# Vite 8 روی ^20.19 || >=22.12 بالا می‌آید. روی ۲۰٫۹ یا ۱۸، `npm install` موفق
# می‌شود و فقط `npm run dev` می‌میرد — که تقصیر را به گردنِ فرانت‌اند می‌اندازد.
MIN_NODE = (20, 19)


@dataclass(frozen=True)
class Paths:
    root: Path
    backend: Path
    frontend: Path
    venv: Path

    @property
    def venv_python(self) -> Path:
        return self.venv / ("Scripts/python.exe" if WINDOWS else "bin/python")

    @property
    def env_file(self) -> Path:
        return self.backend / ".env"

    @property
    def requirements(self) -> Path:
        return self.backend / "requirements.txt"

    @property
    def deps_marker(self) -> Path:
        return self.venv / ".deps_installed"

    @property
    def node_modules(self) -> Path:
        return self.frontend / "node_modules"


def locate(start: Path | None = None) -> Paths:
    """ریشهٔ مخزن را از محلِ همین فایل پیدا کن.

    از `cwd` استفاده نمی‌شود: راه‌انداز ممکن است با دابل‌کلیک از هر جایی اجرا شود
    و آن‌وقت مسیرِ نسبی به جای دیگری اشاره می‌کند.
    """
    root = (start or Path(__file__).resolve().parent.parent.parent)
    return Paths(root=root, backend=root / "backend", frontend=root / "frontend", venv=root / "backend" / ".venv")


@dataclass(frozen=True)
class Tool:
    ok: bool
    version: tuple[int, ...] = ()
    text: str = ""
    path: str = ""

    @property
    def pretty(self) -> str:
        return self.text or ".".join(str(part) for part in self.version) or "not found"


def _probe_version(argv: list[str]) -> str:
    try:
        done = subprocess.run(
            argv, capture_output=True, text=True, timeout=25, errors="replace", **NO_WINDOW
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return (done.stdout or "").strip() if done.returncode == 0 else ""


def parse_version(text: str) -> tuple[int, ...]:
    """«v20.19.4» و «3.11.9» هر دو باید به یک شکل درآیند."""
    digits = text.strip().lstrip("vV").split()[0] if text.strip() else ""
    parts: list[int] = []
    for chunk in digits.split("."):
        head = "".join(ch for ch in chunk if ch.isdigit())
        if not head:
            break
        parts.append(int(head))
    return tuple(parts)


def python_tool() -> Tool:
    """مفسری که خودِ راه‌انداز رویش اجرا می‌شود.

    اگر با `pythonw.exe` بالا آمده باشیم (تا پنجرهٔ کنسول باز نشود)، برای ساختنِ
    venv همان هم کار می‌کند؛ ولی `python.exe` کنارش را ترجیح می‌دهیم چون خروجیِ
    خطای pip را می‌شود از آن خواند.
    """
    exe = Path(sys.executable)
    if WINDOWS and exe.name.lower() == "pythonw.exe":
        console = exe.with_name("python.exe")
        if console.exists():
            exe = console
    version = sys.version_info[:2]
    return Tool(ok=version >= MIN_PYTHON, version=version, text=".".join(map(str, version)), path=str(exe))


def node_tool() -> Tool:
    node = shutil.which("node") or ""
    if not node:
        return Tool(ok=False)
    text = _probe_version([node, "-v"])
    version = parse_version(text)
    return Tool(ok=node_version_ok(version), version=version, text=text, path=node)


def node_version_ok(version: tuple[int, ...]) -> bool:
    """شرطِ Vite 8: ^20.19 || >=22.12 — یعنی ۲۱ و ۲۲ های اولیه رد می‌شوند."""
    if len(version) < 2:
        return False
    major, minor = version[0], version[1]
    if major == 20:
        return minor >= 19
    if major == 22:
        return minor >= 12
    return major >= 23


def npm_command() -> str:
    """روی ویندوز npm یک فایلِ `.cmd` است، نه `.exe`.

    `shutil.which` این را می‌فهمد؛ نوشتنِ خامِ «npm» در `subprocess` بدونِ shell
    نمی‌فهمد و با FileNotFoundError می‌افتد.
    """
    return shutil.which("npm") or ("npm.cmd" if WINDOWS else "npm")


def lan_address() -> str:
    """آدرسِ این دستگاه در شبکهٔ محلی.

    بدون فرستادنِ بسته: یک سوکتِ UDP به یک آدرسِ بیرونی «وصل» می‌شود تا سیستم‌عامل
    مسیرِ پیش‌فرض را انتخاب کند، و بعد فقط آدرسِ محلیِ آن سوکت خوانده می‌شود.
    این از `gethostbyname(hostname)` قابل‌اعتمادتر است، که روی ویندوزِ چنداینترفیسی
    اغلب آدرسِ یک آداپتورِ مجازیِ Hyper-V را برمی‌گرداند.
    """
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(0.5)
        sock.connect(("10.255.255.255", 1))
        address = sock.getsockname()[0]
    except OSError:
        return ""
    finally:
        sock.close()
    return "" if address.startswith(("127.", "169.254.")) else address


def child_environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    """محیطی که سرورها با آن اجرا می‌شوند.

    `PYTHONUTF8` این‌جا ست می‌شود و نه در فایلِ .bat، چون حالا راه‌انداز است که
    پروسه‌ها را می‌سازد. بدونِ آن، `slowapi` هنگامِ ساختِ Limiter فایلِ
    `backend/.env` را با انکودینگِ پیش‌فرضِ سیستم می‌خواند — روی ویندوزِ فارسی
    یعنی cp1252 — و یک کامنتِ فارسی، برنامه را پیش از bind کردنِ پورت می‌کشد.

    `PYTHONUNBUFFERED` هم لازم است وگرنه خروجیِ سرور در بافر می‌ماند و پنلِ
    گزارش تا وقتی چند کیلوبایت جمع نشود چیزی نشان نمی‌دهد.
    """
    env = dict(os.environ)
    env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"})
    if extra:
        env.update(extra)
    return env
