"""دفترِ راستی‌آزماییِ زنجیرهٔ ممیزی (لنگر) — فازِ ۳پ

`audit_chain_checks`: یک ردیف به‌ازای هر راستی‌آزماییِ *کاملِ* زنجیره. تازه‌ترین
ردیفِ موفق، «لنگر» است — نقطه‌ای که بررسیِ تعاملی از آن‌جا به بعد را می‌سنجد
به‌جای کلِ تاریخ.

چرا شکست‌ها هم ثبت می‌شوند، در `models/audit_chain_check.py` نوشته شده.

این جدول هم append-only است، به همان دلیلِ خودِ لاگ: دفترِ راستی‌آزمایی که
بشود ویرایشش کرد، چیزی را راستی‌آزمایی نمی‌کند. برای همین تابعِ تریگر از
`forbid_audit_log_mutation` به `forbid_append_only_mutation` تعمیم داده می‌شود
و نامِ جدول را از `TG_TABLE_NAME` می‌گیرد — یک قاعده، یک پیاده‌سازی. متنِ خطا
همان شکل را دارد («… is append-only: UPDATE is not permitted») پس تریگرهای
موجودِ `audit_log` هم بی تغییرِ رفتار به همان تابع وصل می‌شوند.

Revision ID: e6b4c1af90d2
Revises: d2a7f04b16c8
"""
import sqlalchemy as sa
from alembic import op

revision = "e6b4c1af90d2"
down_revision = "d2a7f04b16c8"
branch_labels = None
depends_on = None

_GENERIC_GUARD = """
CREATE OR REPLACE FUNCTION forbid_append_only_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        '% is append-only: % is not permitted', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;
"""

_AUDIT_LOG_GUARD = """
CREATE OR REPLACE FUNCTION forbid_audit_log_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'audit_log is append-only: % is not permitted', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;
"""


def _attach_guards(table: str, function: str) -> None:
    op.execute(
        f"CREATE TRIGGER trg_{table}_append_only "
        f"BEFORE UPDATE OR DELETE ON {table} "
        f"FOR EACH ROW EXECUTE FUNCTION {function}()"
    )
    # `TRUNCATE` هیچ ردیفی را UPDATE/DELETE نمی‌کند، پس تریگرِ سطری نمی‌بیندش؛
    # و TRUNCATE تریگرِ سطری هم نمی‌پذیرد. همان درسِ مایگریشنِ c1e5a9d2f70b.
    op.execute(
        f"CREATE TRIGGER trg_{table}_no_truncate "
        f"BEFORE TRUNCATE ON {table} "
        f"FOR EACH STATEMENT EXECUTE FUNCTION {function}()"
    )


def upgrade() -> None:
    op.execute(_GENERIC_GUARD)

    # تریگرهای موجودِ لاگ به تابعِ تعمیم‌یافته وصل می‌شوند و تابعِ قدیمی می‌رود.
    # پیامِ خطا همان شکل را دارد، پس هیچ رفتاری عوض نمی‌شود.
    op.execute("DROP TRIGGER IF EXISTS trg_audit_log_append_only ON audit_log")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_log_no_truncate ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS forbid_audit_log_mutation()")
    _attach_guards("audit_log", "forbid_append_only_mutation")

    op.create_table(
        "audit_chain_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("log_id", sa.Integer(), sa.ForeignKey("audit_log.id"), nullable=True),
        sa.Column("entry_hash", sa.String(length=64), nullable=True),
        sa.Column("verified_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("broken_at_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(length=300), nullable=True),
        sa.Column(
            "verified_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # هر دو خواندنِ داغ روی همین ستون‌هاست: «تازه‌ترین لنگر» و «تازه‌ترین بررسی».
    op.create_index(
        "ix_audit_chain_checks_ok_id", "audit_chain_checks", ["ok", "id"]
    )
    _attach_guards("audit_chain_checks", "forbid_append_only_mutation")

    # هیچ لنگرِ اولیه‌ای ساخته نمی‌شود. لنگر باید از یک راستی‌آزماییِ *واقعی*
    # بیرون بیاید و نه از یک مایگریشن؛ لنگرِ نوشته‌شده با دست، دقیقاً همان
    # نقطهٔ کوری است که این طراحی برای پرهیز از آن است. تا اولین اجرای جارو،
    # بررسیِ سریع خودش را کامل انجام می‌دهد.


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_chain_checks_append_only ON audit_chain_checks")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_chain_checks_no_truncate ON audit_chain_checks")
    op.drop_index("ix_audit_chain_checks_ok_id", table_name="audit_chain_checks")
    op.drop_table("audit_chain_checks")

    op.execute("DROP TRIGGER IF EXISTS trg_audit_log_append_only ON audit_log")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_log_no_truncate ON audit_log")
    op.execute(_AUDIT_LOG_GUARD)
    _attach_guards("audit_log", "forbid_audit_log_mutation")
    op.execute("DROP FUNCTION IF EXISTS forbid_append_only_mutation()")
