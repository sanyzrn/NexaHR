/** صفحهٔ تغییرِ رمز، یک لایهٔ متمرکز است — و در حالتِ اجباری، بسته نمی‌شود.
 *
 * حالتِ اجباری و اختیاری دو قاعدهٔ متفاوت دارند و هر دو مهم‌اند:
 *
 * * **اجباری** — کاربر هنوز رمزِ تعیین‌شدهٔ منابع انسانی را دارد. نه Escape،
 *   نه کلیکِ پس‌زمینه، نه دکمهٔ بستن. تنها دو راهِ بیرون: گذاشتنِ رمزِ تازه،
 *   یا خروج از حساب. آن دکمهٔ خروج عمدی است — کسی که رمزِ فعلی‌اش را به‌یاد
 *   نمی‌آورد نباید در یک صفحه حبس شود.
 * * **اختیاری** — کاربر خودش آمده و باید بتواند برگردد.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const authState = { must_change_password: true };
const logout = vi.fn();
const navigate = vi.fn();

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({
    user: {
      id: 1,
      username: "ali",
      display_name: "علی",
      role: "employee",
      personnel_id: 5,
      must_change_password: authState.must_change_password,
    },
    logout,
    refreshUser: vi.fn(),
    loading: false,
    login: vi.fn(),
  }),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigate };
});

vi.mock("../api/client", () => ({
  apiClient: { post: vi.fn() },
  authToken: { set: vi.fn() },
  extractErrorMessage: (e: unknown) => String(e),
}));

import { ToastProvider } from "../components/Toast";
import { ChangePasswordPage } from "./ChangePasswordPage";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ToastProvider>
          <ChangePasswordPage />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const dialog = () => screen.getByRole("dialog");

describe("صفحهٔ تغییر رمز — حالتِ اجباری", () => {
  beforeEach(() => {
    authState.must_change_password = true;
    logout.mockReset();
    navigate.mockReset();
  });

  it("یک لایهٔ مودال است، نه کارتی در میانهٔ صفحه", () => {
    renderPage();
    expect(dialog()).toHaveAttribute("aria-modal", "true");
  });

  it("پشتِ لایه واقعاً تار می‌شود — نه فقط کم‌رنگ", () => {
    /* «نه چیزی دیده بشه»: پردهٔ استانداردِ مودال `blur-sm` است که متن را محو
       می‌کند ولی خواندنی می‌گذارد. لایه‌ای که بسته نمی‌شود، پردهٔ سنگین‌تری
       می‌خواهد. */
    const { container } = renderPage();
    const scrim = container.ownerDocument.querySelector(".fixed.inset-0");
    expect(scrim?.className).toMatch(/backdrop-blur-lg/);
    expect(scrim?.className).not.toMatch(/backdrop-blur-sm/);
  });

  it("دکمهٔ بستن ندارد", () => {
    renderPage();
    expect(screen.queryByRole("button", { name: "بستن" })).toBeNull();
  });

  it("Escape لایه را نمی‌بندد", () => {
    renderPage();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(navigate).not.toHaveBeenCalled();
    expect(dialog()).toBeInTheDocument();
  });

  it("فوکوس روی اولین فیلد می‌نشیند، نه جای دیگر", () => {
    renderPage();
    expect(document.activeElement).toBe(screen.getByLabelText("رمز عبور فعلی"));
  });

  it("راهِ خروج دارد: دکمهٔ خروج از حساب", () => {
    // بی این، کسی که رمزِ فعلی‌اش را به‌یاد نمی‌آورد در این صفحه حبس می‌شد.
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "خروج از حساب" }));
    expect(logout).toHaveBeenCalled();
    expect(navigate).toHaveBeenCalledWith("/login");
  });
});

describe("صفحهٔ تغییر رمز — حالتِ اختیاری", () => {
  beforeEach(() => {
    authState.must_change_password = false;
    logout.mockReset();
    navigate.mockReset();
  });

  it("قابلِ بستن است و راهِ برگشت دارد", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "بستن" }));
    expect(navigate).toHaveBeenCalledWith(-1);
  });

  it("دکمهٔ خروج از حساب ندارد — کاربر که گیر نیفتاده", () => {
    renderPage();
    expect(screen.queryByRole("button", { name: "خروج از حساب" })).toBeNull();
  });

  it("فوکوس روی فیلد می‌نشیند، نه روی دکمهٔ بستن", () => {
    /* این‌جا — و نه در حالتِ اجباری — است که `initialFocusRef` واقعاً کار
       می‌کند: دکمهٔ بستن در هدر و *پیش از* فیلدهاست، پس تلهٔ فوکوس بی این
       سراغِ آن می‌رفت. کاربری که آمده رمز عوض کند، نباید روی «بستن» بایستد. */
    renderPage();
    expect(document.activeElement).toBe(screen.getByLabelText("رمز عبور فعلی"));
    expect(document.activeElement).not.toBe(screen.getByRole("button", { name: "بستن" }));
  });
});
