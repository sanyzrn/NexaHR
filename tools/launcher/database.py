"""عوض کردنِ دیتابیس، و گرفتن و برگرداندنِ نسخهٔ پشتیبان.

این ماژول عمداً به `psycopg` دست نمی‌زند. راه‌انداز با پایتونِ سیستم اجرا
می‌شود — چون خودش همان venv را می‌سازد — و هر پرسشی که کتابخانهٔ دیتابیس
می‌خواهد از `backend/scripts/db_info.py` رد می‌شود که داخلِ venv اجرا می‌گردد.
آنچه این‌جا می‌ماند سه چیزِ بی‌نیاز از درایور است: تجزیه و ساختِ آدرس، ویرایشِ
امنِ `backend/.env`، و صدا زدنِ `pg_dump`/`pg_restore`.

دربارهٔ پیدا کردنِ `pg_dump`
---------------------------
نصب‌کنندهٔ رسمیِ PostgreSQL روی ویندوز پوشهٔ `bin` را به PATH اضافه نمی‌کند. این
همان چیزی است که یک بار در `ensure_database.py` هزینه داد: راه‌انداز دستوری
چاپ می‌کرد (`psql -U postgres ...`) که خودش هم اجرا نمی‌شد. پس این‌جا هم فرض
نمی‌کنیم روی PATH است — دنبالش می‌گردیم، و اگر نبود همان را صریح می‌گوییم به
جای این‌که دستوری بدهیم که کار نمی‌کند.
"""
from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from .ports import WINDOWS
from .shell import Result, stream

DEFAULT_PORT = 5432
SCHEME = "postgresql+psycopg"

#: جایی که نسخه‌های پشتیبان می‌نشینند. کنارِ مخزن و نه داخلِ `backend/`، تا با
#: هیچ ابزارِ بسته‌بندی یا پاک‌سازیِ venv قاطی نشود.
BACKUP_DIRNAME = "backups"


@dataclass(frozen=True)
class Endpoint:
    """اجزای `DATABASE_URL`، به شکلی که بشود یکی‌شان را عوض کرد."""

    user: str = "nexahr"
    password: str = ""
    host: str = "localhost"
    port: int = DEFAULT_PORT
    name: str = "nexahr"

    @property
    def url(self) -> str:
        # کدگذاری درصدی اجباری است: رمزی که `@` یا `:` دارد، بدونِ آن آدرس را
        # از وسط می‌شکند. ضمناً همین باعث می‌شود فایلِ `.env` هرگز بایتِ
        # غیرِ ASCII نگیرد — که خودش یک اشکالِ جداگانه بود.
        user = quote(self.user, safe="")
        secret = f":{quote(self.password, safe='')}" if self.password else ""
        return f"{SCHEME}://{user}{secret}@{self.host}:{self.port}/{quote(self.name, safe='')}"

    @property
    def label(self) -> str:
        return f"{self.name} on {self.host}:{self.port}"

    @classmethod
    def parse(cls, url: str) -> Endpoint | None:
        """آدرس را بشکن. `None` یعنی این رشته اصلاً آدرسِ PostgreSQL نیست."""
        if not url or "://" not in url:
            return None
        parts = urlsplit(url)
        if not parts.scheme.startswith(("postgresql", "postgres")):
            return None
        try:
            port = parts.port or DEFAULT_PORT
        except ValueError:
            # پورتِ غیرعددی — `urlsplit` تازه موقعِ خواندنِ `.port` می‌ترکد.
            return None
        return cls(
            user=unquote(parts.username or "nexahr"),
            password=unquote(parts.password or ""),
            host=parts.hostname or "localhost",
            port=port,
            # نامِ دیتابیس هم مثلِ کاربر و رمز کدگشایی می‌شود. بدونِ این، آدرسی
            # که خودمان نوشته‌ایم را خودمان غلط می‌خوانیم: نامِ غیرِ ASCII
            # به‌صورتِ `%D9%BE...` برمی‌گردد و راه‌انداز همان را نشان می‌دهد و
            # همان را هم می‌سازد.
            name=unquote((parts.path or "/").lstrip("/")) or "nexahr",
        )

    def with_name(self, name: str) -> Endpoint:
        return replace(self, name=name.strip())


