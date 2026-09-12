/** تقویمِ شمسی با کیبورد.
 *
 * پیش از این، کاربرِ فقط-کیبورد **هیچ تاریخی نمی‌توانست انتخاب کند** — نه
 * اینکه سخت بود. پاپ‌آور به `body` پورتال می‌شود و هیچ‌چیز فوکوس را داخلش
 * نمی‌بُرد؛ داخلِ مودال بدتر بود، چون تلهٔ فوکوسِ مودال فقط درونِ ظرفِ خودش
 * جست‌وجو می‌کند و تقویمِ پورتال‌شده اصلاً در چرخهٔ Tab نبود. تاریخِ قرارداد
 * در نیمی از فرم‌های این سامانه هست (WCAG 2.1.2 و 2.4.3).
 */
import { useRef, useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { JalaliDatePicker } from "./JalaliDatePicker";
import { useFocusTrap } from "./focusTrap";

/** ۱۴۰۵/۰۶/۱۵ — وسطِ ماه، تا حرکت در هر چهار جهت جا داشته باشد. */
const VALUE = "2026-09-06";

function Picker({ initial = VALUE }: { initial?: string }) {
  const [value, setValue] = useState(initial);
  return (
    <>
      <JalaliDatePicker value={value} onChange={setValue} />
      <output data-testid="value">{value}</output>
    </>
  );
}

function ModalWithPicker() {
  const ref = useRef<HTMLDivElement>(null);
  const [value, setValue] = useState(VALUE);
  useFocusTrap(ref, { active: true });
  return (
    <div ref={ref} role="dialog" aria-modal="true" tabIndex={-1}>
      <JalaliDatePicker value={value} onChange={setValue} />
    </div>
  );
}

const openCalendar = () =>
  fireEvent.click(screen.getByRole("button", { name: /۱۴۰۵|انتخاب تاریخ/ }));

const grid = () => screen.getByRole("grid");
const activeDay = () => document.activeElement as HTMLElement;

describe("پیمایشِ تقویم با کیبورد", () => {
  it("با باز شدن، فوکوس روی روزِ انتخاب‌شده می‌نشیند", async () => {
    render(<Picker />);
    openCalendar();
    await waitFor(() => expect(activeDay().tagName).toBe("BUTTON"));
    expect(activeDay()).toHaveAccessibleName(/۱۵ شهریور ۱۴۰۵/);
  });

  it("در RTL، فلشِ راست یک روز عقب و فلشِ چپ یک روز جلو می‌رود", async () => {
    render(<Picker />);
    openCalendar();
    await waitFor(() => expect(activeDay().tagName).toBe("BUTTON"));

    fireEvent.keyDown(grid(), { key: "ArrowRight" });
    expect(activeDay()).toHaveAccessibleName(/۱۴ شهریور/);

    fireEvent.keyDown(grid(), { key: "ArrowLeft" });
    fireEvent.keyDown(grid(), { key: "ArrowLeft" });
    expect(activeDay()).toHaveAccessibleName(/۱۶ شهریور/);
  });

  it("بالا و پایین یک هفته جابه‌جا می‌کنند", async () => {
    render(<Picker />);
    openCalendar();
    await waitFor(() => expect(activeDay().tagName).toBe("BUTTON"));

    fireEvent.keyDown(grid(), { key: "ArrowUp" });
    expect(activeDay()).toHaveAccessibleName(/۸ شهریور/);
    fireEvent.keyDown(grid(), { key: "ArrowDown" });
    fireEvent.keyDown(grid(), { key: "ArrowDown" });
    expect(activeDay()).toHaveAccessibleName(/۲۲ شهریور/);
  });

  it("از مرزِ ماه رد می‌شود و ماهِ نمایش را با خودش می‌بَرد", async () => {
    render(<Picker />);
    openCalendar();
    await waitFor(() => expect(activeDay().tagName).toBe("BUTTON"));

    // ۱۵ + ۷ + ۷ + ۷ = ۳۶ ← شهریور ۳۱ روز دارد، پس ۵ مهر
    for (let i = 0; i < 3; i += 1) fireEvent.keyDown(grid(), { key: "ArrowDown" });
    expect(activeDay()).toHaveAccessibleName(/۵ مهر ۱۴۰۵/);
  });

  it("Home و End به اول و آخرِ ماه می‌روند", async () => {
    render(<Picker />);
    openCalendar();
    await waitFor(() => expect(activeDay().tagName).toBe("BUTTON"));

    fireEvent.keyDown(grid(), { key: "Home" });
    expect(activeDay()).toHaveAccessibleName(/^۱ شهریور/);
    fireEvent.keyDown(grid(), { key: "End" });
    // شهریور ۳۱ روز دارد
    expect(activeDay()).toHaveAccessibleName(/۳۱ شهریور/);
  });

  it("PageUp و PageDown ماه را عوض می‌کنند و روز را از طولِ ماه بیرون نمی‌اندازند", async () => {
    render(<Picker initial="2026-08-22" />); // ۳۱ مرداد ۱۴۰۵
    openCalendar();
    await waitFor(() => expect(activeDay().tagName).toBe("BUTTON"));
    expect(activeDay()).toHaveAccessibleName(/۳۱ مرداد/);

    // مهر ۳۰ روز دارد، پس روزِ ۳۱ باید به ۳۰ بیاید نه اینکه سرریز کند
    fireEvent.keyDown(grid(), { key: "PageDown" });
    fireEvent.keyDown(grid(), { key: "PageDown" });
    expect(activeDay()).toHaveAccessibleName(/۳۰ مهر/);

    // و لنگرِ *حالت* هم باید همان ۳۰ باشد، نه ۳۱ِ نامرئی: یک قدم جلوتر باید
    // اولِ آبان بیفتد، نه دوم. اگر state و آنچه فوکوس دارد دو عدد باشند،
    // کلیدهای جهت از جایی حرکت می‌کنند که کاربر نمی‌بیند.
    fireEvent.keyDown(grid(), { key: "ArrowLeft" });
    expect(activeDay()).toHaveAccessibleName(/^۱ آبان/);
  });

  it("Enter روی روزِ فعال، همان تاریخ را انتخاب می‌کند", async () => {
    render(<Picker />);
    openCalendar();
    await waitFor(() => expect(activeDay().tagName).toBe("BUTTON"));

    fireEvent.keyDown(grid(), { key: "ArrowLeft" }); // ۱۶ شهریور
    fireEvent.click(activeDay()); // Enter روی button همین را می‌زند
    await waitFor(() => expect(screen.getByTestId("value")).toHaveTextContent("2026-09-07"));
  });

  it("فقط یک روز در چرخهٔ Tab است — نه هر ۳۱ روز", async () => {
    /* بی tabindexِ غلتان، رسیدن به دکمهٔ «ثبت» سی‌ویک بار Tab لازم داشت. */
    render(<Picker />);
    openCalendar();
    await waitFor(() => expect(activeDay().tagName).toBe("BUTTON"));

    const days = screen.getAllByRole("button", { name: /شهریور ۱۴۰۵$/ });
    expect(days.length).toBeGreaterThan(20);
    expect(days.filter((d) => d.tabIndex === 0)).toHaveLength(1);
  });

  it("داخلِ مودال هم فوکوس به تقویم می‌رسد", async () => {
    /* همان حالتی که اصلاً کار نمی‌کرد: تلهٔ فوکوسِ مودال فقط درونِ ظرفِ خودش
       می‌گردد و تقویمِ پورتال‌شده فرزندِ آن ظرف نیست. */
    render(<ModalWithPicker />);
    openCalendar();
    await waitFor(() => expect(activeDay().tagName).toBe("BUTTON"));
    expect(activeDay()).toHaveAccessibleName(/شهریور ۱۴۰۵/);
    expect(screen.getByRole("dialog", { name: "انتخاب تاریخ" })).toContainElement(activeDay());
  });

  it("با بسته‌شدن، فوکوس به دکمهٔ بازکننده برمی‌گردد", async () => {
    render(<Picker />);
    const trigger = screen.getByRole("button", { name: /۱۴۰۵/ });
    // مرورگرِ واقعی با کلیک، دکمه را فوکوس می‌کند و jsdom نمی‌کند. کاربرِ
    // کیبورد هم دقیقاً همین‌طور می‌رسد: Tab تا دکمه، بعد Enter.
    trigger.focus();
    fireEvent.click(trigger);
    await waitFor(() => expect(activeDay().tagName).toBe("BUTTON"));

    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });
});
