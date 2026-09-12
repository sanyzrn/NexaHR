import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CharCounter } from "./CharCounter";

/** `maxLength` به‌تنهایی کافی نبود و در کلِ فرانت هم *یک بار* به‌کار رفته بود:
 *  کاربر اعتراضِ ۲٬۵۰۰ نویسه‌ای می‌نوشت، تا لحظهٔ «ثبت» هیچ نشانه‌ای نمی‌دید و
 *  بعد ۴۲۲ می‌گرفت. حالا `maxLength` جلوی تایپ را می‌گیرد و این شمارنده
 *  می‌گوید چرا. */
describe("CharCounter", () => {
  it("تا نزدیکِ سقف ساکت است — نوشتن نباید به شمردن تبدیل شود", () => {
    const { container } = render(<CharCounter value={"م".repeat(40)} max={100} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("از ۸۰٪ به بعد عدد را نشان می‌دهد، با ارقام فارسی", () => {
    render(<CharCounter value={"م".repeat(85)} max={100} />);
    expect(screen.getByText(/۸۵ از ۱۰۰ نویسه/)).toBeInTheDocument();
  });

  it("روی سقف، صریح می‌گوید که دیگر جا نیست", () => {
    render(<CharCounter value={"م".repeat(100)} max={100} />);
    expect(screen.getByText(/به سقف رسید/)).toBeInTheDocument();
  });

  it("برای صفحه‌خوان خوانده می‌شود، ولی نه وسطِ تایپ", () => {
    render(<CharCounter value={"م".repeat(95)} max={100} />);
    expect(screen.getByText(/۹۵ از ۱۰۰/)).toHaveAttribute("aria-live", "polite");
  });
});
