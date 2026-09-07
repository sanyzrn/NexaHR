"""رندرِ ناموفقِ سند نباید نهایی‌شدنِ پرونده را بشکند — و این‌جا واقعاً سنجیده می‌شود.

تستِ قبلی (`test_load_shape.test_the_background_helper_swallows_a_render_failure`)
**پوچ** بود: رندر را به استثنا وادار می‌کرد ولی بعد
`archive_final_pdf_detached(10**9)` را صدا می‌زد — شناسه‌ای که وجود ندارد، پس
تابع در همان `record is None` برمی‌گشت و *هیچ‌وقت* به رندر نمی‌رسید.
monkeypatch کدِ مرده بود و تست بی‌صدا همان مسیرِ «پروندهٔ ناموجود» را دوباره
می‌سنجید که تستِ بالایش پوشش می‌داد.

عاقبتش: حذفِ کاملِ `except Exception: rollback` از آن تابع، ۳۴ تست را در چهار
فایل سبز رد کرد.

این فایل هر دو شاخه را می‌سنجد و برای هر دو به پروندهٔ **commit‌شده** نیاز
دارد (وگرنه `SessionLocal()`ِ تازه چیزی نمی‌بیند — همان دامی که تستِ قبلی در
آن افتاد):

* `archive_final_pdf_detached` — کارِ پس‌زمینه، پس از ارسالِ پاسخ. هیچ‌کس
  آن‌جا نیست که خطایش را بگیرد.
* `archive_final_pdf` — همان کار در دلِ درخواست. نهایی‌شدن باید موفق بماند و
  سند بعداً با جارو ساخته شود.
"""
from datetime import date

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import hash_password
from app.models.enums import EvaluationStatus
from app.models.evaluation import EvaluationRecord
from app.models.evaluation_document import EvaluationDocument
from app.models.personnel import Personnel
from app.models.user import User


@pytest.fixture
def committed_finalized():
    """یک پروندهٔ نهایی‌شدهٔ واقعاً commit‌شده، با snapshot.

    `archive_final_pdf_detached` نشستِ خودش را باز می‌کند، پس پروندهٔ داخلِ
    تراکنشِ تست را نمی‌بیند. الگو از `test_score_write_lock.committed_draft`.
    """
    engine = create_engine(settings.database_url)
    make_session = sessionmaker(bind=engine)

    with make_session() as setup:
        password_hash = hash_password("Archive-Test-1")
        users = [
            User(username="arch_sup", password_hash=password_hash, role="unit_supervisor"),
            User(username="arch_dep", password_hash=password_hash, role="deputy"),
            User(username="arch_ceo", password_hash=password_hash, role="ceo"),
        ]
        setup.add_all(users)
        setup.flush()
        sup_id, dep_id, ceo_id = (user.id for user in users)

        personnel = Personnel(
            personnel_code="P-ARCH",
            full_name="کارمندِ بایگانی",
            job_title="کارشناس",
            org_unit="واحد تست",
            contract_start_date=date(2025, 1, 1),
            contract_end_date=date(2026, 1, 1),
        )
        setup.add(personnel)
        setup.flush()
        personnel_id = personnel.id

        record = EvaluationRecord(
            evaluation_code="EVL-ARCH",
            subject_personnel_id=personnel_id,
            unit_supervisor_user_id=sup_id,
            deputy_user_id=dep_id,
            ceo_user_id=ceo_id,
            status=EvaluationStatus.finalized,
            verify_token="arch" * 8,
            # snapshotِ کمینه: این تست‌ها رندر را عمداً می‌شکنند، پس محتوایش
            # هیچ‌وقت خوانده نمی‌شود. شکلش فقط باید `None` نباشد.
            final_snapshot={"version": 6, "comments": [], "scores": []},
        )
        setup.add(record)
        setup.flush()
        record_id = record.id
        setup.commit()

    yield {"make_session": make_session, "record_id": record_id}

    with make_session() as teardown:
        teardown.execute(
            text("DELETE FROM evaluation_documents WHERE evaluation_record_id = :r"),
            {"r": record_id},
        )
        teardown.execute(text("DELETE FROM evaluation_records WHERE id = :r"), {"r": record_id})
        teardown.execute(text("DELETE FROM personnel WHERE id = :p"), {"p": personnel_id})
        teardown.execute(
            text("DELETE FROM users WHERE id = ANY(:u)"), {"u": [sup_id, dep_id, ceo_id]}
        )
        teardown.commit()
    engine.dispose()


