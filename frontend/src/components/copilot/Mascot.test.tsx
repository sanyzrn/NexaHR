/** نشانِ همکار.
 *
 * دو چیزی که این‌جا قفل می‌شود، هر دو از آن‌هایی‌اند که خرابی‌شان بی‌صداست —
 * SVG بدونِ خطا رندر می‌شود و فقط *غلط* دیده می‌شود:
 *
 * ۱. کلاسِ `mascot` باید روی خودِ SVG باشد. قاعده‌های انیمیشن در `index.css`
 *    فرزندانِ همین کلاس را هدف می‌گیرند؛ بی‌آن، شخصیت رندر می‌شود ولی هیچ‌وقت
 *    پلک نمی‌زند و کسی هم متوجه نمی‌شود که چیزی خراب است.
 *
 * ۲. `MascotFace` نباید دست و پا داشته باشد. دلیلِ وجودش همین است: در اندازهٔ
 *    آواتار، اندام‌ها به چند پیکسلِ درهم تبدیل می‌شوند.
 */
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { Mascot, MascotFace } from "./Mascot";

describe("Mascot", () => {
  it("کلاسِ انیمیشن روی خودِ svg می‌نشیند", () => {
    const { container } = render(<Mascot />);
    expect(container.querySelector("svg")?.classList.contains("mascot")).toBe(true);
  });

  it("قطعاتی که انیمیشن می‌گیرند سرِ جایشان‌اند", () => {
    const { container } = render(<Mascot />);
    for (const part of ["mascot-body", "mascot-head", "mascot-eyes", "mascot-spark", "mascot-arm"]) {
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

  it("نسخهٔ کوچک فقط سر است — نه دست، نه پا", () => {
    const { container } = render(<MascotFace />);
    expect(container.querySelector(".mascot-eyes")).toBeTruthy();
    expect(container.querySelector(".mascot-arm")).toBeNull();
    expect(container.querySelector(".mascot-body")).toBeNull();
  });
});
