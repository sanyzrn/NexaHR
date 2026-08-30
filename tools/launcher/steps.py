"""کارهایی که باید پیش از بالا آمدنِ سرورها انجام شوند.

هر مرحله یک تابع است که `Context` می‌گیرد و `Outcome` می‌دهد. دو قاعده از
راه‌اندازِ قدیمی این‌جا هم برقرارند و کلِ ساختار بر همان‌ها سوار است:

۱. **هیچ‌وقت روی پشتهٔ خراب، مرورگر باز نکن.** بک‌اندِ مرده هم یک صفحهٔ ورودِ
   کاملاً سالم نشان می‌دهد که فقط کسی نمی‌تواند با آن وارد شود — گیج‌کننده‌ترین
   شکلِ ممکنِ خرابی.

۲. **هیچ‌وقت با دستوری تمام نکن که کاربر نمی‌تواند اجرایش کند.** نسخهٔ قدیمی
   می‌گفت `psql -U postgres ...` را بزن، در حالی که نصب‌کنندهٔ PostgreSQL روی
   ویندوز `psql` را به PATH اضافه نمی‌کند. هر جا این‌جا می‌شود کاری کرد، انجام
   می‌شود؛ هر جا واقعاً نمی‌شود، `Remedy` می‌گوید دقیقاً چه باید کرد.

مرحله‌ها حالت‌دار نیستند و ترتیبشان معنا دارد: تشخیصِ «PostgreSQL بالا نیست»
پیش از مایگریشن انجام می‌شود، چون شکستِ مایگریشن ده‌ها علت دارد و «چیزی روی
۵۴۳۲ گوش نمی‌دهد» فقط یکی.
"""
from __future__ import annotations

import re
import socket
from collections.abc import Callable
from dataclasses import dataclass, field

from . import ports as portlib
from .environment import (
    MIN_NODE,
    MIN_PYTHON,
    Paths,
    Tool,
    child_environment,
    locate,
    node_tool,
    npm_command,
    python_tool,
)
from .shell import stream

# پورت‌های دلخواه. هیچ‌کدام الزامی نیستند — اگر گرفته باشند، راه‌انداز پورتِ
# بعدی را برمی‌دارد و به هر دو طرف می‌گوید کجا را صدا بزنند.
DEFAULT_BACKEND_PORT = 8000
DEFAULT_FRONTEND_PORT = 5173


@dataclass
class Remedy:
    """وقتی راه‌انداز نمی‌تواند خودش درستش کند: چه شد، و چه باید کرد."""

    title: str
    body: str = ""
    commands: list[str] = field(default_factory=list)
    url: str = ""


@dataclass
class Outcome:
    ok: bool
    summary: str = ""
    remedy: Remedy | None = None


@dataclass
class Context:
    paths: Paths
    log: Callable[[str, str], None]
    ask_password: Callable[[str], str | None] = lambda prompt: None
    python: Tool = field(default_factory=python_tool)
    node: Tool = field(default_factory=node_tool)
    backend_port: int | None = None
    frontend_port: int | None = None
    notes: list[str] = field(default_factory=list)
    advice: list[str] = field(default_factory=list)

    def say(self, line: str) -> None:
        self.log("setup", line)

    def run(self, argv, *, cwd=None, env=None, stream_name="setup") -> int:
        return stream(argv, cwd=cwd, env=env or child_environment(), log=lambda line: self.log(stream_name, line))


# ---------------------------------------------------------------------------
#  ۱. ابزارها
# ---------------------------------------------------------------------------

