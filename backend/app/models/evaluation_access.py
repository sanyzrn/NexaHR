from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EvaluationAccess(Base):
    __tablename__ = "evaluation_access"

    id: Mapped[int] = mapped_column(primary_key=True)
    personnel_id: Mapped[int] = mapped_column(ForeignKey("personnel.id"), nullable=False)
    # هر دو خالی‌پذیرند، و هرکدام یک مرحلهٔ *نبودنی* را نشان می‌دهند:
    #
    # مسئول واحدِ خالی = مسیر «مدیر»؛ معاونت خودش نمره‌دهندهٔ اول است.
    # معاونتِ خالی = فرد مستقیم زیر نظر مدیرعامل است.
    #
    # دومی از روی ساختار واقعی یک سازمان اضافه شد: در فایل پرسنلی که وارد شد، ۹
    # نفر هیچ معاونتی بالای سرشان نداشتند. تا پیش از این ستون NOT NULL بود، یعنی
    # تنها راه ثبتشان این بود که یک معاونتِ ساختگی بالای سرشان گذاشته شود — و
    # همان اسمِ ساختگی بعداً پای تأیید پروندهٔ آن‌ها می‌نشست.
    unit_supervisor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    deputy_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ceo_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ایندکس‌ها در مایگریشن‌ها ساخته شده‌اند و تا امروز روی مدل اعلام نشده بودند،
    # پس `alembic revision --autogenerate` آن‌ها را «اضافی» می‌دید و DROP پیشنهاد
    # می‌داد. اعلامشان این‌جا یعنی autogenerate واقعیتِ دیتابیس را می‌بیند.
    __table_args__ = (
        # سه مرحله باید سه نفر باشند. در مایگریشن با NOT VALID اضافه شده‌اند
        # (توضیحش آن‌جاست)؛ اعلامشان این‌جا فقط برای این است که
        # `alembic --autogenerate` آن‌ها را «اضافی» نبیند و DROP پیشنهاد ندهد.
        CheckConstraint(
            "unit_supervisor_user_id IS NULL OR deputy_user_id IS NULL "
            "OR unit_supervisor_user_id <> deputy_user_id",
            name="ck_evaluation_access_supervisor_not_deputy",
        ),
        # «مسئول واحد = مدیرعامل» عمداً قید ندارد.
        #
        # اعلانِ یک `CheckConstraint` این‌جا بود که در دیتابیس وجود ندارد —
        # یعنی مدل قاعده‌ای را ادعا می‌کرد که سامانه ندارد، و
        # `alembic --autogenerate` روزی پیشنهادِ ساختنش را می‌داد. ساختنش
        # ثبتِ کسی را که *مستقیم زیر نظر مدیرعامل* کار می‌کند ناممکن می‌کرد:
        # مدیرعامل هم نمره‌دهندهٔ اولش است و هم تأییدکنندهٔ نهایی، و بالای سرش
        # کسِ دیگری وجود ندارد.
        #
        # تصمیمِ اصلی در مایگریشنِ `e9c47b3f1a52` نوشته شده: دو ترکیبِ دیگر
        # («مسئول واحد = معاونت» و «معاونت = مدیرعامل») بیانِ درست‌تری دارند —
        # خالی گذاشتنِ آن صندلی — پس ممنوع‌اند. این یکی ندارد، پس مجاز است و
        # به‌جای ممنوعیت، روی سندِ نهایی *افشا* می‌شود (`single_decider`).
        CheckConstraint(
            "deputy_user_id IS NULL OR deputy_user_id <> ceo_user_id",
            name="ck_evaluation_access_deputy_not_ceo",
        ),
        UniqueConstraint("personnel_id", name="uq_evaluation_access_personnel_id"),
    )
