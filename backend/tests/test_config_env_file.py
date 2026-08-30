"""فایل `.env` محلی نباید تنظیماتِ تست را عوض کند.

چرا این تست هست
----------------
`backend/.env` را راه‌انداز محیط توسعه می‌سازد و عمداً مقادیر دمو دارد:
`MIN_COHORT_SIZE=1` تا نمودارهای داشبورد با دادهٔ کمِ نمونه خالی نمانند، و
`SEED_DEMO_DATA=true`. همان فایل در اجرای `pytest` هم خوانده می‌شد.

نتیجه‌اش دو چیز بود، و دومی بدتر از اولی:

۱. هر کس راه‌انداز را اجرا کرده بود و بعد تست می‌گرفت، ۱۷ تستِ قرمز می‌دید که
   هیچ‌کدام به تغییرات خودش ربطی نداشت.

۲. تستِ «میانگینِ گروهِ کوچک سرکوب می‌شود» با `MIN_COHORT_SIZE=1` بی‌صدا بی‌معنا
   می‌شد. یعنی همان گاردی که نمی‌گذارد «میانگینِ واحد» روی دو نفر خوانده شود،
   دقیقاً در جایی که باید سنجیده شود، سنجیده نمی‌شد.
"""
from __future__ import annotations

import os

from app.core import config


def test_the_test_run_reads_no_settings_file():
    # `conftest.py` این را پیش از اولین import از `app` خالی می‌کند.
    assert os.environ.get(config.ENV_FILE_VARIABLE) == ""
    assert config._ENV_FILE is None


def test_a_demo_settings_file_would_otherwise_win_over_the_defaults(tmp_path, monkeypatch):
    """اثباتِ این‌که مسئله واقعی بود، نه فرضی.

    همان فایل، یک‌بار با خواندن و یک‌بار بدونِ آن. اگر روزی کسی `env_file` را
    دوباره ثابت کند، این تست است که می‌گوید چه چیزی شکسته.
    """
    env_file = tmp_path / ".env"
    env_file.write_text("MIN_COHORT_SIZE=1\nSEED_DEMO_DATA=true\n", encoding="ascii")
    monkeypatch.chdir(tmp_path)

    # با خواندنِ فایل: سرکوبِ گروهِ کوچک عملاً خاموش می‌شود.
    assert config.Settings(_env_file=".env").min_cohort_size == 1

    # بدونِ آن: همان پیش‌فرضِ محافظه‌کارانه‌ای که تست‌ها رویش حساب می‌کنند.
    assert config.Settings(_env_file=None).min_cohort_size == 5


def test_explicit_environment_variables_still_win():
    # خاموش‌کردنِ فایل نباید راهِ تنظیمِ صریح را ببندد — `conftest` خودش
    # `DATABASE_URL` و `JWT_SECRET_KEY` را از همین راه می‌دهد.
    assert config.settings.database_url == os.environ["DATABASE_URL"]
