/** دو ماژول، دو نیمهٔ جدا از «کارنامه من».
 *
 * چرا این فایل هست: تا امروز کارتِ پروندهٔ باز — که تنها دری است به فرمِ
 * خودارزیابی — به ماژولِ `employee_evaluation_visibility` گره بود، و آن ماژول
 * **پیش‌فرض خاموش** است. ماژولِ `self_assessment` پیش‌فرض روشن است و سرور هم
 * `/me/evaluations/open` را بی‌قید سرو می‌کند. نتیجه در پیکربندیِ پیش‌فرض:
 * منابع انسانی دعوت می‌فرستاد، کارمند روی لینک می‌زد، به این صفحه می‌رسید و
 * چیزی نمی‌دید — و مهلت بی‌صدا تمام می‌شد.
 *
 * و لینکِ دعوت (`/me?self-assessment={id}`) را هیچ‌کس نمی‌خواند.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConfirmProvider } from "../../components/ConfirmDialog";
import { ToastProvider } from "../../components/Toast";
import { MyEvaluationsPanel } from "./MyEvaluationsPage";

const get = vi.fn();
vi.mock("../../api/client", () => ({
  apiClient: { get: (...a: unknown[]) => get(...a) },
  extractErrorMessage: () => "خطا",
}));

let modules: Record<string, boolean> = {};
vi.mock("../../auth/PermissionsContext", () => ({
  usePermissions: () => ({
    loading: false,
    moduleEnabled: (key: string) => modules[key] === true,
    can: () => true,
  }),
}));

const OPEN_CASE = {
  id: 42,
  evaluation_code: "EVL-0042",
  status: "draft",
  created_at: "2026-01-05T08:00:00Z",
  stage_entered_at: "2026-01-05T08:00:00Z",
  self_assessment_submitted_at: null,
  stage_label: "ثبت امتیاز",
  indicator_ids: [1, 2],
  hr_review_skipped: false,
  self_assessment_open: true,
  submission_deadline: "2026-02-01",
  submission_deadline_extended: false,
};

function renderPanel(initialPath = "/me") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialPath]}>
        <ToastProvider>
          <ConfirmProvider>
            <MyEvaluationsPanel />
          </ConfirmProvider>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  get.mockReset();
  get.mockImplementation((url: string) => {
    if (url === "/me/evaluations/open") return Promise.resolve({ data: [OPEN_CASE] });
    if (url === "/me/evaluations") return Promise.resolve({ data: { total: 0, items: [] } });
    if (url === "/me/improvement-plans") return Promise.resolve({ data: [] });
    if (url === "/indicators") return Promise.resolve({ data: [] });
    return Promise.resolve({ data: null });
  });
});

describe("MyEvaluationsPanel — تفکیک دو ماژول", () => {
  it("با پیکربندیِ پیش‌فرض (نمایشِ نتیجه خاموش، خودارزیابی روشن) فرم در دسترس است", async () => {
    modules = { self_assessment: true, employee_evaluation_visibility: false };
    renderPanel();

    expect(await screen.findByText(/پروندهٔ در جریان/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "ثبت خودارزیابی" })).toBeTruthy();
    // ولی «کدام مرحله» بخشی از ماژولِ خاموش است و نمی‌آید.
    expect(screen.queryByText("ثبت امتیاز")).toBeNull();
  });

  it("با هر دو ماژولِ خاموش، هیچ کارتی نمی‌آید", async () => {
    modules = { self_assessment: false, employee_evaluation_visibility: false };
    renderPanel();

    await waitFor(() =>
      expect(screen.getByText(/نمایش جزئیات کارنامه در این سازمان فعال نشده است/)).toBeTruthy()
    );
    expect(screen.queryByText(/پروندهٔ در جریان/)).toBeNull();
  });

  it("با نمایشِ نتیجهٔ روشن، مرحله هم دیده می‌شود", async () => {
    modules = { self_assessment: true, employee_evaluation_visibility: true };
    renderPanel();

    expect(await screen.findByText(/پروندهٔ در جریان/)).toBeTruthy();
    expect(screen.getByText("ثبت امتیاز")).toBeTruthy();
  });

  it("لینکِ دعوت، فرم را خودش باز می‌کند", async () => {
    modules = { self_assessment: true, employee_evaluation_visibility: false };
    renderPanel("/me?self-assessment=42");

    // دکمهٔ «ثبت خودارزیابی» جایش را به خودِ فرم داده است — و فرم با جای
    // نوشتنِ دستاورد شناخته می‌شود، نه با یک واژهٔ مشترک.
    expect(
      await screen.findByPlaceholderText(/راه‌اندازی سامانهٔ گزارش‌گیری/)
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "ثبت خودارزیابی" })).toBeNull();
  });

  it("لینکِ دعوت برای پروندهٔ دیگری، این کارت را باز نمی‌کند", async () => {
    modules = { self_assessment: true, employee_evaluation_visibility: false };
    renderPanel("/me?self-assessment=999");

    expect(await screen.findByRole("button", { name: "ثبت خودارزیابی" })).toBeTruthy();
  });
});
