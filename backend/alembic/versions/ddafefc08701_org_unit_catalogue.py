"""فهرست واحدهای سازمانی — یک کاتالوگ که بشود تعریفش کرد

تا امروز فهرست واحدها *استخراج‌شده* بود: هر واحدی که کسی در آن ثبت شده بود. دو
پیامد داشت که هر دو در عمل دیده شدند:

* غلط تایپی («فناوری اطلاعا») بی‌سروصدا یک واحد تازه می‌ساخت، و در فیلترها کنار
  واحد درست می‌نشست بی‌آنکه کسی بفهمد چرا دو تا شده‌اند.
* واحدی که هنوز هیچ‌کس در آن نبود اصلاً وجود نداشت — یعنی برای ثبتِ اولین نفرِ
  یک واحد تازه، باید نامش را از حفظ و بی‌غلط تایپ می‌کردی.

جدول عمداً کاتالوگ است و نه کلید خارجی: `personnel.org_unit` همان رشته می‌ماند و
هیچ‌کدام از ~۱۰۰ کوئریِ موجود دست نمی‌خورد.

کاتالوگ از خودِ داده پر می‌شود
------------------------------
جدولِ خالی یعنی فرم ثبت پرسنل هیچ گزینه‌ای پیشنهاد نمی‌دهد در حالی که سازمان
ده‌ها واحد دارد. پس همان واحدهایی که همین حالا در پرونده‌های پرسنلی هستند، به
کاتالوگ منتقل می‌شوند — با همان تفکیک محل/واحدی که `split_site` می‌فهمد.

Revision ID: ddafefc08701
Revises: b3e7d19c4f60
Create Date: 2026-08-25
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "ddafefc08701"
down_revision: str | None = "b3e7d19c4f60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "org_units",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("site", sa.String(length=100), nullable=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site", "name", name="uq_org_unit_site_name"),
    )

    conn = op.get_bind()
    existing = [row[0] for row in conn.execute(text("SELECT DISTINCT org_unit FROM personnel"))]
    if not existing:
        return

    # همان تابعی که کل سامانه با آن محل را از واحد جدا می‌کند — نه یک تجزیهٔ
    # دوباره در SQL، که یعنی دو نسخه از یک قانون.
    from app.services.org_unit import split_site

    seen: set[tuple[str | None, str]] = set()
    rows = []
    for order, raw in enumerate(sorted(existing)):
        site, name = split_site(raw or "")
        if not name or (site, name) in seen:
            continue
        seen.add((site, name))
        rows.append({"site": site, "name": name, "order": order})

    if rows:
        conn.execute(
            text(
                "INSERT INTO org_units (site, name, is_active, display_order) "
                "VALUES (:site, :name, true, :order) ON CONFLICT DO NOTHING"
            ),
            rows,
        )


def _refuse_if_the_unit_catalogue_would_be_lost(bind=None) -> None:
    """نامِ واحد روی خودِ پرسنل می‌ماند؛ چیزی که می‌رود، *معنای* آن نام است.

    `personnel.org_unit` یک رشته است و با این جدول نمی‌رود، پس در نگاهِ اول
    چیزی گم نمی‌شود. ولی `is_hr_unit` این‌جاست — همان پرچمی که تصمیم می‌گیرد
    پروندهٔ چه کسی مرحلهٔ بررسیِ منابع انسانی *ندارد*. `upgrade`ِ بعدی جدول را
    خالی می‌سازد، و آن پرچم روی هیچ واحدی روشن نیست.

    نتیجه‌اش یک خرابیِ بی‌صداست: پرونده‌های واحدِ منابع انسانی از فردا دوباره
    از صفِ خودِ منابع انسانی می‌گذرند — یعنی همان تعارضِ منافعی که
    `hr_review_skipped` برای بستنش ساخته شد، بی‌آنکه کسی خبردار شود.
    """
    bind = bind if bind is not None else op.get_bind()
    units = bind.execute(sa.text("SELECT count(*) FROM org_units")).scalar_one()
    hr_units = bind.execute(
        sa.text("SELECT count(*) FROM org_units WHERE is_hr_unit")
    ).scalar_one()
    if units:
        raise RuntimeError(
            f"downgrade متوقف شد: کاتالوگِ واحدها {units} ردیف دارد "
            f"({hr_units} واحدِ منابع انسانی). این downgrade جدول را می‌ریزد و "
            "upgradeِ بعدی آن را خالی برمی‌گرداند — نامِ واحدها روی پرسنل "
            "می‌ماند ولی پرچمِ «واحدِ منابع انسانی» نه، و پرونده‌های آن واحد "
            "بی‌صدا دوباره از صفِ خودشان رد می‌شوند. اگر واقعاً همین را "
            "می‌خواهید، اول کاتالوگ را بیرون بگیرید."
        )


def downgrade() -> None:
    _refuse_if_the_unit_catalogue_would_be_lost()
    op.drop_table("org_units")
