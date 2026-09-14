"""خلاصهٔ غلتانِ گفت‌وگو — تا جلسهٔ طولانی وسطش قطع نشود.

مسئله
------
پنجرهٔ تاریخچه دوازده پیام است. در یک جلسهٔ چهل‌پیامیِ اصلاحِ اکسل، مدل
پیام‌های ۱ تا ۲۸ را *اصلاً* نمی‌بیند: نه فایلی که اول کار معرفی شد، نه
تصمیمی که وسطِ راه گرفته شد، نه ستونی که کاربر گفت نادیده بگیر. از بیرون
این‌طور دیده می‌شود که «دستیار یادش رفت».

بزرگ‌کردنِ پنجره جوابش نیست: هزینهٔ هر نوبت خطی بالا می‌رود و سقفِ متنِ
سرویس هم بالاخره می‌خورَد. پس دوازده پیامِ آخر **دست‌نخورده** می‌ماند و
آن‌چه از پنجره بیرون افتاده، در یک پاراگراف جمع می‌شود.

دو تصمیم که ارزشِ نوشتن دارند
------------------------------
**۱. خلاصه‌ساز همان سرویس است و هزینه‌اش شمرده می‌شود.** فراخوانیِ اضافی در
همان نوبت اتفاق می‌افتد و مصرفش به مصرفِ همان نوبت اضافه می‌شود، پس در
دفترِ هزینه دیده می‌شود. دفتری که یک فراخوانیِ پنهانِ سامانه‌ای را نشمارد،
همان دفترِ کم‌گویی است که تازه رفعش کردیم.

**۲. شکستِ خلاصه، نوبت را نمی‌شکند.** اگر سرویس جواب نداد، خلاصهٔ قبلی سرِ
جایش می‌ماند و نوبت عادی تمام می‌شود. بدترین حالتش این است که مدل همان
چیزی را ببیند که تا دیروز می‌دید.
"""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai import AiConversation, AiMessage
from app.services.ai.port import ChatMessage

#: همان پنجره‌ای که `_history_messages` می‌فرستد. این‌جا تکرار نمی‌شود —
#: فراخواننده مقدارش را می‌دهد تا دو عدد نتوانند واگرا شوند.
DEFAULT_WINDOW = 12

#: چند پیامِ بیرون‌افتاده جمع شود تا خلاصه به‌روز شود. کوچک‌تر یعنی هزینهٔ
#: بیشتر و دقتِ بیشتر؛ شش، یعنی در یک جلسهٔ چهل‌پیامی حدودِ سه فراخوانیِ
#: اضافه.
REFRESH_AFTER = 6

#: سقفِ خلاصه. متنِ بلند دوباره همان مسئلهٔ پنجره را می‌سازد، یک لایه
#: پایین‌تر.
MAX_SUMMARY_CHARS = 1200

_INSTRUCTION = (
    "این بخشِ قدیمیِ یک گفت‌وگوی کاری در سامانهٔ ارزیابی عملکرد است. "
    "در حداکثر صد کلمهٔ فارسی خلاصه‌اش کن: چه چیزی خواسته شد، چه تصمیمی "
    "گرفته شد، چه فایلی در کار است، و چه چیزی هنوز باز مانده. "
    "فقط از همین متن بنویس و هیچ چیزی را حدس نزن. "
    "اگر خلاصهٔ قبلی داده شده، آن را با این بخش ادغام کن و یک متنِ واحد بده."
)


@dataclass
class SummaryRefresh:
    """نتیجهٔ یک تلاش برای به‌روزکردنِ خلاصه."""

    updated: bool = False
    usage: dict | None = None
    calls: int = 0


def _pending_messages(
    db: Session, conversation: AiConversation, window: int
) -> list[AiMessage]:
    """پیام‌هایی که از پنجره بیرون افتاده‌اند و هنوز خلاصه نشده‌اند."""
    rows = list(
        db.scalars(
            select(AiMessage)
            .where(
                AiMessage.conversation_id == conversation.id,
                AiMessage.role.in_(("user", "assistant")),
            )
            .order_by(AiMessage.id)
        )
    )
    outside = rows[:-window] if len(rows) > window else []
    return [row for row in outside if row.id > (conversation.summary_through_message_id or 0)]


def build_prompt(conversation: AiConversation, pending: list[AiMessage]) -> list[ChatMessage]:
    """پیام‌هایی که برای *ساختنِ خلاصه* به سرویس می‌رود.

    جدا از `refresh` نگه داشته شده تا بشود بی هیچ سرویسی آزمودش: شکلِ این
    درخواست خودش یک ادعاست — خلاصهٔ قبلی باید برود، وگرنه هر بار از صفر
    شروع می‌شود و نیمهٔ اولِ جلسه برای همیشه گم می‌شود.
    """
    transcript = "\n".join(
        f"{'کاربر' if row.role == 'user' else 'دستیار'}: {row.content}" for row in pending
    )
    previous = (conversation.summary_text or "").strip()
    body = (f"خلاصهٔ قبلی:\n{previous}\n\n" if previous else "") + f"بخشِ تازه:\n{transcript}"
    return [ChatMessage("system", _INSTRUCTION), ChatMessage("user", body)]


async def refresh(
    db: Session,
    conversation: AiConversation,
    adapter_factory,
    *,
    window: int = DEFAULT_WINDOW,
) -> SummaryRefresh:
    """اگر لازم بود، خلاصه را به‌روز کن. هیچ استثنایی بیرون نمی‌رود."""
    pending = _pending_messages(db, conversation, window)
    if len(pending) < REFRESH_AFTER:
        return SummaryRefresh()

    try:
        response = await adapter_factory().send(build_prompt(conversation, pending))
    except Exception:  # noqa: BLE001 — خلاصهٔ نداشته بهتر از نوبتِ شکسته است
        return SummaryRefresh()

    text = (response.content or "").strip()
    if not text:
        return SummaryRefresh(usage=response.usage, calls=1)

    conversation.summary_text = text[:MAX_SUMMARY_CHARS]
    conversation.summary_through_message_id = pending[-1].id
    return SummaryRefresh(updated=True, usage=response.usage, calls=1)
