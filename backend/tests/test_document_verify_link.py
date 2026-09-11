"""لینکِ تأییدِ اصالت، داخلِ خودِ سندِ امضاشده.

سند یک QR و یک آدرس چاپ می‌کند که ادعا می‌کنند «این مدرک را می‌شود تأیید
کرد». زنجیره‌اش سه حلقه دارد:

    record.verify_token → verify_url_for() → qr_data_uri() → داخلِ PDF

حلقهٔ اول و آخر تست داشتند (`test_documents.py` خودِ endpointِ عمومی را
می‌سنجد، و توکن روی پرونده ادعا می‌شود) ولی *وصلِ بینشان* نه: هر دو تستِ
رندر، `verify_url=None, verify_qr=None` پاس می‌دادند. یعنی جهشِ
`verify_qr=None` در `pdf.py` — یا برگرداندنِ `/verify/wrong` از
`verify_url_for` — کلِ مجموعه را سبز رد می‌کرد و سند با QRِ غلط یا بی QR
چاپ می‌شد، بی آنکه چیزی صدا در بیاورد.

روی مدرکی که هش می‌شود و بایگانی، «قابلِ تأیید بودن» یک ادعای روی کاغذ است.
این فایل همان ادعا را می‌سنجد.
"""
import base64
import re

from app.core.config import settings
from app.services.documents import verify_url_for
from app.services.pdf import build_evaluation_summary_html, qr_data_uri

_TOKEN = "Xq7" + "a" * 29  # ۳۲ نویسه، شبیهِ خروجیِ token_urlsafe(24)

SNAPSHOT = {
    "version": 6,
    "evaluation_code": "EVL-0142",
    "personnel": {"full_name": "کارمند تست", "personnel_code": "P-1", "org_unit": "واحد"},
    "evaluator": {"role_label": "مسئول واحد", "display_name": "ارزیاب"},
    "scores": [],
    "comments": [],
    "self_assessment": None,
    "signatories": [],
    "single_decider": False,
}


def _render(verify_url: str | None) -> str:
    """*همان* تابعی که رندرِ واقعی صدا می‌زند — و نه یک بازسازیِ آن.

    اگر این‌جا قالب را خودمان render می‌کردیم، جهشِ `verify_qr=None` در
    `pdf.py` از تست رد می‌شد: تست، ساختِ QR را خودش انجام می‌داد. همان دامی
    که تستِ قبلیِ «بلعیدنِ خطای رندر» در آن افتاده بود.
    """
    return build_evaluation_summary_html(SNAPSHOT, verify_url)


def test_the_url_is_built_from_the_public_base_and_the_token():
    url = verify_url_for(_TOKEN)
    assert url == f"{settings.public_base_url.rstrip('/')}/verify/{_TOKEN}"
    assert url.endswith(f"/verify/{_TOKEN}")
    # کدِ ترتیبیِ پرونده هرگز روی endpointِ عمومی نمی‌رود.
    assert "EVL-" not in url


def test_the_document_prints_the_url_and_a_qr_that_decodes_to_it():
    url = verify_url_for(_TOKEN)
    html = _render(url)

    # آدرس، خوانا و کامل روی سند.
    assert url in html, "آدرسِ تأیید روی سند چاپ نشد"

    # و QR — که *همان* آدرس را در خود دارد، نه چیزِ دیگری.
    match = re.search(r'src="data:image/png;base64,([A-Za-z0-9+/=]+)"', html)
    assert match, "تصویرِ QR در سند نیست"
    png = base64.b64decode(match.group(1))
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert png == base64.b64decode(qr_data_uri(url).split(",", 1)[1]), (
        "QRِ چاپ‌شده با آدرسِ تأیید ساخته نشده"
    )
    # و QRِ آدرسِ دیگری با این یکی فرق دارد — یعنی ادعای بالا توخالی نیست.
    assert png != base64.b64decode(qr_data_uri(url + "x").split(",", 1)[1])


def test_a_record_without_a_token_prints_no_verification_claim():
    """پروندهٔ خیلی قدیمی که هرگز backfill نشده: به‌جای لینکِ شکسته، هیچ.

    `documents.archive_final_pdf` وقتی `verify_token` خالی است `verify_url`
    نمی‌سازد — تا کدِ ترتیبیِ پرونده روی endpointِ عمومی نیفتد.
    """
    html = _render(None)
    assert "/verify/" not in html
    assert "data:image/png;base64," not in html
