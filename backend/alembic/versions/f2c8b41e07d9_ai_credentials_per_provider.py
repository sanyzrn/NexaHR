"""اطلاعاتِ اتصال، یک ست برای هر سرویس

پیش از این آدرس، نام مدل و کلید در همان ردیفِ تکِ `ai_settings` بودند، پس سازمان
یک ست اطلاعات داشت و عوض‌کردنِ سرویس رویشان می‌نوشت. کسی که کلید Anthropic را
وارد کرده بود و Gemini را امتحان می‌کرد، برای برگشتن باید کلید را دوباره پیدا
می‌کرد.

سه ستون به جدولِ تازه منتقل و بعد حذف می‌شوند — نه کپی می‌مانند. دو منبع برای
یک حقیقت یعنی روزی که یکی‌شان عوض شود و آن یکی نداند.

انتقالِ داده اجباری است و نه اختیاری: نصبِ در حال کار باید بعد از این مایگریشن
هم کار کند. کلید *رمزشده* جابه‌جا می‌شود و نه رمزگشایی‌شده، پس مایگریشن هیچ‌وقت
به کلیدِ رمزنگاری نیاز ندارد و متنِ خامِ کلید هیچ‌جا نمی‌نشیند.

Revision ID: f2c8b41e07d9
Revises: e1a5c7d93f24
"""
import sqlalchemy as sa
from alembic import op

revision = "f2c8b41e07d9"
down_revision = "e1a5c7d93f24"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_provider_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        # یکتا: یک ست اطلاعات برای هر سرویس، نه چندتا. بدونِ این قید، دو ردیف
        # برای «anthropic» ممکن می‌شود و هیچ‌کس نمی‌داند کدام کار می‌کند.
        sa.Column("provider", sa.String(length=40), nullable=False, unique=True),
        sa.Column("base_url", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("model", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # اطلاعاتِ امروز به ردیفِ سرویسِ فعال می‌رود. شرطِ `<> ''` عمدی است: ردیفِ
    # خالی ساختن یعنی جدول از روز اول یک ردیفِ بی‌محتوا دارد.
    op.execute(
        """
        INSERT INTO ai_provider_credentials (provider, base_url, model, api_key_encrypted)
        SELECT provider, base_url, model, api_key_encrypted
        FROM ai_settings
        WHERE provider <> ''
          AND (base_url <> '' OR model <> '' OR api_key_encrypted <> '')
        """
    )

    op.drop_column("ai_settings", "api_key_encrypted")
    op.drop_column("ai_settings", "model")
    op.drop_column("ai_settings", "base_url")


def downgrade() -> None:
    op.add_column(
        "ai_settings",
        sa.Column("base_url", sa.String(length=300), nullable=False, server_default=""),
    )
    op.add_column(
        "ai_settings",
        sa.Column("model", sa.String(length=120), nullable=False, server_default=""),
    )
    op.add_column(
        "ai_settings",
        sa.Column("api_key_encrypted", sa.Text(), nullable=False, server_default=""),
    )

    # فقط اطلاعاتِ سرویسِ فعال برمی‌گردد؛ بقیه در همین مایگریشن از دست می‌روند
    # چون جایی برای نگه‌داشتنشان در شِمای قدیم نیست. همان محدودیتی که این
    # مایگریشن برای رفعش نوشته شد.
    op.execute(
        """
        UPDATE ai_settings AS s
        SET base_url = c.base_url,
            model = c.model,
            api_key_encrypted = c.api_key_encrypted
        FROM ai_provider_credentials AS c
        WHERE c.provider = s.provider
        """
    )

    op.drop_table("ai_provider_credentials")
