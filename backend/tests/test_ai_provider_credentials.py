"""اطلاعاتِ اتصال، یک ست برای هر سرویس.

مسئله‌ای که این تغییر حل کرد
-----------------------------
آدرس، نام مدل و کلید در همان ردیفِ تکِ `ai_settings` بودند، پس سازمان یک ست
اطلاعات داشت و عوض‌کردنِ سرویس رویشان می‌نوشت. مدیری که کلید Anthropic را وارد
کرده بود و Gemini را امتحان می‌کرد، برای برگشتن باید کلید را دوباره پیدا و وارد
می‌کرد — و کلیدِ API چیزی نیست که آدم دومرتبه دستش باشد.

چیزهایی که این‌جا قفل می‌شوند، چون خرابی‌شان *بی‌صدا* است: هیچ‌کدام خطا
نمی‌دهند، فقط یک کلید را در جای اشتباه می‌نویسند یا یکی را از بین می‌برند.
"""
from sqlalchemy import delete, select

from app.core.crypto import decrypt
from app.models.ai import AiProviderCredential, AiUserAccess
from app.models.enums import Capability
from tests.helpers import auth_header, enable_ai_provider, make_user


def _admin(db):
    user = make_user(db, "support", username="cred_admin", capabilities=[Capability.manage_ai])
    db.commit()
    return user


def _save(client, admin, **payload):
    response = client.put("/api/ai/settings", json=payload, headers=auth_header(admin))
    assert response.status_code == 200, response.text
    return response.json()


def _stored(db, provider: str) -> AiProviderCredential | None:
    return db.scalar(select(AiProviderCredential).where(AiProviderCredential.provider == provider))


def _forget(db, provider: str) -> None:
    """ردیفِ این سرویس را پاک کن.

    این جدول سراسری است و یکی از تست‌های `test_audit_fixes` عمداً روی اتصالِ
    *واقعی* commit می‌کند (برای سنجشِ یک مسابقهٔ هم‌زمانی)، پس ممکن است ردیفی از
    اجرای پیشین مانده باشد. تستی که به *نبودنِ* ردیف تکیه کند، به ترتیب اجرا
    وابسته می‌شود.
    """
    db.execute(delete(AiProviderCredential).where(AiProviderCredential.provider == provider))
    db.flush()


# ── نگه‌داشتن، نه رونویسی ─────────────────────────────────────────────────


def test_switching_provider_keeps_the_previous_one_s_key(client, db_session):
    """قلبِ این تغییر: کلیدِ Anthropic باید بعد از یک دور رفتن به Gemini سرِ جا باشد."""
    admin = _admin(db_session)

    _save(client, admin, provider="anthropic", model="claude-sonnet-5", api_key="sk-ant-1234")
    _save(client, admin, provider="gemini", model="gemini-2.0-flash", api_key="sk-gem-9876")

    body = client.get("/api/ai/settings", headers=auth_header(admin)).json()
    saved = {c["provider"]: c for c in body["provider_credentials"]}

    assert body["provider"] == "gemini", "آخرین انتخاب باید فعال باشد"
    assert saved["anthropic"]["api_key_configured"] is True
    assert saved["anthropic"]["api_key_hint"].endswith("1234")
    assert saved["gemini"]["api_key_hint"].endswith("9876")
    assert saved["anthropic"]["model"] == "claude-sonnet-5"


def test_switching_back_makes_the_old_key_active_again(client, db_session):
    """و برگشتن هم یک کلیک است: بدونِ وارد کردنِ دوبارهٔ کلید."""
    admin = _admin(db_session)
    _save(client, admin, provider="anthropic", api_key="sk-ant-1234")
    _save(client, admin, provider="gemini", api_key="sk-gem-9876")

    # فقط سرویس عوض می‌شود؛ هیچ کلیدی همراهش نمی‌رود.
    body = _save(client, admin, provider="anthropic")

    assert body["api_key_configured"] is True
    assert body["api_key_hint"].endswith("1234")
    assert body["model"] == "claude-sonnet-5", "مدلِ ذخیره‌شدهٔ خودش برمی‌گردد"


def test_a_behaviour_only_change_touches_no_credentials(client, db_session):
    """تغییرِ دما نباید به کلید دست بزند.

    اگر «سرویسِ هدف» را از خودِ درخواست نگیریم و مثلاً همیشه ردیف بسازیم، یک
    ذخیرهٔ ساده می‌تواند کلیدی را با رشتهٔ خالی رونویسی کند.
    """
    admin = _admin(db_session)
    _save(client, admin, provider="anthropic", api_key="sk-ant-1234")

    _save(client, admin, temperature=55)

    body = client.get("/api/ai/settings", headers=auth_header(admin)).json()
    assert body["temperature"] == 55
    assert body["api_key_configured"] is True
    assert body["api_key_hint"].endswith("1234")


# ── پیش‌فرضِ کاتالوگ ──────────────────────────────────────────────────────


def test_a_never_configured_provider_gets_the_catalogue_address(client, db_session):
    """سوییچ بدونِ تایپ‌کردن نباید به آدرسِ خالی برسد.

    فرم هم پیش‌فرض‌ها را می‌گذارد، ولی آن یک راحتی است نه یک تضمین: مدیری که
    سرویس را عوض می‌کند و مستقیم ذخیره می‌زند، باید آدرسِ درست بگیرد.
    """
    admin = _admin(db_session)
    _forget(db_session, "openai")
    db_session.commit()

    body = _save(client, admin, provider="openai")

    assert body["base_url"] == "https://api.openai.com/v1"
    assert body["model"] == "gpt-4o-mini"


