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


def stored_module_state(db: Session, key: str) -> bool:
    """سوییچِ *ذخیره‌شدهٔ* این ماژول، بی توجه به وابستگی‌هایش.

    پنلِ مدیریت این را می‌خواهد (کاربر باید ببیند خودش چه انتخاب کرده)، و
    `is_module_enabled` آن یکی را — «آیا واقعاً کار می‌کند».
    """
    module = MODULES_BY_KEY.get(key)
    if module is None:
        raise KeyError(f"ماژولی با کلید «{key}» تعریف نشده است (core/modules.py)")
    row = db.get(ModuleSetting, key)
    return row.enabled if row is not None else module.default_enabled


def unmet_requirements(db: Session, key: str) -> tuple[str, ...]:
    """وابستگی‌های خاموشِ این ماژول — تهی یعنی چیزی سرِ راهش نیست."""
    module = MODULES_BY_KEY[key]
    return tuple(
        required for required in module.requires if not stored_module_state(db, required)
    )


def is_module_enabled(db: Session, key: str) -> bool:
    """این ماژول روشن است؟ کلیدِ ناشناخته خطاست، نه «روشن».

    پیش از این کلیدِ ناشناخته `True` برمی‌گشت. تنها راهِ رسیدن به آن شاخه یک
    غلطِ تایپی در خودِ کد است (ردیفِ دیتابیس زودتر پیدا می‌شود)، و نتیجه‌اش
    گاردی بود که همیشه می‌گذارد — یعنی درست همان حالتی که به‌نظر گارد است و
    نیست. حالا بلند می‌شکند و تست همان لحظه می‌گیردش.
    """
    if not stored_module_state(db, key):
        return False
    # و وابستگی‌هایش. ماژولی که والدش خاموش است، *واقعاً* کار نمی‌کند حتی اگر
    # سوییچ خودش روشن باشد: «اعتراض به نتیجه» بی «نمایش نتیجه» یعنی کارمند به
    # عددی اعتراض کند که سرور از نشان‌دادنش امتناع می‌کند.
    #
    # این‌جا و نه فقط در پنل، چون پیکربندیِ ناسازگار همین حالا ممکن است در
    # دیتابیس نشسته باشد — سوییچ‌ها از روزِ اول مستقل بودند. غیرفعال‌کردنِ
    # سوییچ در رابط، وضعیتِ ذخیره‌شده را عوض نمی‌کند؛ این می‌کند.
    return not unmet_requirements(db, key)


#: ماژولی که «کارمند نتیجهٔ خودش را می‌بیند» را کنترل می‌کند.
SUBJECT_RESULT_MODULE = "employee_evaluation_visibility"


def subject_may_read_own_result(db: Session) -> bool:
    """آیا سوژهٔ پرونده حق دارد نتیجهٔ خودش را *از سرور* بخواند؟

    این سوییچ عمداً خواندنِ سمتِ سرور را می‌بندد و نه فقط رابط را — تصمیمی که
    گرفته و ثبت شده. ولی «سمتِ سرور» یک مسیر نیست، چند مسیر است، و تا امروز
    فقط یکی‌شان می‌پرسید:

    * `/api/me/evaluations` می‌پرسید و درست جواب می‌داد (تهی).
    * `GET /api/evaluations` نمی‌پرسید: کارمند پروندهٔ نهایی‌شدهٔ خودش را با
      اسکیمای *سمتِ زنجیره* می‌گرفت — با `evaluator_comment`، نامِ کارشناسِ
      HR و شناسهٔ هر سه صندلی.
    * `GET /api/evaluations/{id}/summary.pdf` هم نمی‌پرسید: شاخهٔ `is_subject`
      کلِ سندِ رسمیِ هش‌شده را می‌داد — امتیازِ هر شاخص، شواهدِ ارزیاب، و
      کامنت‌های همهٔ مراحل.

    یعنی سوییچی که خاموش بود، فقط *دو تا* از سه در را بسته بود. و شناسهٔ پرونده
    هم از همان فهرست به‌دست می‌آمد، پس در سومی خودبه‌خود باز می‌شد.

    این تابع همان یک قاعده است، با یک نام، تا مسیرِ تازه‌ای که فردا اضافه شود
    مجبور باشد صریح بگوید که پرسیده یا نپرسیده.

    وابستگی‌های ماژول هم از راهِ `is_module_enabled` اعمال می‌شوند، پس
    «اعتراض» و «ثبت رؤیت» که والدشان همین ماژول است خودبه‌خود پوشیده‌اند.
    """
    return is_module_enabled(db, SUBJECT_RESULT_MODULE)


def ensure_subject_may_read_own_result(db: Session) -> None:
    """قرینهٔ گارددارِ `subject_may_read_own_result`، برای مسیرهایی که پاسخِ
    تهی معنا ندارد (دانلودِ سند)."""
    if not subject_may_read_own_result(db):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail=(
                "نمایش نتیجهٔ ارزیابی برای کارکنان در این سازمان فعال نیست. "
                "برای دریافت سند به منابع انسانی مراجعه کنید."
            ),
        )


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
    if is_module_enabled(db, key):
        return
    module = MODULES_BY_KEY[key]
    # اگر خودِ سوییچ روشن است و مانع یک وابستگیِ خاموش است، پیام باید *همان* را
    # بگوید. وگرنه مدیری که سوییچ را روشن می‌بیند، دنبال خطایی می‌گردد که وجود
    # ندارد.
    blockers = unmet_requirements(db, key) if stored_module_state(db, key) else ()
    if blockers:
        names = "، ".join(f"«{MODULES_BY_KEY[b].label}»" for b in blockers)
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail=(
                f"بخش «{module.label}» به {names} نیاز دارد و آن خاموش است؛ "
                "اول آن را روشن کنید."
            ),
        )
    raise HTTPException(
        status_code=http_status.HTTP_403_FORBIDDEN,
        detail=f"بخش «{module.label}» توسط مدیر سامانه غیرفعال شده است",
    )
