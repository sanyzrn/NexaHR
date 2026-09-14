"""seed indicators

Revision ID: 65a700d744d4
Revises: 0e25894e177a
Create Date: 2026-07-01 03:36:20.660882

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '65a700d744d4'
down_revision: Union[str, None] = '0e25894e177a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


indicator_section_enum = sa.Enum(
    "general", "specialized", name="indicator_section", create_type=False
)

indicators_table = sa.table(
    "indicators",
    sa.column("section", indicator_section_enum),
    sa.column("category", sa.String),
    sa.column("description", sa.String),
    sa.column("display_order", sa.Integer),
    sa.column("is_active", sa.Boolean),
)

# بخش ۷.۱ سند پرامپت — شاخص‌های عمومی (section='general', وزن کل بخش ۶۰٪)
GENERAL_INDICATORS = [
    ("تعهد سازمانی", "رعایت ساعات کاری مصوب طبق سامانه حضور و غیاب در بازه ارزیابی"),
    ("تعهد سازمانی", "تعداد دفعات حضور/همراهی در شرایط اضطراری یا فوق‌العاده طبق درخواست ثبت‌شده واحد"),
    ("تعهد سازمانی", "تعداد موارد مستند تعامل مؤثر با سایر واحدها بر اساس گزارش یا ایمیل تأییدشده"),
    ("مسئولیت‌پذیری", "تعداد مواردی که اشتباه شناسایی و بدون انتساب به دیگران اصلاح شده طبق گزارش"),
    ("مسئولیت‌پذیری", "درصد انجام تعهدات و وظایف محوله در سررسید تعیین‌شده طبق چک‌لیست/سیستم وظایف"),
    ("انعطاف‌پذیری و یادگیری", "تعداد مواردی که بازخورد دریافتی منجر به اصلاح رفتار/خروجی شده طبق سابقه مستند"),
    ("انعطاف‌پذیری و یادگیری", "تعداد دوره/فعالیت آموزشی گذرانده‌شده مرتبط با شغل در بازه ارزیابی"),
    ("انضباط فردی", "تعداد تذکرات کتبی/شفاهی ثبت‌شده بابت عدم رعایت مقررات عمومی در بازه ارزیابی"),
    ("انضباط فردی", "تعداد موارد مستند نقض اصول اخلاق حرفه‌ای یا تعامل نامناسب با همکاران"),
    ("بهبود مستمر", "تعداد پیشنهادهای بهبود فرآیند ثبت‌شده در سامانه/مستندات واحد"),
    ("بهبود مستمر", "تعداد پیشنهادهای اجراشده یا منجر به بهینه‌سازی روش کاری با تأیید مسئول واحد"),
    ("محرمانگی", "تعداد موارد مستند نقض رازداری در مکاتبات/اسناد محرمانه طبق گزارش رسمی"),
]

# بخش ۷.۲ سند پرامپت — شاخص‌های تخصصی (section='specialized', وزن کل بخش ۴۰٪)
SPECIALIZED_INDICATORS = [
    ("کیفیت خروجی کار", "میزان انطباق خروجی با استاندارد/چک‌لیست شغلی تعریف‌شده طبق ممیزی یا بازبینی"),
    ("کیفیت خروجی کار", "تعداد موارد خطا، اصلاح یا بازگشت کار توسط واحد دریافت‌کننده در بازه ارزیابی"),
    ("دانش و مهارت تخصصی", "نتیجه ارزیابی/آزمون دانش فنی مرتبط با شغل یا نظر سرپرست مستقیم"),
    ("دانش و مهارت تخصصی", "تعداد دفعات نیاز به راهنمایی مکرر برای انجام صحیح وظایف در بازه ارزیابی"),
    ("تشخیص و حل مسئله", "تعداد مواردی که علت ریشه‌ای مشکل به‌درستی و مستند شناسایی شده"),
    ("تشخیص و حل مسئله", "تعداد راه‌حل‌های عملی ارائه‌شده که اجرا یا تأیید شده‌اند"),
    ("رعایت الزامات واحد و سازمان", "تعداد موارد مستند عدم انطباق با روش‌های اجرایی/فرآیندهای مصوب واحد"),
    ("رعایت الزامات واحد و سازمان", "تعداد موارد مستند عدم رعایت الزامات GMP/HSE یا استانداردهای کیفی مرتبط با شغل"),
]


def upgrade() -> None:
    rows = []
    for order, (category, description) in enumerate(GENERAL_INDICATORS, start=1):
        rows.append(
            {
                "section": "general",
                "category": category,
                "description": description,
                "display_order": order,
                "is_active": True,
            }
        )
    for order, (category, description) in enumerate(SPECIALIZED_INDICATORS, start=1):
        rows.append(
            {
                "section": "specialized",
                "category": category,
                "description": description,
                "display_order": order,
                "is_active": True,
            }
        )
    op.bulk_insert(indicators_table, rows)


def _refuse_if_the_catalogue_is_no_longer_the_seed(bind=None) -> None:
    """این `downgrade` بر اساسِ *بخش* پاک می‌کند، نه بر اساسِ «ما ساختیمش».

    یعنی شاخصی که منابع انسانی خودش اضافه کرده — و متنش را خودش نوشته — با
    همان `DELETE` می‌رود، چون آن هم `general` یا `specialized` است. هیچ‌جا
    نگه نمی‌داریم کدام ردیف از این سید آمده و کدام بعداً اضافه شده.

    شاخصی که نمره خورده، به‌خاطرِ کلیدِ خارجیِ `evaluation_scores` اصلاً پاک
    نمی‌شود و `DELETE` با خطای دیتابیس می‌افتد — یک پیامِ نامفهوم وسطِ یک
    ارتقا. شاخصی که هنوز نمره نخورده، بی‌صدا می‌رود.

    هر دو حالت بد است و هر دو یک علاج دارند: پیش از ریختنِ کاتالوگ باید
    تصمیمِ صریح گرفته شود.
    """
    bind = bind if bind is not None else op.get_bind()
    total = bind.execute(
        sa.text(
            "SELECT count(*) FROM indicators WHERE section IN ('general', 'specialized')"
        )
    ).scalar_one()
    scored = bind.execute(
        sa.text(
            "SELECT count(DISTINCT indicator_id) FROM evaluation_scores s "
            "JOIN indicators i ON i.id = s.indicator_id "
            "WHERE i.section IN ('general', 'specialized')"
        )
    ).scalar_one()
    if total > len(GENERAL_INDICATORS) + len(SPECIALIZED_INDICATORS) or scored:
        raise RuntimeError(
            f"downgrade متوقف شد: کاتالوگِ شاخص‌ها {total} ردیف دارد و "
            f"{scored} تایشان نمره خورده‌اند. این downgrade بر اساسِ *بخش* پاک "
            "می‌کند و نمی‌داند کدام ردیف از سیدِ اولیه آمده — یعنی شاخص‌هایی که "
            "خودتان اضافه کرده‌اید هم می‌روند، و آن‌هایی که نمره خورده‌اند "
            "اصلاً پاک نمی‌شوند و کلیدِ خارجی ارتقا را با خطا می‌شکند. اگر "
            "واقعاً همین را می‌خواهید، اول کاتالوگ را بیرون بگیرید."
        )


def downgrade() -> None:
    _refuse_if_the_catalogue_is_no_longer_the_seed()
    op.execute(
        sa.delete(indicators_table).where(
            indicators_table.c.section.in_(["general", "specialized"])
        )
    )
