"""برچسبِ فارسیِ هر نوعِ رویدادِ ممیزی — یک منبع، برای همهٔ مصرف‌کننده‌ها.

پیش از این *دو* نگاشت وجود داشت: یکی در `routers/audit_log.py` برای خروجیِ
اکسل، و یکی در `frontend/src/types.ts` برای فیلتر و نمایش. کامنتِ بالای اولی
می‌گفت «هم‌راستا با AUDIT_EVENT_LABELS فرانت‌اند» — و نبود: بک‌اند ۴۳ برچسب
داشت، فرانت ۴۵، و خودِ سامانه ۷۹ نوع رویداد می‌نوشت. یعنی **۳۵ نوع رویداد هیچ
برچسبی نداشت**، از جمله کلِ خانوادهٔ `ai_*`؛ منابع انسانی نمی‌توانست ردِ
نوشتن‌های دستیار را از رابط فیلتر کند و در اکسل هم فقط شناسهٔ خام می‌دید.

این فایل منبعِ بک‌اند است. نسخهٔ فرانت با
`tests/test_audit_event_labels.py` به همین قفل می‌شود: آن آزمون هر سه مجموعه
را — رویدادهایی که کد واقعاً می‌نویسد، کلیدهای این‌جا، و کلیدهای `types.ts` —
دوطرفه برابر می‌خواهد. پس رویدادِ تازه‌ای که برچسب نگیرد، همان روز قرمز
می‌شود؛ نه یک سال بعد در یک بازبینی.
"""

