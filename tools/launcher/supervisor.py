"""نگه‌داشتنِ دو سرور، بدونِ دو پنجرهٔ کنسول.

راه‌اندازِ قبلی هر سرور را با `start ... cmd /k` بالا می‌آورد. سه اشکال داشت که
هر سه از همین‌جا حل می‌شوند:

* **دیده نمی‌شد.** خطای واقعی در پنجره‌ای بود که کاربر کمینه‌اش کرده بود؛ چیزی
  که می‌دید فقط «سایت بالا نمی‌آید» بود. حالا هر دو جریانِ خروجی به یک جا
  می‌آیند و برچسبِ منبع دارند.

* **قابلِ کنترل نبود.** بستنِ پنجره تنها راهِ توقف بود، و آن هم کامل نبود:
  `uvicorn --reload` و `npm run dev` هر دو پروسهٔ فرزند می‌سازند و آن فرزند —
  که پورت را گرفته — زنده می‌ماند. همین بازمانده، علتِ شمارهٔ یکِ «پورت ۸۰۰۰
  اشغال است» در اجرای بعدی بود. پس این‌جا کلِ درختِ پروسه بسته می‌شود.

* **مرگِ بی‌صدا داشت.** اگر سرور بعد از بالا آمدن می‌مرد، هیچ‌کس خبردار نمی‌شد.
  حالا یک نگهبان وضعیت را می‌پاید و همان لحظه گزارش می‌دهد.
"""
from __future__ import annotations

import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .jobs import ProcessGroup
from .ports import NO_WINDOW, WINDOWS

if WINDOWS:  # pragma: no cover - مسیرِ ویندوز
    # پروسه در گروهِ خودش ساخته می‌شود تا Ctrl+C ای که کاربر به راه‌انداز می‌دهد،
    # سرورها را وسطِ کار قطع نکند و از مسیرِ منظمِ توقف رد شود.
    _GROUP = {"creationflags": NO_WINDOW["creationflags"] | subprocess.CREATE_NEW_PROCESS_GROUP}
else:
    import os
    import signal

    _GROUP = {"start_new_session": True}


class State:
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass
class ServerSpec:
    name: str
    argv: Sequence[str]
    cwd: Path
    env: dict[str, str]
    port: int
    ready_path: str = "/"


class Server:
    """یک پروسهٔ سرور، با خروجیِ لوله‌شده و وضعیتِ قابلِ خواندن."""

    def __init__(self, spec: ServerSpec, log: Callable[[str, str], None]) -> None:
        self.spec = spec
        self._log = log
        self._proc: subprocess.Popen[str] | None = None
        self._tail: list[str] = []
        self.state = State.IDLE

    # -- چرخهٔ عمر ---------------------------------------------------------

    def start(self) -> None:
        self.state = State.STARTING
        self._tail.clear()
        try:
            self._proc = subprocess.Popen(
                list(self.spec.argv),
                cwd=str(self.spec.cwd),
                env=self.spec.env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                errors="replace",
                **_GROUP,
            )
        except OSError as exc:
            self.state = State.FAILED
            self._log(self.spec.name, f"could not start: {exc}")
            return
        threading.Thread(target=self._pump, name=f"{self.spec.name}-log", daemon=True).start()

    def adopt_into(self, group: ProcessGroup) -> None:
        if self._proc is not None and group.active and not group.adopt(self._proc):
            self._log(self.spec.name, "note: could not tie this server's lifetime to the launcher")

    def _pump(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            text = line.rstrip("\r\n")
            # چند خطِ آخر نگه داشته می‌شود تا اگر پروسه مرد، بشود گفت با چه پیامی
            # مرد — بدونِ این‌که کاربر مجبور باشد کلِ گزارش را بالا برود.
            self._tail.append(text)
            del self._tail[:-40]
            self._log(self.spec.name, text)

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            self.state = State.STOPPED
            return
        if WINDOWS:  # pragma: no cover - مسیرِ ویندوز
            # `taskkill /T` یعنی «و همهٔ فرزندانش». بدونِ /T، کارگرِ reload زنده
            # می‌ماند و پورت را نگه می‌دارد — همان چیزی که این راه‌انداز آمده که
            # حل کند.
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True, timeout=15, **NO_WINDOW,
            )
        else:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (OSError, ProcessLookupError):
                proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover
            proc.kill()
        self.state = State.STOPPED

    # -- وضعیت -------------------------------------------------------------

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def exit_code(self) -> int | None:
        return self._proc.poll() if self._proc else None

    @property
    def tail(self) -> list[str]:
        return list(self._tail)

    @property
    def url(self) -> str:
        return f"http://localhost:{self.spec.port}"

    def wait_until_ready(self, timeout: float = 60.0) -> bool:
        """صبر کن تا سرور جواب بدهد — یا تا وقتی بمیرد.

        مرگِ پروسه هم به‌اندازهٔ جوابِ HTTP یک نتیجهٔ قطعی است. نسخهٔ قبلی این را
        نمی‌دید و در همان حالت، تمامِ چهل ثانیه را نقطه چاپ می‌کرد.
        """
        target = f"http://127.0.0.1:{self.spec.port}{self.spec.ready_path}"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.alive:
                self.state = State.FAILED
                return False
            if _answers(target):
                self.state = State.RUNNING
                return True
            time.sleep(0.5)
        self.state = State.FAILED
        return False


def _answers(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return 200 <= response.status < 500
    except urllib.error.HTTPError as exc:
        # ۴۰۴ هم یعنی سرور زنده است و دارد جواب می‌دهد؛ فقط این مسیر را ندارد.
        return exc.code < 500
    except (urllib.error.URLError, OSError, ValueError):
        return False


class Supervisor:
    """هر دو سرور با هم: بالا آوردن، پاییدن، و بستنِ کاملِ درختِ پروسه."""

    def __init__(self, log: Callable[[str, str], None]) -> None:
        self._log = log
        self.servers: list[Server] = []
        self._watch: threading.Thread | None = None
        self._stopping = threading.Event()
        self.on_crash: Callable[[Server], None] = lambda server: None
        # روی ویندوز، تضمینی که `stop()` نمی‌تواند بدهد: اگر خودِ راه‌انداز بدونِ
        # خداحافظی بمیرد، هسته سرورها را می‌بندد. توضیحش در `jobs.py`.
        self._group = ProcessGroup()

    def launch(self, specs: Sequence[ServerSpec]) -> list[Server]:
        self.servers = [Server(spec, self._log) for spec in specs]
        for server in self.servers:
            server.start()
            server.adopt_into(self._group)
        return self.servers

    def watch(self, interval: float = 1.0) -> None:
        """اگر سروری بعد از بالا آمدن مُرد، همان لحظه خبر بده."""
        def loop() -> None:
            while not self._stopping.wait(interval):
                for server in self.servers:
                    if server.state is State.RUNNING and not server.alive:
                        server.state = State.FAILED
                        self.on_crash(server)

        self._watch = threading.Thread(target=loop, name="watchdog", daemon=True)
        self._watch.start()

    def stop(self) -> None:
        self._stopping.set()
        for server in self.servers:
            server.stop()
