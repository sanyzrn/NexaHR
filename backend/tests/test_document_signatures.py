"""بلوکِ امضای سند و پرچمِ «تصمیم‌گیرِ یگانه» — برای هر پنج شکلِ زنجیره.

هر دو پیش از این از یک *رشتهٔ نمایشی* تصمیم می‌گرفتند، نه از صندلی‌های واقعیِ
پرونده، و روی سندی اثر می‌گذاشتند که هش می‌شود و QR تأیید دارد. این آزمون‌ها
همان پنج شکل را می‌سنجند تا بازگشتِ رفتار دیده شود.
"""
import re

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
    # مدیرعاملی که *در صندلیِ مسئولِ واحد نشسته* — شکلی که `may_act_at` مجاز
    # می‌داند و `_REDUNDANT_PAIRS` رد نمی‌کند. یک آدم، یک امضا، با هر دو سِمَت
    # روی همان یک خط. پیش از این دو خطِ جدا چاپ می‌شد و سند دو امضاکننده
    # اعلام می‌کرد که دو نفر نبودند.
    ("ceo_in_supervisor_seat", _record(CEO, DEP, CEO, HR, False),
     ["مسئول واحد و مدیرعامل", "منابع انسانی", "معاونت"]),
    # همان، بی معاونت: مدیرعامل هم نمره می‌دهد و هم امضا، و HR وسط.
    ("ceo_in_supervisor_seat_no_deputy", _record(CEO, None, CEO, HR, False),
     ["مسئول واحد و مدیرعامل", "منابع انسانی"]),
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
    """سندِ واقعی رندر می‌شود، نه فقط تابعِ پشتش.

    خطوطِ چاپ‌شده *به‌ترتیب* با فهرستِ انتظار مقایسه می‌شوند و نه با
    زیررشته‌جویی برای هر برچسب: برچسبِ ترکیبی («مسئول واحد و مدیرعامل») هر دو
    نامِ ساده را در خودش دارد، پس زیررشته‌جویی برای شکلی که یک نفر دو صندلی
    دارد جوابِ درست نمی‌دهد — و ترتیب را هم اصلاً نمی‌سنجید.
    """
    html = _render(document_signatories(record))
    block = html.split('class="signatures"')[1].split("</div>\n\n")[0]
    printed = re.findall(r"<div>امضای ([^<]+)</div>", block)
    assert printed == expected, name


def test_old_snapshots_keep_their_original_block():
    """snapshot نسخهٔ ≤۴ کلیدِ `signatories` ندارد؛ سندِ بایگانی نباید بشکند."""
    html = _render(None)
    assert "امضای مدیرعامل" in html


def test_one_person_gets_one_signature_line_even_with_two_seats():
    """شمارشِ *آدم‌ها* و نه صندلی‌ها — روی سندی که هش می‌شود.

    `may_act_at` به مدیرعامل اجازه می‌دهد در صندلیِ مسئولِ واحد بنشیند (برای
    کسی که مستقیم زیر نظر اوست ولی معاونتی هم بالای سرش هست). آن‌وقت هر دو
    صندلی پر بودند و حلقه دو ردیف می‌ساخت.
    """
    record = _record(CEO, DEP, CEO, HR, False)
    rows = document_signatories(record)
    user_ids = [row["user_id"] for row in rows]
    assert len(user_ids) == len(set(user_ids)), "یک آدم دو بار امضا نمی‌کند"
    combined = next(row for row in rows if row["user_id"] == CEO)
    assert combined["label"] == "مسئول واحد و مدیرعامل"
    assert combined["seat"] == "unit_supervisor_user_id+ceo_user_id"
