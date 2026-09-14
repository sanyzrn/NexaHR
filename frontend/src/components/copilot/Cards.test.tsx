import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PendingActionCard } from "./Cards";
import type { AiPendingAction } from "../../types";

/**
 * کارتِ تأیید، آخرین خطِ دفاع در برابر تزریق است.
 *
 * بازبینی ثابت کرد مدلِ کاملاً مطیع هم پیش از ساختِ کارت ۴۰۳ می‌گیرد. ولی
 * اگر روزی چیزی از آن گارد رد شود، تنها چیزی که بینِ مهاجم و دیتابیس
 * می‌ماند همین کارت است — پس «چه چیزی عوض می‌شود» باید *دیده* شود، نه
 * اینکه پشتِ یک دکمه و یک JSONِ خام پنهان باشد.
 */
const BASE: AiPendingAction = {
  id: 1,
  tool: "grant_capabilities",
  summary: "تنظیم مجوزهای حساب «مریم» به ۲ مجوز",
  status: "pending",
  arguments: { user_id: 7, capabilities: ["manage_users"] },
  changes: [
    { label: "حساب کاربری", before: "", after: "مریم", kind: "info" },
    { label: "ساخت و ویرایش حساب کاربری", before: "", after: "اضافه می‌شود", kind: "add" },
    { label: "دادن و گرفتن مجوزها", before: "دارد", after: "حذف می‌شود", kind: "remove" },
  ],
};

function renderCard(action: Partial<AiPendingAction> = {}) {
  return render(
    <PendingActionCard
      action={{ ...BASE, ...action }}
      onConfirm={vi.fn()}
      onReject={vi.fn()}
    />,
  );
}

describe("کارت تأیید", () => {
  it("تفاوت را بدون هیچ کلیکی نشان می‌دهد", async () => {
    // اگر جمع‌شده بود، کاربر «تأیید» را بی‌دیدنش می‌زد — و همان حالتی است
    // که این کارت برای حذفش وجود دارد.
    renderCard();

    expect(screen.getByText("اضافه می‌شود")).toBeInTheDocument();
    expect(screen.getByText("حذف می‌شود")).toBeInTheDocument();
    expect(screen.getByText("مریم")).toBeInTheDocument();
  });

  it("مقدار قبلی را وقتی واقعاً بوده نشان می‌دهد", () => {
    renderCard();
    expect(screen.getByText("دارد")).toBeInTheDocument();
  });

  it("«—» به «—» را به‌عنوان تغییر نشان نمی‌دهد", () => {
    // صندلیِ خالی که خالی می‌ماند، یک سطرِ شلوغ است و هیچ اطلاعاتی ندارد.
    renderCard({
      changes: [{ label: "معاونت", before: "—", after: "—", kind: "info" }],
    });
    expect(screen.queryByText("←")).not.toBeInTheDocument();
  });

  it("دادهٔ خام پشتِ یک دکمه می‌ماند، نه تفاوت", async () => {
    renderCard();
    expect(screen.queryByText(/manage_users/)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "دادهٔ خام" }));
    expect(screen.getByText(/manage_users/)).toBeInTheDocument();
  });

  it("کارتِ بی‌تفاوت (ردیف قدیمی) نمی‌شکند", () => {
    renderCard({ changes: undefined });
    expect(screen.getByText(BASE.summary)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "دادهٔ خام" })).toBeInTheDocument();
  });
});
