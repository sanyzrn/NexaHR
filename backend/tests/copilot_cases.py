"""درخواست‌های واقعیِ فارسی، با ابزاری که *باید* جوابشان بدهد.

این فهرست داده است و نه تست: `test_copilot_eval.py` از رویش می‌خوانَد. جدا
نگه داشته شده تا افزودنِ یک سناریو یک سطر باشد، نه یک تابع — هارنسی که
اضافه‌کردن به آن هزینه داشته باشد، بزرگ نمی‌شود.

هر ردیف یک پرسشِ واقعی است، همان‌طور که یک کاربرِ فارسی‌زبان می‌نویسد: بدون
نامِ ابزار، با نیم‌فاصله و غلطِ تایپیِ طبیعی. `tool` همان ابزاری است که
سامانه باید برای این نیت در اختیارِ *همان نقش* گذاشته باشد.
"""
from dataclasses import dataclass, field

from app.models.enums import Capability, UserRole


@dataclass(frozen=True)
class EvalCase:
    prompt: str
    role: UserRole
    tool: str
    caps: tuple[Capability, ...] = field(default=())
    #: کنشِ پرخطر اجرا نمی‌شود و کارتِ تأیید می‌سازد — هارنس همین را می‌سنجد.
    risky: bool = False


_HR = UserRole.hr
_SUP = UserRole.unit_supervisor
_DEP = UserRole.deputy
_CEO = UserRole.ceo
_EMP = UserRole.employee

_P = (Capability.manage_personnel,)
_U = (Capability.manage_users,)
_S = (Capability.manage_scoring,)
_C = (Capability.manage_capabilities,)
_A = (Capability.view_audit_log,)