def test_a_saved_address_wins_over_the_catalogue(client, db_session):
    """پیش‌فرض فقط جای خالی را پر می‌کند و انتخابِ مدیر را پس نمی‌زند."""
    admin = _admin(db_session)
    _save(client, admin, provider="openai", base_url="https://proxy.internal/v1", model="gpt-4o")

    body = _save(client, admin, provider="anthropic")
    body = _save(client, admin, provider="openai")

    assert body["base_url"] == "https://proxy.internal/v1"
    assert body["model"] == "gpt-4o"


def test_custom_has_no_catalogue_default_and_stays_empty(client, db_session):
    """«سفارشی» پیش‌فرضی ندارد، پس نباید آدرسِ کس دیگری را قرض بگیرد."""
    admin = _admin(db_session)
    _forget(db_session, "custom")
    db_session.commit()

    body = _save(client, admin, provider="custom")

    assert body["base_url"] == ""
    assert body["model"] == ""


# ── گاردها ───────────────────────────────────────────────────────────────


def test_an_unknown_provider_is_refused(client, db_session):
    """رد می‌شود و به «سفارشی» نمی‌افتد: افتادنِ خاموش یعنی فرم چیزی را ذخیره
    کند که کاربر انتخاب نکرده — و بدتر، کلید را جایی بنویسد که کسی نمی‌بیند."""
    admin = _admin(db_session)

    response = client.put(
        "/api/ai/settings",
        json={"provider": "not-a-service", "api_key": "sk-oops"},
        headers=auth_header(admin),
    )

    assert response.status_code == 400
    assert _stored(db_session, "not-a-service") is None


def test_the_key_never_comes_back_from_the_server(client, db_session):
    """نه در فیلدهای سرویسِ فعال، نه در فهرستِ همهٔ سرویس‌ها."""
    admin = _admin(db_session)
    _save(client, admin, provider="anthropic", api_key="sk-ant-secret-value")

    raw = client.get("/api/ai/settings", headers=auth_header(admin)).text

    assert "sk-ant-secret-value" not in raw
    assert "alue" in raw, "چهار نویسهٔ آخر باید بیاید تا آدم کلیدش را بشناسد"


def test_an_empty_key_clears_only_that_provider(client, db_session):
    """رشتهٔ خالی یعنی «پاکش کن» — و فقط برای همان سرویس."""
    admin = _admin(db_session)
    _save(client, admin, provider="anthropic", api_key="sk-ant-1234")
    _save(client, admin, provider="gemini", api_key="sk-gem-9876")

    _save(client, admin, provider="gemini", api_key="")

    body = client.get("/api/ai/settings", headers=auth_header(admin)).json()
    saved = {c["provider"]: c for c in body["provider_credentials"]}
    assert saved["gemini"]["api_key_configured"] is False
    assert saved["anthropic"]["api_key_configured"] is True


# ── مصرف‌کننده‌ها ─────────────────────────────────────────────────────────


def test_status_reads_the_key_of_the_active_provider(client, db_session):
    """`/status` باید کلیدِ سرویسِ فعال را ببیند، نه هر کلیدی که در جدول هست.

    اگر «آیا کلیدی هست» به‌جای سرویسِ فعال روی کلِ جدول سنجیده شود، دکمهٔ همکار
    ظاهر می‌شود و اولین پیام با خطای سرویس برمی‌گردد.
    """
    admin = _admin(db_session)
    _save(client, admin, provider="anthropic", api_key="sk-ant-1234")
    _save(client, admin, provider="gemini", api_key="")
    _save(client, admin, enabled=True)
    db_session.add(AiUserAccess(user_id=admin.id, enabled=True))
    db_session.commit()

    # `_save(enabled=True)` سرویس را عوض نکرد، پس فعال همان gemini است.
    _save(client, admin, provider="anthropic")
    on_anthropic = client.get("/api/ai/status", headers=auth_header(admin)).json()
    assert on_anthropic["available"] is True, on_anthropic

    _save(client, admin, provider="gemini")
    on_gemini = client.get("/api/ai/status", headers=auth_header(admin)).json()
    assert on_gemini["available"] is False
    assert "کلید" in on_gemini["reason"]


def test_the_stored_key_is_encrypted_at_rest(client, db_session):
    """همان قاعدهٔ قبلی، روی جدولِ تازه: بک‌آپِ لو رفته کلیدِ معتبر ندهد."""
    admin = _admin(db_session)
    _save(client, admin, provider="anthropic", api_key="sk-ant-1234")

    row = _stored(db_session, "anthropic")
    assert "sk-ant-1234" not in row.api_key_encrypted
    assert decrypt(row.api_key_encrypted) == "sk-ant-1234"


def test_the_helper_and_the_endpoint_agree(client, db_session):
    """`enable_ai_provider` تست‌ها باید همان چیزی را بسازد که مسیرِ واقعی می‌سازد."""
    admin = _admin(db_session)
    enable_ai_provider(db_session, provider="openai", api_key="sk-helper")
    db_session.commit()

    body = client.get("/api/ai/settings", headers=auth_header(admin)).json()

    assert body["provider"] == "openai"
    assert body["api_key_configured"] is True