# ---------------------------------------------------------------------------
#  فایل تنظیمات
# ---------------------------------------------------------------------------

def read_setting(env_file: Path, key: str) -> str:
    if not env_file.exists():
        return ""
    for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        name, sep, value = stripped.partition("=")
        if sep and name.strip() == key:
            return value.strip()
    return ""


def write_setting(env_file: Path, key: str, value: str) -> None:
    """یک کلید را عوض کن و بقیهٔ فایل را دست‌نخورده بگذار.

    بازنویسیِ کاملِ فایل ساده‌تر بود ولی غلط: کاربر ممکن است `JWT_SECRET_KEY` یا
    تنظیماتِ دیگرِ خودش را آن‌جا داشته باشد، و یک «عوض کردنِ نامِ دیتابیس» نباید
    آن‌ها را ببرد.
    """
    lines = env_file.read_text(encoding="utf-8", errors="replace").splitlines() if env_file.exists() else []
    replaced = False
    for index, line in enumerate(lines):
        name, sep, _ = line.strip().partition("=")
        if sep and not line.strip().startswith("#") and name.strip() == key:
            lines[index] = f"{key}={value}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{key}={value}")
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def current_endpoint(env_file: Path) -> Endpoint:
    return Endpoint.parse(read_setting(env_file, "DATABASE_URL")) or Endpoint()


def apply_endpoint(env_file: Path, endpoint: Endpoint) -> None:
    write_setting(env_file, "DATABASE_URL", endpoint.url)


# ---------------------------------------------------------------------------
#  ابزارهای خطِ فرمانِ PostgreSQL
# ---------------------------------------------------------------------------

_WINDOWS_ROOTS = (r"C:\Program Files\PostgreSQL", r"C:\Program Files (x86)\PostgreSQL")
_POSIX_ROOTS = ("/usr/lib/postgresql", "/usr/local/pgsql", "/opt/homebrew/opt")


def _version_key(path: Path) -> tuple[int, str]:
    """پوشهٔ نسخه را عددی مرتب کن تا «۹» بعد از «۱۶» نیاید."""
    name = path.parent.parent.name
    digits = "".join(ch for ch in name if ch.isdigit())
    return (int(digits) if digits else 0, str(path))


def find_tool(name: str) -> str:
    """مسیرِ `pg_dump` و برادرانش. رشتهٔ خالی یعنی پیدا نشد."""
    found = shutil.which(name)
    if found:
        return found

    executable = f"{name}.exe" if WINDOWS else name
    candidates: list[Path] = []
    for root in _WINDOWS_ROOTS if WINDOWS else _POSIX_ROOTS:
        base = Path(root)
        if not base.is_dir():
            continue
        candidates += [path for path in base.glob(f"*/bin/{executable}") if path.is_file()]
    if not candidates:
        return ""
    return str(sorted(candidates, key=_version_key)[-1])


MISSING_TOOLS = (
    "PostgreSQL's command-line tools were not found. The official Windows installer "
    "does not add its bin folder to PATH, so this is normal — reinstall PostgreSQL "
    "with the \"Command Line Tools\" component ticked, or add its bin folder "
    "(usually C:\\Program Files\\PostgreSQL\\16\\bin) to PATH."
)


# ---------------------------------------------------------------------------
#  پشتیبان‌گیری و بازگردانی
# ---------------------------------------------------------------------------

def _environment(endpoint: Endpoint) -> dict[str, str]:
    # رمز از راهِ محیط می‌رود و نه آرگومان: آرگومان‌ها در فهرستِ پروسه‌ها دیده
    # می‌شوند، که یعنی هر کاربرِ دیگری روی همان ماشین می‌تواند بخواندشان.
    env = dict(os.environ)
    if endpoint.password:
        env["PGPASSWORD"] = endpoint.password
    return env


