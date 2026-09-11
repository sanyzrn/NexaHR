/** یک Escape، یک لایه.
 *
 * تقویمِ شمسی تقریباً همیشه داخلِ یک مودال باز می‌شود (دوره‌ها، پرسنل،
 * برنامهٔ بهبود، ساختِ دسته‌ای). هر دو — تقویم و `useFocusTrap` — شنوندهٔ
 * Escape روی `document` دارند و تا امروز هیچ‌کدام جلوی دیگری را نمی‌گرفت.
 * نتیجه: کاربر تاریخ را باز می‌کرد، Escape می‌زد که فقط تقویم برود، و کلِ
 * دیالوگ می‌پرید — در `BulkCreateDialog` به‌همراه انتخابِ پرسنلِ
 * چندمرحله‌ای که تا آن لحظه انجام داده بود.
 *
 * این تست همان چیدمانِ واقعی را می‌سازد: یک تلهٔ فوکوس که `onEscape` دارد، و
 * تقویمی داخلش.
 */
import { useRef, useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { JalaliDatePicker } from "./JalaliDatePicker";
import { useFocusTrap } from "./focusTrap";

function ModalWithPicker({ onClose }: { onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const [value, setValue] = useState("");
  useFocusTrap(ref, { active: true, onEscape: onClose });
  return (
    <div ref={ref} role="dialog" aria-modal="true" tabIndex={-1}>
      <JalaliDatePicker value={value} onChange={setValue} />
    </div>
  );
}

function openCalendar() {
  fireEvent.click(screen.getByRole("button", { name: /انتخاب تاریخ/ }));
}

const calendar = () => screen.queryByRole("dialog", { name: "انتخاب تاریخ" });

describe("Escape داخلِ مودال", () => {
  it("اول تقویم را می‌بندد و مودال را دست نمی‌زند", async () => {
    const onClose = vi.fn();
    render(<ModalWithPicker onClose={onClose} />);

    openCalendar();
    expect(calendar()).toBeTruthy();

    fireEvent.keyDown(document, { key: "Escape" });

    // `AnimatePresence` انیمیشنِ خروج دارد، پس حذف از DOM یک تیک بعد است.
    await waitFor(() => expect(calendar()).toBeNull());
    expect(onClose).not.toHaveBeenCalled();
  });

  it("و Escape بعدی — که تقویمی باز نیست — مودال را می‌بندد", () => {
    const onClose = vi.fn();
    render(<ModalWithPicker onClose={onClose} />);

    openCalendar();
    fireEvent.keyDown(document, { key: "Escape" }); // تقویم
    fireEvent.keyDown(document, { key: "Escape" }); // مودال

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("بی تقویمِ باز، Escape مستقیم به مودال می‌رسد", () => {
    const onClose = vi.fn();
    render(<ModalWithPicker onClose={onClose} />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
