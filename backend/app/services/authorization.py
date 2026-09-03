"""خواندن مجوزها و وضعیت ماژول‌ها (نیمهٔ دوم P0-03)."""
from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.modules import MODULES, MODULES_BY_KEY
from app.models.capability import UserCapability
from app.models.enums import Capability
from app.models.module import ModuleSetting

DEFAULT_HR_CAPABILITIES = frozenset(
    {
        Capability.manage_users,
        Capability.manage_personnel,
        Capability.manage_scoring,
    }
)


def capabilities_of(db: Session, user_id: int) -> set[Capability]:
    return set(
        db.scalars(select(UserCapability.capability).where(UserCapability.user_id == user_id))
    )


def has_capability(db: Session, user_id: int, capability: Capability) -> bool:
    return (
        db.scalar(
            select(UserCapability.id).where(
                UserCapability.user_id == user_id,
                UserCapability.capability == capability,
            )
        )
        is not None
    )


def apply_default_hr_capabilities(db: Session, user_id: int) -> None:
    """Set the baseline permissions for a human-resources account."""
    db.query(UserCapability).filter(UserCapability.user_id == user_id).delete(
        synchronize_session=False
    )
    db.add_all(
        UserCapability(user_id=user_id, capability=capability)
        for capability in DEFAULT_HR_CAPABILITIES
    )


def module_states(db: Session) -> dict[str, bool]:
    """وضعیت همهٔ ماژول‌ها. ماژولی که ردیفی ندارد، پیش‌فرضِ خودش را می‌گیرد.

    یعنی افزودن یک ماژول تازه به کد، بدون مایگریشن کار می‌کند — و مهم‌تر،
    ماژولِ تازه با حالتِ درستش شروع می‌شود نه با «خاموش» فقط چون ردیف ندارد.
    """
    stored = {row.key: row.enabled for row in db.scalars(select(ModuleSetting))}
    return {
        module.key: stored.get(module.key, module.default_enabled)
        for module in MODULES
    }


def is_module_enabled(db: Session, key: str) -> bool:
    """این ماژول روشن است؟ کلیدِ ناشناخته خطاست، نه «روشن».

    پیش از این کلیدِ ناشناخته `True` برمی‌گشت. تنها راهِ رسیدن به آن شاخه یک
    غلطِ تایپی در خودِ کد است (ردیفِ دیتابیس زودتر پیدا می‌شود)، و نتیجه‌اش
    گاردی بود که همیشه می‌گذارد — یعنی درست همان حالتی که به‌نظر گارد است و
    نیست. حالا بلند می‌شکند و تست همان لحظه می‌گیردش.
    """
    module = MODULES_BY_KEY.get(key)
    if module is None:
        raise KeyError(f"ماژولی با کلید «{key}» تعریف نشده است (core/modules.py)")
    row = db.get(ModuleSetting, key)
    if row is not None:
        return row.enabled
    return module.default_enabled


def ensure_module_enabled(db: Session, key: str) -> None:
    """گاردِ ماژولِ خاموش — یک تابعِ ساده، عمداً نه یک `Depends`.

    تا امروز این گارد یک `Depends`ِ استفاده‌نشده در `api/deps.py` بود
    (`require_module`) و هیچ روتی به آن وصل نبود، پس *همهٔ* سوییچ‌های ماژول
    فقط ظاهری بودند: سازمانی که کانالِ اعتراض را عمداً باز نکرده بود همچنان
    اعتراض می‌پذیرفت، و سازمانی که خودارزیابی را خاموش کرده بود همچنان
    خودارزیابی ثبت می‌کرد.

    و چرا `Depends` نه: مسیرِ دستیار *تابعِ* endpoint را صدا می‌زند و نه خودِ
    HTTP را، پس `Depends`ها اجرا نمی‌شوند — همان ریشه‌ای که C1–C3 از آن آمد.
    گاردی که فقط در یکی از دو مسیر باشد گارد نیست. این‌جا در بدنهٔ خودِ
    endpoint صدا زده می‌شود، پس هر دو مسیر از آن رد می‌شوند.
    """
    if not is_module_enabled(db, key):
        module = MODULES_BY_KEY[key]
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail=f"بخش «{module.label}» توسط مدیر سامانه غیرفعال شده است",
        )
