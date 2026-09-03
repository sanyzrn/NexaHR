/** قفلِ فوکوس، یک‌جا — و همان‌جا سنجیده می‌شود.
 *
 *  کشوی ناوبریِ موبایل Escape و قفلِ اسکرول داشت و قفلِ فوکوس نداشت: کاربرِ
 *  کیبورد یا صفحه‌خوان با Tab از کشویِ *باز* مستقیم به صفحهٔ پشتِ پرده می‌رفت،
 *  یعنی در فهرستی حرکت می‌کرد که نمی‌دید (WCAG 2.1، بند ۲٫۴٫۳). `Modal`
 *  همین را درست پیاده کرده بود؛ حالا هر دو یک هوک دارند.
 */
import { useRef, useState } from "react";
import { describe, expect, it } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { useFocusTrap } from "./focusTrap";

function Host() {
  const [open, setOpen] = useState(false);
  const layer = useRef<HTMLDivElement>(null);
  useFocusTrap(layer, { active: open, onEscape: () => setOpen(false) });
  return (
    <div>
      <button onClick={() => setOpen(true)}>باز کن</button>
      <button>بیرونِ لایه</button>
      {open && (
        <div ref={layer} role="dialog" aria-modal="true" aria-label="لایه" tabIndex={-1}>
          <button>اول</button>
          <button>دوم</button>
        </div>
      )}
    </div>
  );
}

/** در jsdom، `element.click()` عنصر را فوکوس *نمی‌کند* — در مرورگر می‌کند.
 *  فوکوسِ صریح، همان حالتی را می‌سازد که کاربر واقعاً در آن است. */
function openLayer() {
  const opener = screen.getByText("باز کن");
  act(() => {
    opener.focus();
    opener.click();
  });
  return opener;
}

describe("useFocusTrap", () => {
  it("فوکوس در باز شدن داخل لایه می‌رود", () => {
    render(<Host />);
    openLayer();
    expect(document.activeElement).toBe(screen.getByText("اول"));
  });

  it("Tab از آخرین عنصر به اولی برمی‌گردد، نه به صفحهٔ پشتِ لایه", () => {
    render(<Host />);
    openLayer();
    const last = screen.getByText("دوم");
    act(() => last.focus());
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(screen.getByText("اول"));
  });

  it("Shift+Tab از اولی به آخری می‌رود", () => {
    render(<Host />);
    openLayer();
    act(() => screen.getByText("اول").focus());
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(screen.getByText("دوم"));
  });

  it("Escape می‌بندد و فوکوس به بازکننده برمی‌گردد", () => {
    render(<Host />);
    const opener = screen.getByText("باز کن");
    openLayer();
    act(() => {
      fireEvent.keyDown(document, { key: "Escape" });
    });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(opener);
  });

  it("اسکرولِ صفحه در حالِ باز قفل است و بعد آزاد", () => {
    render(<Host />);
    expect(document.body.style.overflow).toBe("");
    openLayer();
    expect(document.body.style.overflow).toBe("hidden");
    act(() => {
      fireEvent.keyDown(document, { key: "Escape" });
    });
    expect(document.body.style.overflow).toBe("");
  });

  it("تا لایه باز نشده هیچ‌کاری نمی‌کند", () => {
    render(<Host />);
    expect(document.body.style.overflow).toBe("");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.getByText("باز کن")).toBeInTheDocument();
  });
});
