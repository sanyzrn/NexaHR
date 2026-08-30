"""آیا حسابی هست که بشود با آن وارد شد و سامانه را اداره کرد؟

چرا این فایل هست
----------------
`services/bootstrap_admin.py` در هر بالا آمدنِ سرویس همین را تضمین می‌کند، ولی
رمزِ آن حساب یک رشتهٔ تصادفی است که فقط **یک بار** در لاگ نوشته می‌شود. کسی که
آن خط را ندیده باشد، حسابی دارد که رمزش را نمی‌داند — و از بیرون این دقیقاً شبیه
«هیچ حسابی نیست» است.

پس راه‌انداز باید بتواند بپرسد «چه حساب‌هایی هستند؟» و اگر لازم بود، یکی با رمزِ
انتخابیِ خودِ کاربر بسازد (`scripts.create_admin`). این فایل نیمهٔ *پرسش* است.

معیارِ «مدیر» همان است که `bootstrap_admin` می‌سنجد — کاربرِ فعالی که مجوزِ
`manage_capabilities` دارد — و عمداً از همان‌جا import می‌شود تا دو تعریف از هم
دور نیفتند.

اجرا (از پوشهٔ backend)::

    python -m scripts.admin_status
"""
from __future__ import annotations

import json
import sys

OK = 0


def collect() -> dict:
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.capability import UserCapability
    from app.models.enums import Capability
    from app.models.user import User

    with SessionLocal() as db:
        rows = db.execute(
            select(User.username, User.full_name, User.is_active)
            .join(UserCapability, UserCapability.user_id == User.id)
            .where(UserCapability.capability == Capability.manage_capabilities)
            .order_by(User.username)
        ).all()
        total_users = db.scalar(select(User.id).limit(1)) is not None

    admins = [
        {"username": username, "full_name": full_name or "", "active": bool(active)}
        for username, full_name, active in rows
    ]
    return {
        "admins": admins,
        "has_active_admin": any(entry["active"] for entry in admins),
        "any_user": total_users,
        "error": "",
    }


def main() -> int:
    # مثل `db_info`: نتوانستن یک *جواب* است و باید در JSON بیاید، وگرنه فراخوان
    # فقط یک کدِ خروجِ لخت می‌گیرد و چیزی برای نشان دادن ندارد.
    try:
        report = collect()
    except Exception as exc:  # noqa: BLE001 - هر شکستی این‌جا باید گزارش شود
        report = {"admins": [], "has_active_admin": False, "any_user": False, "error": str(exc).strip()}

    json.dump(report, sys.stdout, ensure_ascii=False)
    print()
    return OK


if __name__ == "__main__":
    raise SystemExit(main())
