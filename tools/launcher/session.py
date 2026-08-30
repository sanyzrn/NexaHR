"""یک اجرای کامل: از چکِ پیش‌نیازها تا دو سرورِ زنده و آدرس‌هایشان.

این‌جا عمداً هیچ چیزِ گرافیکی نیست. رابطِ Tk و حالتِ خطِ فرمان هر دو همین کلاس
را صدا می‌زنند، پس رفتارشان نمی‌تواند از هم جدا بیفتد — چیزی که وقتی «نسخهٔ
گرافیکی» و «نسخهٔ متنی» هرکدام منطقِ خودشان را داشته باشند، خیلی زود اتفاق
می‌افتد.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import admin as adminlib
from . import database as db
from . import prerequisites
from .environment import child_environment, lan_address, npm_command
from .shell import Result, json_probe, stream
from .steps import PIPELINE, Context, Outcome, Remedy, Step, new_context, provision_database
from .supervisor import Server, ServerSpec, State, Supervisor


@dataclass
class Links:
    """آدرس‌هایی که به کاربر نشان داده می‌شوند."""

    local: str = ""
    network: str = ""
    api: str = ""

    @property
    def all(self) -> list[tuple[str, str]]:
        pairs = [("On this computer", self.local)]
        if self.network:
            pairs.append(("On your network", self.network))
        pairs.append(("Backend API", self.api))
        return [(label, url) for label, url in pairs if url]


@dataclass
class Session:
    log: Callable[[str, str], None]
    ask_password: Callable[[str], str | None] = lambda prompt: None
    on_step: Callable[[Step, Outcome | None], None] = lambda step, outcome: None
    on_crash: Callable[[Server], None] = lambda server: None

    ctx: Context = field(init=False)
    supervisor: Supervisor = field(init=False)
    links: Links = field(default_factory=Links)
    failure: Outcome | None = None

    def __post_init__(self) -> None:
        self.ctx = new_context(self.log, self.ask_password)
        self.supervisor = Supervisor(self.log)
        self.supervisor.on_crash = lambda server: self.on_crash(server)

    # -- مرحله‌ها ----------------------------------------------------------

    def prepare(self) -> bool:
        """پایپ‌لاین را اجرا کن. اولین شکست، اجرا را متوقف می‌کند.

        ادامه‌دادن بعد از یک شکست فقط خطاهای بعدی را تولید می‌کند که همه معلولِ
        همان اولی‌اند، و پیدا کردنِ علتِ اصلی را سخت‌تر می‌کند.
        """
        for step in PIPELINE:
            self.on_step(step, None)
            outcome = step.run(self.ctx)
            self.on_step(step, outcome)
            if not outcome.ok:
                self.failure = outcome
                return False
        return True

    # -- سرورها ------------------------------------------------------------

    def _specs(self) -> list[ServerSpec]:
        paths = self.ctx.paths
        api_port = self.ctx.backend_port
        web_port = self.ctx.frontend_port
        assert api_port and web_port  # `choose_ports` تضمینش می‌کند

        lan = lan_address()
        origins = [f"http://localhost:{web_port}", f"http://127.0.0.1:{web_port}"]
        if lan:
            origins.append(f"http://{lan}:{web_port}")

        backend_env = child_environment({
            # پورت‌ها ممکن است جابه‌جا شده باشند، پس هر چیزی که آدرس می‌سازد باید
            # پورتِ واقعی را بگیرد. متغیرِ محیطی بر `backend/.env` اولویت دارد
            # (رفتارِ استانداردِ pydantic-settings)، پس فایل دست‌نخورده می‌ماند.
            "PUBLIC_BASE_URL": f"http://localhost:{web_port}",
            "CORS_ORIGINS": ",".join(origins),
        })
        frontend_env = child_environment({
            # همان یک متغیری که کلِ «پورت ۸۰۰۰ باید ۸۰۰۰ باشد» را از بین می‌برد:
            # مقصدِ پروکسیِ Vite دیگر در فایلِ تنظیمات ثابت نیست.
            "NEXAHR_BACKEND_URL": f"http://127.0.0.1:{api_port}",
        })

        return [
            ServerSpec(
                name="backend",
                argv=[
                    str(paths.venv_python), "-m", "uvicorn", "app.main:app",
                    "--reload", "--host", "0.0.0.0", "--port", str(api_port),
                ],
                cwd=paths.backend,
                env=backend_env,
                port=api_port,
                ready_path="/api/health",
            ),
            ServerSpec(
                name="frontend",
                argv=[
                    npm_command(), "run", "dev", "--",
                    "--host", "--port", str(web_port), "--strictPort",
                ],
                cwd=paths.frontend,
                env=frontend_env,
                port=web_port,
            ),
        ]

    def serve(self, timeout: float = 90.0) -> bool:
        """سرورها را بالا بیاور و صبر کن تا واقعاً جواب بدهند.

        قاعدهٔ «هیچ‌وقت روی پشتهٔ خراب مرورگر باز نکن» این‌جا اعمال می‌شود:
        تا وقتی `/api/health` جواب ندهد، هیچ لینکی نشان داده نمی‌شود.
        """
        backend, frontend = self.supervisor.launch(self._specs())

        if not backend.wait_until_ready(timeout):
            self.failure = Outcome(False, "the backend did not come up", self._backend_diagnosis(backend))
            return False
        if not frontend.wait_until_ready(timeout):
            self.failure = Outcome(False, "the web server did not come up", self._frontend_diagnosis(frontend))
            return False

        web_port = self.ctx.frontend_port
        lan = lan_address()
        self.links = Links(
            local=f"http://localhost:{web_port}",
            network=f"http://{lan}:{web_port}" if lan else "",
            api=f"http://localhost:{self.ctx.backend_port}",
        )
        self.supervisor.watch()
        return True

    # -- تشخیص ------------------------------------------------------------

    def _backend_diagnosis(self, server: Server) -> Remedy:
        # اگر پروسه مرده، آخرین چیزی که چاپ کرده تقریباً همیشه خودِ علت است.
        # نسخهٔ قبلی این را نداشت و به‌جایش `import app.main` را دوباره اجرا
        # می‌کرد تا خطا را بازتولید کند — که هم کندتر بود و هم خطاهای زمانِ
        # bind را اصلاً نشان نمی‌داد.
        tail = [line for line in server.tail if line.strip()][-12:]
        body = "\n".join(tail) if tail else "The backend produced no output before it stopped."
        return Remedy(
            "The backend started but never answered",
            "Until it does, the login page loads and no one can sign in: every /api request "
            "fails behind it. Last output:\n\n" + body,
            commands=[
                "UnicodeDecodeError    -> backend\\.env has non-ASCII comments",
                "OperationalError      -> DATABASE_URL in backend\\.env is wrong",
            ],
        )

    def _frontend_diagnosis(self, server: Server) -> Remedy:
        tail = [line for line in server.tail if line.strip()][-12:]
        return Remedy(
            "The web server started but never answered",
            "Last output:\n\n" + ("\n".join(tail) if tail else "(nothing)"),
        )

    # -- کارهای نگهداری ----------------------------------------------------
    #
    # همه از نخِ کاری صدا زده می‌شوند و هیچ‌کدام به رابط کاربری دست نمی‌زنند؛
    # فقط `Result` برمی‌گردانند و از راهِ `log` حرف می‌زنند. کارهایی که به
    # دیتابیس دست می‌زنند، سرورها را اول می‌خوابانند: یک اتصالِ باز کافی است تا
    # `pg_restore --clean` روی حذفِ جدول‌ها گیر کند، و یک بک‌اند که وسطِ عوض شدنِ
    # دیتابیس زنده مانده باشد، به دیتابیسِ قبلی وصل است بی‌آنکه چیزی بگوید.

    @property
    def _interpreter(self) -> Path:
        return self.ctx.paths.venv_python

    def endpoint(self) -> db.Endpoint:
        return db.current_endpoint(self.ctx.paths.env_file)

    def database_report(self) -> dict:
        """وضعیتِ دیتابیس از دیدِ خودِ درایور — نه حدسِ ما."""
        return json_probe(
            [str(self._interpreter), "-m", "scripts.db_info"],
            cwd=self.ctx.paths.backend, env=child_environment(),
        )

    def switch_database(self, endpoint: db.Endpoint) -> Result:
        """به دیتابیسِ دیگری وصل شو: فایل تنظیمات، ساخت اگر نبود، مایگریشن، اجرا.

        ترتیب اهمیت دارد. نوشتنِ فایل پیش از ساختنِ دیتابیس یعنی اگر ساخت شکست
        بخورد، تنظیمات به جایی اشاره می‌کند که نیست — پس در آن حالت فایل به حالِ
        قبل برگردانده می‌شود.
        """
        previous = self.endpoint()
        self.stop()
        db.apply_endpoint(self.ctx.paths.env_file, endpoint)
        self.log("setup", f"switching to {endpoint.label}")

        # همان مسیرِ راه‌اندازی، شاملِ پرسیدنِ رمزِ ادمین وقتی دیتابیس هنوز نیست.
        # صدا زدنِ مستقیمِ اسکریپت این‌جا یک بار امتحان شد و بی‌صدا با کدِ ۳ شکست
        # خورد: کاربر «نشد وصل شوم» می‌دید، در حالی که فقط یک رمز کم بود.
        if provision_database(self.ctx) != 0:
            db.apply_endpoint(self.ctx.paths.env_file, previous)
            self.restart()
            return Result(
                False,
                f"Could not reach or create “{endpoint.name}”. The settings file has been "
                f"put back to {previous.name}.",
            )

        if stream(
            [str(self._interpreter), "-m", "alembic", "upgrade", "head"],
            cwd=self.ctx.paths.backend, env=child_environment(),
            log=lambda line: self.log("setup", line),
        ) != 0:
            return Result(False, f"Connected to “{endpoint.name}”, but the migrations failed.")

        started = self.restart()
        if not started:
            return Result(False, "The database was switched, but the servers did not come back.")
        return Result(True, f"Now using {endpoint.label}")

    def back_up(self) -> Result:
        endpoint = self.endpoint()
        destination = db.backup_path(self.ctx.paths.root, endpoint)
        return db.backup(endpoint, destination, lambda line: self.log("setup", line))

    def restore_from(self, source: Path) -> Result:
        """بازگردانی — برگشت‌ناپذیر. تأیید باید پیش از رسیدن به این‌جا گرفته شده باشد."""
        endpoint = self.endpoint()
        self.stop()
        result = db.restore(endpoint, source, lambda line: self.log("setup", line))
        self.restart()
        return result

    def backups(self) -> list[Path]:
        return db.backups(self.ctx.paths.root)

    def admin_status(self) -> adminlib.Status:
        return adminlib.status(self._interpreter, self.ctx.paths.backend)

    def create_admin(self, *, username: str, full_name: str, password: str) -> Result:
        return adminlib.create(
            self._interpreter, self.ctx.paths.backend,
            username=username, full_name=full_name, password=password,
            log=lambda line: self.log("setup", line),
        )

    def features(self) -> prerequisites.Report:
        return prerequisites.inspect(self._interpreter)

    def install_package(self, package: str) -> Result:
        code = stream(
            [str(self._interpreter), "-m", "pip", "install", package],
            cwd=self.ctx.paths.backend, env=child_environment(),
            log=lambda line: self.log("setup", line),
        )
        if code != 0:
            return Result(False, f"pip could not install {package} — the log has the error.")
        return Result(True, f"Installed {package}. Restart NexaHR for it to take effect.")

    # -- توقف و راه‌اندازی دوباره ------------------------------------------

    def restart(self) -> bool:
        """سرورها را ببند و از نو بالا بیاور.

        کلِ پایپ‌لاین دوباره اجرا می‌شود و نه فقط `serve`: بعد از یک ویرایشِ
        تنظیمات یا نصبِ بسته، همان مرحله‌ها هستند که باید دوباره سنجیده شوند.
        روی محیطی که از قبل آماده است این چند ثانیه بیشتر طول نمی‌کشد.

        زمینه از نو ساخته می‌شود چون `notes` و پورت‌ها به اجرای قبلی تعلق
        دارند؛ نگه داشتنشان یعنی پیامِ «پورت ۸۰۰۰ عوض شد» تا ابد روی صفحه بماند.
        """
        self.stop()
        self.ctx = new_context(self.log, self.ask_password)
        self.supervisor = Supervisor(self.log)
        self.supervisor.on_crash = lambda server: self.on_crash(server)
        self.failure = None
        self.links = Links()
        return self.prepare() and self.serve()

    def stop(self) -> None:
        self.supervisor.stop()

    def stop_on_exit(self) -> None:
        """هر راهِ خروجی که به کد برسد، سرورها را ببندد.

        `atexit` مسیرِ عادی را می‌گیرد و هندلرهای سیگنال، `kill` و بستنِ ترمینال
        را. آنچه هیچ‌کدام نمی‌گیرند `SIGKILL` و Task Manager است — و همان‌جاست که
        Job Object روی ویندوز (‏`jobs.py`) وارد می‌شود.
        """
        import atexit
        import signal

        atexit.register(self.stop)
        for name in ("SIGTERM", "SIGHUP", "SIGBREAK"):
            handler = getattr(signal, name, None)
            if handler is None:
                continue
            try:
                signal.signal(handler, lambda *_: self._exit())
            except (ValueError, OSError):
                # ثبتِ سیگنال فقط در نخِ اصلی ممکن است؛ نبودنش کشنده نیست.
                pass

    def _exit(self) -> None:
        self.stop()
        raise SystemExit(0)

    @property
    def running(self) -> bool:
        return bool(self.supervisor.servers) and all(s.state is State.RUNNING for s in self.supervisor.servers)
