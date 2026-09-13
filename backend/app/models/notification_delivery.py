"""صف تحویل بیرونی — «صندوق خروجی» (P1-03).

اعلان درون‌برنامه‌ای یا هست یا نیست؛ ارسال بیرونی این‌طور نیست. شبکه قطع می‌شود،
سهمیه تمام می‌شود، شماره غلط است، سرویس ۵۰۰ می‌دهد. بدون یک ردیف پایدار برای هر
ارسال، پیامی که نرفته هیچ ردی ندارد — و «چرا فلانی خبردار نشد؟» بی‌جواب می‌ماند.

سه تصمیم:

**۱. ارسال هرگز داخل تراکنش گردش‌کار انجام نمی‌شود.** فقط یک ردیف `pending` ثبت
می‌شود. اگر ارسال روی مسیر درخواست بود، کندی یا خطای سرویس پیامک به شکستِ
«تأیید پرونده» ترجمه می‌شد — همان اشتباهی که برای رندر PDF مرتکب شده بودیم.

**۲. نشانی گیرنده در لحظهٔ ثبت عکس‌برداری می‌شود.** اگر کاربر فردا شماره‌اش را
عوض کند، تلاشِ مجددِ پیامِ دیروز نباید به شمارهٔ تازه برود؛ آن پیام برای مخاطبِ
آن روز بوده و زنجیرهٔ حسابرسی باید بگوید به کجا فرستاده شد.

**۳. شکستِ دائمی از شکستِ گذرا جدا می‌ماند.** شمارهٔ نامعتبر با تلاش دوباره
درست نمی‌شود؛ تکرارش فقط سهمیه را می‌سوزاند و صف را شلوغ می‌کند.
"""
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.text_limits import DELIVERY_ERROR_MAX
from app.db.base import Base
from app.models.enums import DeliveryChannel, DeliveryStatus
from app.models.notification import Notification  # noqa: TC001  (relationship target)


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    notification_id: Mapped[int] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[DeliveryChannel] = mapped_column(
        Enum(DeliveryChannel, name="delivery_channel", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    #: نشانی/شمارهٔ گیرنده، همان‌طور که در لحظهٔ ثبت بوده
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)

    status: Mapped[DeliveryStatus] = mapped_column(
        Enum(DeliveryStatus, name="delivery_status", values_callable=lambda e: [m.value for m in e]),
        default=DeliveryStatus.pending,
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: علتِ آخرین شکست، به همان زبانی که سرویس گفته — این تنها چیزی است که موقع
    #: عیب‌یابی «چرا نرفت» در دست است.
    last_error: Mapped[str | None] = mapped_column(String(DELIVERY_ERROR_MAX), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    #: خودِ اعلان — نه فقط شناسه‌اش.
    #:
    #: بی این، ثبت‌کننده مجبور بود پیش از ساختنِ ردیفِ تحویل یک `flush()` بزند
    #: تا شناسه‌ی اعلان را داشته باشد؛ و چون هر اعلان جدا flush می‌شد، هر
    #: اعلان یک INSERTِ جدا و یک رفت‌وبرگشتِ جدا به دیتابیس بود. در جاروی SLA
    #: با هزار پروندهٔ باز، همین دو هزار رفت‌وبرگشت بود. حالا SQLAlchemy خودش
    #: ترتیب را می‌فهمد و کلیدِ خارجی را در همان flushِ پایانی پر می‌کند —
    #: یعنی درج‌ها دسته‌ای می‌شوند.
    #:
    #: فقط همین یک سمت اعلام شده و نه `Notification.deliveries`: سمتِ مقابل
    #: کاربردی ندارد و داشتنش یعنی هر بار که اعلانی پاک شود، SQLAlchemy
    #: سراغِ ردیف‌های تحویل می‌رود — کاری که خودِ `ON DELETE CASCADE` دیتابیس
    #: بهتر و ارزان‌تر انجام می‌دهد.
    notification: Mapped["Notification"] = relationship()

    __table_args__ = (
        # جاروی تحویل فقط دنبال ردیف‌های در انتظار می‌گردد، به ترتیب قدمت.
        Index("ix_deliveries_pending", "status", "created_at"),
        Index("ix_deliveries_notification", "notification_id"),
    )
