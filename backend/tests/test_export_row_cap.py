"""هیچ خروجیِ Excelی بی‌سقف ساخته نمی‌شود — و بریدگی سکوت نمی‌کند.

این فایل‌ها روی نخِ درخواست و کاملاً در حافظه ساخته می‌شوند. بی سقف، یک
«خروجی اکسل»ِ بی‌فیلتر در پایانِ دوره یک worker و یک اتصالِ دیتابیس را برای
دقیقه‌ها می‌گیرد — همان استخری که به بقیهٔ کاربران خدمت می‌دهد.

گزارشِ رویدادها از ابتدا سقف داشت و چهار خروجیِ دیگر نداشتند. بدترین حالت
هم سقفِ *ساکت* بود: HR فایلی می‌گیرد که کامل به‌نظر می‌رسد و نیست، و تصمیمِ
دوره را روی نمونه‌ای می‌گیرد که خودش نمی‌داند نمونه است.
"""
from io import BytesIO

import pytest
from openpyxl import load_workbook

from app.models.enums import Capability
from app.services.authorization import DEFAULT_HR_CAPABILITIES
from app.services.excel import (
    EXPORT_MAX_ROWS,
    EXPORT_TRUNCATED_NOTE,
    build_personnel_workbook,
    cap_rows,
    note_truncation,
)
from tests.helpers import auth_header, make_personnel, make_user

# ── خودِ قاعده ─────────────────────────────────────────────────────────────


def test_cap_rows_keeps_the_cap_and_reports_the_overflow():
    """ردیفِ `+۱`ِ اضافه تنها راهِ تشخیصِ «دقیقاً به سقف خورد» از «بیشتر بود» است."""
    exactly = list(range(EXPORT_MAX_ROWS))
    rows, truncated = cap_rows(exactly)
    assert len(rows) == EXPORT_MAX_ROWS
    assert truncated is False

    one_more = list(range(EXPORT_MAX_ROWS + 1))
    rows, truncated = cap_rows(one_more)
    assert len(rows) == EXPORT_MAX_ROWS
    assert truncated is True


def test_cap_rows_leaves_a_small_result_alone():
    rows, truncated = cap_rows([1, 2, 3])
    assert rows == [1, 2, 3]
    assert truncated is False


def test_the_note_travels_with_the_file():
    """هشدار روی خودِ فایل می‌نشیند، نه فقط در هدرِ پاسخ.

    فایلِ Excel دست‌به‌دست می‌شود؛ کسی که آن را در جلسه باز می‌کند هدرِ HTTP
    را ندیده است.
    """
    plain = build_personnel_workbook([])
    noted = note_truncation(plain)

    sheet = load_workbook(BytesIO(noted)).worksheets[0]
    texts = [str(c.value) for row in sheet.iter_rows() for c in row if c.value]
    assert any(EXPORT_TRUNCATED_NOTE in t for t in texts), texts
    # و فایلِ بی‌بریدگی این جمله را ندارد
    plain_sheet = load_workbook(BytesIO(plain)).worksheets[0]
    plain_texts = [str(c.value) for row in plain_sheet.iter_rows() for c in row if c.value]
    assert not any(EXPORT_TRUNCATED_NOTE in t for t in plain_texts)


# ── و روی مسیرِ واقعی ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "/api/personnel/export.xlsx",
        "/api/evaluations/export.xlsx",
        "/api/users/export.xlsx",
        "/api/improvement-plans/export.xlsx",
        "/api/audit-log/export.xlsx",
    ],
)
def test_every_export_answers_without_a_full_table_scan(client, db_session, url):
    """هر پنج خروجی باید سقف‌دار باشند — این تست فهرست را کامل نگه می‌دارد.

    اگر خروجیِ تازه‌ای اضافه شود و این‌جا نیاید، خودِ تستِ بعدی
    (`test_no_export_is_uncapped`) می‌گیردش.
    """
    # `view_audit_log` جزوِ مجوزهای پیش‌فرضِ HR نیست و خروجیِ گزارشِ رویدادها
    # آن را لازم دارد.
    hr = make_user(db_session, "hr", capabilities=list(DEFAULT_HR_CAPABILITIES) + [Capability.view_audit_log])
    make_personnel(db_session)
    db_session.commit()

    response = client.get(url, headers=auth_header(hr))
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml"
    )


def test_no_export_is_uncapped():
    """هر endpointِ `export.xlsx` باید سقف را اعمال کند.

    فهرست‌کردنِ امروزی‌ها کافی نیست: خروجیِ ششم که فردا اضافه شود، همان اشکال
    را از نو می‌آورد. پس *قاعده* سنجیده می‌شود، مثل تستِ هدفِ لمسیِ فرانت.
    """
    import re
    from pathlib import Path

    routers = Path(__file__).resolve().parents[1] / "app" / "api" / "routers"
    offenders = []
    for path in sorted(routers.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        if '@router.get("/export.xlsx")' not in source:
            continue
        # بدنهٔ هر تابعِ خروجی، از دکوراتور تا دکوراتورِ بعدی
        for block in re.split(r"^@router\.", source, flags=re.M)[1:]:
            if not block.startswith('get("/export.xlsx")'):
                continue
            # معافیتِ اعلام‌شده در خودِ تابع — با دلیلی که همان‌جا نوشته شده.
            # (گزارش‌های تجمیعی ردیفِ خام ندارند و شمارشان به ساختارِ سازمان
            # بند است، نه به حجمِ داده.)
            if "EXPORT_ROW_CAP_NOT_APPLICABLE" in block:
                continue
            if "EXPORT_MAX_ROWS" not in block:
                offenders.append(path.name)

    assert offenders == [], (
        f"این خروجی‌ها سقفِ ردیف ندارند: {offenders}. "
        "از `cap_rows` و `EXPORT_MAX_ROWS` در `services/excel.py` استفاده کنید."
    )
