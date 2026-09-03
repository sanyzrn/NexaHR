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
vi.mock("../api/client", () => ({ apiClient: { get: (...a: unknown[]) => get(...a) } }));
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
