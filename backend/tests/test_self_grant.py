"""هیچ‌کس مجوزی را که ندارد به خودش نمی‌دهد.

تا امروز برای این حالت *هیچ قاعده‌ای* نوشته نشده بود — نه اجازه، نه منع. یعنی
دارندهٔ `manage_capabilities` با یک کلیک هر مجوزِ دیگری را برای خودش روشن
می‌کرد و در لاگ فقط یک سطر می‌ماند: «فلانی به فلانی داد».

همان قاعده‌ای که سامانه جای دیگر دارد (`ensure_not_deciding_about_oneself`):
کسی که موضوعِ یک تصمیم است، در آن تصمیم نقش ندارد.

**مرزِ صادقانهٔ این گارد:** کسی که واقعاً بخواهد، حسابِ دومی می‌سازد، مجوز را
به آن می‌دهد و با آن وارد می‌شود. این را با یک شرط نمی‌شود گرفت. چیزی که این
گارد می‌دهد *ردِ دو نفره* است: ارتقای مجوز از این پس دستِ کم دو حساب و دو
ردیفِ لاگ لازم دارد. تستِ آخرِ این فایل همان مرز را صریح می‌کند، تا کسی این
گارد را با چیزی که نیست اشتباه نگیرد.
"""
from app.models.enums import Capability
from app.services.authorization import capabilities_of
from tests.helpers import auth_header, make_user


def _admin(db):
    return make_user(db, "hr", capabilities=[Capability.manage_capabilities])


def _put(client, actor, target, capabilities):
    return client.put(
        f"/api/administration/capabilities/{target.id}",
        json={"capabilities": [c.value for c in capabilities]},
        headers=auth_header(actor),
    )


def test_you_cannot_add_a_capability_to_yourself(client, db_session):
    admin = _admin(db_session)
    db_session.commit()

    response = _put(
        client, admin, admin, [Capability.manage_capabilities, Capability.view_audit_log]
    )

    assert response.status_code == 403
    assert "حساب خودتان" in response.json()["detail"]
    assert Capability.view_audit_log not in capabilities_of(db_session, admin.id)


def test_you_can_still_take_a_capability_away_from_yourself(client, db_session):
    """کم‌کردنِ اختیارِ خود مسئله‌ای نیست — و بستنش یعنی گیر افتادن."""
    admin = _admin(db_session)
    second = make_user(db_session, "hr", capabilities=[Capability.manage_capabilities])
    db_session.add_all([])
    db_session.commit()
    # مجوزِ دومی که بشود پس داد
    assert _put(
        client,
        second,
        admin,
        [Capability.manage_capabilities, Capability.view_audit_log],
    ).status_code == 200

    response = _put(client, admin, admin, [Capability.manage_capabilities])

    assert response.status_code == 200
    assert Capability.view_audit_log not in capabilities_of(db_session, admin.id)


def test_a_no_op_write_on_yourself_is_not_blocked(client, db_session):
    """ذخیرهٔ همان مجموعهٔ فعلی نباید ۴۰۳ بگیرد.

    گارد روی *افزودن* است و نه روی «این کاربر خودت هستی». بی این تفکیک،
    فرمِ مدیریتِ مجوزها برای حسابِ خودِ کاربر اصلاً قابلِ ذخیره نبود.
    """
    admin = _admin(db_session)
    db_session.commit()

    response = _put(client, admin, admin, [Capability.manage_capabilities])

    assert response.status_code == 200


def test_a_mixed_write_is_refused_by_the_authority_rule_first(client, db_session):
    """باری که هم‌زمان می‌گیرد و می‌دهد، به کدام گارد می‌خورد؟

    این حالت دو گارد را با هم روشن می‌کند: «به خودت مجوز نده» (۴۰۳) و
    «آخرین دارنده نمی‌تواند خودش را خلع کند» (۴۰۰). ترتیب اتفاقی نیست —
    اولی پرسشِ *اختیار* است («اصلاً این تصمیم با توست؟») و دومی پرسشِ
    *اعتبارِ محتوا*. مثل خودِ `require_capability`، اختیار جلوتر سنجیده
    می‌شود؛ پس پاسخ ۴۰۳ است.

    و مهم‌تر از شمارهٔ پاسخ: هیچ نیمه‌ای اجرا نمی‌شود — نه آن مجوز اضافه
    می‌شود و نه این یکی می‌رود.
    """
    sole = _admin(db_session)
    db_session.commit()

    response = _put(client, sole, sole, [Capability.manage_users])

    assert response.status_code == 403
    assert "حساب خودتان" in response.json()["detail"]
    held = capabilities_of(db_session, sole.id)
    assert Capability.manage_users not in held
    assert Capability.manage_capabilities in held


def test_someone_else_can_grant_it_to_you(client, db_session):
    """راهِ درست باز می‌ماند: نفرِ دوم همان مجوز را می‌دهد."""
    admin = _admin(db_session)
    colleague = _admin(db_session)
    db_session.commit()

    response = _put(
        client, colleague, admin, [Capability.manage_capabilities, Capability.view_audit_log]
    )

    assert response.status_code == 200
    assert Capability.view_audit_log in capabilities_of(db_session, admin.id)


def test_the_guard_does_not_pretend_to_stop_a_determined_admin(client, db_session):
    """مرزِ گارد، صریح و آزموده.

    کسی که هم `manage_capabilities` دارد و هم `manage_users` — یعنی یک مدیرِ
    سامانهٔ تمام‌اختیار — می‌تواند حسابِ دیگری بسازد و هر مجوزی را به آن بدهد.
    این تست آن را *تأیید* می‌کند، نه اینکه شکایتش را داشته باشد: اگر روزی کسی
    فکر کند این گارد ارتقای مجوز را ناممکن کرده، همین‌جا خلافش نوشته است.

    و همین‌جا معلوم می‌شود گارد چقدر *هست*: با مجوزِ `manage_capabilities`ِ
    تنها، این راه هم بسته است — ساختنِ حساب خودش `manage_users` می‌خواهد.
    """
    admin = make_user(
        db_session,
        "hr",
        capabilities=[Capability.manage_capabilities, Capability.manage_users],
    )
    db_session.commit()

    created = client.post(
        "/api/users",
        json={"username": "hesab-dovom", "password": "Str0ng-Pass-9", "role": "hr"},
        headers=auth_header(admin),
    )
    assert created.status_code == 201

    from app.models.user import User

    second = db_session.get(User, created.json()["id"])
    granted = _put(client, admin, second, [Capability.view_audit_log])

    assert granted.status_code == 200
    assert Capability.view_audit_log in capabilities_of(db_session, second.id)


def test_manage_capabilities_alone_cannot_even_create_the_second_account(client, db_session):
    """و بدونِ `manage_users`، همان راهِ دور هم بسته است.

    این تست مرزِ تستِ بالا را می‌بندد: گارد در برابرِ دارندهٔ *یک* مجوز واقعاً
    کار می‌کند، و آن‌چه دورش می‌زند ترکیبِ دو مجوز است — که خودش یک تصمیمِ
    آگاهانهٔ اعطاست، نه یک در پشتی.
    """
    admin = _admin(db_session)
    db_session.commit()

    created = client.post(
        "/api/users",
        json={"username": "hesab-mamnoo", "password": "Str0ng-Pass-9", "role": "hr"},
        headers=auth_header(admin),
    )

    assert created.status_code == 403
