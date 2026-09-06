import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { apiClient } from "../../api/client";
import { ConfirmProvider } from "../../components/ConfirmDialog";
import { ToastProvider } from "../../components/Toast";
import { UsersPage } from "./UsersPage";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    apiClient: { ...actual.apiClient, get: vi.fn(), patch: vi.fn(), post: vi.fn() },
  };
});

// صفحه برای محافظ «قفل‌نشدن حساب خود» به کاربر فعلی نیاز دارد
vi.mock("../../auth/AuthContext", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../auth/AuthContext")>();
  return {
    ...actual,
    useAuth: () => ({
      user: {
        id: 999,
        username: "hr-admin",
        display_name: "hr-admin",
        role: "hr",
        personnel_id: null,
        must_change_password: false,
      },
      loading: false,
      login: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
    }),
  };
});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ToastProvider>
          <ConfirmProvider>
            <UsersPage />
          </ConfirmProvider>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("UsersPage edit modal", () => {
  const getMock = vi.mocked(apiClient.get);
  const patchMock = vi.mocked(apiClient.patch);
  const postMock = vi.mocked(apiClient.post);

  beforeEach(() => {
    getMock.mockReset();
    patchMock.mockReset();
    postMock.mockReset();
    postMock.mockResolvedValue({ data: {} } as never);
  });

  it("opens the edit modal for an existing user and submits a role + password change", async () => {
    getMock.mockImplementation(async (url: string) => {
      if (url === "/users") {
        return {
          data: {
            total: 1,
            items: [
              {
                id: 1,
                username: "sup1",
                full_name: "مسئول واحد فروش، آقای رضایی",
                display_name: "مسئول واحد فروش، آقای رضایی",
                role: "unit_supervisor",
                is_active: true,
                personnel_id: null,
                created_at: "",
              },
            ],
          },
        };
      }
      if (url === "/personnel") {
        return { data: { total: 0, items: [] } };
      }
      throw new Error(`unexpected GET ${url}`);
    });
    patchMock.mockResolvedValue({ data: {} });

    renderPage();

    await screen.findByText("sup1");
    // نامِ آدم کنار نام کاربری دیده می‌شود؛ فهرستی که فقط «sup1» دارد همان چیزی
    // است که این ستون برای رفعش اضافه شد.
    expect(screen.getByText("مسئول واحد فروش، آقای رضایی")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "ویرایش" }));

    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText("ویرایش کاربر: مسئول واحد فروش، آقای رضایی")
    ).toBeInTheDocument();

    await userEvent.selectOptions(within(dialog).getByLabelText("نقش"), "hr");
    await userEvent.type(within(dialog).getByLabelText(/تعیین رمز جدید/), "NewPassword123");
    await userEvent.click(within(dialog).getByRole("button", { name: "ذخیره" }));

    // فقط چیزی که عوض شده. `full_name` دست‌نخورده مانده و `personnel_id` هم
    // از اول تهی بوده، پس هیچ‌کدام در بدنه نیستند.
    await waitFor(() =>
      expect(patchMock).toHaveBeenCalledWith("/users/1", {
        role: "hr",
        password: "NewPassword123",
      })
    );
  });

  it("ویرایشِ حسابِ غیرِ کارمند، اتصالِ پرسنلی‌اش را پاک نمی‌کند", async () => {
    // این دقیقاً همان اشکالی است که بی‌صدا رخ می‌داد: بازنشانیِ رمزِ یک مسئولِ
    // واحد، اتصالِ پرسنلی‌اش را می‌بُرید و کارنامه و خودارزیابی و اعلانِ نتیجهٔ
    // خودش را با هم می‌برد.
    getMock.mockImplementation(async (url: string) => {
      if (url === "/users") {
        return {
          data: {
            total: 1,
            items: [
              {
                id: 7,
                username: "sup2",
                full_name: null,
                display_name: "زهرا محمدی",
                role: "unit_supervisor",
                is_active: true,
                personnel_id: 42,
                created_at: "",
              },
            ],
          },
        };
      }
      if (url === "/personnel") {
        return {
          data: {
            total: 1,
            items: [{ id: 42, full_name: "زهرا محمدی", personnel_code: "P-42" }],
          },
        };
      }
      throw new Error(`unexpected GET ${url}`);
    });
    patchMock.mockResolvedValue({ data: {} });

    renderPage();
    await screen.findByText("sup2");
    await userEvent.click(screen.getByRole("button", { name: "ویرایش" }));

    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/تعیین رمز جدید/), "NewPassword123");
    await userEvent.click(within(dialog).getByRole("button", { name: "ذخیره" }));

    await waitFor(() => expect(patchMock).toHaveBeenCalled());
    expect(patchMock).toHaveBeenCalledWith("/users/7", { password: "NewPassword123" });
  });

  it("ساختِ حساب، اتصالِ پرسنلی را برای هر نقشی می‌فرستد", async () => {
    getMock.mockImplementation(async (url: string) => {
      if (url === "/users") return { data: { total: 0, items: [] } };
      if (url === "/personnel") {
        return {
          data: {
            total: 1,
            items: [{ id: 42, full_name: "زهرا محمدی", personnel_code: "P-42" }],
          },
        };
      }
      throw new Error(`unexpected GET ${url}`);
    });

    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: /ساخت کاربر/ }));

    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("نام کاربری"), "sup3");
    await userEvent.type(within(dialog).getByLabelText("رمز عبور"), "NewPassword123");
    await userEvent.selectOptions(within(dialog).getByLabelText("نقش"), "unit_supervisor");
    await userEvent.selectOptions(within(dialog).getByLabelText(/پرسنل متناظر/), "42");
    await userEvent.click(within(dialog).getByRole("button", { name: "ساخت کاربر" }));

    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect(postMock.mock.calls[0]?.[1]).toMatchObject({ personnel_id: 42 });
  });
});
