"""پیدا کردنِ پورتی که سرور واقعاً می‌تواند رویش بالا بیاید.

مسئله‌ای که این فایل حل می‌کند
------------------------------
شکایتِ همیشگیِ راه‌اندازِ قدیمی این بود: «بک‌اند روی پورت ۸۰۰۰ بالا نمی‌آید و
دلیلش معلوم نیست.» سه علتِ کاملاً متفاوت پشتِ همین یک جمله بود، و چون هر سه
یک‌جور دیده می‌شدند، هیچ‌کدام درست حل نمی‌شد:

۱. **یووی‌کورنِ اجرای قبلی هنوز زنده است.** با `--reload` یووی‌کورن یک پروسهٔ
   فرزند می‌سازد؛ بستنِ پنجرهٔ cmd پدر را می‌کشد و فرزند — که همان کسی است که
   پورت را گرفته — زنده می‌ماند. این شایع‌ترین حالت است و کاربر هیچ راهی ندارد
   بفهمد پورت دستِ خودِ برنامه است.

۲. **ویندوز پورت را برای خودش رزرو کرده.** Hyper-V و WSL2 و Docker Desktop
   بازه‌هایی از پورت‌ها را کنار می‌گذارند (excluded port range). داخلِ آن بازه
   هیچ‌کس listen نکرده — پس `netstat` خالی است و همه‌چیز «آزاد» به‌نظر می‌رسد —
   ولی `bind` با WSAEACCES (10013) رد می‌شود. این بازه‌ها با هر ری‌استارت
   جابه‌جا می‌شوند، برای همین مشکل «گاهی هست، گاهی نیست».

۳. **یک برنامهٔ بی‌ربط پورت را گرفته.**

نکتهٔ اصلی این است که برای هیچ‌کدام لازم نیست کاربر کاری بکند. عددِ ۸۰۰۰ هیچ
تقدسی ندارد؛ تنها چیزی که به آن وابسته بود، مقصدِ پروکسیِ Vite بود — و آن هم حالا
از متغیرِ محیطی `NEXAHR_BACKEND_URL` خوانده می‌شود. پس راه‌انداز می‌تواند پورت را
خودش انتخاب کند: اگر ۸۰۰۰ دستِ خودمان است پس می‌گیریمش، وگرنه می‌رویم روی
اولین پورتِ آزادِ بعدی و به فرانت‌اند می‌گوییم کجا را صدا بزند.

«ما» یعنی چه
------------
کشتنِ یک پروسه از رویِ حدس خطرناک است. این‌جا فقط پروسه‌ای کشته می‌شود که ثابت
شود مالِ همین مخزن است: یا فایلِ اجرایی‌اش داخلِ پوشهٔ پروژه است (پایتونِ venv)،
یا خطِ فرمانش مسیرِ پروژه را دارد (`npm run dev` داخلِ frontend). هر چیزِ دیگری
دست‌نخورده می‌ماند و به‌جایش پورت عوض می‌شود.

همهٔ توابعِ سنجش، اجرای دستورِ بیرونی را از یک نقطه می‌گیرند (`_run`) تا تست
بتواند بدونِ ویندوز، خروجیِ واقعیِ `netstat` و `netsh` را به تابع بدهد.
"""
from __future__ import annotations

import errno
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

WINDOWS = sys.platform.startswith("win")

# هر subprocess روی ویندوز یک پنجرهٔ کنسول باز می‌کند. کلِ هدفِ این راه‌انداز
# نبودنِ آن پنجره‌هاست، پس CREATE_NO_WINDOW همه‌جا لازم است — از جمله برای همین
# چند فراخوانیِ کوچکِ تشخیصی که وگرنه به‌صورتِ پلک‌زدنِ پنجرهٔ سیاه دیده می‌شوند.
CREATE_NO_WINDOW = 0x08000000
NO_WINDOW: dict = {"creationflags": CREATE_NO_WINDOW} if WINDOWS else {}


class Verdict(str, Enum):
    """چرا نمی‌شود روی این پورت listen کرد — یا این‌که می‌شود."""

    FREE = "free"
    IN_USE = "in_use"        # یکی آن‌جا listen کرده
    RESERVED = "reserved"    # بازهٔ رزروِ ویندوز، یا نبودِ دسترسی
    ERROR = "error"          # هر شکستِ دیگری در bind


@dataclass(frozen=True)
class Probe:
    port: int
    verdict: Verdict
    detail: str = ""

    @property
    def free(self) -> bool:
        return self.verdict is Verdict.FREE


