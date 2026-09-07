/** قرینهٔ فرانت‌اندیِ جدولِ گذارهای بک‌اند (`services/workflow.TRANSITIONS`).
 *
 * این‌ها پیش از این درونِ بدنهٔ `EvaluationDetailPage` زندگی می‌کردند و همان
 * اتفاقی افتاد که برای هر قاعدهٔ دو-نسخه‌ای می‌افتد: یکی عوض شد و دیگری نه.
 * بک‌اند سه شکلِ زنجیره را می‌شناسد و صفحه فقط یکی را:
 *
 * * زنجیرهٔ **بی‌معاونت** روی `hr_approved` روی میزِ مدیرعامل می‌نشیند، ولی
 *   `canCeoFinalize` شرطِ `status === "deputy_approved"` داشت — پس آن پرونده
 *   *هیچ* دکمه‌ای نداشت: نه تأیید، نه برگشت، نه در هیچ صفی. سرور همان لحظه
 *   `POST /ceo-finalize` را با ۲۰۰ می‌پذیرفت.
 * * مسیرِ **«مدیر»** به مدیرعامل می‌رود و نه به معاونت، ولی متنِ تأییدِ
 *   منابع انسانی می‌گفت «به مرحله بررسی معاونت منتقل می‌شود».
 * * پروندهٔ **سپرشدهٔ واحدِ HR** ابزارِ نجاتش را به معاونت و مدیرعامل می‌دهد
 *   (`ensure_may_administer`)، ولی صفحه آن جعبه را فقط به `role === "hr"`
 *   نشان می‌داد — همان یک نقشی که سرور ۴۰۳ می‌دهد.
 *
 * یک تابعِ خالص، تا بشود هر شکلِ زنجیره را بی‌رندر سنجید.
 */
import type { EvaluationStatus, UserRole } from "../types";

/** جایگاه هر نقش در زنجیره — قرینهٔ `workflow._CHAIN_RANK`.
 *
 * مافوق می‌تواند کارِ مرحلهٔ پایین‌تر را بکند (مدیرعاملی که برای چند نفر خودش
 * نمره‌دهندهٔ اول است). نقشی که این‌جا نیست، در هیچ مرحله‌ای از زنجیره
 * نمی‌نشیند — و `-1` یعنی هیچ مقایسه‌ای را نمی‌برد. */
const RANK: Record<string, number> = { unit_supervisor: 1, deputy: 2, ceo: 3 };
const rankOf = (role: string) => RANK[role] ?? -1;

/** آنچه از پرونده برای تصمیمِ «چه دکمه‌ای» لازم است — و نه بیشتر. */
export interface ChainShape {
  status: EvaluationStatus;
  stage: string | null;
  unit_supervisor_user_id: number | null;
  deputy_user_id: number | null;
  ceo_user_id: number;
  hr_user_id?: number | null;
  hr_review_skipped?: boolean;
}

export interface Actor {
  id: number;
  role: UserRole | string;
}

export interface ChainActions {
  isManagerPath: boolean;
  isCeoOnlyPath: boolean;
  skipsDeputy: boolean;
  isShieldedHrCase: boolean;
  /** نقشِ صندلیِ نمره‌دهنده — برچسبِ «نظر کلی» به همان صندلی می‌رود. */
  scorerRole: "unit_supervisor" | "deputy" | "ceo";
  scorerUserId: number | null;
  isEditableScoring: boolean;
  hrClosesTheCase: boolean;
  canHrApprove: boolean;
  canDeputyApprove: boolean;
  canCeoFinalize: boolean;
  canCeoReturn: boolean;
  canRecoverStuckCase: boolean;
  canComment: boolean;
  /** مرحلهٔ بعد از تأییدِ منابع انسانی، برای متنِ دیالوگ. */
  hrApprovalMovesTo: "deputy" | "ceo" | "final";
}

