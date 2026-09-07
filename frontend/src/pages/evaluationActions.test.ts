/** قرینهٔ فرانت با جدولِ گذارهای بک‌اند — هر پنج شکلِ زنجیره.
 *
 * چهار مورد از این تست‌ها اشکالِ واقعیِ گزارش‌شده را می‌سنجند و بی رفع
 * می‌شکنند: زنجیرهٔ بی‌معاونت که هیچ دکمه‌ای نداشت (FND-02-01)، متنِ دیالوگ
 * در مسیرِ «مدیر» (FND-09-01)، پنجرهٔ اصلاحِ مدیرعامل در مسیرِ مستقیم
 * (FND-09-02)، ابزارِ نجاتِ پروندهٔ سپرشده (FND-09-03) و دکمهٔ تأییدِ HR روی
 * پرونده‌ای که مالکش کسِ دیگری است (FND-09-04).
 */
import { describe, expect, it } from "vitest";
import { chainActions, type ChainShape } from "./evaluationActions";

const SUP = 11;
const DEP = 22;
const CEO = 33;
const HR = 44;

/** وضعیت→مرحله، قرینهٔ `STAGE_BY_STATUS`. */
const STAGE: Record<string, string> = {
  draft: "supervisor_scoring",
  submitted: "hr_review",
  hr_approved: "deputy_review",
  deputy_approved: "ceo_final",
};

function shape(over: Partial<ChainShape> & { status: ChainShape["status"] }): ChainShape {
  return {
    stage: STAGE[over.status] ?? null,
    unit_supervisor_user_id: SUP,
    deputy_user_id: DEP,
    ceo_user_id: CEO,
    hr_user_id: null,
    hr_review_skipped: false,
    ...over,
  };
}

describe("زنجیرهٔ کامل — رفتارِ مرجع", () => {
  it("مدیرعامل روی deputy_approved هم تأیید می‌کند و هم برگشت می‌دهد", () => {
    const a = chainActions(shape({ status: "deputy_approved" }), { id: CEO, role: "ceo" });
    expect(a.canCeoFinalize).toBe(true);
    expect(a.canCeoReturn).toBe(true);
  });

  it("روی hr_approved نوبتِ معاونت است و نه مدیرعامل", () => {
    const s = shape({ status: "hr_approved" });
    expect(chainActions(s, { id: DEP, role: "deputy" }).canDeputyApprove).toBe(true);
    expect(chainActions(s, { id: CEO, role: "ceo" }).canCeoFinalize).toBe(false);
  });

  it("متنِ تأییدِ منابع انسانی «معاونت» می‌گوید — چون واقعاً معاونت است", () => {
    expect(chainActions(shape({ status: "submitted" }), { id: HR, role: "hr" }).hrApprovalMovesTo).toBe(
      "deputy"
    );
  });
});

describe("زنجیرهٔ بی‌معاونت (FND-02-01)", () => {
  const noDeputy = (status: ChainShape["status"]) =>
    shape({ status, deputy_user_id: null });

  it("مدیرعامل روی hr_approved تأیید نهایی می‌کند — تا امروز هیچ دکمه‌ای نداشت", () => {
    const a = chainActions(noDeputy("hr_approved"), { id: CEO, role: "ceo" });
    expect(a.canCeoFinalize).toBe(true);
    expect(a.skipsDeputy).toBe(true);
  });

  it("و می‌تواند برگرداند، نه فقط امضا کند", () => {
    expect(chainActions(noDeputy("hr_approved"), { id: CEO, role: "ceo" }).canCeoReturn).toBe(
      true
    );
  });

  it("مدیرعاملِ زنجیرهٔ دیگری نه", () => {
    const a = chainActions(noDeputy("hr_approved"), { id: 99, role: "ceo" });
    expect(a.canCeoFinalize).toBe(false);
    expect(a.canCeoReturn).toBe(false);
  });

  it("متنِ تأییدِ HR به «مدیرعامل» اشاره می‌کند و نه به معاونتِ غایب", () => {
    expect(
      chainActions(noDeputy("submitted"), { id: HR, role: "hr" }).hrApprovalMovesTo
    ).toBe("ceo");
  });
});

