import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { apiClient } from "../api/client";
import { EvaluationList } from "./EvaluationList";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, apiClient: { ...actual.apiClient, get: vi.fn() } };
});

function renderWithProviders(ui: React.ReactElement, route = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

function mockPage(items: unknown[] = []) {
  return { data: { total: items.length, items } };
}

describe("EvaluationList tabs", () => {
  it("defaults to the first tab's status filter and switches status on tab click", async () => {
    const getMock = vi.mocked(apiClient.get);
    getMock.mockResolvedValue(mockPage());

    renderWithProviders(
      <EvaluationList
        title="پرونده‌های ارزیابی"
        tabs={[
          { key: "pending", label: "در انتظار تأیید نهایی", status: "deputy_approved" },
          { key: "finalized", label: "نهایی‌شده", status: "finalized" },
          { key: "all", label: "همهٔ پرونده‌های من" },
        ]}
      />
    );

    await waitFor(() => expect(getMock).toHaveBeenCalled());
    expect(getMock.mock.calls[0]?.[1]?.params).toMatchObject({ status: "deputy_approved" });

    await userEvent.click(screen.getByRole("tab", { name: "همهٔ پرونده‌های من" }));

    // تب «همه» = بدون فیلتر وضعیت؛ پارامترهای خالی از query string حذف می‌شوند
    await waitFor(() =>
      expect(getMock.mock.calls.at(-1)?.[1]?.params).not.toHaveProperty("status")
    );
  });

  it("does not render a tab bar when only one tab is given", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(mockPage());
    renderWithProviders(<EvaluationList title="ارزیابی‌های من" tabs={[{ key: "all", label: "همه" }]} />);
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
  });
});


/** فیلترِ «صندلیِ فلان کاربر» — مقصدِ لینکِ اعلانِ «صندلی بی‌صاحب».
 *
 *  پیش از این، اعلان کدهای پرونده را نام می‌برد و منابع انسانی باید یکی‌یکی
 *  در جست‌وجو می‌چسباندشان — و برای فهرستِ بلندتر از ده مورد، بقیه اصلاً نام
 *  برده نمی‌شدند و راهی برای پیداکردنشان نبود.
 */
describe("EvaluationList seat filter", () => {
  const TABS = [
    { key: "submitted", label: "در انتظار بررسی", status: "submitted" as const },
    { key: "all", label: "همه" },
  ];

  it("فیلترِ صندلی را از آدرس می‌خواند و به سرور می‌فرستد", async () => {
    const getMock = vi.mocked(apiClient.get);
    getMock.mockResolvedValue(mockPage());

    renderWithProviders(
      <EvaluationList title="پرونده‌ها" tabs={TABS} />,
      "/hr/queue?seat_user_id=42&tab=all",
    );

    await waitFor(() =>
      expect(getMock).toHaveBeenCalledWith(
        "/evaluations",
        expect.objectContaining({ params: expect.objectContaining({ seat_user_id: 42 }) }),
      ),
    );
  });

  it("لینک `tab=all` تبِ «همه» را باز می‌کند، نه تبِ پیش‌فرض", async () => {
    // پروندهٔ متأثر می‌تواند در هر مرحله‌ای باشد؛ تبِ پیش‌فرض بیشترشان را
    // پنهان می‌کرد و فهرست خالی به‌نظر می‌رسید.
    const getMock = vi.mocked(apiClient.get);
    getMock.mockResolvedValue(mockPage());

    renderWithProviders(
      <EvaluationList title="پرونده‌ها" tabs={TABS} />,
      "/hr/queue?seat_user_id=42&tab=all",
    );

    await waitFor(() => expect(getMock).toHaveBeenCalled());
    const params = getMock.mock.calls.at(-1)![1] as { params: Record<string, unknown> };
    expect(params.params.status).toBeUndefined();
  });

  it("فیلترِ فعال دیده می‌شود و یک کلیک برداشته می‌شود", async () => {
    // فهرستی که بی‌صدا فیلتر شده بدترین حالت است: کاربر فکر می‌کند پرونده‌ای
    // وجود ندارد.
    const getMock = vi.mocked(apiClient.get);
    getMock.mockResolvedValue(mockPage());

    renderWithProviders(
      <EvaluationList title="پرونده‌ها" tabs={TABS} />,
      "/hr/queue?seat_user_id=42&tab=all",
    );

    expect(await screen.findByText(/مسئولِ مرحله است/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "نمایش همه" }));

    await waitFor(() => {
      const last = getMock.mock.calls.at(-1)![1] as { params: Record<string, unknown> };
      expect(last.params.seat_user_id).toBeUndefined();
    });
  });

  it("بی این پارامتر، هیچ فیلتری اضافه نمی‌شود و نواری نمی‌آید", async () => {
    const getMock = vi.mocked(apiClient.get);
    getMock.mockResolvedValue(mockPage());

    renderWithProviders(<EvaluationList title="پرونده‌ها" tabs={TABS} />);

    await waitFor(() => expect(getMock).toHaveBeenCalled());
    const params = getMock.mock.calls.at(-1)![1] as { params: Record<string, unknown> };
    expect(params.params.seat_user_id).toBeUndefined();
    expect(screen.queryByText(/مسئولِ مرحله است/)).toBeNull();
  });

  it("مقدارِ نامعتبر در آدرس نادیده گرفته می‌شود", async () => {
    const getMock = vi.mocked(apiClient.get);
    getMock.mockResolvedValue(mockPage());

    renderWithProviders(
      <EvaluationList title="پرونده‌ها" tabs={TABS} />,
      "/hr/queue?seat_user_id=abc",
    );

    await waitFor(() => expect(getMock).toHaveBeenCalled());
    const params = getMock.mock.calls.at(-1)![1] as { params: Record<string, unknown> };
    expect(params.params.seat_user_id).toBeUndefined();
    expect(screen.queryByText(/مسئولِ مرحله است/)).toBeNull();
  });
});
