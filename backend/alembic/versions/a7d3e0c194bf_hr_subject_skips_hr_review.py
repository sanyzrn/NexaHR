"""پروندهٔ اعضای واحدِ منابع انسانی، مرحلهٔ بررسیِ منابع انسانی ندارد

مرحلهٔ HR تنها مرحله‌ای است که صاحبِ از پیش تعیین‌شده ندارد و از یک صفِ مشترک
برداشته می‌شود — صفی که برای *همهٔ* کاربران HR دیده می‌شود. پس پروندهٔ اعضای همان
واحد در صفی می‌نشست که داورش هم‌تیمیِ خودشان بود.

دو ستون:

* `org_units.is_hr_unit` — کدام واحد، واحدِ منابع انسانی است. ملاک عضویتِ واحد
  است و نه نقشِ حساب، چون `may_act_at` عمداً نقشِ `hr` را از صندلی‌های زنجیره
  بیرون گذاشته: مدیرِ منابع انسانی که مسئولِ مستقیمِ کارشناسانش است نمی‌تواند
  نقشِ `hr` داشته باشد، و با ملاکِ نقشی پروندهٔ خودِ او از قلم می‌افتاد.

* `evaluation_records.hr_review_skipped` — شکلِ زنجیرهٔ *این* پرونده، مهرشده در
  لحظهٔ ساخت مثل سه صندلیِ دیگر. اگر زنده خوانده می‌شد، عوض‌شدنِ واحدِ یک نفر
  وسط چرخه پروندهٔ نشسته در صفِ HR را بی‌صدا غیرقابل‌تأیید می‌کرد.

پرچمِ واحد این‌جا با نام حدس زده می‌شود
---------------------------------------
واحدی که «منابع انسانی» در نامش هست، پرچم می‌گیرد. این یک *نقطهٔ شروع* است نه
یک قاعده: در پنل مدیریت قابل تغییر است و باید بازبینی شود. بدیلش این بود که
مهاجرت هیچ واحدی را پرچم نزند و قابلیت تا وقتی کسی دستی تنظیمش نکند بی‌اثر
بماند — یعنی همان اشکالی که این تغییر برایش نوشته شد، بی‌سروصدا باقی می‌ماند.

پرونده‌های *بسته* هم مهر می‌خورند و نه فقط بازها: ستون شکلِ زنجیره‌ای را توصیف
می‌کند که پرونده از آن گذشته، و رابط از همین می‌فهمد مرحلهٔ HR را «رد شده» نشان
بدهد یا «انجام شده». مهرنزدنِ پرونده‌های گذشته یعنی سابقهٔ همان افراد، مرحله‌ای
را نشان بدهد که هیچ‌وقت طی نشده.

Revision ID: a7d3e0c194bf
Revises: f2c8b41e07d9
"""
import sqlalchemy as sa
from alembic import op

revision = "a7d3e0c194bf"
down_revision = "f2c8b41e07d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "org_units",
        sa.Column(
            "is_hr_unit", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "evaluation_records",
        sa.Column(
            "hr_review_skipped",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # حدسِ اولیه — توضیحش بالاست.
    op.execute(
        """
        UPDATE org_units
        SET is_hr_unit = true
        WHERE name LIKE '%منابع انسانی%'
        """
    )

    # «موضوعِ این پرونده در واحدی است که پرچمِ منابع انسانی دارد؟»
    #
    # پیوند از راهِ رشته است چون `personnel.org_unit` کلید خارجی نیست. رشتهٔ
    # مقایسه همان «محل / واحد» است که `OrgUnit.full_name` می‌سازد؛ برای واحدِ
    # بی‌محل، فقط نام.
    op.execute(
        """
        UPDATE evaluation_records AS r
        SET hr_review_skipped = true
        WHERE EXISTS (
            SELECT 1
            FROM personnel AS p
            JOIN org_units AS o
              ON p.org_unit = CASE
                   WHEN o.site IS NULL OR o.site = '' THEN o.name
                   ELSE o.site || ' / ' || o.name
                 END
            WHERE p.id = r.subject_personnel_id
              AND o.is_hr_unit
        )
        """
    )


def downgrade() -> None:
    op.drop_column("evaluation_records", "hr_review_skipped")
    op.drop_column("org_units", "is_hr_unit")
