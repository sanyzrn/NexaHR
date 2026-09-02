/** فرمِ پاسخ به اعتراض، به همان کسی نشان داده شود که سرور به او اجازه می‌دهد.
 *
 * دو نسخه از یک قاعده وجود دارد — `workflow.objection_resolver_field` در بک‌اند
 * و `resolverSeatId` این‌جا — و ناهم‌ترازیشان دو جور خرابی می‌دهد که هر دو بد
 * است: فرمی که ۴۰۳ می‌گیرد، یا پرونده‌ای که پاسخ‌دهنده‌اش راه پاسخ نمی‌بیند و
 * اعتراض بی‌جواب می‌ماند.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ObjectionPanel } from "./ObjectionPanel";
import { ToastProvider } from "./Toast";
import type { CurrentUser, EvaluationDetail } from "../types";

const HR = 1;
const SUPERVISOR = 2;
const DEPUTY = 3;
const CEO = 4;

function user(id: number, role: CurrentUser["role"], personnelId: number | null = null): CurrentUser {
  return {
    id,
    username: `u${id}`,
    display_name: `u${id}`,
    role,
    personnel_id: personnelId,
    must_change_password: false,
  };
}

/** پروندهٔ نهایی‌شده‌ای که اعتراضِ بی‌پاسخ دارد. */
function evaluation(over: Partial<EvaluationDetail> = {}): EvaluationDetail {
  return {
    id: 7,
    evaluation_code: "EV-7",
    subject_personnel_id: 50,
    subject_full_name: "علی قاسمی",
    period_id: null,
    unit_supervisor_user_id: SUPERVISOR,
    deputy_user_id: DEPUTY,
    ceo_user_id: CEO,
    hr_user_id: null,
    hr_username: null,
    stage: null,
    status: "finalized",
    general_score_pct: null,
    specialized_score_pct: null,
    base_weighted_pct: null,
    final_weighted_pct: 80,
    bonus_points: null,
    bonus_reason: null,
    recommendation: null,
    evaluator_comment: null,
    created_at: "2026-01-01T00:00:00Z",
    finalized_at: "2026-01-02T00:00:00Z",
    acknowledged_at: "2026-01-03T00:00:00Z",
    was_returned: false,
    objection_at: "2026-01-04T00:00:00Z",
    objection_reason: "با این نتیجه موافق نیستم",
    objection_resolved_at: null,
    objection_resolution: null,
    scores: [],
    comments: [],
    ...over,
  } as EvaluationDetail;
}

function show(current: CurrentUser, over: Partial<EvaluationDetail> = {}) {
  return render(
    <ToastProvider>
      <ObjectionPanel evaluation={evaluation(over)} user={current} onChanged={() => {}} />
    </ToastProvider>,
  );
}

const answerBox = () => screen.queryByRole("button", { name: "ثبت پاسخ" });

describe("ObjectionPanel", () => {
  it("پروندهٔ معمولی: پاسخ با منابع انسانی است", () => {
    show(user(HR, "hr"));
    expect(answerBox()).not.toBeNull();
  });

  it("پروندهٔ واحد منابع انسانی: منابع انسانی فرم پاسخ نمی‌بیند", () => {
    // همان چیزی که سرور هم ۴۰۳ می‌دهد — هم‌تیمیِ معترض بی‌طرف نیست.
    show(user(HR, "hr"), { hr_review_skipped: true });
    expect(answerBox()).toBeNull();
    expect(screen.getByText(/در انتظار پاسخ مسئول بالادست/)).toBeTruthy();
  });

  it("کارشناسِ منابع انسانی: پاسخ با معاونت است", () => {
    // نمره‌دهنده مسئولِ واحد (مدیرِ HR) است، پس نخستین سطحِ بی‌طرف معاونت است.
    show(user(DEPUTY, "deputy"), { hr_review_skipped: true });
    expect(answerBox()).not.toBeNull();
  });

  it("مدیرِ منابع انسانی: پاسخ با مدیرعامل است، نه با معاونتی که نمره داده", () => {
    const managerPath = { hr_review_skipped: true, unit_supervisor_user_id: null };
    show(user(DEPUTY, "deputy"), managerPath);
    expect(answerBox()).toBeNull();

    show(user(CEO, "ceo"), managerPath);
    expect(answerBox()).not.toBeNull();
  });

  it("موضوعِ پرونده، اعتراضِ خودش را نمی‌بندد", () => {
    // حالتِ مرزی: کاربری با نقشِ `hr` که خودش هم موضوعِ همین پرونده است.
    show(user(HR, "hr", 50));
    expect(answerBox()).toBeNull();
  });

  it("اعتراضِ پاسخ‌داده‌شده فرم ندارد، پاسخ را نشان می‌دهد", () => {
    show(user(HR, "hr"), {
      objection_resolved_at: "2026-01-05T00:00:00Z",
      objection_resolution: "بررسی شد و نتیجه بدون تغییر ماند",
    });
    expect(answerBox()).toBeNull();
    expect(screen.getByText(/نتیجه بدون تغییر ماند/)).toBeTruthy();
  });
});
