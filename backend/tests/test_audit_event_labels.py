"""هر رویدادی که سامانه می‌نویسد، باید در هر دو طرف برچسبِ فارسی داشته باشد.

این آزمون یک بازبینیِ دستی را به یک قفلِ دائمی تبدیل می‌کند. آن بازبینی سه عدد
پیدا کرد که قرار بود یکی باشند: ۷۹ نوع رویداد در بک‌اند، ۴۳ برچسب در
`routers/audit_log.py` و ۴۵ در `frontend/src/types.ts` — با کامنتی بالای اولی
که ادعا می‌کرد «هم‌راستا با فرانت‌اند» است.

سه مجموعه دوطرفه سنجیده می‌شوند، و «دوطرفه» عمدی است: برچسبِ یتیم هم اشکال
است، چون یعنی یا رویدادی حذف شده و کسی برچسبش را برنداشته، یا اسمِ رویداد
تایپی دارد و آن برچسب هیچ‌وقت نمایش داده نمی‌شود. یکی از همان یتیم‌ها
(`audit_log_excel_exported`) نشان داد خروجیِ اکسلِ گزارشِ رویدادها — تنها
خروجی‌ای که کلِ ممیزی را از سامانه بیرون می‌برد — خودش را ثبت نمی‌کرد.
"""
import re
from pathlib import Path

import pytest

from app.services.audit_events import EVENT_LABELS

BACKEND = Path(__file__).resolve().parent.parent
FRONTEND_TYPES = BACKEND.parent / "frontend" / "src" / "types.ts"


def _event_types_written_by_the_code() -> set[str]:
    """هر `event_type="..."` در کدِ بک‌اند."""
    found: set[str] = set()
    for path in (BACKEND / "app").rglob("*.py"):
        found |= set(
            re.findall(r'event_type\s*=\s*"([a-z0-9_]+)"', path.read_text(encoding="utf-8"))
        )
    return found


def _frontend_label_keys() -> set[str]:
    source = FRONTEND_TYPES.read_text(encoding="utf-8")
    start = source.index("export const AUDIT_EVENT_LABELS: Record<string, string> = {")
    body = source[start : source.index("\n};", start)]
    return set(re.findall(r"^\s{2}([a-z0-9_]+):\s*\"", body, re.M))


def test_no_event_type_is_built_by_string_interpolation():
    """اگر روزی `event_type=f"..."` بیاید، اسکنِ بالا کورش می‌شود.

    آن‌وقت این آزمون سبز می‌ماند و کارش را نمی‌کند — پس همان الگو ممنوع است.
    """
    offenders = [
        str(path.relative_to(BACKEND))
        for path in (BACKEND / "app").rglob("*.py")
        if re.search(r'event_type\s*=\s*f"', path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], (
        "نوعِ رویداد باید رشتهٔ ثابت باشد تا قابلِ شمارش و برچسب‌گذاری بماند: "
        f"{offenders}"
    )


def test_every_written_event_has_a_backend_label():
    missing = _event_types_written_by_the_code() - set(EVENT_LABELS)
    assert missing == set(), f"بی‌برچسب در بک‌اند: {sorted(missing)}"


def test_no_backend_label_is_an_orphan():
    orphans = set(EVENT_LABELS) - _event_types_written_by_the_code()
    assert orphans == set(), (
        f"برچسب برای رویدادی که هیچ‌جا نوشته نمی‌شود: {sorted(orphans)}"
    )


@pytest.mark.skipif(not FRONTEND_TYPES.exists(), reason="فرانت‌اند در این نصب نیست")
def test_the_frontend_map_matches_the_backend_exactly():
    frontend, backend = _frontend_label_keys(), set(EVENT_LABELS)
    assert frontend - backend == set(), (
        f"در فرانت هست و در بک‌اند نیست: {sorted(frontend - backend)}"
    )
    assert backend - frontend == set(), (
        f"در بک‌اند هست و در فرانت نیست: {sorted(backend - frontend)}"
    )


@pytest.mark.skipif(not FRONTEND_TYPES.exists(), reason="فرانت‌اند در این نصب نیست")
def test_the_two_maps_carry_the_same_text():
    """هم‌کلید بودن کافی نیست: دو متنِ متفاوت برای یک رویداد یعنی اکسل و رابط
    دو چیز می‌گویند، و کسی که هر دو را می‌بیند فکر می‌کند دو رویداد است."""
    source = FRONTEND_TYPES.read_text(encoding="utf-8")
    start = source.index("export const AUDIT_EVENT_LABELS: Record<string, string> = {")
    body = source[start : source.index("\n};", start)]
    frontend = dict(re.findall(r"^\s{2}([a-z0-9_]+):\s*\"([^\"]*)\"", body, re.M))
    mismatched = {
        key: (EVENT_LABELS[key], frontend[key])
        for key in EVENT_LABELS.keys() & frontend.keys()
        if EVENT_LABELS[key] != frontend[key]
    }
    assert mismatched == {}, f"متنِ برچسب یکی نیست: {mismatched}"