def check_toolchain(ctx: Context) -> Outcome:
    if not ctx.python.ok:
        return Outcome(
            False,
            f"Python {ctx.python.pretty} is too old",
            Remedy(
                "This project needs Python "
                f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer",
                "The backend imports datetime.UTC, which only exists from 3.11 on, so an "
                "older interpreter fails at import time — after everything else has already "
                "reported success.",
                url="https://python.org",
            ),
        )

    if not ctx.node.ok:
        missing = not ctx.node.path
        return Outcome(
            False,
            "Node.js was not found" if missing else f"Node {ctx.node.pretty} is too old",
            Remedy(
                f"Install Node.js {MIN_NODE[0]}.{MIN_NODE[1]}+ (or 22.12+)",
                "Vite 8 refuses to start on anything older. npm install still succeeds there, "
                "so the failure looks like a frontend bug rather than a Node version problem."
                + ("" if missing else f" Found {ctx.node.pretty}."),
                commands=["After installing, close this window and start NexaHR again."],
                url="https://nodejs.org",
            ),
        )

    ctx.say(f"python {ctx.python.pretty} · node {ctx.node.pretty}")
    return Outcome(True, f"Python {ctx.python.pretty}, Node {ctx.node.pretty}")


# ---------------------------------------------------------------------------
#  ۲. محیط مجازی
# ---------------------------------------------------------------------------

def ensure_venv(ctx: Context) -> Outcome:
    interpreter = ctx.paths.venv_python
    if not interpreter.exists():
        ctx.say(f"creating virtual environment at {ctx.paths.venv}")
        ctx.run([ctx.python.path, "-m", "venv", str(ctx.paths.venv)])

    # `python -m venv` می‌تواند موفق گزارش دهد و یک venv غیرقابل‌استفاده جا بگذارد
    # (اجرای نیمه‌کاره، آنتی‌ویروس، پوشهٔ نیمه‌پاک‌شده). به‌جای اعتماد به کدِ خروج،
    # خودِ مفسر را امتحان می‌کنیم.
    if not interpreter.exists() or ctx.run([str(interpreter), "-c", "import sys"]) != 0:
        return Outcome(
            False,
            "the virtual environment is not usable",
            Remedy(
                "Delete the .venv folder and start again",
                "This is almost always a half-created virtual environment — an interrupted "
                "run, or antivirus removing a file while pip was writing it.",
                commands=[f"rmdir /s /q \"{ctx.paths.venv}\""],
            ),
        )
    return Outcome(True, "ready")


# ---------------------------------------------------------------------------
#  ۳. وابستگی‌های بک‌اند
# ---------------------------------------------------------------------------

def ensure_backend_packages(ctx: Context) -> Outcome:
    interpreter = str(ctx.paths.venv_python)
    marker, requirements = ctx.paths.deps_marker, ctx.paths.requirements

    changed = True
    if marker.exists() and requirements.exists():
        changed = marker.read_bytes() != requirements.read_bytes()

    # نشانه می‌گوید «ما این‌ها را نصب کردیم» — نمی‌گوید «هنوز سرِ جایشان هستند».
    # همین فاصله گران‌ترین اشکالِ این پروژه بود: بسته‌ها از venv می‌رفتند، نشانه
    # هنوز با requirements.txt یکی بود، این مرحله می‌گفت «همه‌چیز نصب است»،
    # یووی‌کورن در پنجرهٔ خودش با ModuleNotFoundError می‌مرد و فرانت‌اند فقط
    # ECONNREFUSED نشان می‌داد. پس سؤالِ واقعی را از venv می‌پرسیم.
    healthy = ctx.run([interpreter, "-m", "scripts.check_deps"], cwd=ctx.paths.backend) == 0
    if not healthy and not changed:
        ctx.say("the marker says installed, but the venv cannot import them — reinstalling")

    if changed or not healthy:
        ctx.say("installing Python packages (this can take a few minutes)")
        ctx.run([interpreter, "-m", "pip", "install", "--upgrade", "pip", "--quiet"])
        if ctx.run([interpreter, "-m", "pip", "install", "-r", str(requirements)]) != 0:
            return Outcome(
                False,
                "pip install failed",
                Remedy(
                    "Installing the backend packages did not finish",
                    "The most common cause by far is no internet access, or a proxy that "
                    "blocks pypi.org. The log above has the exact error.",
                ),
            )
        marker.write_bytes(requirements.read_bytes())
    else:
        return Outcome(True, "already installed")

    # همان سؤال، حالا به‌عنوان حرفِ آخرِ این مرحله. اگر pip موفق بوده و import ها
    # هنوز شکست می‌خورند، خودِ venv خراب است و تکرارِ pip درستش نمی‌کند.
    if ctx.run([interpreter, "-m", "scripts.check_deps"], cwd=ctx.paths.backend) != 0:
        return Outcome(
            False,
            "packages are still missing after pip install",
            Remedy(
                "Delete the .venv folder and start again",
                "pip reported success but the environment still cannot import what the app "
                "imports, which means the environment itself is damaged.",
                commands=[f"rmdir /s /q \"{ctx.paths.venv}\""],
            ),
        )
    return Outcome(True, "installed")


