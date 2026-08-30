"""تست‌های عوض کردنِ دیتابیس و فایلِ تنظیمات.

دو چیز این‌جا سنجیده می‌شود که شکستنشان بی‌صداست: آدرسی که رمزش را نصفه
می‌فهمد، و ویرایشی که بقیهٔ فایل را می‌برد. هیچ‌کدام موقعِ خودِ عمل خطا
نمی‌دهند — بعداً، وقتی چیزِ دیگری کار نکند، معلوم می‌شوند.
"""
from __future__ import annotations

import pytest

from tools.launcher import database as db

# ── تجزیه و ساختِ آدرس ──────────────────────────────────────────────────

def test_a_plain_url_is_split_into_its_parts():
    endpoint = db.Endpoint.parse("postgresql+psycopg://nexahr:pw@localhost:5432/nexahr")
    assert endpoint == db.Endpoint(user="nexahr", password="pw", host="localhost", port=5432, name="nexahr")


def test_a_missing_port_falls_back_to_the_postgres_default():
    endpoint = db.Endpoint.parse("postgresql+psycopg://nexahr:pw@db.internal/dbsp")
    assert endpoint and endpoint.port == 5432 and endpoint.name == "dbsp"


def test_a_password_with_punctuation_survives_the_round_trip():
    # `@` و `:` داخلِ رمز، آدرس را از وسط می‌شکنند اگر کدگذاری نشوند. رمزی که
    # نصفه خوانده شود یعنی «رمز اشتباه است» — و کاربر دنبالِ رمز می‌گردد نه
    # دنبالِ باگِ ما.
    original = db.Endpoint(user="ne@xa", password="p@ss:word/1", host="localhost", port=5432, name="dbsp")
    again = db.Endpoint.parse(original.url)
    assert again == original


def test_a_url_is_always_ascii_even_when_the_name_is_not():
    # فایلِ `.env` باید ASCII بماند: خوانندهٔ غیرِ UTF-8 با یک بایتِ فارسی
    # بک‌اند را پیش از bind شدنِ پورت می‌کشد.
    url = db.Endpoint(name="پایگاه").url
    assert url.isascii()
    assert db.Endpoint.parse(url).name == "پایگاه"


@pytest.mark.parametrize("value", ["", "not a url", "mysql://root@localhost/x", "postgresql://h:notaport/x"])
def test_something_that_is_not_a_postgres_url_is_rejected(value):
    assert db.Endpoint.parse(value) is None


def test_changing_only_the_name_keeps_the_credentials():
    original = db.Endpoint(user="me", password="secret", host="10.0.0.5", port=6543, name="nexahr")
    moved = original.with_name("  dbsp  ")
    assert moved.name == "dbsp"
    assert (moved.user, moved.password, moved.host, moved.port) == ("me", "secret", "10.0.0.5", 6543)


# ── ویرایشِ فایلِ تنظیمات ────────────────────────────────────────────────

SETTINGS = """\
# NexaHR - local development settings

ENVIRONMENT=development
DATABASE_URL=postgresql+psycopg://nexahr:pw@localhost:5432/nexahr
JWT_SECRET_KEY=my-own-secret
MIN_COHORT_SIZE=1
"""


def test_changing_one_key_leaves_every_other_line_alone(tmp_path):
    # بازنویسیِ کاملِ فایل ساده‌تر بود و غلط: کاربر ممکن است کلید یا تنظیمِ
    # خودش را آن‌جا داشته باشد، و «عوض کردنِ نامِ دیتابیس» نباید آن را ببرد.
    env = tmp_path / ".env"
    env.write_text(SETTINGS)
    db.write_setting(env, "DATABASE_URL", "postgresql+psycopg://nexahr:pw@localhost:5432/dbsp")

    text = env.read_text()
    assert "JWT_SECRET_KEY=my-own-secret" in text
    assert "MIN_COHORT_SIZE=1" in text
    assert text.startswith("# NexaHR - local development settings")
    assert text.count("DATABASE_URL=") == 1
    assert "/dbsp" in text


def test_a_key_that_is_not_there_yet_is_appended(tmp_path):
    env = tmp_path / ".env"
    env.write_text("ENVIRONMENT=development\n")
    db.write_setting(env, "DATABASE_URL", "postgresql+psycopg://a@b:5432/c")
    assert db.read_setting(env, "DATABASE_URL") == "postgresql+psycopg://a@b:5432/c"
    assert db.read_setting(env, "ENVIRONMENT") == "development"


