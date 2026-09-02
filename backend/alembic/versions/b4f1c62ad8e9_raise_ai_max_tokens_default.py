"""سقفِ توکنِ پاسخِ دستیار: ۱۲۰۰ → ۴۰۰۰

۱۲۰۰ سقفِ نسخه‌ای بود که دستیار فقط حرف می‌زد. حالا یک نوبت ممکن است چند پله
داشته باشد و مدل در هر پله یا خواستهٔ ابزار می‌نویسد یا جمع‌بندیِ نهایی — و
جمع‌بندی معمولاً یک جدول است. با ۱۲۰۰ توکن، دو خرابیِ بی‌صدا رخ می‌داد:

* جوابِ نهایی وسطِ جمله بریده می‌شد و به‌عنوان جوابِ کامل نمایش داده می‌شد؛
* اگر بُرش وسطِ نوشتنِ `tool_calls` می‌افتاد، آرگومان‌ها JSONِ ناقص بودند و
  ابزار با آرگومانِ *خالی* اجرا می‌شد — جست‌وجو بی عبارت، فهرست بی فیلتر.

هر دو حالا صریح گزارش می‌شوند (`port.ChatResponse.truncated`)، ولی گزارشِ
خطا جایگزینِ سقفِ درست نیست.

فقط ردیف‌هایی بالا می‌روند که هنوز دقیقاً روی ۱۲۰۰ نشسته‌اند — یعنی کسی دستی
عوضشان نکرده. عددی که مدیر سامانه خودش انتخاب کرده، تصمیمِ اوست و مهاجرت
نبایدش بازنویسی کند.

Revision ID: b4f1c62ad8e9
Revises: a7d3e0c194bf
"""
from alembic import op

revision = "b4f1c62ad8e9"
down_revision = "a7d3e0c194bf"
branch_labels = None
depends_on = None

_OLD_DEFAULT = "1200"
_NEW_DEFAULT = "4000"


def upgrade() -> None:
    op.alter_column("ai_settings", "max_tokens", server_default=_NEW_DEFAULT)
    op.execute(
        f"UPDATE ai_settings SET max_tokens = {_NEW_DEFAULT} "
        f"WHERE max_tokens = {_OLD_DEFAULT}"
    )


def downgrade() -> None:
    op.alter_column("ai_settings", "max_tokens", server_default=_OLD_DEFAULT)
    op.execute(
        f"UPDATE ai_settings SET max_tokens = {_OLD_DEFAULT} "
        f"WHERE max_tokens = {_NEW_DEFAULT}"
    )
