/** دو رفتارِ پنجرهٔ همکار که هرکدام یک‌بار جا افتاده بودند.
 *
 *  N16 — کلیک روی یک «پیشنهاد» باید همان پیشنهاد را *بفرستد*. پیش‌تر فقط
 *  کادرِ ورودی را پر می‌کرد و کاربر باید دکمهٔ ارسال را هم می‌زد؛ ولی
 *  پیشنهادها شبیه دکمه‌اند و کسی که رویشان کلیک می‌کند منتظرِ پاسخ می‌ماند،
 *  نه منتظرِ کارِ دوم. بدترش این بود که در همان کلیک `setDraft` هنوز
 *  ننشسته بود، پس زدنِ فوریِ «ارسال» متنِ خالی می‌فرستاد.
 *
 *  N18 — کشو `role="dialog"` را ادعا می‌کرد و رفتارش را نداشت: بی
 *  `aria-modal` و بی قفلِ فوکوس. کاربرِ کیبورد با Tab از کشویِ *باز* به
 *  صفحهٔ پشتِ پرده می‌رفت (WCAG 2.1، بند ۲٫۴٫۳).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AiStatus } from "../../types";
import { CopilotSessionProvider } from "./CopilotSession";
import { CopilotPanel } from "./CopilotPanel";
import { Copilot } from "./Copilot";

const get = vi.fn();
const post = vi.fn();

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...a: unknown[]) => get(...a),
    post: (...a: unknown[]) => post(...a),
  },
  extractErrorMessage: () => "خطا",
}));
vi.mock("../../auth/AuthContext", () => ({ useAuth: () => ({ user: { id: 1, role: "hr" } }) }));
vi.mock("../Toast", () => ({ useToast: () => ({ showError: vi.fn(), showSuccess: vi.fn() }) }));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn() }));

const status: AiStatus = {
  available: true,
  allow_write_actions: true,
  allow_uploads: true,
} as AiStatus;

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CopilotSessionProvider>{node}</CopilotSessionProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  get.mockResolvedValue({ data: [] });
});

describe("پیشنهادهای خوش‌آمد (N16)", () => {
  it("کلیک روی پیشنهاد، همان متن را می‌فرستد", async () => {
    post.mockResolvedValue({
      data: { conversation_id: 7, reply: "باشد", steps: [], pending: [] },
    });
    wrap(<CopilotPanel status={status} variant="page" />);

    const suggestion = await screen.findByRole("button", {
      name: "قراردادهای رو به اتمام را نشانم بده",
    });
    fireEvent.click(suggestion);

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/ai/chat", {
        conversation_id: null,
        message: "قراردادهای رو به اتمام را نشانم بده",
      }),
    );
  });

  it("متنِ پیشنهاد بلافاصله در گفت‌وگو دیده می‌شود", async () => {
    // پیش از این، پیشنهاد فقط داخل کادرِ ورودی می‌نشست و تا کلیکِ دومِ کاربر
    // هیچ‌چیز در گفت‌وگو نبود.
    post.mockReturnValue(new Promise(() => {}));
    wrap(<CopilotPanel status={status} variant="page" />);

    fireEvent.click(await screen.findByRole("button", { name: "گزارش میانگین واحدها را بده" }));

    await waitFor(() =>
      expect(screen.getByText("گزارش میانگین واحدها را بده")).toBeInTheDocument(),
    );
  });

  it("کادرِ ورودی پس از انتخابِ پیشنهاد خالی می‌ماند", async () => {
    // رفتارِ قبلی این بود: پیشنهاد داخل کادر می‌نشست و منتظرِ کلیکِ دومِ کاربر
    // می‌ماند. حالا متن مستقیم می‌رود و کادر برای پرسشِ بعدی خالی است.
    post.mockReturnValue(new Promise(() => {}));
    wrap(<CopilotPanel status={status} variant="page" />);

    fireEvent.click(
      await screen.findByRole("button", { name: "قراردادهای رو به اتمام را نشانم بده" }),
    );

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(screen.getByPlaceholderText("بپرسید یا بخواهید…")).toHaveValue("");
  });

});

describe("کشوی همکار (N18)", () => {
  beforeEach(() => {
    get.mockImplementation(async (url: string) =>
      url === "/ai/status" ? { data: status } : { data: [] },
    );
  });

  async function openDrawer() {
    wrap(<Copilot />);
    const opener = await screen.findByRole("button", { name: "همکار هوشمند" });
    opener.focus();
    fireEvent.click(opener);
    return { dialog: await screen.findByRole("dialog"), opener };
  }

  it("کشو یک لایهٔ modal است، نه فقط یک dialog اسمی", async () => {
    const { dialog } = await openDrawer();
    expect(dialog).toHaveAttribute("aria-modal", "true");
    // بدون tabIndex، اگر لایه هیچ عنصرِ فوکوس‌پذیری نداشت، فوکوس جایی
    // نمی‌رفت و Tab دوباره به پشتِ پرده می‌افتاد.
    expect(dialog).toHaveAttribute("tabindex", "-1");
  });

  it("با باز شدن، فوکوس داخل کشو می‌رود", async () => {
    const { dialog } = await openDrawer();
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));
  });

  it("Tab از انتهای کشو به ابتدای خودش برمی‌گردد، نه به صفحهٔ پشتِ پرده", async () => {
    const { dialog } = await openDrawer();
    const focusable = dialog.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
    );
    expect(focusable.length).toBeGreaterThan(1);
    const first = focusable[0]!;
    const last = focusable[focusable.length - 1]!;

    last.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(first);

    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(last);
  });

  it("Escape می‌بندد و فوکوس به دکمهٔ بازکننده برمی‌گردد", async () => {
    const { opener } = await openDrawer();
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(opener));
  });

  it("اسکرولِ صفحهٔ زیر قفل نمی‌شود — همکار همراهِ همان صفحه است", async () => {
    await openDrawer();
    expect(document.body.style.overflow).not.toBe("hidden");
  });
});
