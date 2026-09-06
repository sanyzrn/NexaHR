"""بلوکِ امضای سند و پرچمِ «تصمیم‌گیرِ یگانه» — برای هر پنج شکلِ زنجیره.

هر دو پیش از این از یک *رشتهٔ نمایشی* تصمیم می‌گرفتند، نه از صندلی‌های واقعیِ
پرونده، و روی سندی اثر می‌گذاشتند که هش می‌شود و QR تأیید دارد. این آزمون‌ها
همان پنج شکل را می‌سنجند تا بازگشتِ رفتار دیده شود.
"""
import pytest

from app.models.evaluation import EvaluationRecord
from app.services.pdf import _env
from app.services.workflow import document_signatories

SUP, DEP, CEO, HR = 11, 22, 33, 44


def _record(sup, dep, ceo, hr, hr_skipped):
    record = EvaluationRecord()
    record.unit_supervisor_user_id = sup
    record.deputy_user_id = dep
    record.ceo_user_id = ceo
    record.hr_user_id = hr
    record.hr_review_skipped = hr_skipped
    return record


#: (نامِ شکل، پرونده، امضاهای درست به ترتیب)
SHAPES = [
    ("full", _record(SUP, DEP, CEO, HR, False),
     ["مسئول واحد", "منابع انسانی", "معاونت", "مدیرعامل"]),
    ("manager", _record(None, DEP, CEO, HR, False),
     ["معاونت", "منابع انسانی", "مدیرعامل"]),
    ("ceo_direct", _record(None, None, CEO, HR, False),
     ["مدیرعامل", "منابع انسانی"]),
    ("hr_subject_full", _record(SUP, DEP, CEO, None, True),
     ["مسئول واحد", "معاونت", "مدیرعامل"]),
    ("hr_subject_manager", _record(None, DEP, CEO, None, True),
     ["معاونت", "مدیرعامل"]),
]


@pytest.mark.parametrize("name,record,expected", SHAPES, ids=[s[0] for s in SHAPES])
def test_signatories_match_the_real_seats(name, record, expected):
    assert [s["label"] for s in document_signatories(record)] == expected


def test_no_signature_for_an_empty_seat():
    """مستقیمِ مدیرعامل، همان شکلی که دو امضای جعلی می‌گرفت."""
    labels = [s["label"] for s in document_signatories(_record(None, None, CEO, HR, False))]
    assert "مسئول واحد" not in labels
    assert "معاونت" not in labels


def test_hr_signs_the_manager_path():
    """مسیرِ «مدیر» مرحلهٔ HR *دارد*؛ امضایش پیش از این می‌افتاد."""
    record = _record(None, DEP, CEO, HR, False)
    hr = [s for s in document_signatories(record) if s["seat"] == "hr_user_id"]
    assert len(hr) == 1
    assert hr[0]["user_id"] == HR


def test_hr_does_not_sign_a_shielded_record():
    """پروندهٔ خودِ واحدِ HR مرحلهٔ HR ندارد، پس امضای HR هم ندارد."""
    labels = [s["label"] for s in document_signatories(_record(SUP, DEP, CEO, None, True))]
    assert "منابع انسانی" not in labels


def test_the_direct_ceo_chain_is_no_longer_a_single_decider():
    """مدیرعامل نمره می‌دهد و منابع انسانی می‌بندد، پس دو نفرند.

    ادعا عوض شد چون سیاست عوض شد: تا پیش از این همان مدیرعامل تأییدکنندهٔ نهایی
    هم بود و سند با یک جملهٔ افشا اعلامش می‌کرد. حالا تفکیکِ واقعی برقرار است و
    جمله‌ای برای گفتن نمانده (`models/chain.hr_finalizes`).
    """
    assert _record(None, None, CEO, HR, False).single_decider is False


def test_the_hr_unit_direct_ceo_chain_is_still_a_single_decider():
    """استثنای ناگزیر: پروندهٔ خودِ واحدِ HR مرحلهٔ بی‌طرفی ندارد.

    آن پرونده به‌عمد مرحلهٔ منابع انسانی ندارد (داورش هم‌تیمیِ موضوعِ پرونده
    می‌شد)، پس کسی جز مدیرعامل نمانده و جملهٔ افشا سرِ جایش است.
    """
    assert _record(None, None, CEO, None, True).single_decider is True


def test_the_final_approver_is_hr_only_in_the_direct_ceo_chain():
    assert _record(None, None, CEO, HR, False).final_approver_user_id == HR
    assert _record(SUP, DEP, CEO, HR, False).final_approver_user_id == CEO
    assert _record(None, DEP, CEO, HR, False).final_approver_user_id == CEO
    assert _record(None, None, CEO, None, True).final_approver_user_id == CEO


def test_single_decider_sees_the_ceo_in_the_supervisor_seat():
    """همان حالتی که پیش از این تنها حالتِ شناخته‌شده بود — نباید بشکند."""
    assert _record(CEO, DEP, CEO, HR, False).single_decider is True


def test_single_decider_is_false_for_an_ordinary_chain():
    assert _record(SUP, DEP, CEO, HR, False).single_decider is False


def _render(signatories, single_decider=False):
    template = _env.get_template("evaluation_summary.html")
    return template.render(
        snapshot={
            "personnel": {"full_name": "آ", "personnel_code": "۱", "job_title": "ب", "org_unit": "پ"},
            "evaluator": {"username": "u", "role_label": "مسئول واحد"},
            "evaluation_code": "EV-1",
            "evaluation_started_at": None,
            "finalized_at": None,
            "general_score_pct": None,
            "specialized_score_pct": None,
            "base_weighted_pct": None,
            "final_weighted_pct": None,
            "bonus_points": None,
            "bonus_reason": None,
            "recommendation": None,
            "evaluator_comment": None,
            "single_decider": single_decider,
            "self_assessment": None,
            "scores": [],
            "comments": [],
            "signatories": signatories,
        },
        verify_url=None,
        verify_qr=None,
        stage_labels={},
    )


@pytest.mark.parametrize("name,record,expected", SHAPES, ids=[s[0] for s in SHAPES])
def test_rendered_document_prints_exactly_those_signatures(name, record, expected):
    """سندِ واقعی رندر می‌شود، نه فقط تابعِ پشتش."""
    html = _render(document_signatories(record))
    block = html.split('class="signatures"')[1].split("</div>\n\n")[0]
    for label in ["مسئول واحد", "منابع انسانی", "معاونت", "مدیرعامل"]:
        assert (f"امضای {label}" in block) is (label in expected), f"{name}: {label}"


def test_old_snapshots_keep_their_original_block():
    """snapshot نسخهٔ ≤۴ کلیدِ `signatories` ندارد؛ سندِ بایگانی نباید بشکند."""
    html = _render(None)
    assert "امضای مدیرعامل" in html
