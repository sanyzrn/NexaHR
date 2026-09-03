/** متنِ پاسخ از مدل می‌آید، و متنِ مدل از زمینه‌ای که هر کسی با دسترسیِ نوشتنِ
 *  یک ردیفِ پرسنلی یا بارگذاریِ یک اکسل در آن می‌نویسد. پس `href` داده است، نه
 *  دستور: تا امروز عیناً همان چیزی می‌نشست که در متن آمده بود.
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Markdown } from "./Markdown";

const renderMd = (text: string) => render(<Markdown text={text} />);

describe("پیوندهای پاسخِ همکار", () => {
  it("http و https و mailto لنگر می‌شوند", () => {
    renderMd("[سایت](https://example.com) و [ایمیل](mailto:a@b.c)");
    expect(screen.getByText("سایت").closest("a")).toHaveAttribute(
      "href",
      "https://example.com"
    );
    expect(screen.getByText("ایمیل").closest("a")).toHaveAttribute("href", "mailto:a@b.c");
  });

  it("مسیرِ نسبیِ همین اصل هم لنگر می‌شود", () => {
    renderMd("[پروندهٔ من](/evaluations/7)");
    expect(screen.getByText("پروندهٔ من").closest("a")).toHaveAttribute(
      "href",
      "/evaluations/7"
    );
  });

  it.each([
    "[کلیک](javascript:alert(1))",
    "[کلیک](data:text/html,<script>alert(1)</script>)",
    "[کلیک](vbscript:msgbox)",
    "[کلیک](//evil.example.com/x)",
  ])("طرحِ نامجاز لنگر نمی‌شود: %s", (source) => {
    const { container } = renderMd(source);
    expect(container.querySelector("a")).toBeNull();
    // و متنش دیده می‌شود، تا کاربر بفهمد مدل چه نوشته.
    expect(container.textContent).toContain("کلیک");
  });
});
