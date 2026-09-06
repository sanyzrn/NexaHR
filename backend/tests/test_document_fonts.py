"""سندِ رسمی باید کاملاً با فونتِ خودش چاپ شود، نه با فونتِ سیستمِ اجرا.

زیرمجموعهٔ عربیِ Vazirmatn هیچ رقمِ ASCII و هیچ `+`/`-`/`—`/`/` و هیچ حرفِ
لاتینی ندارد، پس همهٔ آن‌ها به فونتِ سیستم می‌افتادند. `url_fetcher` منابعِ
بیرونی را می‌بندد ولی fallbackِ فونت واکشی نیست و از آن گارد رد می‌شود — یعنی
ظاهرِ مدرکی که هش و QR دارد به ایمیجِ اجرا بند بود.
"""
import re
import zlib

import pytest

from app.services.pdf import fa_digits, render_evaluation_summary_pdf, weasyprint_available

pytestmark = pytest.mark.skipif(
    not weasyprint_available(), reason="WeasyPrint در این محیط نصب نیست"
)

SNAPSHOT = {
    "evaluation_code": "EVL-0427",
    "personnel": {
        "full_name": "زهرا محمدی",
        "job_title": "کارشناس مالی",
        "org_unit": "مالی",
        "personnel_code": "10427",
    },
    "evaluator": {"username": "m.rezaei", "role_label": "مسئول واحد"},
    "evaluation_started_at": "2026-08-01T06:30:00+00:00",
    "finalized_at": "2026-09-06T01:10:00+00:00",
    "general_score_pct": 82.5,
    "specialized_score_pct": 91.0,
    "base_weighted_pct": 86.75,
    "final_weighted_pct": 89.75,
    "bonus_points": 3,
    "bonus_reason": "پروژهٔ بستنِ سالِ مالی",
    "recommendation": "ادامهٔ همکاری",
    "evaluator_comment": "عملکرد مطلوب",
    "single_decider": False,
    "signatories": [
        {"seat": "unit_supervisor_user_id", "label": "مسئول واحد", "user_id": 1},
        {"seat": "hr_user_id", "label": "منابع انسانی", "user_id": 2},
        {"seat": "ceo_user_id", "label": "مدیرعامل", "user_id": 3},
    ],
    "scores": [
        {
            "indicator_id": 1,
            "category": "همکاری",
            "description": "همکاری تیمی",
            "section": "general",
            "score": 4,
            "evidence_text": None,
        }
    ],
    "self_assessment": {
        "submitted_at": "2026-08-20T08:00:00+00:00",
        "note": "سالِ پرکاری بود",
        "rows": [
            {
                "indicator_id": 1,
                "category": "همکاری",
                "description": "همکاری تیمی",
                "self_score": 5,
                "evaluator_score": 4,
                "gap": 1,
                "note": None,
            }
        ],
    },
    "comments": [
        {"stage": "hr_review", "commenter_user_id": 2, "comment_text": "تأیید شد"}
    ],
}


def _embedded_fonts(pdf_bytes: bytes) -> set[str]:
    """نامِ هر فونتِ تعبیه‌شده در خروجی — از `/BaseFont` داخلِ streamهای فشرده."""
    blobs = [pdf_bytes]
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf_bytes, re.S):
        try:
            blobs.append(zlib.decompress(match.group(1)))
        except zlib.error:
            continue
    names: set[bytes] = set()
    for blob in blobs:
        names |= set(re.findall(rb"/BaseFont\s*/[A-Z]{6}\+([A-Za-z0-9\- ]+)", blob))
    return {name.decode() for name in names}


def test_the_document_embeds_nothing_but_vazirmatn():
    """پیش از این DejaVu-Sans و DejaVu-Sans-Bold هم تعبیه می‌شدند."""
    fonts = _embedded_fonts(render_evaluation_summary_pdf(SNAPSHOT, verify_url="https://x/v/AB12"))
    assert fonts, "هیچ فونتی تعبیه نشده — یعنی سنجش بی‌معنا شده"
    outsiders = {name for name in fonts if not name.startswith("Vazirmatn")}
    assert outsiders == set(), f"فونتِ بیرون از خانوادهٔ سند: {sorted(outsiders)}"


def test_the_latin_half_is_actually_used():
    """نامِ کاربری و کدِ پرونده لاتین‌اند و باید از نیمهٔ لاتینِ *همین* فونت بیایند."""
    fonts = _embedded_fonts(render_evaluation_summary_pdf(SNAPSHOT, verify_url="https://x/v/AB12"))
    assert any("Latin" in name for name in fonts), fonts


# ── و ارقامِ متن، فارسی ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        (82.5, "۸۲٫۵"),
        (100, "۱۰۰"),
        (0, "۰"),
        ("+3", "+۳"),
        ("-1", "-۱"),
        (None, "—"),
    ],
)
def test_fa_digits(value, expected):
    assert fa_digits(value) == expected


def test_identifiers_stay_latin():
    """کدِ پرونده و کدِ پرسنلی برچسب‌اند، نه عدد: باید همان‌طور چاپ شوند که
    در سامانه جست‌وجو می‌شوند."""
    from app.services.pdf import _env

    html = _env.get_template("evaluation_summary.html").render(
        snapshot=SNAPSHOT, verify_url=None, verify_qr=None, stage_labels={}
    )
    assert "EVL-0427" in html
    assert "10427" in html
    assert "m.rezaei" in html
    # ولی نمره‌ها فارسی‌اند
    assert "۸۲٫۵٪" in html, "امتیاز عمومی باید با ارقام فارسی چاپ شود"
    assert "82.5" not in html
