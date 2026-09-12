/** ماژولی که سرور دربارهٔ آن چیزی نگفته، خاموش است — نه روشن.
 *
 *  پیش از این روشن فرض می‌شد. نگرانیِ پشتش («در فاصلهٔ بارگذاری منو نباید
 *  بخش‌های سالم را پنهان کند») درست بود ولی جایش `loading` است، و بهایش این:
 *  اگر `/administration/my-permissions` *شکست بخورد*، `loading` دیگر true
 *  نیست و `data` هم نیست، پس هر ماژولی روشن دیده می‌شد — از جمله «نمایش
 *  نتیجه به کارمند» که پیش‌فرضش خاموش است. یعنی یک درخواستِ ناموفق، نتیجهٔ
 *  ارزیابی را روی استقراری نشان می‌داد که عمداً خاموشش کرده بود.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PermissionsProvider, isModuleEnabled, usePermissions } from "./PermissionsContext";

const get = vi.fn();
// شنونده‌های ۴۰۳ را نگه می‌داریم تا بشود «سرور یک ۴۰۳ داد» را شبیه‌سازی کرد
// بی آنکه لازم باشد یک axios واقعی بالا بیاید.
const forbiddenListeners = new Set<() => void>();
vi.mock("../api/client", () => ({
  apiClient: { get: (...a: unknown[]) => get(...a) },
  onForbidden: (listener: () => void) => {
    forbiddenListeners.add(listener);
    return () => forbiddenListeners.delete(listener);
  },
}));
vi.mock("./AuthContext", () => ({ useAuth: () => ({ user: { id: 1 } }) }));

describe("isModuleEnabled", () => {
  it("وضعیتِ واقعیِ سرور را می‌گوید", () => {
    expect(isModuleEnabled({ objections: false, periods: true }, "periods")).toBe(true);
    expect(isModuleEnabled({ objections: false, periods: true }, "objections")).toBe(false);
  });

  it("نبودِ داده — درخواستِ ناموفق یا نرسیده — یعنی خاموش، نه روشن", () => {
    expect(isModuleEnabled(undefined, "employee_evaluation_visibility")).toBe(false);
  });

  it("کلیدی که سرور نامش را نبرده هم خاموش است", () => {
    expect(isModuleEnabled({ periods: true }, "objections")).toBe(false);
  });
});

function Probe() {
  const { moduleEnabled, loading } = usePermissions();
  if (loading) return <p>در حال بارگذاری</p>;
  return (
    <p data-testid="state">
      {String(moduleEnabled("objections"))}/{String(moduleEnabled("periods"))}
    </p>
  );
}

describe("PermissionsProvider", () => {
  beforeEach(() => get.mockReset());

  it("پاسخِ سرور را به همان شکل به مصرف‌کننده می‌دهد", async () => {
    get.mockResolvedValue({
      data: { capabilities: [], modules: { objections: false, periods: true } },
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <PermissionsProvider>
          <Probe />
        </PermissionsProvider>
      </QueryClientProvider>
    );
    await waitFor(() => expect(screen.getByTestId("state").textContent).toBe("false/true"));
  });
});

describe("تازه‌شدنِ مجوزها", () => {
  beforeEach(() => {
    get.mockReset();
    forbiddenListeners.clear();
  });

  it("۴۰۳ از هر مسیری، مجوزها را دوباره می‌پرسد", async () => {
    /* کشِ مجوزها `staleTime` داشت ولی هیچ محرکی نداشت: refetch روی فوکوس
       سراسری خاموش است و بازهٔ زمانی هم نبود. پس اگر ادمینِ دیگری دسترسی را
       می‌گرفت، منو تا رفرشِ کاملِ صفحه همان دکمه‌های مرده را نشان می‌داد —
       و کلیک روی هرکدام ۴۰۳ می‌گرفت، بی آنکه رابط چیزی یاد بگیرد. */
    get.mockResolvedValue({
      data: { capabilities: ["manage_users"], modules: { periods: true } },
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <PermissionsProvider>
          <Probe />
        </PermissionsProvider>
      </QueryClientProvider>
    );
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    expect(forbiddenListeners.size).toBe(1);

    // سرور یک درخواست را رد می‌کند…
    get.mockResolvedValue({ data: { capabilities: [], modules: { periods: false } } });
    for (const listener of forbiddenListeners) listener();

    // …و مجوزها دوباره پرسیده می‌شوند، با نتیجهٔ تازه.
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByTestId("state").textContent).toBe("false/false"));
  });

  it("با خروجِ کامپوننت، شنونده هم برداشته می‌شود", async () => {
    get.mockResolvedValue({ data: { capabilities: [], modules: {} } });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { unmount } = render(
      <QueryClientProvider client={client}>
        <PermissionsProvider>
          <Probe />
        </PermissionsProvider>
      </QueryClientProvider>
    );
    await waitFor(() => expect(forbiddenListeners.size).toBe(1));
    unmount();
    expect(forbiddenListeners.size).toBe(0);
  });
});
