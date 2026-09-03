import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { apiClient } from "../../api/client";
import { ConfirmProvider } from "../../components/ConfirmDialog";
import { ToastProvider } from "../../components/Toast";
import { AdministrationPage } from "./AdministrationPage";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    apiClient: { ...actual.apiClient, get: vi.fn(), put: vi.fn(), post: vi.fn(), patch: vi.fn() },
  };
});

vi.mock("../../auth/AuthContext", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../auth/AuthContext")>();
  return {
    ...actual,
    useAuth: () => ({
      user: {
        id: 1,
        username: "admin",
        display_name: "admin",
        role: "support",
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

vi.mock("../../auth/PermissionsContext", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../auth/PermissionsContext")>();
  return { ...actual, usePermissions: () => ({ can: () => true, moduleEnabled: () => true }) };
});

const POLICY_FIELDS = [
  {
    key: "objection_window_days",
    label: "مهلت اعتراض کارمند (روز)",
    kind: "number",
    help: "از لحظهٔ نهایی‌شدن پرونده",
    value: 7,
    minimum: 1,
    maximum: 365,
  },
  {
    key: "min_cohort_size",
    label: "حداقل جمعیت برای نمایش میانگین",
    kind: "number",
    help: "",
    value: 5,
    minimum: 1,
    maximum: 100,
  },
];

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ToastProvider>
          <ConfirmProvider>
            <AdministrationPage />
          </ConfirmProvider>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

type ModuleRow = {
  key: string;
  label: string;
  description: string;
  enabled: boolean;
  requires: string[];
  blocked_by: string[];
  dependents: string[];
};

function mockGets(modules: ModuleRow[] = []) {
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url === "/administration/policy") return { data: { fields: POLICY_FIELDS } } as never;
    if (url === "/ai/settings")
      return {
        data: {
          enabled: false,
          provider: "custom",
          providers: [
            { id: "openai", label: "OpenAI", base_url: "https://api.openai.com/v1",
              default_model: "gpt-4o-mini", note: "" },
            { id: "custom", label: "سفارشی", base_url: "", default_model: "", note: "" },
          ],
          base_url: "", model: "", api_key_hint: "", api_key_configured: false,
          temperature: 30, max_tokens: 1200, timeout_seconds: 60, instructions: "x",
          restrict_to_platform: true, context_record_limit: 25,
          allow_write_actions: true, max_user_chars: 4000,
        },
      } as never;
    if (url === "/ai/access") return { data: [] } as never;
    if (url === "/administration/integrations")
      return { data: { fields: [], secrets: [], active_channels: [] } } as never;
    if (url === "/administration/modules") return { data: modules } as never;
    if (url === "/administration/separation")
      return { data: { separated: true, overlapping_users: [] } } as never;
    if (url === "/org-units") return { data: [] } as never;
    if (url === "/personnel/sites") return { data: ["دفتر مرکزی"] } as never;
    return { data: [] } as never;
  });
}

async function openTab(name: string) {
  await userEvent.click(await screen.findByRole("tab", { name }));
}

describe("تب‌های مدیریت سامانه", () => {
  it("بخش‌ها را در تب‌های جداگانه نشان می‌دهد و فقط تب انتخاب‌شده را نمایش می‌دهد", async () => {
    mockGets();
    renderPage();

    const tabs = await screen.findAllByRole("tab");
    expect(tabs).toHaveLength(7);
    expect(screen.getByRole("tab", { name: "واحدهای سازمانی" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.queryByText("دستیار در این سامانه فعال باشد")).not.toBeInTheDocument();

    await openTab("دستیار هوشمند");
    expect(screen.getByRole("tab", { name: "دستیار هوشمند" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(await screen.findByText("دستیار در این سامانه فعال باشد")).toBeInTheDocument();
  });
});


describe("کارت قاعده‌های سازمانی", () => {
  it("کف و سقفِ سرور را روی خودِ ورودی می‌گذارد", async () => {
    // فرم باید همان قاعده‌ای را نشان بدهد که سرور اعمال می‌کند، نه اینکه کاربر
    // با ذخیره‌کردن کشفش کند.
    mockGets();
    renderPage();
    await openTab("قاعده‌های سازمانی");

    const input = await screen.findByLabelText(/مهلت اعتراض کارمند/);
    expect(input).toHaveAttribute("min", "1");
    expect(input).toHaveAttribute("max", "365");
    expect(input).toHaveValue(7);
  });

  it("فقط مقدارهای همین گروه را می‌فرستد", async () => {
    mockGets();
    vi.mocked(apiClient.put).mockResolvedValue({ data: { fields: POLICY_FIELDS } } as never);
    renderPage();
    await openTab("قاعده‌های سازمانی");

    const input = await screen.findByLabelText(/حداقل جمعیت/);
    await userEvent.clear(input);
    await userEvent.type(input, "8");
    await userEvent.click(screen.getByRole("button", { name: "ذخیرهٔ قاعده‌ها" }));

    await waitFor(() => expect(apiClient.put).toHaveBeenCalled());
    const [url, body] = vi.mocked(apiClient.put).mock.calls[0]!;
    expect(url).toBe("/administration/policy");
    expect((body as { values: Record<string, unknown> }).values).toMatchObject({
      min_cohort_size: 8,
      objection_window_days: 7,
    });
  });

  it("دکمهٔ ذخیره تا وقتی چیزی عوض نشده خاموش است", async () => {
    mockGets();
    renderPage();
    await openTab("قاعده‌های سازمانی");
    expect(await screen.findByRole("button", { name: "ذخیرهٔ قاعده‌ها" })).toBeDisabled();
  });
});


describe("کارت دستیار هوشمند", () => {
  it("انتخاب یک سرویس، آدرس و مدلش را با هم می‌گذارد", async () => {
    // نیمی از مشکلات راه‌اندازی یک `/v1` جامانده در آدرس بود؛ این‌جا هر دو با
    // یک کلیک می‌آیند و ذخیره باید همان‌ها را بفرستد.
    mockGets();
    vi.mocked(apiClient.put).mockResolvedValue({ data: {} } as never);
    renderPage();
    await openTab("دستیار هوشمند");

    await userEvent.click(await screen.findByRole("button", { name: /OpenAI/ }));
    await userEvent.click(screen.getByRole("button", { name: /ذخیرهٔ تنظیمات دستیار/ }));

    await waitFor(() => expect(apiClient.put).toHaveBeenCalledWith(
      "/ai/settings",
      expect.objectContaining({
        provider: "openai",
        base_url: "https://api.openai.com/v1",
        model: "gpt-4o-mini",
      }),
    ));
  });

  /* ── وابستگیِ بخش‌ها (B-H1) ────────────────────────────────────────────
     سه بخشِ نمایشِ کارمند بی «نتیجه و وضعیت پروندهٔ کارمند» بی‌معنا هستند، و
     تا امروز این وابستگی فقط در *متنِ* توضیح نوشته شده بود. نتیجه‌اش
     پیکربندیِ بی‌معنایی بود که ظاهرِ سالم داشت: کارمند دکمهٔ اعتراض دارد به
     عددی که سرور از نشان‌دادنش امتناع می‌کند. */
  const PARENT: ModuleRow = {
    key: "employee_evaluation_visibility",
    label: "نتیجه و وضعیت پروندهٔ کارمند",
    description: "نمایش نتایج نهایی",
    enabled: false,
    requires: [],
    blocked_by: [],
    dependents: ["objections"],
  };
  const CHILD: ModuleRow = {
    key: "objections",
    label: "اعتراض به نتیجه",
    description: "مسیر رسمی اعتراض",
    enabled: false,
    requires: ["employee_evaluation_visibility"],
    blocked_by: ["employee_evaluation_visibility"],
    dependents: [],
  };

  const switchOf = (label: string) =>
    screen.getByRole("switch", { name: `فعال بودن ${label}` });

  it("سوییچِ بخشی که پیش‌نیازش خاموش است، غیرفعال می‌شود و دلیلش را می‌گوید", async () => {
    mockGets([PARENT, CHILD]);
    renderPage();
    await openTab("بخش‌های سامانه");

    expect(await screen.findByText(/به «نتیجه و وضعیت پروندهٔ کارمند» نیاز دارد/)).toBeInTheDocument();
    expect(switchOf(CHILD.label)).toBeDisabled();
    // سوییچِ خودِ پیش‌نیاز آزاد است
    expect(switchOf(PARENT.label)).toBeEnabled();
  });

  it("با روشن‌بودنِ پیش‌نیاز، سوییچ آزاد است و توضیحِ مانع نمی‌آید", async () => {
    mockGets([
      { ...PARENT, enabled: true },
      { ...CHILD, blocked_by: [] },
    ]);
    renderPage();
    await openTab("بخش‌های سامانه");

    await waitFor(() => expect(switchOf(CHILD.label)).toBeEnabled());
    expect(screen.queryByText(/نیاز دارد/)).toBeNull();
  });

  it("بخشی که روشن مانده و پیش‌نیازش خاموش شده، همچنان قابلِ خاموش‌کردن است", async () => {
    // وگرنه مدیر با یک پیکربندیِ بی‌معنا گیر می‌افتد و راهِ بیرون‌آمدن ندارد.
    mockGets([PARENT, { ...CHILD, enabled: true }]);
    renderPage();
    await openTab("بخش‌های سامانه");

    await waitFor(() => expect(switchOf(CHILD.label)).toBeEnabled());
    expect(screen.getByText(/و تا روشن‌نشدنِ آن بی‌اثر است/)).toBeInTheDocument();
  });

  it("خاموش‌کردنِ پیش‌نیاز، پیش از تأیید می‌گوید چه چیزهایی با آن می‌روند", async () => {
    mockGets([
      { ...PARENT, enabled: true },
      { ...CHILD, enabled: true, blocked_by: [] },
    ]);
    vi.mocked(apiClient.put).mockResolvedValue({ data: {} } as never);
    renderPage();
    await openTab("بخش‌های سامانه");

    await userEvent.click(switchOf(PARENT.label));
    expect(
      await screen.findByText(/پیش‌نیازِ «اعتراض به نتیجه» است، پس آن‌ها هم از کار می‌افتند/),
    ).toBeInTheDocument();
  });
});
