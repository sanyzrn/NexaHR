/** تا رمزِ موقت عوض نشود، هیچ چیزِ دیگری نه دیده می‌شود نه کار می‌کند.
 *
 * پیش از این، `Layout` فقط به `/change-password` هدایت می‌کرد و خودِ صفحه
 * *داخلِ همان پوسته* رندر می‌شد — پس ناوبری، زنگِ اعلان با متنِ اعلان‌ها،
 * دستیار و منوی پروفایل کنارش زنده می‌ماندند. کاربری که هنوز رمزِ تعیین‌شدهٔ
 * منابع انسانی را داشت، اعلان‌هایش را می‌خواند.
 *
 * رفعش «پنهان‌کردن با پرده» نیست، *نساختنِ* پوسته است: چیزی که رندر نشده نه
 * با z-index بالا می‌آید، نه با Tab پیدا می‌شود، نه صفحه‌خوان می‌بیندش، و نه
 * کوئری‌هایش به سرور می‌رود.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const authState = { must_change_password: true };

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
    logout: vi.fn(),
    loading: false,
    login: vi.fn(),
    refreshUser: vi.fn(),
  }),
}));

vi.mock("../auth/PermissionsContext", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../auth/PermissionsContext")>();
  return { ...actual, usePermissions: () => ({ can: () => true, moduleEnabled: () => true, loading: false }) };
});

// زنگِ اعلان و دستیار خودشان به سرور می‌زنند؛ این‌جا فقط نشانه‌ای می‌خواهیم
// که بگوید «رندر شد یا نشد».
vi.mock("./NotificationBell", () => ({
  NotificationBell: () => <div data-testid="bell">اعلان‌ها</div>,
}));
vi.mock("./copilot/Copilot", () => ({ Copilot: () => <div data-testid="copilot">دستیار</div> }));
vi.mock("./copilot/CopilotSession", () => ({
  CopilotSessionProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

import { Layout } from "./Layout";

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/change-password" element={<p>فرمِ تغییر رمز</p>} />
            <Route path="/evaluations" element={<p>فهرستِ پرونده‌ها</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("قفلِ تغییرِ رمزِ اجباری", () => {
  beforeEach(() => {
    authState.must_change_password = true;
  });

  it("پوستهٔ برنامه اصلاً ساخته نمی‌شود", () => {
    renderAt("/change-password");

    expect(screen.getByText("فرمِ تغییر رمز")).toBeInTheDocument();
    // همان چیزی که کاربر گزارش کرد: اعلان‌ها دیده می‌شدند.
    expect(screen.queryByTestId("bell")).toBeNull();
    expect(screen.queryByTestId("copilot")).toBeNull();
    // و هیچ پیوندِ ناوبری‌ای هم نیست که کاربر را جای دیگری ببرد.
    expect(screen.queryAllByRole("link")).toHaveLength(0);
  });

  it("هر مسیرِ دیگری به همان صفحه برمی‌گردد", () => {
    renderAt("/evaluations");

    expect(screen.getByText("فرمِ تغییر رمز")).toBeInTheDocument();
    expect(screen.queryByText("فهرستِ پرونده‌ها")).toBeNull();
  });

  it("با رمزِ عوض‌شده، پوسته دوباره سرِ جایش است", () => {
    // مرزِ این قفل: فقط تا وقتی رمزِ موقت هست. وگرنه این یک قفلِ دائمی بود،
    // نه یک گامِ اجباری.
    authState.must_change_password = false;
    renderAt("/evaluations");

    expect(screen.getByText("فهرستِ پرونده‌ها")).toBeInTheDocument();
    expect(screen.getByTestId("bell")).toBeInTheDocument();
  });
});