def _break_render(monkeypatch, error: Exception) -> None:
    from app.services import documents

    def _raise(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(documents, "render_evaluation_summary_pdf", _raise)
    # و WeasyPrint را «موجود» اعلام می‌کنیم، وگرنه تابع پیش از رندر
    # `skipped_no_weasyprint` می‌دهد و باز هم به شاخهٔ مورد نظر نمی‌رسیم —
    # همان جنسِ دامی که تستِ قبلی در آن افتاد.
    monkeypatch.setattr(documents, "weasyprint_available", lambda: True)


def test_the_background_helper_really_swallows_a_render_failure(
    committed_finalized, monkeypatch
):
    """کارِ پس‌زمینه: نه استثنا بالا می‌رود، نه سندِ نیم‌کاره می‌ماند."""
    from app.services import documents

    _break_render(monkeypatch, RuntimeError("boom"))
    record_id = committed_finalized["record_id"]

    documents.archive_final_pdf_detached(record_id)  # نباید چیزی پرتاب کند

    with committed_finalized["make_session"]() as check:
        assert (
            check.scalar(
                select(EvaluationDocument).where(
                    EvaluationDocument.evaluation_record_id == record_id
                )
            )
            is None
        ), "سندی ساخته شد در حالی که رندر شکست خورده بود"
        record = check.get(EvaluationRecord, record_id)
        assert record.status is EvaluationStatus.finalized, "پروندهٔ نهایی‌شده دست‌خورد"


def test_an_unexpected_error_type_is_swallowed_too(committed_finalized, monkeypatch):
    """`except Exception` و نه `except RuntimeError`.

    این تابع پس از ارسالِ پاسخ اجرا می‌شود؛ هر استثنایی که از آن بیرون بزند
    فقط در لاگِ کارگر می‌نشیند و هیچ‌کس نمی‌بیندش — پس دامنه‌اش عمداً باز است.
    """
    from app.services import documents

    _break_render(monkeypatch, ValueError("unexpected"))
    documents.archive_final_pdf_detached(committed_finalized["record_id"])


def test_the_in_request_branch_leaves_finalization_intact(committed_finalized, monkeypatch):
    """شاخهٔ درونِ درخواست: `None` برمی‌گرداند و نهایی‌شدن را نمی‌شکند."""
    from app.services import documents

    _break_render(monkeypatch, RuntimeError("boom"))
    with committed_finalized["make_session"]() as session:
        record = session.get(EvaluationRecord, committed_finalized["record_id"])
        assert documents.archive_final_pdf(session, record) is None
        session.commit()
        assert record.status is EvaluationStatus.finalized


def test_a_missing_record_is_still_a_silent_no_op(monkeypatch):
    """و شاخهٔ «پرونده نیست» سرِ جایش می‌ماند — این‌جا با رندرِ *سالم*، تا
    ثابت شود همان شاخه است که برمی‌گرداند و نه شکستِ رندر."""
    from app.services import documents

    called: list[int] = []
    monkeypatch.setattr(
        documents, "render_evaluation_summary_pdf", lambda *a, **k: called.append(1) or b"%PDF"
    )
    documents.archive_final_pdf_detached(10**9)
    assert called == [], "برای پروندهٔ ناموجود نباید رندری انجام شود"
