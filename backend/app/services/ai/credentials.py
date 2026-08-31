"""اطلاعاتِ اتصالِ هر سرویس، و اینکه کدام‌شان امروز کار می‌کند.

مسئله
-----
تا امروز سازمان *یک* ست اطلاعات داشت: یک آدرس، یک نام مدل، یک کلید — همه در
همان ردیفِ تکِ `ai_settings`. عوض‌کردنِ سرویس رویشان می‌نوشت، پس مدیری که
کلید Anthropic را وارد کرده بود و می‌خواست Gemini را امتحان کند، برای برگشتن
باید کلید را دوباره پیدا می‌کرد. کلیدِ API چیزی نیست که آدم دومرتبه دستش باشد،
و همین یک چیز، «امتحان‌کردنِ یک سرویسِ دیگر» را از یک کلیک به یک تصمیم تبدیل
می‌کرد.

حالا هر سرویس ردیفِ خودش را دارد و `ai_settings.provider` فقط می‌گوید کدام فعال
است.

چرا این ماژول هست و نه دسترسیِ مستقیم به ستون‌ها
-------------------------------------------------
«اطلاعاتِ اتصالِ فعال» حالا یک *محاسبه* است، نه یک ستون: ردیفِ سرویسِ فعال،
به‌علاوهٔ آدرس و مدلِ پیش‌فرضِ کاتالوگ آن‌جا که خالی مانده. اگر این محاسبه در
مسیرها تکرار شود، روزی یکی‌شان `base_url` خالی را همان‌طور به آداپتور می‌دهد و
خطایی می‌گیریم که دربارهٔ آدرس چیزی نمی‌گوید.

پیش‌فرضِ کاتالوگ چرا این‌جا اعمال می‌شود و نه فقط در فرم
--------------------------------------------------------
فرانت‌اند هم موقعِ کلیک روی یک سرویس پیش‌فرض‌ها را می‌گذارد، ولی آن یک راحتی
است نه یک تضمین: مدیری که سرویس را عوض می‌کند و بی‌آنکه چیزی تایپ کند ذخیره
می‌زند، نباید به آدرسِ خالی برسد. پس سرور هم همان کار را می‌کند.

برای «سفارشی» پیش‌فرضی در کاتالوگ نیست، پس هر چه مدیر نوشته همان می‌ماند.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ai_providers import PROVIDERS_BY_ID
from app.core.crypto import decrypt
from app.models.ai import AiProviderCredential, AiSettings


@dataclass(frozen=True)
class Credentials:
    """اطلاعاتِ آمادهٔ مصرف برای ساختنِ آداپتور."""

    provider: str
    base_url: str
    model: str
    #: کلیدِ *رمزگشایی‌شده*. رشتهٔ خالی یعنی تنظیم نشده — یا خواناست نبوده
    #: (کلیدِ رمزنگاری عوض شده)، که `decrypt` عمداً همان «تنظیم نشده» می‌خواندش.
    api_key: str
    #: شکلِ رمزشده، برای جاهایی که فقط «هست یا نه» و چهار نویسهٔ آخر لازم است.
    api_key_encrypted: str


def row_for(db: Session, provider: str) -> AiProviderCredential:
    """ردیفِ این سرویس؛ اگر نبود ساخته می‌شود و با پیش‌فرضِ کاتالوگ پر می‌شود.

    `flush` می‌کند و نه `commit`: تراکنش دستِ فراخواننده است، مثل بقیهٔ سرویس‌ها.
    """
    row = db.scalar(
        select(AiProviderCredential).where(AiProviderCredential.provider == provider)
    )
    if row is not None:
        return row

    catalogue = PROVIDERS_BY_ID.get(provider)
    row = AiProviderCredential(
        provider=provider,
        base_url=catalogue.base_url if catalogue else "",
        model=catalogue.default_model if catalogue else "",
        api_key_encrypted="",
    )
    db.add(row)
    db.flush()
    return row


def rows_by_provider(db: Session) -> dict[str, AiProviderCredential]:
    """هر چه ذخیره شده. کلیدهای غایب یعنی آن سرویس هنوز تنظیم نشده."""
    return {row.provider: row for row in db.scalars(select(AiProviderCredential))}


def active(db: Session, config: AiSettings) -> Credentials:
    """اطلاعاتِ سرویسی که `ai_settings.provider` می‌گوید.

    خواندنی است: ردیفِ نداشته را *نمی‌سازد*. مسیرهای فقط-خواندنی (`/status`،
    فرستادنِ پیام) نباید با یک GET چیزی در دیتابیس بنویسند.
    """
    row = db.scalar(
        select(AiProviderCredential).where(AiProviderCredential.provider == config.provider)
    )
    catalogue = PROVIDERS_BY_ID.get(config.provider)
    fallback_url = catalogue.base_url if catalogue else ""
    fallback_model = catalogue.default_model if catalogue else ""
    return Credentials(
        provider=config.provider,
        base_url=(row.base_url if row else "") or fallback_url,
        model=(row.model if row else "") or fallback_model,
        api_key=decrypt(row.api_key_encrypted) if row else "",
        api_key_encrypted=row.api_key_encrypted if row else "",
    )