# ---------------------------------------------------------------------------
#  ۴. فایل تنظیمات
# ---------------------------------------------------------------------------

# عمداً این‌جا نوشته می‌شود و از `.env.example` کپی نمی‌شود: آن فایل توضیحاتِ
# فارسی دارد، و همان توضیحات دقیقاً چیزی است که خوانندهٔ غیرِ UTF-8 را می‌کشد.
# این نسخه ASCII می‌ماند تا یووی‌کورنِ دستی هم بالا بیاید.
LOCAL_ENV = """\
# NexaHR - local development settings
#
# ASCII only, on purpose: this file is also read by starlette's Config using the
# OS default encoding, which is cp1252 on a Persian Windows install. One Persian
# comment here and the backend dies at import time with UnicodeDecodeError.
#
# The annotated Persian reference lives in .env.example.

ENVIRONMENT=development
DATABASE_URL=postgresql+psycopg://nexahr:nexahr_dev_password@localhost:5432/nexahr
JWT_SECRET_KEY=local-development-only-not-a-real-secret
CORS_ORIGINS=http://localhost:5173,http://localhost:8080
PUBLIC_BASE_URL=http://localhost:5173
SEED_DEMO_DATA=true

# Aggregate averages are hidden below this many evaluations, so that a "unit
# average" over two people cannot be read back as those two people's scores. The
# production default is 5; the demo data set is smaller than that, so every
# dashboard chart would come up empty and look broken. 1 disables suppression -
# LOCAL DEMO ONLY.
MIN_COHORT_SIZE=1
"""


def ensure_settings(ctx: Context) -> Outcome:
    env_file = ctx.paths.env_file
    if not env_file.exists():
        env_file.write_text(LOCAL_ENV, encoding="ascii")
        ctx.say(f"wrote {env_file}")
        return Outcome(True, "created")

    # یک .env قدیمی ممکن است هنوز کامنتِ فارسی داشته باشد. تا وقتی راه‌انداز
    # `PYTHONUTF8=1` می‌دهد بی‌ضرر است، ولی یووی‌کورنِ دستی با آن بالا نمی‌آید —
    # پس گفته می‌شود، نه این‌که بی‌صدا رد شود.
    if any(byte > 127 for byte in env_file.read_bytes()):
        ctx.notes.append(
            "backend\\.env has non-ASCII characters. Harmless here (NexaHR sets PYTHONUTF8), "
            "but starting uvicorn by hand will fail with UnicodeDecodeError."
        )
    return Outcome(True, "in place")


_DATABASE_URL = re.compile(r"^\s*DATABASE_URL\s*=\s*(\S+)", re.MULTILINE)
_HOST_PORT = re.compile(r"@([^/:@]+)(?::(\d+))?/")


