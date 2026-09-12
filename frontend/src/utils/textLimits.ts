/** سقفِ طولِ فیلدهای متنیِ آزاد — قرینهٔ `backend/app/core/text_limits.py`.
 *
 * این اعداد تنظیمِ زمانِ اجرا نیستند (برخلافِ قواعدِ طرحِ نمره‌دهی که از
 * `/api/config` می‌آیند)؛ ثابتِ کدند و بی استقرارِ تازه عوض نمی‌شوند. پس
 * به‌جای یک رفت‌وبرگشتِ شبکه، این‌جا آینه می‌شوند و
 * `test_text_limits.py` می‌سنجد که دو طرف از هم جدا نشوند — همان الگویی
 * که برچسب‌های رویدادِ ممیزی و `ORG_TIMEZONE` دارند.
 *
 * چرا اصلاً لازم است: `maxLength` در کلِ فرانت **یک بار** به‌کار رفته بود.
 * یعنی کارمندی که اعتراضِ ۲٬۵۰۰ نویسه‌ای می‌نوشت، تا لحظهٔ زدنِ «ثبت» هیچ
 * نشانه‌ای نمی‌دید و بعد ۴۲۲ می‌گرفت. داده خراب نمی‌شد؛ فرم با سکوتش دروغ
 * می‌گفت.
 */

/** شواهدِ یک شاخص، و یادداشتِ خودارزیابی روی یک شاخص */
export const EVIDENCE_MAX = 2000;
export const SELF_ASSESSMENT_NOTE_MAX = 1000;
/** یادداشتِ کلیِ خودارزیابی (یکی برای کلِ پرونده، نه هر شاخص) */
export const SELF_ASSESSMENT_SUMMARY_MAX = 2000;

/** گفت‌وگوی زنجیره روی پرونده */
export const COMMENT_MAX = 4000;
/** جمع‌بندیِ ارزیاب روی کلِ پرونده */
export const EVALUATOR_COMMENT_MAX = 4000;

/** دلیلِ یک تصمیم: برگشت، لغو، واگذاریِ HR، جابه‌جاییِ مسئولِ مرحله */
export const REASON_MAX = 1000;

/** اعتراضِ کارمند و پاسخِ منابع انسانی — هر دو سندِ رسمی‌اند */
export const OBJECTION_MAX = 2000;

/** دلیلِ امتیازِ ویژه */
export const BONUS_REASON_MIN = 10;
export const BONUS_REASON_MAX = 500;

/** برنامهٔ بهبود */
export const PLAN_TITLE_MAX = 200;
export const PLAN_SUMMARY_MAX = 4000;
export const PLAN_GOAL_MAX = 1000;

/** شاخص‌های فرمِ ارزیابی (نوشتنی توسط منابع انسانی) */
export const INDICATOR_CATEGORY_MAX = 200;
export const INDICATOR_DESCRIPTION_MAX = 1000;
