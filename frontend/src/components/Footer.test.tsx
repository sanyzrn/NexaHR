/** پاصفحه — و جایی که برای نشانِ همکار خالی می‌گذارد.
 *
 *  این تنها جایی است که دو تصمیمِ چیدمانیِ *جدا* باید با هم بخوانند: دکمهٔ
 *  شناور در `Copilot.tsx` روی لبهٔ چپِ پوسته می‌ایستد، و پاصفحه باید همان
 *  اندازه از چپ عقب بنشیند. اگر یکی عوض شود و دیگری نه، خرابی‌اش «دکمه روی
 *  امضای توسعه‌دهنده افتاده» است — چیزی که در تست‌های واحد دیده نمی‌شود،
 *  مگر همین‌جا صریح قفل شود.
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Footer } from "./Footer";

describe("پاصفحه", () => {
  it("بی همکار، تمامِ عرض را می‌گیرد", () => {
    // صفحهٔ ورود و صفحهٔ استعلامِ سند همین پاصفحه را دارند و همکار آن‌جا
    // نیست؛ فضای خالی برای چیزی که وجود ندارد، خرابیِ چیدمان است.
    const { container } = render(<Footer />);
    expect(container.querySelector("footer")?.className).not.toMatch(/me-\[/);
  });

  it("با همکار، از سمتِ چپ جا باز می‌کند", () => {
    const { container } = render(<Footer roomForCopilot />);
    expect(container.querySelector("footer")?.className).toMatch(/me-\[68px\]/);
  });

  it("امضا و نسخه سرِ جایشان می‌مانند", () => {
    render(<Footer roomForCopilot />);
    expect(screen.getByText(/Developed by/)).toBeInTheDocument();
    expect(screen.getByText(/^v\d+\.\d+\.\d+$/)).toBeInTheDocument();
  });
});