def database_endpoint(env_text: str) -> tuple[str, int]:
    """میزبان و پورتِ PostgreSQL از روی DATABASE_URL.

    عدد ۵۴۳۲ ثابت نوشته نمی‌شود چون کاربری که پستگرسِ خودش را روی پورتِ دیگری
    دارد، وگرنه پیامِ «چیزی روی ۵۴۳۲ گوش نمی‌دهد» را می‌گیرد که دربارهٔ سرورِ او
    اصلاً صادق نیست.
    """
    match = _DATABASE_URL.search(env_text or "")
    if match:
        endpoint = _HOST_PORT.search(match.group(1))
        if endpoint:
            return endpoint.group(1), int(endpoint.group(2) or 5432)
    return "localhost", 5432


# ---------------------------------------------------------------------------
#  ۵. دیتابیس
# ---------------------------------------------------------------------------

ADMIN_LOGIN_FAILED = 3  # کدِ خروجِ scripts.ensure_database وقتی رمزِ ادمین لازم است


def ensure_database(ctx: Context) -> Outcome:
    env_text = ctx.paths.env_file.read_text(encoding="utf-8", errors="replace")
    host, port = database_endpoint(env_text)

    probe = socket.socket()
    probe.settimeout(2)
    reachable = probe.connect_ex((host, port)) == 0
    probe.close()
    if not reachable:
        return Outcome(
            False,
            f"nothing is listening on {host}:{port}",
            Remedy(
                "PostgreSQL is not running",
                "Start the PostgreSQL service and try again. The service name ends with the "
                "major version, so it differs between installs — the second command lists "
                "the exact name on this machine.",
                commands=[
                    "net start postgresql-x64-16",
                    "sc query state= all | findstr /i postgres",
                ],
            ),
        )

    interpreter = str(ctx.paths.venv_python)
    code = ctx.run([interpreter, "-m", "scripts.ensure_database"], cwd=ctx.paths.backend)

    # نقش و دیتابیس این‌جا ساخته می‌شوند به‌جای این‌که از کاربر خواسته شوند، چون
    # دستوری که قبلاً چاپ می‌شد قابلِ اجرا نبود: psql بعد از نصبِ پیش‌فرضِ ویندوز
    # روی PATH نیست. psycopg تا این مرحله در venv هست، پس مستقیم انجامش می‌دهیم.
    if code == ADMIN_LOGIN_FAILED:
        secret = ctx.ask_password(
            "The database does not exist yet. Creating it needs the PostgreSQL admin "
            "password — the one set for the \"postgres\" user during installation."
        )
        if secret:
            # از راهِ محیط، نه آرگومانِ خطِ فرمان: libpq آن را می‌خواند و رمز در
            # فهرستِ پروسه‌ها — که کاربرانِ دیگر هم می‌بینند — ظاهر نمی‌شود.
            code = ctx.run(
                [interpreter, "-m", "scripts.ensure_database"],
                cwd=ctx.paths.backend,
                env=child_environment({"PGPASSWORD": secret}),
            )

    if code != 0:
        return Outcome(
            False,
            "the application database is not available",
            Remedy(
                "NexaHR could not create its database",
                "If you have pgAdmin (installed alongside PostgreSQL), create a role "
                "\"nexahr\" with password \"nexahr_dev_password\" and a database \"nexahr\" "
                "owned by it. Otherwise run these from the PostgreSQL bin folder, usually "
                "C:\\Program Files\\PostgreSQL\\16\\bin. If your credentials differ, edit "
                "DATABASE_URL in backend\\.env instead.",
                commands=[
                    "psql -U postgres -c \"CREATE ROLE nexahr LOGIN PASSWORD 'nexahr_dev_password';\"",
                    "psql -U postgres -c \"CREATE DATABASE nexahr OWNER nexahr;\"",
                ],
            ),
        )
    return Outcome(True, f"available on {host}:{port}")


# ---------------------------------------------------------------------------
#  ۶. مایگریشن
# ---------------------------------------------------------------------------