@dataclass(frozen=True)
class Owner:
    """پروسه‌ای که پورت را گرفته."""

    pid: int
    name: str = ""
    path: str = ""
    cmdline: str = ""
    cwd: str = ""

    @property
    def label(self) -> str:
        return f"{self.name or 'process'} (PID {self.pid})"


def probe(port: int, host: str = "0.0.0.0") -> Probe:
    """آیا می‌شود اینجا bind کرد؟

    عمداً `bind` است نه `connect`. `connect` به سؤالِ «الان کسی آن‌جاست؟» جواب
    می‌دهد، و همان است که حالتِ ۲ بالا را جا می‌انداخت: در بازهٔ رزروشده هیچ‌کس
    نیست، پس connect می‌گفت «آزاد است» و یووی‌کورن یک ثانیه بعد می‌مرد.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # روی ویندوز SO_REUSEADDR یعنی «بگذار روی سوکتِ فعالِ دیگری هم bind کنم»؛
        # با آن، پورتِ واقعاً اشغال هم «آزاد» گزارش می‌شود — دقیقاً برعکسِ کاری که
        # این تابع باید بکند. روی لینوکس/مک برعکس، بدونش سوکتِ TIME_WAIT به‌اشتباه
        # «اشغال» دیده می‌شود؛ یووی‌کورن هم همین گزینه را ست می‌کند.
        if not WINDOWS:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError as exc:
            win = getattr(exc, "winerror", None)
            if win == 10048 or exc.errno == errno.EADDRINUSE:
                return Probe(port, Verdict.IN_USE, "another program is listening there")
            if win == 10013 or exc.errno == errno.EACCES:
                return Probe(port, Verdict.RESERVED, "bind refused with WSAEACCES/EACCES")
            return Probe(port, Verdict.ERROR, str(exc))
    finally:
        sock.close()
    return Probe(port, Verdict.FREE)


# ---------------------------------------------------------------------------
#  مالکِ پورت
# ---------------------------------------------------------------------------

def _run(argv: Sequence[str], timeout: float = 10.0) -> str:
    """دستور را اجرا کن و stdout بده؛ هر شکستی یعنی رشتهٔ خالی.

    تنها نقطهٔ تماس این ماژول با بیرون، تا تست بتواند جایش را بگیرد.
    """
    try:
        done = subprocess.run(
            list(argv), capture_output=True, text=True, timeout=timeout,
            errors="replace", **NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout or ""


#   TCP    0.0.0.0:8000     0.0.0.0:0     LISTENING     12345
_NETSTAT_ROW = re.compile(r"^\s*TCP\s+(\S+)\s+\S+\s+LISTENING\s+(\d+)\s*$", re.IGNORECASE | re.MULTILINE)


def _port_of(local_address: str) -> int | None:
    """«0.0.0.0:8000» و «[::]:8000» هر دو باید ۸۰۰۰ بدهند."""
    _, sep, tail = local_address.rpartition(":")
    if not sep or not tail.isdigit():
        return None
    return int(tail)


def pids_from_netstat(text: str, port: int) -> list[int]:
    """PID هایی که روی این پورت listen کرده‌اند، از خروجیِ `netstat -ano`.

    جدا از فراخوانی نگه داشته شده چون تنها بخشِ ظریفِ کار همین تجزیه است و باید
    بدونِ ویندوز تست شود. لیست برمی‌گرداند چون IPv4 و IPv6 دو سطرِ جدا هستند.
    """
    found: list[int] = []
    for local, pid in _NETSTAT_ROW.findall(text):
        if _port_of(local) == port and int(pid) not in found:
            found.append(int(pid))
    return found


def _listening_pid(port: int) -> int | None:
    if WINDOWS:
        pids = pids_from_netstat(_run(["netstat", "-ano", "-p", "tcp"], timeout=15), port)
        return pids[0] if pids else None
    # lsof دقیق‌ترین است ولی همه‌جا نصب نیست؛ ss روی لینوکسِ مدرن هست.
    out = _run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"]).split()
    for token in out:
        if token.isdigit():
            return int(token)
    match = re.search(r"pid=(\d+)", _run(["ss", "-lptnH", f"sport = :{port}"]))
    return int(match.group(1)) if match else None


_PS_ONE_LINER = (
    "$p = Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\";"
    "if ($p) {{ [pscustomobject]@{{ name=$p.Name; path=$p.ExecutablePath;"
    " cmdline=$p.CommandLine }} | ConvertTo-Json -Compress }}"
)


def _describe(pid: int) -> Owner:
    """نام، مسیرِ اجرایی و خطِ فرمانِ یک PID.

    خطِ فرمان لازم است چون `npm run dev` در نهایت یک `node.exe` است که مسیرش
    داخلِ پروژه نیست؛ تنها چیزی که مالِ ما بودنش را ثابت می‌کند، مسیرِ پروژه
    داخلِ آرگومان‌هاست.
    """
    if WINDOWS:
        raw = _run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_ONE_LINER.format(pid=pid)],
            timeout=15,
        ).strip()
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {}
        return Owner(
            pid=pid,
            name=str(data.get("name") or ""),
            path=str(data.get("path") or ""),
            cmdline=str(data.get("cmdline") or ""),
        )

    name = path = cmdline = cwd = ""
    proc = Path("/proc") / str(pid)
    if proc.is_dir():  # لینوکس
        try:
            name = (proc / "comm").read_text().strip()
            cmdline = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
            # `exe` سیم‌لینک‌ها را باز می‌کند، و پایتونِ داخلِ venv خودش یک
            # سیم‌لینک به مفسرِ پایه است — پس مسیرِ اجرایی از پروژه بیرون
            # می‌زند و ردِ ما را گم می‌کند. پوشهٔ کاری این را جبران می‌کند.
            path = os.readlink(proc / "exe")
            cwd = os.readlink(proc / "cwd")
        except OSError:
            pass
    else:  # مک و بقیه
        out = _run(["ps", "-p", str(pid), "-o", "comm=,command="]).strip()
        if out:
            name, _, cmdline = out.partition(" ")
            path = name
    return Owner(pid=pid, name=Path(name).name or name, path=path, cmdline=cmdline, cwd=cwd)


def owner_of(port: int) -> Owner | None:
    pid = _listening_pid(port)
    return _describe(pid) if pid else None


def belongs_to(owner: Owner, root: Path) -> bool:
    """آیا این پروسه مالِ همین مخزن است؟

    شرطِ کشتن. مقایسه روی متن است و نه روی مسیرِ resolve شده، چون خطِ فرمان
    فقط متن است؛ حروفِ بزرگ/کوچک و جهتِ اسلش روی ویندوز یکدست می‌شوند.
    """
    needle = str(root).replace("\\", "/").rstrip("/").lower()
    # ریشهٔ تباه‌شده باید رد شود، نه این‌که با همه‌چیز جور دربیاید. `Path("")`
    # به `.` تبدیل می‌شود و آن‌وقت `"." in haystack` تقریباً همیشه درست است —
    # یعنی راه‌انداز هر پروسه‌ای را «مالِ خودمان» می‌دید و می‌کشت.
    if needle in {"", ".", "..", "/"}:
        return False
    haystack = f"{owner.path} {owner.cmdline} {owner.cwd}".replace("\\", "/").lower()
    return needle in haystack


def reclaim(owner: Owner, timeout: float = 8.0) -> bool:
    """پروسه و کلِ درختِ فرزندانش را ببند.

    درخت، نه فقط خودش: همان `--reload` یووی‌کورن که این مشکل را می‌سازد، یعنی
    کشتنِ پدر پورت را آزاد نمی‌کند — پورت دستِ فرزند است.
    """
    if WINDOWS:
        _run(["taskkill", "/PID", str(owner.pid), "/T", "/F"], timeout=timeout)
    else:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.kill(owner.pid, sig)
            except (OSError, ProcessLookupError):
                break
            time.sleep(0.4)
    return True


def wait_until_free(port: int, host: str = "0.0.0.0", timeout: float = 8.0) -> bool:
    """آزاد شدنِ پورت بعد از کشتن آنی نیست؛ چند صد میلی‌ثانیه طول می‌کشد."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if probe(port, host).free:
            return True
        time.sleep(0.25)
    return probe(port, host).free


