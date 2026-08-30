// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * مقصدِ پروکسیِ `/api` باید قابلِ جابه‌جایی بماند.
 *
 * پیش از این `http://localhost:8000` ثابت نوشته شده بود، و همان یک خط بود که
 * پورت ۸۰۰۰ را اجباری می‌کرد. روی ویندوز آن پورت مرتب در دسترس نیست — گاهی
 * یووی‌کورنِ اجرای قبلی هنوز زنده است، گاهی Hyper-V/WSL2 کلِ بازه را رزرو کرده —
 * و چون فرانت‌اند فقط ۸۰۰۰ را بلد بود، تنها راهِ پیش‌رو «آن پورت را آزاد کن» بود.
 *
 * حالا `tools/launcher` هر پورتی را که واقعاً بشود رویش listen کرد برمی‌دارد و
 * آدرسش را از `NEXAHR_BACKEND_URL` می‌دهد. این تست هر دو نیمهٔ آن قرارداد را
 * قفل می‌کند: خوانده‌شدنِ متغیر، و پیش‌فرضی که `npm run dev` دستی به آن تکیه دارد.
 *
 * پیکربندی هر بار از نو import می‌شود چون در بارگذاریِ ماژول ارزیابی می‌گردد و
 * یک نسخهٔ کش‌شده مقدارِ قبلیِ متغیر را نگه می‌دارد.
 */
type DevConfig = { server?: { proxy?: Record<string, { target?: string }> } };

async function proxyTarget(): Promise<string | undefined> {
  vi.resetModules();
  // `unknown` عمدی است: `defineConfig` هم شیء می‌پذیرد و هم تابع، و اگر روزی این
  // پیکربندی تابع شد، تست باید همچنان مقدار را پیدا کند نه این‌که کامپایل نشود.
  const exported: unknown = (await import("../../vite.config")).default;
  const config = (
    typeof exported === "function"
      ? await (exported as (env: { command: string; mode: string }) => DevConfig)({
          command: "serve",
          mode: "development",
        })
      : exported
  ) as DevConfig;
  return config.server?.proxy?.["/api"]?.target;
}

afterEach(() => {
  delete process.env.NEXAHR_BACKEND_URL;
});

describe("مقصدِ پروکسیِ توسعه", () => {
  it("بدونِ متغیرِ محیطی، همان پورتِ ۸۰۰۰ می‌ماند", async () => {
    expect(await proxyTarget()).toBe("http://localhost:8000");
  });

  it("اگر راه‌انداز پورتِ دیگری داده باشد، همان را صدا می‌زند", async () => {
    process.env.NEXAHR_BACKEND_URL = "http://127.0.0.1:8003";
    expect(await proxyTarget()).toBe("http://127.0.0.1:8003");
  });

  it("متغیرِ خالی مثل نبودنش رفتار می‌کند", async () => {
    // یک متغیرِ ست‌شده ولی خالی، اگر با `??` سنجیده شود مقصد را به رشتهٔ خالی
    // می‌برد و پروکسی بی‌صدا از کار می‌افتد.
    process.env.NEXAHR_BACKEND_URL = "";
    expect(await proxyTarget()).toBe("http://localhost:8000");
  });
});
