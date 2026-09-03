"""گاردِ append-only لاگ ممیزی، برای TRUNCATE هم

تریگرِ موجود `BEFORE UPDATE OR DELETE ... FOR EACH ROW` است. `TRUNCATE` هیچ
ردیفی را «UPDATE/DELETE» نمی‌کند، پس هیچ تریگرِ سطریِ نمی‌بیندش: یک
`TRUNCATE audit_log` کلِ زنجیره را بی هیچ اعتراضی پاک می‌کرد.

و شدنی هم بود: `audit_log` سمتِ *ارجاع‌دهندهٔ* کلیدهای خارجی‌اش است
(به `users` و `evaluation_records` اشاره می‌کند و کسی به آن اشاره نمی‌کند)،
پس `TRUNCATE` بی `CASCADE` هم موفق می‌شود.

تریگرِ `BEFORE TRUNCATE` عمداً `FOR EACH STATEMENT` است — TRUNCATE تریگرِ
سطری نمی‌پذیرد. همان تابعِ قبلی استفاده می‌شود، پس پیامِ خطا و ERRCODE یکی
است و `TG_OP` خودش می‌گوید کدام عملیات رد شده.

این گارد جلوی کسی که superuser است و تریگر را خاموش می‌کند را نمی‌گیرد — و
قرار هم نیست. کارش این است که پاک‌شدنِ زنجیره *تصادفی* یا از راهِ یک اسکریپتِ
نگهداریِ بی‌دقت نباشد، همان‌طور که تریگرِ UPDATE/DELETE هم همین کار را می‌کند.

Revision ID: c1e5a9d2f70b
Revises: b4f1c62ad8e9
"""
from alembic import op

revision = "c1e5a9d2f70b"
down_revision = "b4f1c62ad8e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TRIGGER trg_audit_log_no_truncate "
        "BEFORE TRUNCATE ON audit_log "
        "FOR EACH STATEMENT EXECUTE FUNCTION forbid_audit_log_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_log_no_truncate ON audit_log")
