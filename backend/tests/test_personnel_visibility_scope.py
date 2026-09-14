"""«چه کسی کلِ فهرستِ پرسنل را می‌بیند» باید در هر پنج مسیر یک جواب بدهد.

مجوزِ `manage_personnel` را منابع انسانی به کسی می‌دهد که نقشش HR نیست — مثلاً
یک معاونت. تا امروز آن یک نفر، جواب‌های متفاوت می‌گرفت:

| مسیر | چه می‌دید |
|---|---|
| خروجیِ اکسلِ پرسنل | همه |
| ساخت / ویرایش / حذفِ پرسنل | همه |
| دستیارِ هوشمند | همه |
| فهرستِ پرسنل روی صفحه | **فقط افرادِ خودش** |
| بازکردنِ یک ردیف (و رادار/روند/پروندهٔ جاری) | **فقط افرادِ خودش** |

سه‌تا می‌گفتند «همه» و دوتا نه، چون قاعده چندبار و جدا نوشته شده بود.
حالا یک تابع است (`authorization.sees_all_personnel`) و **تصمیمِ ثبت‌شده این
است که این مجوز سازمان‌گستر است**: کسی که می‌تواند هر پرسنلی را بسازد، ویرایش
یا حذف کند، دیدنش هم باید بتواند.

ردیفِ آخر یک گامِ دیرتر بسته شد و درسش را هم داد: وقتی فقط فهرست باز شد و
بازکردنِ ردیف باز نشد، حالت از «ناهمگون» به **بن‌بست** رفت — دارندهٔ مجوز همه
را می‌دید و با کلیک روی هر کدام ۴۰۳ می‌گرفت. قاعده‌ای که نیمه‌کاره یکی شود،
بدتر از قاعده‌ای است که همه‌جا یکسانْ تنگ باشد.

این فایل خودِ آن هم‌خوانی را می‌سنجد و نه پیاده‌سازی را: اگر فردا کسی یکی از
این مسیرها را عوض کند، همین‌جا می‌افتد.
"""
import pytest

from app.models.enums import Capability, UserRole
from app.schemas.auth import CurrentUser
from app.services.ai.context import _visible_personnel_ids as context_visible
from app.services.ai.tools.people import _visible_personnel_ids as tools_visible
from app.services.authorization import sees_all_personnel
from tests.helpers import auth_header, make_access, make_personnel, make_user


@pytest.fixture()
def org(db_session):
    """سه پرسنل، که فقط یکی‌شان در زنجیرهٔ معاونت است."""
    hr = make_user(db_session, "hr")
    sup = make_user(db_session, "unit_supervisor")
    ceo = make_user(db_session, "ceo", capabilities=[])
    deputy = make_user(db_session, "deputy", capabilities=[])

    mine = make_personnel(db_session, full_name="زیرمجموعهٔ من")
    make_access(db_session, mine, sup, deputy, ceo)
    strangers = []
    for name in ("غریبهٔ یک", "غریبهٔ دو"):
        stranger = make_personnel(db_session, full_name=name)
        make_access(db_session, stranger, sup, None, ceo)
        strangers.append(stranger)
    db_session.commit()
    return {
        "hr": hr,
        "deputy": deputy,
        "ceo": ceo,
        "mine": mine,
        "stranger": strangers[0],
    }


def _grant(db, user, capability: Capability) -> None:
    from app.models.capability import UserCapability

    db.add(UserCapability(user_id=user.id, capability=capability))
    db.commit()


def _as_current(user) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        username=user.username,
        role=user.role,
        personnel_id=user.personnel_id,
    )


# ── خودِ قاعده ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("role", "caps", "expected"),
    [
        (UserRole.hr, set(), True),
        (UserRole.deputy, {Capability.manage_personnel}, True),
        (UserRole.support, {Capability.manage_personnel}, True),
        (UserRole.deputy, set(), False),
        (UserRole.ceo, set(), False),
        (UserRole.support, set(), False),
        # مجوزِ دیگری همان کار را نمی‌کند
        (UserRole.deputy, {Capability.manage_users}, False),
    ],
)
def test_the_rule_itself(role, caps, expected):
    assert sees_all_personnel(role, caps) is expected


# ── و همان مسیرها، برای یک نفر ────────────────────────────────────────────


def test_all_four_surfaces_agree_without_the_capability(client, db_session, org):
    """معاونتِ بی‌مجوز: همه‌جا فقط افرادِ زنجیرهٔ خودش."""
    deputy = org["deputy"]

    listed = client.get("/api/personnel", headers=auth_header(deputy)).json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == org["mine"].id

    assert client.get(
        "/api/personnel/export.xlsx", headers=auth_header(deputy)
    ).status_code == 403

    current = _as_current(deputy)
    assert tools_visible(db_session, current, frozenset()) == {org["mine"].id}
    assert context_visible(db_session, current, set()) == {org["mine"].id}