def apply_migrations(ctx: Context) -> Outcome:
    if ctx.run([str(ctx.paths.venv_python), "-m", "alembic", "upgrade", "head"], cwd=ctx.paths.backend) != 0:
        return Outcome(
            False,
            "alembic upgrade head failed",
            Remedy(
                "The database schema could not be brought up to date",
                "The database exists and is reachable, so this is a migration error rather "
                "than a connection problem. The log above names the failing revision.",
            ),
        )
    return Outcome(True, "schema is up to date")


# ---------------------------------------------------------------------------
#  ۷. وابستگی‌های فرانت‌اند
# ---------------------------------------------------------------------------

def ensure_frontend_packages(ctx: Context) -> Outcome:
    if ctx.paths.node_modules.exists():
        return Outcome(True, "already installed")
    ctx.say("running npm install (this can take a few minutes)")
    if ctx.run([npm_command(), "install"], cwd=ctx.paths.frontend) != 0:
        return Outcome(
            False,
            "npm install failed",
            Remedy(
                "Installing the frontend packages did not finish",
                "As with pip, the usual cause is no internet access or a proxy in the way. "
                "The log above has the exact error.",
            ),
        )
    return Outcome(True, "installed")


# ---------------------------------------------------------------------------
#  ۸. پورت‌ها
# ---------------------------------------------------------------------------

def choose_ports(ctx: Context) -> Outcome:
    """پورتی که بشود رویش listen کرد — نه لزوماً پورتی که دوست داریم.

    این همان جایی است که «بک‌اند روی ۸۰۰۰ بالا نمی‌آید» حل می‌شود: یا پورت را از
    بازماندهٔ اجرای قبلیِ خودمان پس می‌گیریم، یا می‌رویم روی پورتِ بعدی و مقصدِ
    پروکسیِ Vite را با خودمان می‌بریم. توضیحِ ماجرا در `ports.choose` است.
    """
    backend = portlib.choose(DEFAULT_BACKEND_PORT, root=ctx.paths.root)
    ctx.notes += backend.story
    ctx.advice += backend.advice
    if not backend.ok:
        return Outcome(
            False,
            f"no usable port near {DEFAULT_BACKEND_PORT}",
            Remedy(
                "Could not find a free port for the backend",
                "\n".join(backend.story),
                commands=backend.advice,
            ),
        )

    frontend = portlib.choose(DEFAULT_FRONTEND_PORT, root=ctx.paths.root)
    ctx.notes += frontend.story
    ctx.advice += frontend.advice
    if not frontend.ok:
        return Outcome(
            False,
            f"no usable port near {DEFAULT_FRONTEND_PORT}",
            Remedy(
                "Could not find a free port for the web app",
                "\n".join(frontend.story),
                commands=frontend.advice,
            ),
        )

    ctx.backend_port, ctx.frontend_port = backend.port, frontend.port
    moved = " (moved)" if backend.moved or frontend.moved else ""
    return Outcome(True, f"backend {backend.port}, web {frontend.port}{moved}")


@dataclass(frozen=True)
class Step:
    key: str
    title: str
    run: Callable[[Context], Outcome]


PIPELINE: tuple[Step, ...] = (
    Step("toolchain", "Toolchain", check_toolchain),
    Step("venv", "Virtual environment", ensure_venv),
    Step("backend_packages", "Backend packages", ensure_backend_packages),
    Step("settings", "Settings file", ensure_settings),
    Step("database", "Database", ensure_database),
    Step("migrations", "Migrations", apply_migrations),
    Step("frontend_packages", "Web packages", ensure_frontend_packages),
    Step("ports", "Ports", choose_ports),
)


def new_context(log: Callable[[str, str], None], ask_password=lambda prompt: None) -> Context:
    return Context(paths=locate(), log=log, ask_password=ask_password)


__all__ = [
    "Context",
    "Outcome",
    "PIPELINE",
    "Remedy",
    "Step",
    "database_endpoint",
    "new_context",
]