def test_a_commented_out_key_is_not_mistaken_for_the_real_one(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# DATABASE_URL=postgresql+psycopg://old@host:5432/old\nENVIRONMENT=development\n")
    db.write_setting(env, "DATABASE_URL", "postgresql+psycopg://a@b:5432/c")

    text = env.read_text()
    # کامنت باید دست‌نخورده بماند و مقدارِ تازه جداگانه اضافه شود.
    assert "# DATABASE_URL=postgresql+psycopg://old@host:5432/old" in text
    assert db.read_setting(env, "DATABASE_URL") == "postgresql+psycopg://a@b:5432/c"


def test_reading_a_file_that_is_not_there_gives_the_built_in_defaults(tmp_path):
    endpoint = db.current_endpoint(tmp_path / "nope.env")
    assert endpoint.name == "nexahr" and endpoint.port == 5432


def test_writing_then_reading_the_endpoint_round_trips(tmp_path):
    env = tmp_path / ".env"
    env.write_text(SETTINGS)
    target = db.Endpoint(user="me", password="p@ss", host="10.0.0.5", port=6543, name="dbsp")
    db.apply_endpoint(env, target)
    assert db.current_endpoint(env) == target
    assert env.read_text().isascii()


# ── پیدا کردنِ ابزارهای PostgreSQL ───────────────────────────────────────

def test_newer_postgres_installs_win_over_older_ones(tmp_path):
    # مرتب‌سازیِ متنی «۹» را بعد از «۱۶» می‌گذارد، و آن‌وقت راه‌انداز با
    # `pg_dump` ۹ به سرورِ ۱۶ وصل می‌شود و pg_dump با «server version mismatch»
    # رد می‌کند.
    paths = []
    for version in ("9", "16", "14"):
        binary = tmp_path / version / "bin" / "pg_dump"
        binary.parent.mkdir(parents=True)
        binary.touch()
        paths.append(binary)
    assert max(paths, key=db._version_key).parent.parent.name == "16"


def test_backup_says_what_is_missing_instead_of_failing_silently(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "find_tool", lambda name: "")
    result = db.backup(db.Endpoint(), tmp_path / "out.dump", lambda line: None)
    assert not result.ok
    assert "PATH" in result.message  # می‌گوید چرا، نه فقط «نشد»


def test_restoring_a_file_that_is_not_there_is_refused_before_anything_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "find_tool", lambda name: "/usr/bin/pg_restore")
    monkeypatch.setattr(db, "stream", lambda *a, **k: pytest.fail("pg_restore should not have run"))
    result = db.restore(db.Endpoint(), tmp_path / "missing.dump", lambda line: None)
    assert not result.ok


def test_a_failed_backup_leaves_no_half_written_file(tmp_path, monkeypatch):
    # فایلِ نیمه‌نوشته بدتر از نبودنِ فایل است: بعداً شبیهِ پشتیبانِ سالم دیده
    # می‌شود و فقط موقعِ برگرداندن معلوم می‌شود که نیست.
    destination = tmp_path / "out.dump"

    def fake_stream(argv, **kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"half")
        return 1

    monkeypatch.setattr(db, "find_tool", lambda name: "/usr/bin/pg_dump")
    monkeypatch.setattr(db, "stream", fake_stream)

    result = db.backup(db.Endpoint(), destination, lambda line: None)
    assert not result.ok
    assert not destination.exists()


def test_the_password_never_reaches_the_command_line(tmp_path, monkeypatch):
    # آرگومان‌ها در فهرستِ پروسه‌ها دیده می‌شوند؛ محیط نه.
    seen: dict = {}

    def fake_stream(argv, *, env=None, log=None, **kwargs):
        seen["argv"] = list(argv)
        seen["env"] = env or {}
        (tmp_path / "x.dump").write_bytes(b"dump")
        return 0

    monkeypatch.setattr(db, "find_tool", lambda name: "/usr/bin/pg_dump")
    monkeypatch.setattr(db, "stream", fake_stream)
    endpoint = db.Endpoint(password="hunter2-secret")

    db.backup(endpoint, tmp_path / "x.dump", lambda line: None)

    assert "hunter2-secret" not in " ".join(seen["argv"])
    assert seen["env"].get("PGPASSWORD") == "hunter2-secret"
