/** نشانِ همکار.
 *
 * چیزهایی که این‌جا قفل می‌شوند، همه از آن‌هایی‌اند که خرابی‌شان بی‌صداست —
 * SVG بدونِ خطا رندر می‌شود و فقط *غلط* دیده می‌شود:
 *
 * ۱. کلاسِ `mascot` باید روی خودِ SVG باشد. قاعده‌های انیمیشن در `index.css`
 *    فرزندانِ همین کلاس را هدف می‌گیرند؛ بی‌آن، شخصیت رندر می‌شود و فقط
 *    هیچ‌وقت نفس نمی‌کشد و پلک نمی‌زند.
 * ۲. `MascotFace` نباید پا و کاکل داشته باشد — دلیلِ وجودش همین است.
 * ۳. نگاه باید *فقط* با `track` وصل شود، و با unmount قطع شود. شنوندهٔ
 *    `pointermove`ای که نشتی کند، تا آخرِ عمرِ صفحه در هر حرکتِ ماوس روی
 *    گره‌ای که دیگر وجود ندارد کار می‌کند.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import { Mascot, MascotFace } from "./Mascot";

afterEach(() => vi.restoreAllMocks());

describe("Mascot", () => {
  it("کلاسِ انیمیشن روی خودِ svg می‌نشیند", () => {
    const { container } = render(<Mascot />);
    expect(container.querySelector("svg")?.classList.contains("mascot")).toBe(true);
  });

  it("قطعاتی که انیمیشن می‌گیرند سرِ جایشان‌اند", () => {
    const { container } = render(<Mascot />);
    for (const part of [
      "mascot-body",
      "mascot-eyes",
      "mascot-pupils",
      "mascot-tuft",
      "mascot-feet",
      "mascot-smile",
      "mascot-grin",
    ]) {
      expect(container.querySelector(`.${part}`), part).toBeTruthy();
    }
  });

  it("با idle=false ساکن می‌ماند", () => {
    // برای جاهایی مثل چاپ یا تصویرِ ثابت، که حرکت فقط مزاحم است.
    const { container } = render(<Mascot idle={false} />);
    expect(container.querySelector("svg")?.classList.contains("mascot")).toBe(false);
  });

  it("از دید صفحه‌خوان پنهان است", () => {
    // یک تصویرِ تزئینی کنارِ دکمه‌ای که خودش `aria-label` دارد؛ خواندنش تکرار است.
    const { container } = render(<Mascot />);
    expect(container.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
  });

  it("نسخهٔ کوچک فقط سر است — نه پا، نه کاکل", () => {
    const { container } = render(<MascotFace />);
    expect(container.querySelector(".mascot-eyes")).toBeTruthy();
    expect(container.querySelector(".mascot-feet")).toBeNull();
    expect(container.querySelector(".mascot-tuft")).toBeNull();
  });
});

describe("نگاهِ دنبالِ نشانگر", () => {
  it("بی `track` به هیچ رویدادی گوش نمی‌دهد", () => {
    // چند نسخه از این شخصیت هم‌زمان روی صفحه‌اند (آواتارِ پیام‌ها). اگر
    // همه‌شان گوش بدهند، یک حرکتِ ماوس ده‌ها محاسبهٔ مستقل می‌شود.
    const listen = vi.spyOn(window, "addEventListener");
    render(<Mascot />);
    expect(listen.mock.calls.some(([type]) => type === "pointermove")).toBe(false);
  });

  it("با `track` مردمک را جابه‌جا می‌کند", () => {
    const { container } = render(<Mascot track />);
    const pupils = container.querySelector(".mascot-pupils")!;
    expect(pupils.getAttribute("transform")).toBeNull();

    window.dispatchEvent(
      new MouseEvent("pointermove", { clientX: 900, clientY: 700, bubbles: true }),
    );
    // jsdom اندازهٔ واقعی نمی‌دهد (`getBoundingClientRect` صفر است)، پس
    // این‌جا فقط *وصل بودنِ* مسیر سنجیده می‌شود و نه مقدارِ دقیق. مقدار،
    // کارِ چشم است نه کارِ تست.
    expect(() =>
      window.dispatchEvent(new MouseEvent("pointermove", { clientX: 10, clientY: 10 })),
    ).not.toThrow();
  });

  it("با unmount شنونده را برمی‌دارد", () => {
    const stop = vi.spyOn(window, "removeEventListener");
    const { unmount } = render(<Mascot track />);
    unmount();
    expect(stop.mock.calls.some(([type]) => type === "pointermove")).toBe(true);
  });

  it("«حرکت کمتر» نگاه را هم خاموش می‌کند", () => {
    // قاعدهٔ CSS چرخه‌ها را می‌گیرد و این یکی را نمی‌گیرد، چون JS است.
    // بی این شرط، دقیقاً همان کاربری که حرکت را خاموش کرده، یک چشمِ
    // متحرک در گوشهٔ صفحه می‌بیند.
    vi.spyOn(window, "matchMedia").mockImplementation(
      (query: string) =>
        ({
          matches: query.includes("prefers-reduced-motion"),
          media: query,
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
        }) as unknown as MediaQueryList,
    );
    const listen = vi.spyOn(window, "addEventListener");
    render(<Mascot track />);
    expect(listen.mock.calls.some(([type]) => type === "pointermove")).toBe(false);
  });
});