def test_all_four_surfaces_agree_with_the_capability(client, db_session, org):
    """همان معاونت، با مجوز: همه‌جا کلِ فهرست.

    پیش از این سه‌تا «همه» می‌گفتند و فهرستِ روی صفحه «یکی».
    """
    deputy = org["deputy"]
    _grant(db_session, deputy, Capability.manage_personnel)

    listed = client.get("/api/personnel", headers=auth_header(deputy)).json()
    assert listed["total"] == 3, (
        "فهرستِ روی صفحه باید کلِ پرسنل را بدهد — همان چیزی که اکسل و دستیار "
        "از قبل می‌دادند."
    )

    assert client.get(
        "/api/personnel/export.xlsx", headers=auth_header(deputy)
    ).status_code == 200

    current = _as_current(deputy)
    caps = {Capability.manage_personnel}
    assert tools_visible(db_session, current, frozenset(caps)) is None
    assert context_visible(db_session, current, caps) is None


def test_the_narrowing_switch_still_works_for_someone_who_sees_everything(
    client, db_session, org
):
    """`accessible_to_me` تنگ‌کردنِ داوطلبانه است و باید برای HR هم کار کند.

    اگر با «چه کسی حق دارد» قاطی می‌شد، فیلترِ «فقط افرادِ من» برای منابع
    انسانی بی‌اثر می‌شد — و آن فیلتر دقیقاً برای همان کاربر ساخته شده.
    """
    hr = org["hr"]
    assert client.get("/api/personnel", headers=auth_header(hr)).json()["total"] == 3
    narrowed = client.get(
        "/api/personnel?accessible_to_me=true", headers=auth_header(hr)
    ).json()
    assert narrowed["total"] == 0, "HR در هیچ زنجیره‌ای صندلی ندارد"


# ── و ردیفی که باز می‌شود ──────────────────────────────────────────────────


def _row_surfaces(client, user, personnel_id) -> dict[str, int]:
    """هر چهار مسیری که `_can_view_personnel` را صدا می‌زنند، با هم."""
    head = auth_header(user)
    return {
        "detail": client.get(f"/api/personnel/{personnel_id}", headers=head).status_code,
        "radar": client.get(
            f"/api/dashboard/personnel/{personnel_id}/radar", headers=head
        ).status_code,
        "trend": client.get(
            f"/api/dashboard/personnel/{personnel_id}/trend", headers=head
        ).status_code,
        "in_progress": client.get(
            f"/api/dashboard/personnel/{personnel_id}/in-progress", headers=head
        ).status_code,
    }


def test_the_capability_also_opens_the_row_not_just_the_list(client, db_session, org):
    """بن‌بستی که نیمه‌کاره بستنِ قاعده ساخت.

    فهرست کلِ پرسنل را می‌داد و کلیک روی هر ردیف ۴۰۳ — و سه نمودارِ پروفایل
    هم همان. چهار مسیر، یک تابع، پس چهارتایی سنجیده می‌شوند.
    """
    deputy = org["deputy"]
    _grant(db_session, deputy, Capability.manage_personnel)

    assert _row_surfaces(client, deputy, org["stranger"].id) == {
        "detail": 200,
        "radar": 200,
        "trend": 200,
        "in_progress": 200,
    }


def test_without_the_capability_the_row_stays_shut(client, db_session, org):
    """گاردِ کور: تنگی برای کسی که مجوز ندارد دست‌نخورده مانده."""
    deputy = org["deputy"]

    assert _row_surfaces(client, deputy, org["stranger"].id) == {
        "detail": 403,
        "radar": 403,
        "trend": 403,
        "in_progress": 403,
    }


def test_a_seat_on_the_record_itself_is_enough_for_the_assistant(client, db_session, org):
    """دامنهٔ دیدِ دستیار *کم‌شمول* بود، و آن هم یک واگرایی است.

    `_can_view_personnel` دو شرط دارد: ردیفِ دسترسی، و صندلی روی خودِ پرونده.
    دومی در `_visible_personnel_ids` نبود، پس مسئولی که پرونده‌ای را نمره
    داده و زنجیره‌اش بعداً عوض شده، همان فرد را با `get_personnel` می‌دید و با
    `search_personnel` نمی‌دید — دو جوابِ متفاوت برای یک پرسش.
    """
    from app.models.enums import EvaluationStatus
    from app.models.evaluation import EvaluationRecord

    old_supervisor = make_user(db_session, "unit_supervisor", capabilities=[])
    db_session.add(
        EvaluationRecord(
            evaluation_code="VS-1",
            subject_personnel_id=org["stranger"].id,
            unit_supervisor_user_id=old_supervisor.id,
            ceo_user_id=org["ceo"].id,
            status=EvaluationStatus.finalized,
        )
    )
    db_session.commit()

    current = _as_current(old_supervisor)
    # زنجیرهٔ امروزِ این فرد دستِ کسِ دیگری است — ردیفِ دسترسی او را نمی‌آورد.
    assert org["stranger"].id in tools_visible(db_session, current, frozenset())