export function chainActions(evaluation: ChainShape, user: Actor): ChainActions {
  // زنجیره از پایین خالی می‌شود، پس اولین صندلیِ پرشده از پایین نمره‌دهنده است.
  const isManagerPath = evaluation.unit_supervisor_user_id === null;
  const skipsDeputy = evaluation.deputy_user_id === null;
  const isCeoOnlyPath = isManagerPath && skipsDeputy;
  const scorerRole: "unit_supervisor" | "deputy" | "ceo" = isCeoOnlyPath
    ? "ceo"
    : isManagerPath
      ? "deputy"
      : "unit_supervisor";
  const scorerUserId = isCeoOnlyPath
    ? evaluation.ceo_user_id
    : isManagerPath
      ? evaluation.deputy_user_id
      : evaluation.unit_supervisor_user_id;

  const isOpenCase = evaluation.status !== "finalized" && evaluation.status !== "cancelled";
  // قرینهٔ `workflow.hr_panel_is_shielded`.
  const isShieldedHrCase = (evaluation.hr_review_skipped ?? false) && isOpenCase;

  const isCeoSeat = user.role === "ceo" && evaluation.ceo_user_id === user.id;
  const isDeputySeat = user.role === "deputy" && evaluation.deputy_user_id === user.id;

  // مرحلهٔ HR صاحبِ از پیش تعیین‌شده ندارد و از صفِ مشترک برداشته می‌شود؛ ولی
  // وقتی کسی برش داشت، کارِ پرونده با اوست و سرور بقیه را ۴۰۳ می‌کند. صفحه تا
  // امروز *هم* نوارِ مالکیت را نشان می‌داد و *هم* دکمهٔ تأیید را.
  const hrMayHandleThisCase =
    evaluation.hr_user_id === null ||
    evaluation.hr_user_id === undefined ||
    evaluation.hr_user_id === user.id;

  return {
    isManagerPath,
    isCeoOnlyPath,
    skipsDeputy,
    isShieldedHrCase,
    scorerRole,
    scorerUserId,

    // نقشِ بالاتر می‌تواند در مرحلهٔ پایین‌تر بنشیند (`may_act_at`)، ولی مالکیت
    // را شناسهٔ همان صندلی تعیین می‌کند.
    isEditableScoring:
      evaluation.status === "draft" &&
      scorerUserId === user.id &&
      rankOf(user.role) >= rankOf(scorerRole),

    // قرینهٔ `models/chain.hr_finalizes`.
    hrClosesTheCase: isCeoOnlyPath && !evaluation.hr_review_skipped,

    canHrApprove:
      user.role === "hr" && evaluation.status === "submitted" && hrMayHandleThisCase,

    canDeputyApprove:
      isDeputySeat &&
      evaluation.status === "hr_approved" &&
      evaluation.stage === "deputy_review" &&
      !isManagerPath,

    // قرینهٔ دقیقِ گاردِ `ceo_finalize`:
    //   from {deputy_approved, hr_approved}، با شرطِ «`hr_approved` فقط وقتی
    //   معاونتی در زنجیره نیست».
    //
    // شرطِ `stage === "ceo_final"` این‌جا نیست و برنمی‌گردد: `stage` از وضعیت
    // مشتق می‌شود و برای `hr_approved` همیشه `deputy_review` است، پس آن شرط
    // زنجیرهٔ بی‌معاونت را *همیشه* رد می‌کرد.
    canCeoFinalize:
      isCeoSeat &&
      (evaluation.status === "deputy_approved" ||
        (evaluation.status === "hr_approved" && skipsDeputy)),

    // برگشت، مجموعهٔ وضعیت‌های خودش را دارد و نه مجموعهٔ تأیید:
    //   * `deputy_approved` — همیشه (`ceo_return` و دو نسخهٔ مسیرِ «مدیر»).
    //   * `submitted` در مسیرِ «مستقیمِ مدیرعامل» — پنجرهٔ *اصلیِ* اصلاح، چون
    //     از وقتی تأییدِ نهایی به HR سپرده شد این زنجیره دیگر به
    //     `deputy_approved` نمی‌رسد.
    //   * `hr_approved` در زنجیرهٔ بی‌معاونت (`ceo_return_no_deputy`).
    canCeoReturn:
      isCeoSeat &&
      (evaluation.status === "deputy_approved" ||
        (isCeoOnlyPath && evaluation.status === "submitted") ||
        (skipsDeputy && !isCeoOnlyPath && evaluation.status === "hr_approved")),

    // قرینهٔ `self_evaluation.ensure_may_administer`: سپر، منابع انسانی را از
    // پروندهٔ عضوِ واحدِ خودش بیرون می‌گذارد و در عوض معاونتِ همان زنجیره و
    // مدیرعامل را راه می‌دهد.
    canRecoverStuckCase:
      isOpenCase &&
      (user.role === "hr"
        ? !isShieldedHrCase
        : isShieldedHrCase && (isCeoSeat || isDeputySeat)),

    canComment:
      (user.role === "hr" && evaluation.status === "submitted" && hrMayHandleThisCase) ||
      (isDeputySeat && evaluation.status === "hr_approved") ||
      (isCeoSeat && evaluation.status === "deputy_approved"),

    // «مرحلهٔ بعد» در هر سه شکل یکی نیست، و متنِ دیالوگ تا امروز همیشه
    // «معاونت» می‌گفت. در مسیرِ «مدیر» معاونت *خودش نمره داده* و
    // `hr_approve_manager` پرونده را مستقیم به میزِ مدیرعامل می‌برد.
    hrApprovalMovesTo: isCeoOnlyPath && !evaluation.hr_review_skipped
      ? "final"
      : isManagerPath || skipsDeputy
        ? "ceo"
        : "deputy",
  };
}
