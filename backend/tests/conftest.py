import os

# فایل `backend/.env` در تست خوانده نمی‌شود.
#
# آن فایل را راه‌انداز محیط توسعه می‌سازد و عمداً مقادیر دمو دارد
# (`MIN_COHORT_SIZE=1`، `SEED_DEMO_DATA=true`، آدرس‌های محلی). تا امروز همان
# مقادیر در تست هم اعمال می‌شدند: هر کس `setup_and_run` را اجرا کرده بود و بعد
# `pytest` می‌زد ۱۷ تست قرمز می‌دید که به تغییرات خودش ربطی نداشت. خطرناک‌تر
# این‌که تستِ سرکوبِ میانگینِ گروهِ کوچک با `MIN_COHORT_SIZE=1` بی‌صدا بی‌معنا
# می‌شد — یعنی گاردی که باید بسنجد، عملاً سنجیده نمی‌شد.
#
# این خط باید پیش از اولین import از `app` بیاید، چون `Settings` مسیر فایل را
# در زمان تعریف کلاس می‌خواند. زیرپروسه‌ها (alembic) هم همین را به ارث می‌برند.
os.environ.setdefault("NEXAHR_ENV_FILE", "")

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://nexahr:nexahr_dev_password@localhost:5432/nexahr_test"
)
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")
# زمان‌بند در تست عمداً خاموش است: هر تست خودش جاروها را صدا می‌زند و یک حلقهٔ
# پس‌زمینه فقط نویز و ناپایداری اضافه می‌کند.
os.environ.setdefault("ENABLE_SCHEDULER", "false")
# حسابِ مدیرِ خودکار در تست‌ها ساخته نمی‌شود: دیتابیس تست مشترک است و آن حساب
# commit می‌شود، پس بین تست‌ها می‌ماند و فرضِ «هیچ مدیری نیست» را می‌شکند.
os.environ.setdefault("BOOTSTRAP_ADMIN", "false")

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session", autouse=True)
def _migrate_test_db():
    subprocess.run(["alembic", "upgrade", "head"], cwd=BACKEND_DIR, check=True)


@pytest.fixture()
def db_session():
    from app.core.config import settings

    engine = create_engine(settings.database_url)
    connection = engine.connect()
    outer_transaction = connection.begin()
    session_factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
    session = session_factory()

    yield session

    session.close()
    outer_transaction.rollback()
    connection.close()
    engine.dispose()


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """سطل محدودیت نرخِ per-IP بین تست‌ها ریست می‌شود.

    همهٔ تست‌ها از یک آدرس (testclient) درخواست می‌زنند، پس بدون این، هر تستی که به
    /api/auth/login می‌زند سهمیهٔ تست‌های بعدی را می‌سوزاند و شکست‌ها به ترتیب اجرا
    وابسته می‌شوند. تست خودِ محدودیت نرخ سالم می‌ماند چون سهمیه‌اش را در یک تست
    مصرف می‌کند.
    """
    from app.core.rate_limit import limiter

    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture()
def no_cohort_suppression():
    """سرکوب کوهورت حداقلی (P1-08) را برای این تست خاموش می‌کند.

    تست‌هایی که *ریاضیِ* تجمیع را می‌سنجند با دو-سه رکورد کار می‌کنند، یعنی زیر آستانه
    می‌افتند و میانگینشان درست و حسابی سرکوب می‌شود. آن‌ها به عدد نیاز دارند، نه به
    رفتار سرکوب — رفتار سرکوب خودش در test_cohort_suppression.py تست می‌شود.
    عمداً autouse نیست: پیش‌فرض باید همان رفتار واقعی بماند.
    """
    from app.core.config import settings

    original = settings.min_cohort_size
    settings.min_cohort_size = 1
    yield
    settings.min_cohort_size = original


@pytest.fixture()
def client(db_session):
    from app.db.session import get_db
    from app.main import app

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def employee_view_on(db_session):
    """سه ماژولِ «نمایِ خودِ کارمند» را صریح روشن می‌کند.

    پیش‌فرضِ هر سه *خاموش* است (`core/modules.py`)، و از وقتی سوییچ‌ها واقعاً
    اعمال می‌شوند این دیگر یک جزئیاتِ بی‌اثر نیست: تستی که رؤیت یا اعتراض یا
    دیدنِ نتیجه را می‌سنجد باید خودش آن‌ها را روشن کند، وگرنه ۴۰۳ می‌گیرد و
    شکستش شبیه رگرسیونِ گردش‌کار به‌نظر می‌رسد.

    تا امروز همان تست‌ها سبز بودند چون گاردی وجود نداشت — یعنی سبزیِ‌شان
    ثابت می‌کرد سوییچ کار *نمی‌کند*.
    """
    from tests.helpers import set_module

    for key in (
        "employee_evaluation_visibility",
        "employee_result_acknowledgement",
        "objections",
    ):
        set_module(db_session, key, True)
    db_session.commit()
