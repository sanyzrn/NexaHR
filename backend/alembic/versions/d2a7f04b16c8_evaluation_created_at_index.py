"""ایندکسِ مستقلِ `created_at` روی پرونده‌ها

`ix_evaluation_records_status_created` ترکیبی است — `(status, created_at)` —
و ستونِ پیشرو `status` است. هر فیلتری که فقط تاریخ می‌دهد و وضعیت نمی‌دهد، از
آن ایندکس هیچ سودی نمی‌برد و به اسکنِ کاملِ جدول می‌افتد.

و دقیقاً همان شکلِ فیلتر است که «آمارِ مرحله‌ها» می‌زند: پنجرهٔ
`stage_stats_window_days` و فیلترِ دوره، هر دو روی `created_at` تنهایند.

امروز اثرش دیده نمی‌شود (اسکنِ هفت‌هزار ردیف حدودِ دو میلی‌ثانیه است) و همین
دلیلِ ساختنش *حالا*ست: با انباشتِ چند سالِ پرونده، همان اسکن خطی بزرگ می‌شود،
و آن‌وقت ساختنِ ایندکس روی جدولِ شلوغِ تولید کارِ دیگری است.

`CONCURRENTLY` نیست چون مایگریشن‌های این سامانه داخلِ تراکنش اجرا می‌شوند و
جدول در لحظهٔ استقرار کوچک است؛ اگر روزی روی جدولِ بزرگ لازم شد، همان‌جا دستی
با `CONCURRENTLY` ساخته شود.

Revision ID: d2a7f04b16c8
Revises: c1e5a9d2f70b
"""
from alembic import op

revision = "d2a7f04b16c8"
down_revision = "c1e5a9d2f70b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_evaluation_records_created_at", "evaluation_records", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_records_created_at", table_name="evaluation_records")