# ---------------------------------------------------------------------------
#  بازه‌های رزروشدهٔ ویندوز
# ---------------------------------------------------------------------------

# ستاره یعنی «بازه‌ای که مدیر دستی ثبت کرده». اگر انتهای سطر را سفت ببندیم،
# دقیقاً همان بازه‌هایی که کاربر خودش ساخته از قلم می‌افتند.
_RANGE_ROW = re.compile(r"^[ \t]*(\d+)[ \t]+(\d+)[ \t]*\*?[ \t]*$", re.MULTILINE)


def parse_excluded_ranges(text: str) -> list[tuple[int, int]]:
    """خروجیِ `netsh interface ipv4 show excludedportrange` را به بازه تبدیل کن.

    دو ستونش «Start Port» و «End Port» هستند — هر دو خودِ شمارهٔ پورت، نه شروع و
    تعداد. سطرهایی که برعکس خوانده شوند بازه‌هایی ده‌ها برابر بزرگ‌تر می‌سازند و
    راه‌انداز پورت‌های کاملاً سالم را هم «رزروشده» اعلام می‌کند.

    سطرهایی که برعکس باشند (پایانِ کوچک‌تر از شروع) دور ریخته می‌شوند: بازهٔ
    معکوس یعنی سطر چیزی جز بازه بوده و بهتر است نادیده گرفته شود تا این‌که
    تشخیصِ غلط بدهد.
    """
    ranges: list[tuple[int, int]] = []
    for start, end in _RANGE_ROW.findall(text):
        first, last = int(start), int(end)
        if last >= first:
            ranges.append((first, last))
    return ranges


