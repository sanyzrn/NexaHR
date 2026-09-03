import { useId, useRef, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import { useFocusTrap } from "./focusTrap";
import { EASE_SOFT, SPRING_SOFT } from "./motion";

const SIZES = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-2xl",
} as const;

export type ModalSize = keyof typeof SIZES;

/** مودال استاندارد و مشترک برنامه.
 * با createPortal روی body رندر می‌شود تا موقعیت‌دهی fixed هیچ‌وقت تحت‌تأثیر
 * transform/overflow والدها قرار نگیرد (رفع باگ باز شدن مودال خارج از مرکز).
 * Escape و کلیک روی پس‌زمینه = بستن؛ اسکرول body هنگام باز بودن قفل می‌شود.
 * فوکوس هنگام باز شدن وارد مودال می‌شود، با Tab/Shift+Tab داخل آن قفل می‌ماند
 * (کاربر کیبورد/screen reader پشت مودال گم نمی‌شود) و هنگام بسته‌شدن به عنصری
 * که مودال را باز کرده برمی‌گردد.
 * انیمیشن با Framer Motion: scale + fade + spring. */
export function Modal({
  title,
  onClose,
  size = "md",
  children,
  footer,
  initialFocusRef,
}: {
  title: ReactNode;
  onClose: () => void;
  size?: ModalSize;
  children: ReactNode;
  footer?: ReactNode;
  /** عنصری که باید هنگام باز شدن فوکوس بگیرد؛ پیش‌فرض، اولین عنصر فوکوس‌پذیر.
   *
   * بدون این، هر کسی که می‌خواست فوکوس اولیه را جای دیگری ببرد مجبور بود در
   * effect خودش دوباره focus() صدا بزند — و دو جا که سرِ فوکوس دعوا کنند،
   * برنده‌اش به ترتیب اجرای effectها بستگی دارد، نه به تصمیم کسی. */
  initialFocusRef?: RefObject<HTMLElement | null>;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId();

  // قفلِ فوکوس، Escape و قفلِ اسکرول همه از هوکِ مشترک می‌آیند
  // (`ui/focusTrap`). کشوی ناوبریِ موبایل همین رفتار را لازم داشت و نداشتش،
  // و دو نسخهٔ جدا از این منطق یعنی روزی یکی از حالت‌های مرزی فقط در یکی
  // درست است.
  useFocusTrap(dialogRef, { onEscape: onClose, initialFocusRef });

  return createPortal(
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex items-center justify-center bg-gray-900/40 p-4 backdrop-blur-sm"
        onMouseDown={(e) => {
          if (e.target === e.currentTarget) onClose();
        }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.16, ease: EASE_SOFT }}
      >
        <motion.div
          ref={dialogRef}
          role="dialog"
          aria-modal="true"
          // `aria-labelledby` و نه `aria-label`: عنوان می‌تواند `ReactNode`
          // باشد (نشان + متن، یا یک `<span>`ِ رنگی)، و در آن حالت شرطِ
          // `typeof title === "string"` می‌افتاد و دیالوگ *بی‌نام* اعلام
          // می‌شد — صفحه‌خوان فقط «دیالوگ» می‌گفت. ارجاع به خودِ تیتر، هر دو
          // حالت را می‌گیرد.
          aria-labelledby={titleId}
          tabIndex={-1}
          className={`max-h-[90vh] w-full ${SIZES[size]} overflow-y-auto rounded-2xl bg-white shadow-float outline-none`}
          initial={{ opacity: 0, scale: 0.97, y: 8 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.98, y: 4 }}
          transition={SPRING_SOFT}
        >
          {/* بالای مودال: عنوان + دکمه بستن */}
          <div className="mb-2.5 flex items-start justify-between gap-3 border-b border-gray-100 px-5 pt-4 pb-3">
            <h3 id={titleId} className="text-sm font-bold text-gray-900 sm:text-base">
              {title}
            </h3>
            <button
              onClick={onClose}
              aria-label="بستن"
              className="-ml-1 rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700"
            >
              <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M5 5l10 10M15 5L5 15" />
              </svg>
            </button>
          </div>
          {/* بدونِ footer، همین بخش کفِ مودال است — و padding پایین لازم دارد.
              وگرنه آخرین سطرِ متن به لبهٔ کارت می‌چسبد؛ جایی که footer هست،
              خودش `py-3` دارد و فاصله را می‌دهد. */}
          <div className={`px-5 ${footer ? "" : "pb-5"}`}>
            {children}
          </div>
          {footer && (
            <div className="mt-4 flex justify-end gap-2 border-t border-gray-100 px-5 py-3">
              {footer}
            </div>
          )}
        </motion.div>
      </motion.div>
    </AnimatePresence>,
    document.body
  );
}
