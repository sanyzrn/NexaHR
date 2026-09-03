import { useEffect, type RefObject } from "react";

/** انتخابگرِ عناصرِ فوکوس‌پذیر. یک‌جا، تا مودال و کشو یک تعریف داشته باشند. */
export const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** فوکوس را داخل یک لایهٔ روی‌هم قفل می‌کند، و در بسته‌شدن برمی‌گرداند.
 *
 *  چرا هوک و نه کدِ داخلِ `Modal`: کشوی ناوبریِ موبایل همین رفتار را لازم
 *  داشت و نداشتش. Escape می‌بست و اسکرولِ صفحه قفل می‌شد، ولی کاربرِ کیبورد
 *  یا صفحه‌خوان با Tab از کشویِ *باز* مستقیم به صفحهٔ پشتِ پرده می‌رفت —
 *  یعنی در فهرستی حرکت می‌کرد که نمی‌دید. WCAG 2.1، بند ۲٫۴٫۳.
 *
 *  کپی‌کردنِ منطق راهِ دیگر بود و بدترین راه: قفلِ فوکوس چند حالتِ مرزی دارد
 *  (لایهٔ بی عنصرِ فوکوس‌پذیر، برگشتِ فوکوس به بازکنندهٔ لایه، خواندنِ
 *  `onClose` از ref تا فوکوس وسطِ تایپ دزدیده نشود) و دو نسخه یعنی روزی یکی
 *  از این‌ها فقط در یکی درست است.
 *
 *  `active` می‌گوید لایه باز است یا نه. `onEscape` را از ref می‌خواند، پس
 *  هر رندرِ والد این افکت را دوباره اجرا نمی‌کند.
 */
export function useFocusTrap(
  containerRef: RefObject<HTMLElement | null>,
  {
    active = true,
    onEscape,
    lockScroll = true,
    initialFocusRef,
  }: {
    active?: boolean;
    onEscape?: () => void;
    lockScroll?: boolean;
    initialFocusRef?: RefObject<HTMLElement | null>;
  } = {}
): void {
  // در ref نگه داشته می‌شود تا افکت به آن وابسته نباشد: وگرنه هر re-renderِ
  // والد (مثلاً هر کلیدِ فرمی که state‌اش بالاست) افکت را دوباره می‌بندد و
  // باز می‌کند و فوکوس را از فیلدِ در حالِ تایپ می‌دزدد.
  const escapeRef = { current: onEscape };
  escapeRef.current = onEscape;

  useEffect(() => {
    if (!active) return;
    const previousOverflow = document.body.style.overflow;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    if (lockScroll) document.body.style.overflow = "hidden";

    const container = containerRef.current;
    const firstFocusable = container?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
    (initialFocusRef?.current ?? firstFocusable ?? container)?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        escapeRef.current?.();
        return;
      }
      if (event.key !== "Tab" || !container) return;
      const focusable = Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0]!;
      const last = focusable[focusable.length - 1]!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      if (lockScroll) document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKeyDown);
      previouslyFocused?.focus();
    };
    // عمداً فقط به `active` وابسته است؛ بقیه از ref خوانده می‌شوند.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);
}