#: ۴۸ سناریو. پوششش عمدی است: هر پنج نقش، هر دو جنسِ ابزار (خواندنی و
#: پرخطر)، و هر شش خانوادهٔ ابزار (پرسنل، حساب، پرونده، چارچوب، گزارش، فایل).
CASES: tuple[EvalCase, ...] = (
    # ── پرسنل ─────────────────────────────────────────────────────────────
    EvalCase("دنبال احمدی می‌گردم، پیداش کن", _HR, "search_personnel"),
    EvalCase("مشخصات کامل پرسنل شمارهٔ ۱۲ رو بده", _HR, "get_personnel"),
    EvalCase("یه نفر جدید اضافه کن: مریم رضایی، کارشناس مالی", _HR, "create_personnel", _P, True),
    EvalCase("عنوان شغلی احمدی رو بکن سرپرست انبار", _HR, "update_personnel", _P, True),
    EvalCase("رضایی از شرکت رفته، استعفا داده", _HR, "separate_personnel", _P, True),
    EvalCase("زنجیرهٔ ارزیابی مریم رو تنظیم کن", _HR, "set_evaluation_access", _P, True),
    EvalCase("زنجیرهٔ ارزیابی این نفر الان دست کیه؟", _HR, "get_evaluation_access"),
    EvalCase("یه واحد جدید بساز به اسم پشتیبانی فنی", _HR, "create_org_unit", _P, True),
    EvalCase("چه واحدهایی داریم؟", _HR, "list_org_units", _P),
    EvalCase("از احمدی بخواه خودارزیابیش رو پر کنه", _HR, "invite_self_assessment", _P, True),
    # ── حساب کاربری و مجوز ────────────────────────────────────────────────
    EvalCase("حساب کاربری برای مریم بساز با نقش معاونت", _HR, "create_user", _U, True),
    EvalCase("حساب فلانی رو غیرفعال کن", _HR, "update_user", _U, True),
    EvalCase("کاربرهایی که نقششون معاونته رو نشونم بده", _HR, "search_users", _U),
    EvalCase("چه کسی مجوز مدیریت شاخص‌ها رو داره؟", _HR, "list_user_capabilities", _C),
    EvalCase("به حساب مریم مجوز مدیریت کاربران بده", _HR, "grant_capabilities", _C, True),
    EvalCase("من خودم چه دسترسی‌هایی دارم؟", _SUP, "my_permissions"),
    # ── پرونده‌های ارزیابی ────────────────────────────────────────────────
    EvalCase("پرونده‌های باز من کدوم‌هان؟", _SUP, "my_open_cases"),
    EvalCase("چی روی میز منه؟", _DEP, "my_open_cases"),
    EvalCase("پرونده‌های امسال رو لیست کن", _HR, "search_evaluations"),
    EvalCase("جزئیات پروندهٔ EV-۱۴۰۴-۰۰۷ رو بیار", _SUP, "get_evaluation"),
    EvalCase("برای احمدی یه ارزیابی جدید باز کن", _SUP, "create_evaluation", (), True),
    EvalCase("این پرونده رو تأیید کن و بفرست مرحلهٔ بعد", _DEP, "advance_evaluation", (), True),
    EvalCase("یه یادداشت روی این پرونده بذار", _SUP, "add_evaluation_comment", (), True),
    EvalCase("قاعدهٔ محاسبهٔ نمره چطوریه؟", _EMP, "explain_evaluation_rules"),
    EvalCase("برای کل واحد فنی پرونده باز کن", _HR, "preview_bulk_evaluations"),
    EvalCase("همون کار دسته‌جمعی رو انجام بده", _HR, "run_bulk_evaluations", (), True),
    # ── چارچوب و طرح ──────────────────────────────────────────────────────
    EvalCase("شاخص‌های فعال رو نشونم بده", _HR, "list_indicators"),
    EvalCase("یه شاخص جدید اضافه کن برای نظم", _HR, "create_indicator", _S, True),
    EvalCase("متن این شاخص رو اصلاح کن", _HR, "update_indicator", _S, True),
    EvalCase("طرح‌های نمره‌دهی چندتان؟", _HR, "list_scoring_schemes", _S),
    EvalCase("یه نسخهٔ جدید از طرح نمره‌دهی بساز", _HR, "create_scoring_scheme_draft", _S, True),
    EvalCase("طرح جدید رو فعال کن", _HR, "activate_scoring_scheme", _S, True),
    EvalCase("دورهٔ ارزیابی پاییز رو باز کن", _HR, "create_period", (), True),
    EvalCase("دوره‌های ارزیابی رو لیست کن", _HR, "list_periods"),
    EvalCase("دورهٔ جاری چقدر پیش رفته؟", _HR, "period_progress"),
    # ── گزارش و تحلیل ─────────────────────────────────────────────────────
    EvalCase("خلاصهٔ وضعیت سامانه رو بگو", _HR, "dashboard_overview"),
    EvalCase("گزارش کلی امسال رو بده", _HR, "report_summary"),
    EvalCase("قراردادهایی که داره تموم می‌شه کدوم‌هان؟", _HR, "expiring_contracts"),
    EvalCase("نمرهٔ این نفر نسبت به واحدش چطوره؟", _HR, "employee_vs_unit"),
    EvalCase("من سخت‌گیرتر از بقیه نمره می‌دم؟", _SUP, "my_scoring_analysis"),
    EvalCase("یه تحلیل مدیریتی از وضعیت سازمان بده", _CEO, "executive_analysis"),
    EvalCase("برنامه‌های بهبود باز رو نشونم بده", _DEP, "search_improvement_plans"),
    EvalCase("برای این نفر برنامهٔ بهبود بنویس", _HR, "create_improvement_plan", (), True),
    EvalCase("این هدف برنامهٔ بهبود انجام شد", _SUP, "update_improvement_plan_goal", (), True),
    EvalCase("توی گزارش رویدادها دنبال تغییر مجوزها بگرد", _HR, "search_audit_log", _A),
    # ── فایل ──────────────────────────────────────────────────────────────
    EvalCase("این اکسلی که فرستادم رو بررسی کن", _HR, "inspect_upload"),
    EvalCase("ردیف سوم فایل رو اصلاح کن", _HR, "patch_upload_rows", _P, True),
    EvalCase("حالا ردیف‌های سالم رو وارد سامانه کن", _HR, "import_personnel", _P, True),
)