EVENT_LABELS: dict[str, str] = {
    # ── گردشِ کارِ ارزیابی ─────────────────────────────────────────────
    "status_changed": "تغییر وضعیت",
    "score_submitted": "ثبت امتیاز",
    "scores_draft_saved": "ذخیره پیش‌نویس امتیاز",
    "special_score_set": "ثبت امتیاز ویژه",
    "evaluation_returned": "برگشت پرونده",
    "evaluation_cancelled": "لغو پرونده",
    "evaluation_cancelled_on_separation": "لغو خودکار پرونده (خروج از سازمان)",
    "evaluation_acknowledged": "رؤیت نتیجه توسط کارمند",
    "evaluation_access_set": "ثبت زنجیرهٔ ارزیابی پرونده",
    "evaluations_bulk_created": "ساخت دسته‌ای پرونده",
    "stage_owner_reassigned": "تغییر مسئول مرحله",
    "submission_window_extended": "تمدید مهلت ثبت",
    "hr_case_claimed": "برداشتن پرونده توسط منابع انسانی",
    "hr_case_handed_over": "واگذاری مسئولیت منابع انسانی",
    "comment_added": "ثبت کامنت",
    "comment_reply_added": "ثبت پاسخ به کامنت",
    "self_assessment_submitted": "ثبت خودارزیابی کارمند",
    "self_assessment_reminded": "یادآوری خودارزیابی",
    "evaluation_objection_filed": "ثبت اعتراض کارمند",
    "evaluation_objection_resolved": "پاسخ به اعتراض کارمند",
    # ── شاخص‌ها و طرحِ نمره‌دهی ────────────────────────────────────────
    "indicator_created": "افزودن شاخص",
    "indicator_updated": "ویرایش شاخص",
    "indicator_replaced": "جایگزینی شاخص",
    "indicator_deleted": "حذف شاخص",
    "indicators_reordered": "تغییر ترتیب شاخص‌ها",
    "scoring_scheme_drafted": "ساخت پیش‌نویس طرح نمره‌دهی",
    "scoring_scheme_activated": "فعال‌سازی طرح نمره‌دهی",
    "scoring_scheme_draft_deleted": "حذف پیش‌نویس طرح نمره‌دهی",
    # ── پرسنل، کاربران و دسترسی ──────────────────────────────────────
    "personnel_created": "افزودن پرسنل",
    "personnel_updated": "ویرایش پرسنل",
    "personnel_departed": "خروج پرسنل از سازمان",
    "personnel_imported": "ورود گروهی پرسنل از فایل",
    "user_created": "ساخت کاربر",
    "user_updated": "ویرایش کاربر",
    "user_deleted": "حذف کاربر",
    "user_deactivated": "غیرفعال‌سازی کاربر",
    "user_deactivated_on_separation": "غیرفعال‌سازی خودکار حساب (خروج از سازمان)",
    "capabilities_changed": "تغییر مجوزهای کاربر",
    "access_updated": "تنظیم دسترسی ارزیابی",
    "access_supervisor_cleared_on_manager_title": "حذف خودکار مسئول واحد (تغییر عنوان به مدیر)",
    "org_unit_created": "افزودن واحد سازمانی",
    "org_unit_updated": "ویرایش واحد سازمانی",
    "org_unit_deleted": "حذف واحد سازمانی",
    # ── دوره‌ها ──────────────────────────────────────────────────────
    "period_created": "ایجاد دوره ارزیابی",
    "period_updated": "ویرایش دوره ارزیابی",
    "period_closed": "بستن دوره ارزیابی",
    # ── برنامهٔ بهبود ────────────────────────────────────────────────
    "improvement_plan_created": "ایجاد برنامه بهبود",
    "improvement_plan_updated": "ویرایش برنامه بهبود",
    "improvement_plan_completed": "تکمیل برنامه بهبود",
    "improvement_plan_cancelled": "لغو برنامه بهبود",
    "improvement_goal_added": "افزودن هدف برنامه بهبود",
    "improvement_goal_updated": "ویرایش هدف برنامه بهبود",
    "improvement_goal_deleted": "حذف هدف برنامه بهبود",
    # ── ورود، نشست و امنیت ──────────────────────────────────────────
    "login_succeeded": "ورود موفق",
    "login_failed": "ورود ناموفق",
    "password_changed_self": "تغییر رمز توسط خود کاربر",
    "account_locked": "قفل حساب پس از تلاش‌های ناموفق",
    "account_unlocked": "بازکردن قفل حساب",
    "session_revoked": "ابطال نشست",
    # ── دستیار هوشمند ───────────────────────────────────────────────
    #
    # کلِ این خانواده بی‌برچسب بود — یعنی هر کاری که دستیار روی داده‌ها
    # می‌کند در ممیزی ثبت می‌شد ولی از رابط قابل فیلتر نبود.
    "ai_settings_changed": "تغییر تنظیمات دستیار",
    "ai_access_changed": "تغییر دسترسی دستیار",
    "ai_tool_invoked": "اجرای ابزار توسط دستیار",
    "ai_tool_failed": "شکست ابزار دستیار",
    "ai_action_confirmed": "تأیید اقدام پیشنهادی دستیار",
    "ai_action_rejected": "رد اقدام پیشنهادی دستیار",
    "ai_action_failed": "شکست اقدام دستیار",
    "ai_turn_failed": "شکست پاسخ دستیار",
    "ai_upload_staged": "بارگذاری فایل برای دستیار",
    # ── تنظیماتِ سامانه ─────────────────────────────────────────────
    "module_toggled": "روشن/خاموش کردن ماژول",
    "policy_settings_changed": "تغییر تنظیمات سیاست‌ها",
    "integration_settings_changed": "تغییر تنظیمات یکپارچه‌سازی",
    "integration_test_sent": "ارسال پیام آزمایشی یکپارچه‌سازی",
    "scheduled_jobs_run": "اجرای یادآوری‌های خودکار",
    # ── خروجی‌ها ────────────────────────────────────────────────────
    "excel_exported": "خروجی Excel ارزیابی‌ها",
    "personnel_excel_exported": "خروجی Excel پرسنل",
    "users_excel_exported": "خروجی Excel کاربران",
    "improvement_plans_excel_exported": "خروجی Excel برنامه‌های بهبود",
    "audit_log_excel_exported": "خروجی Excel گزارش رویدادها",
    "report_excel_exported": "خروجی اکسل گزارش تحلیلی",
    "pdf_downloaded": "دریافت PDF",
}