describe("مسیرِ «مدیر» — معاونت خودش نمره داده (FND-09-01)", () => {
  const managerPath = (status: ChainShape["status"]) =>
    shape({ status, unit_supervisor_user_id: null });

  it("مرحلهٔ معاونت مصرف شده، پس تأییدِ معاونت بی‌معناست", () => {
    expect(
      chainActions(managerPath("hr_approved"), { id: DEP, role: "deputy" }).canDeputyApprove
    ).toBe(false);
  });

  it("متنِ تأییدِ HR نباید «بررسی معاونت» بگوید", () => {
    expect(
      chainActions(managerPath("submitted"), { id: HR, role: "hr" }).hrApprovalMovesTo
    ).toBe("ceo");
  });

  it("نمره‌دهنده معاونت است و برچسبِ نظر کلی هم به او می‌رود", () => {
    const a = chainActions(managerPath("draft"), { id: DEP, role: "deputy" });
    expect(a.scorerRole).toBe("deputy");
    expect(a.isEditableScoring).toBe(true);
  });
});

describe("مسیرِ «مستقیمِ مدیرعامل» (FND-09-02)", () => {
  const ceoOnly = (status: ChainShape["status"], over: Partial<ChainShape> = {}) =>
    shape({ status, unit_supervisor_user_id: null, deputy_user_id: null, ...over });

  it("پنجرهٔ اصلیِ اصلاح روی submitted است — جایی که هیچ دکمهٔ تأییدی نیست", () => {
    const a = chainActions(ceoOnly("submitted"), { id: CEO, role: "ceo" });
    expect(a.canCeoReturn).toBe(true);
    expect(a.canCeoFinalize).toBe(false);
  });

  it("تأییدِ منابع انسانی این پرونده را *می‌بندد*", () => {
    const a = chainActions(ceoOnly("submitted"), { id: HR, role: "hr" });
    expect(a.hrClosesTheCase).toBe(true);
    expect(a.hrApprovalMovesTo).toBe("final");
  });

  it("ولی پروندهٔ عضوِ واحدِ HR مرحلهٔ HR ندارد، پس بسته نمی‌شود", () => {
    const a = chainActions(ceoOnly("submitted", { hr_review_skipped: true }), {
      id: HR,
      role: "hr",
    });
    expect(a.hrClosesTheCase).toBe(false);
  });
});

describe("پروندهٔ سپرشدهٔ واحدِ منابع انسانی (FND-09-03)", () => {
  const shielded = shape({ status: "hr_approved", hr_review_skipped: true });

  it("ابزارِ نجات به معاونتِ همین زنجیره و مدیرعامل می‌رسد", () => {
    expect(chainActions(shielded, { id: DEP, role: "deputy" }).canRecoverStuckCase).toBe(true);
    expect(chainActions(shielded, { id: CEO, role: "ceo" }).canRecoverStuckCase).toBe(true);
  });

  it("و به منابع انسانی نمی‌رسد — همان یک نقشی که سرور ۴۰۳ می‌دهد", () => {
    expect(chainActions(shielded, { id: HR, role: "hr" }).canRecoverStuckCase).toBe(false);
  });

  it("معاونتِ زنجیرهٔ دیگری هم نه", () => {
    expect(chainActions(shielded, { id: 99, role: "deputy" }).canRecoverStuckCase).toBe(false);
  });

  it("روی پروندهٔ معمولی، کار با منابع انسانی است", () => {
    const normal = shape({ status: "hr_approved" });
    expect(chainActions(normal, { id: HR, role: "hr" }).canRecoverStuckCase).toBe(true);
    expect(chainActions(normal, { id: DEP, role: "deputy" }).canRecoverStuckCase).toBe(false);
  });

  it("پروندهٔ بسته ابزارِ نجات ندارد", () => {
    expect(
      chainActions(shape({ status: "finalized" }), { id: HR, role: "hr" }).canRecoverStuckCase
    ).toBe(false);
  });
});

describe("مالکیتِ مرحلهٔ منابع انسانی (FND-09-04)", () => {
  it("صفِ مشترک: هر کارشناسِ HR می‌تواند برش دارد", () => {
    const a = chainActions(shape({ status: "submitted" }), { id: HR, role: "hr" });
    expect(a.canHrApprove).toBe(true);
    expect(a.canComment).toBe(true);
  });

  it("ولی وقتی کسی برش داشت، دکمه برای بقیه نباید *باشد* تا کلیکش ۴۰۳ بگیرد", () => {
    const owned = shape({ status: "submitted", hr_user_id: 77 });
    const a = chainActions(owned, { id: HR, role: "hr" });
    expect(a.canHrApprove).toBe(false);
    expect(a.canComment).toBe(false);
    // و برای خودِ مالک باز است.
    expect(chainActions(owned, { id: 77, role: "hr" }).canHrApprove).toBe(true);
  });
});