def excluded_ranges() -> list[tuple[int, int]]:
    if not WINDOWS:
        return []
    return parse_excluded_ranges(
        _run(["netsh", "interface", "ipv4", "show", "excludedportrange", "protocol=tcp"], timeout=15)
    )


def covering_range(port: int, ranges: Sequence[tuple[int, int]]) -> tuple[int, int] | None:
    for low, high in ranges:
        if low <= port <= high:
            return (low, high)
    return None


# ---------------------------------------------------------------------------
#  انتخابِ پورت
# ---------------------------------------------------------------------------

@dataclass
class Choice:
    """نتیجهٔ «کدام پورت را برداریم»، همراه با روایتِ این‌که چرا."""

    port: int | None
    preferred: int
    first_verdict: Verdict
    story: list[str] = field(default_factory=list)
    advice: list[str] = field(default_factory=list)
    owner: Owner | None = None

    @property
    def ok(self) -> bool:
        return self.port is not None

    @property
    def moved(self) -> bool:
        return self.port is not None and self.port != self.preferred


def choose(
    preferred: int,
    *,
    host: str = "0.0.0.0",
    root: Path | None = None,
    span: int = 20,
    prober: Callable[[int, str], Probe] = probe,
) -> Choice:
    """پورتی برگردان که واقعاً بشود رویش listen کرد.

    ترتیب عمدی است: اول تلاش برای گرفتنِ پورتِ دلخواه (فقط اگر مالِ خودمان
    باشد)، بعد رفتن سراغِ پورتِ بعدی. برعکسش یعنی هر بار روی یک پورتِ تازه بالا
    بیاییم و بقایای اجرای قبلی برای همیشه بمانند.
    """
    first = prober(preferred, host)
    choice = Choice(port=None, preferred=preferred, first_verdict=first.verdict)

    if first.free:
        choice.port = preferred
        return choice

    if first.verdict is Verdict.IN_USE:
        owner = owner_of(preferred)
        choice.owner = owner
        if owner and root and belongs_to(owner, root):
            choice.story.append(
                f"Port {preferred} was still held by an earlier NexaHR run "
                f"({owner.label}); closed it."
            )
            reclaim(owner)
            if wait_until_free(preferred, host) and prober(preferred, host).free:
                choice.port = preferred
                return choice
            choice.story.append(f"Port {preferred} did not come free, moving on.")
        else:
            who = owner.label if owner else "another program"
            choice.story.append(f"Port {preferred} is taken by {who}.")
            if owner:
                choice.advice.append(f"taskkill /PID {owner.pid} /T /F" if WINDOWS else f"kill {owner.pid}")

    elif first.verdict is Verdict.RESERVED:
        window = covering_range(preferred, excluded_ranges())
        where = f" (inside the reserved range {window[0]}-{window[1]})" if window else ""
        choice.story.append(
            f"Windows has reserved port {preferred}{where}, so nothing is allowed to "
            "listen there. Hyper-V, WSL2 and Docker Desktop each claim such ranges, "
            "and the ranges move on every reboot."
        )
        choice.advice += [
            "net stop winnat  &&  net start winnat",
            f"netsh int ipv4 add excludedportrange protocol=tcp startport={preferred} numberofports=1 store=persistent",
        ]

    else:
        choice.story.append(f"Port {preferred} could not be tested: {first.detail}")

    for candidate in range(preferred + 1, preferred + 1 + span):
        if prober(candidate, host).free:
            choice.port = candidate
            choice.story.append(f"Using port {candidate} instead.")
            return choice

    choice.story.append(
        f"No free port between {preferred} and {preferred + span}."
    )
    return choice
