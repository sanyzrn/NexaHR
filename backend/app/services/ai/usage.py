"""ثبتِ مصرفِ هر نوبت در دفترِ هزینه.

یک ماژولِ کوچک و نه چند خط داخلِ روتر، به دو دلیل:

* **شکلِ `usage` یکسان نیست.** سرویس‌های سازگار با OpenAI
  `prompt_tokens`/`completion_tokens` می‌دهند و خانوادهٔ Anthropic
  `input_tokens`/`output_tokens`. این سامانه هر دو را پشتیبانی می‌کند
  (`core/ai_providers.py`)، پس نرمال‌سازی باید یک جا باشد، وگرنه دفتر برای
  نیمی از سرویس‌ها صفر می‌ماند — و صفرِ بی‌سروصدا بدترین حالتِ یک دفترِ
  هزینه است.
* **نوشتنِ دفتر نباید نوبت را بشکند.** اگر سرویس چیزی نداد یا شکلش عجیب
  بود، ردیف با صفر ثبت می‌شود و کاربر جوابش را می‌گیرد. گزارشِ هزینه ارزشِ
  خراب‌کردنِ یک گفت‌وگو را ندارد.
"""
from sqlalchemy.orm import Session

from app.models.ai_usage import AiUsageLog
from app.schemas.auth import CurrentUser

#: نامِ هر میدان در دو خانوادهٔ رایج. ترتیب مهم است: اولین کلیدِ موجود برنده
#: است، پس سرویسی که *هر دو* را می‌دهد (بعضی می‌دهند) دوباره شمرده نمی‌شود.
_PROMPT_KEYS = ("prompt_tokens", "input_tokens")
_COMPLETION_KEYS = ("completion_tokens", "output_tokens")
_TOTAL_KEYS = ("total_tokens",)


def _first_int(usage: dict, keys: tuple[str, ...]) -> int:
    for key in keys:
        value = usage.get(key)
        if isinstance(value, bool):  # `True` عددِ ۱ نیست، دادهٔ خراب است
            continue
        if isinstance(value, int):
            return max(0, value)
        if isinstance(value, float) and value == int(value):
            return max(0, int(value))
    return 0


def normalize(usage: dict | None) -> dict[str, int]:
    """`usage`ِ خامِ سرویس → سه عددِ قابلِ جمع.

    `total` اگر داده نشده باشد از جمعِ دو تای دیگر ساخته می‌شود و نه برعکس:
    سرویسی که فقط جمع را می‌دهد، تفکیکش را هم نداده و حدس‌زدنش یعنی ساختنِ
    عددی که هیچ‌کس نگفته.
    """
    if not isinstance(usage, dict):
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    prompt = _first_int(usage, _PROMPT_KEYS)
    completion = _first_int(usage, _COMPLETION_KEYS)
    total = _first_int(usage, _TOTAL_KEYS) or (prompt + completion)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }


def record(
    db: Session,
    *,
    user: CurrentUser,
    conversation_id: int | None,
    provider: str,
    model: str,
    usage: dict | None,
    calls: int = 1,
    failed: bool = False,
) -> AiUsageLog | None:
    """یک ردیفِ دفتر. `None` یعنی چیزی برای ثبت نبود.

    نوبتی که هیچ توکنی نسوزانده (سرویس `usage` نداد و خطا هم نداد) ردیف
    نمی‌گیرد: دفتری که پر از صفر باشد، خواندنش سخت‌تر از نداشتنش است. ولی
    نوبتِ *شکست‌خورده* حتی با صفر هم ثبت می‌شود — که شمارشش بماند.
    """
    numbers = normalize(usage)
    if numbers["total_tokens"] == 0 and not failed:
        return None
    row = AiUsageLog(
        user_id=user.id,
        username=user.username,
        conversation_id=conversation_id,
        provider=provider or "",
        model=model or "",
        calls=max(1, int(calls)),
        failed=failed,
        **numbers,
    )
    db.add(row)
    return row
