"""دفترِ مصرفِ دستیار — یک ردیف برای هر نوبتی که به سرویس رفت.

چرا این جدول هست
-----------------
`/api/ai/chat` همین حالا `usage` را از سرویس می‌گیرد و به فرانت پاس می‌دهد،
و با پایانِ درخواست دور می‌ریزدش. یعنی سامانه‌ای که هر پیامش هزینهٔ واقعی
دارد، هیچ‌جا نمی‌تواند بگوید «این ماه چقدر خرج شد» یا «کدام حساب». آن عدد
اولین بار در صورت‌حسابِ سرویس دیده می‌شود — دیرترین و بدترین جای ممکن.

چرا فقط توکن، و نه ریال
------------------------
قیمتِ هر توکن به سرویس، مدل و قراردادِ همان سازمان بستگی دارد و هیچ‌کدام در
این سامانه نیست. عددِ ریالی‌ای که از یک جدولِ قیمتِ حدسی در بیاید، دقیق به
نظر می‌رسد و نیست — و همان بدترین شکلِ گزارش است. پس این‌جا فقط چیزی ثبت
می‌شود که *سرویس گفته*: توکن. تبدیلش به پول کارِ کسی است که قرارداد را
می‌بیند.

چرا ردیف با حذفِ کاربر یا گفت‌وگو نمی‌رود
------------------------------------------
هزینه اتفاق افتاده و پاک‌کردنِ حساب آن را برنمی‌گرداند. هر دو کلیدِ خارجی
`SET NULL` است و `username` به‌صورتِ *عکسِ لحظه* در خودِ ردیف می‌ماند، وگرنه
حذفِ یک حساب، خرجش را هم از دفتر پاک می‌کرد و جمعِ ماه دیگر با صورت‌حساب
نمی‌خواند.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AiUsageLog(Base):
    """مصرفِ یک نوبتِ گفت‌وگو. فقط افزوده می‌شود؛ هیچ‌جا به‌روزرسانی نمی‌شود."""

    __tablename__ = "ai_usage_log"
    __table_args__ = (
        # هر دو پرسشِ این دفتر — «هر روز چقدر» و «هر کاربر چقدر» — پنجرهٔ
        # زمانی دارند، پس `created_at` باید *اولِ* کلید باشد.
        Index("ix_ai_usage_log_created_at", "created_at"),
        Index("ix_ai_usage_log_created_at_user", "created_at", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    #: عکسِ لحظهٔ نامِ کاربری — تا ردیف پس از حذفِ حساب هم خوانا بماند.
    username: Mapped[str] = mapped_column(String(150), nullable=False)

    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="SET NULL"), nullable=True
    )

    #: کدام سرویس و کدام مدل. بی این‌ها جمعِ توکن به قیمت تبدیل نمی‌شود: نرخِ
    #: هر مدل فرق دارد و یک سازمان ممکن است وسطِ ماه مدلش را عوض کند.
    provider: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    model: Mapped[str] = mapped_column(String(120), default="", nullable=False)

    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    #: چند بار در این نوبت به سرویس رفتیم. حلقهٔ ابزار می‌تواند تا
    #: `max_tool_iterations` پله برود و هر پله یک درخواستِ مستقل است.
    calls: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    #: نوبتی که وسطش سرویس خطا داد. هزینه‌اش را داده‌ایم و جوابش را نگرفته‌ایم
    #: — و همین ردیف‌ها هستند که تفاوتِ «جمعِ دفتر» با «جمعِ صورت‌حساب» را
    #: توضیح می‌دهند.
    failed: Mapped[bool] = mapped_column(default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