def _connection_flags(endpoint: Endpoint) -> list[str]:
    return ["--host", endpoint.host, "--port", str(endpoint.port), "--username", endpoint.user, "--no-password"]


def backup_path(root: Path, endpoint: Endpoint) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return root / BACKUP_DIRNAME / f"{endpoint.name}-{stamp}.dump"


def backup(endpoint: Endpoint, destination: Path, log: Callable[[str], None]) -> Result:
    """یک نسخهٔ کاملِ دیتابیس، در قالبِ فشردهٔ خودِ PostgreSQL.

    `--no-owner` و `--no-privileges` عمدی‌اند: بدونشان، فایل به نامِ نقش‌های همین
    ماشین گره می‌خورد و برگرداندنش روی نصبِ دیگری (یا حتی روی دیتابیسی با نامِ
    دیگر) با خطاهای مالکیت پر می‌شود.
    """
    tool = find_tool("pg_dump")
    if not tool:
        return Result(False, MISSING_TOOLS)

    destination.parent.mkdir(parents=True, exist_ok=True)
    code = stream(
        [tool, *_connection_flags(endpoint), "--dbname", endpoint.name,
         "--format=custom", "--no-owner", "--no-privileges", "--file", str(destination)],
        env=_environment(endpoint), log=log,
    )
    if code != 0:
        # فایلِ نیمه‌نوشته بدتر از نبودنِ فایل است: بعداً شبیهِ یک پشتیبانِ سالم
        # دیده می‌شود و فقط موقعِ برگرداندن معلوم می‌شود که نیست.
        destination.unlink(missing_ok=True)
        return Result(False, "pg_dump failed — the log has the exact error.")
    if not destination.is_file():
        # کدِ خروجِ صفر ولی فایلی در کار نیست. نباید پیش بیاید، ولی اگر بیاید
        # باید همین‌جا گفته شود: یک «پشتیبان گرفته شد»ِ دروغ، دقیقاً همان روزی
        # کشف می‌شود که کسی به آن نیاز دارد.
        return Result(False, "pg_dump reported success but wrote no file.")
    size = destination.stat().st_size
    return Result(True, f"Saved {size // 1024:,} KB to {destination.name}", destination)


def restore(endpoint: Endpoint, source: Path, log: Callable[[str], None]) -> Result:
    """محتوای فعلیِ دیتابیس را با فایلِ پشتیبان جایگزین کن.

    این کار برگشت‌ناپذیر است — `--clean` یعنی هرچه هست اول حذف می‌شود — پس
    فراخوان باید پیش از رسیدن به این‌جا تأییدِ صریح گرفته باشد و سرورها را
    خوابانده باشد: یک اتصالِ باز کافی است تا حذفِ جدول‌ها گیر کند.
    """
    tool = find_tool("pg_restore")
    if not tool:
        return Result(False, MISSING_TOOLS)
    if not source.is_file():
        return Result(False, f"No such backup file: {source}")

    code = stream(
        [tool, *_connection_flags(endpoint), "--dbname", endpoint.name,
         "--clean", "--if-exists", "--no-owner", "--no-privileges", str(source)],
        env=_environment(endpoint), log=log,
    )
    if code != 0:
        return Result(
            False,
            "pg_restore reported errors. Some are harmless (it tries to drop objects that "
            "were never there), so check the log before assuming the data did not arrive.",
        )
    return Result(True, f"Restored from {source.name}")


def backups(root: Path) -> list[Path]:
    """نسخه‌های پشتیبانِ موجود، تازه‌ترین اول."""
    folder = root / BACKUP_DIRNAME
    if not folder.is_dir():
        return []
    return sorted(folder.glob("*.dump"), key=lambda path: path.stat().st_mtime, reverse=True)
