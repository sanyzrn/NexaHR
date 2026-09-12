import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import { useAnchoredPopover } from "./useAnchoredPopover";
import { useFocusTrap } from "./focusTrap";
import {
  JALALI_MONTH_NAMES,
  JALALI_WEEKDAY_LABELS,
  isoToJalali,
  jalaliMonthLength,
  jalaliToIso,
  jalaliWeekday,
  toPersianDigits,
  todayJalali,
} from "../utils/jalali";

type PickerMode = "days" | "months" | "years";

/**
 * انتخاب‌گر تاریخ شمسی (جلالی).
 *
 * مقدار ورودی/خروجی همچنان به‌صورت رشته‌ی میلادی استاندارد ISO ("YYYY-MM-DD")
 * است — دقیقاً همان قالبی که <input type="date"> تولید می‌کرد — تا نیازی به
 * تغییر در API یا پایگاه‌داده نباشد. فقط نمایش و ورودی برای کاربر شمسی است.
 *
 * سه حالت داخلی دارد: روز / ماه / سال. با کلیک روی نام ماه یا سال در هدر، به
 * شبکهٔ انتخاب سریع می‌رود تا کاربر بدون کلیک‌های پیاپی به سال‌های دور بپرد.
 */
export function JalaliDatePicker({
  value,
  onChange,
  required,
  className,
  placeholder = "انتخاب تاریخ",
  disabled,
}: {
  value: string;
  onChange: (iso: string) => void;
  required?: boolean;
  className?: string;
  placeholder?: string;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<PickerMode>("days");
  const containerRef = useRef<HTMLDivElement>(null);
  // پاپ‌آور روی body می‌رود تا `overflow-hidden`ِ نوارِ فیلتر نبُردش — توضیح کامل
  // در `useAnchoredPopover`.
  const {
    anchorRef,
    popoverRef,
    style: popoverStyle,
    containsNode: popoverContains,
  } = useAnchoredPopover<HTMLButtonElement, HTMLDivElement>(open);

  const selectedJalali = useMemo(() => isoToJalali(value), [value]);
  const [viewYear, setViewYear] = useState(() => (selectedJalali ?? todayJalali()).jy);
  const [viewMonth, setViewMonth] = useState(() => (selectedJalali ?? todayJalali()).jm);
  // شروع پنجرهٔ ۱۲ سالهٔ حالت انتخاب سال
  const [yearWindowStart, setYearWindowStart] = useState(() => viewYear - 5);

  // ── پیمایش با کیبورد ─────────────────────────────────────────────────
  //
  // تا امروز این تقویم برای کاربرِ فقط-کیبورد *غیرقابل‌استفاده* بود، نه
  // سخت: پاپ‌آور به `body` پورتال می‌شود، پس هیچ‌چیز فوکوس را داخلش نمی‌بُرد.
  // داخلِ مودال بدتر بود — تلهٔ فوکوسِ مودال فقط درونِ ظرفِ خودش جست‌وجو
  // می‌کند و تقویمِ پورتال‌شده اصلاً در چرخهٔ Tab نبود. و تاریخِ قرارداد در
  // نیمی از فرم‌های این سامانه هست (WCAG 2.1.2 و 2.4.3).
  //
  // الگو، همان «tabindex غلتان»ِ استانداردِ شبکه است: در هر لحظه فقط *یک*
  // روز در چرخهٔ Tab است و کلیدهای جهت بینِ روزها می‌گردند. اگر هر ۳۱ روز
  // tabbable بودند، رسیدن به دکمهٔ «ثبت» سی‌ویک بار Tab لازم داشت.
  const [activeDay, setActiveDay] = useState<number>(() => (selectedJalali ?? todayJalali()).jd);
  const activeDayRef = useRef<HTMLButtonElement>(null);
  // با کلیدِ جهت که روز عوض می‌شود، فوکوس باید دنبالش برود — ولی *فقط* آن‌وقت.
  // بی این پرچم، هر رندرِ دیگری (مثلاً باز شدنِ ماهِ بعد با کلیک) فوکوس را از
  // جایی که کاربر گذاشته می‌دزدید.
  const followFocusRef = useRef(false);

  // فوکوس داخلِ پاپ‌آور قفل می‌شود و در بسته‌شدن به دکمهٔ بازکننده برمی‌گردد.
  // `lockScroll` خاموش است: تقویم یک لایهٔ سبک است، نه مودالِ تمام‌صفحه.
  // Escape عمداً به این هوک سپرده نمی‌شود — شنوندهٔ فازِ capture بالاتر
  // خودش آن را می‌گیرد و `stopPropagation` می‌کند تا مودالِ زیرین بسته نشود.
  useFocusTrap(popoverRef, {
    active: open,
    lockScroll: false,
    initialFocusRef: activeDayRef,
  });

  useEffect(() => {
    if (selectedJalali) {
      setViewYear(selectedJalali.jy);
      setViewMonth(selectedJalali.jm);
    }
  }, [selectedJalali]);

  useEffect(() => {
    if (!open) return;
    function onClickOutside(e: MouseEvent) {
      const t = e.target as Node;
      // پاپ‌آور دیگر فرزندِ `containerRef` نیست (پورتال است)، پس باید جداگانه
      // سنجیده شود؛ وگرنه هر کلیک داخلِ تقویم «کلیکِ بیرون» حساب می‌شد و
      // تقویم پیش از رسیدنِ کلیک به روزها بسته می‌شد.
      if (containerRef.current?.contains(t) || popoverContains(t)) return;
      setOpen(false);
    }
    // Escape فقط *این* لایه را می‌بندد، نه هرچه زیرش باز است.
    //
    // تقویم اغلب داخلِ یک مودال است و `useFocusTrap` هم شنوندهٔ Escape روی
    // `document` دارد. تا امروز هیچ‌کدام جلوی دیگری را نمی‌گرفت، پس یک Escape
    // هم تقویم را می‌بست و هم کلِ دیالوگ را: کاربر در «آغاز دورهٔ ارزیابی
    // جدید» تاریخ را باز می‌کرد، Escape می‌زد که فقط تقویم برود، و کلِ فرم
    // ناپدید می‌شد. در `BulkCreateDialog` یعنی از دست رفتنِ انتخابِ پرسنلِ
    // چندمرحله‌ای.
    //
    // فازِ **capture** و نه bubble: هر دو شنونده روی `document` نشسته‌اند، پس
    // `stopPropagation` در فازِ bubble آن یکی را — که روی همان گره است —
    // متوقف نمی‌کند. در capture، رویداد هنوز به هدف نرسیده؛ متوقف‌کردنش
    // یعنی هیچ‌وقت به فازِ bubble و به تلهٔ مودال نمی‌رسد.
    function onKeyDownCapture(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    document.addEventListener("keydown", onKeyDownCapture, true);
    return () => {
      document.removeEventListener("mousedown", onClickOutside);
      document.removeEventListener("keydown", onKeyDownCapture, true);
    };
  }, [open, popoverContains]);

  // با هر بار بازشدن، از حالت روز شروع کن
  function toggleOpen() {
    setOpen((v) => {
      if (!v) {
        setMode("days");
        // لنگرِ کیبورد روی روزِ انتخاب‌شده می‌نشیند، وگرنه روی امروز — نه روی
        // جایی که آخرین بار رهایش کرده بودیم.
        setActiveDay((selectedJalali ?? todayJalali()).jd);
      }
      return !v;
    });
  }

  const displayValue = selectedJalali
    ? toPersianDigits(
        `${selectedJalali.jy}/${String(selectedJalali.jm).padStart(2, "0")}/${String(selectedJalali.jd).padStart(2, "0")}`
      )
    : "";

  function goMonth(delta: number) {
    let m = viewMonth + delta;
    let y = viewYear;
    if (m < 1) {
      m = 12;
      y -= 1;
    } else if (m > 12) {
      m = 1;
      y += 1;
    }
    setViewYear(y);
    setViewMonth(m);
  }

  function pickDay(jd: number) {
    onChange(jalaliToIso(viewYear, viewMonth, jd));
    setOpen(false);
  }

  /** روزِ فعال را `delta` روز جابه‌جا می‌کند و در صورت لزوم از مرزِ ماه رد می‌شود. */
  function moveActiveDay(delta: number) {
    followFocusRef.current = true;
    let y = viewYear;
    let m = viewMonth;
    let d = activeDay + delta;
    // ماه‌های شمسی طولِ متفاوت دارند (و اسفندِ کبیسه ۳۰ روز)، پس مرز با
    // `jalaliMonthLength` سنجیده می‌شود نه با یک عددِ ثابت.
    while (d < 1) {
      m -= 1;
      if (m < 1) {
        m = 12;
        y -= 1;
      }
      d += jalaliMonthLength(y, m);
    }
    while (d > jalaliMonthLength(y, m)) {
      d -= jalaliMonthLength(y, m);
      m += 1;
      if (m > 12) {
        m = 1;
        y += 1;
      }
    }
    setViewYear(y);
    setViewMonth(m);
    setActiveDay(d);
  }

  /** همان ماه، ولی `delta` ماه جلوتر/عقب‌تر — با روزی که از طولِ ماهِ مقصد نزند بیرون. */
  function moveActiveMonth(delta: number) {
    followFocusRef.current = true;
    let m = viewMonth + delta;
    let y = viewYear;
    while (m < 1) {
      m += 12;
      y -= 1;
    }
    while (m > 12) {
      m -= 12;
      y += 1;
    }
    setViewYear(y);
    setViewMonth(m);
    // عمداً این‌جا clamp نمی‌شود. اگر روزِ فعال از طولِ ماهِ مقصد بزند بیرون،
    // رندر لنگر را روی آخرین روز می‌گذارد و `onFocus`ِ همان دکمه حالت را
    // اصلاح می‌کند — پس یک clampِ دوم این‌جا هیچ رفتاری را عوض نمی‌کند و هیچ
    // تستی نمی‌تواند از هم جدایشان کند. دو قاعده برای یک چیز، یعنی روزی یکی
    // از دو تا عوض می‌شود و آن یکی جا می‌ماند.
  }

  /** کلیدهای جهت روی شبکهٔ روزها.
   *
   *  در RTL جهتِ افقی آینه می‌شود: فلشِ راست یک روز *عقب* می‌رود و فلشِ چپ یک
   *  روز جلو — همان‌طور که چشم روی شبکه حرکت می‌کند.
   */
  function onDayGridKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    const moves: Record<string, () => void> = {
      ArrowRight: () => moveActiveDay(-1),
      ArrowLeft: () => moveActiveDay(1),
      ArrowUp: () => moveActiveDay(-7),
      ArrowDown: () => moveActiveDay(7),
      PageUp: () => moveActiveMonth(-1),
      PageDown: () => moveActiveMonth(1),
      Home: () => {
        followFocusRef.current = true;
        setActiveDay(1);
      },
      End: () => {
        followFocusRef.current = true;
        setActiveDay(jalaliMonthLength(viewYear, viewMonth));
      },
    };
    const move = moves[e.key];
    if (!move) return;
    // جلوی اسکرولِ صفحه و جابه‌جاییِ کاراکتر گرفته می‌شود؛ این کلیدها این‌جا
    // معنای خودشان را دارند.
    e.preventDefault();
    move();
  }

  function openYears() {
    setYearWindowStart(viewYear - 5);
    setMode("years");
  }

  useEffect(() => {
    if (!followFocusRef.current) return;
    followFocusRef.current = false;
    activeDayRef.current?.focus();
  }, [activeDay, viewYear, viewMonth]);

  const daysInMonth = jalaliMonthLength(viewYear, viewMonth);
  const firstWeekday = jalaliWeekday(viewYear, viewMonth, 1); // 0=شنبه ... 6=جمعه
  const cells: (number | null)[] = [
    ...Array.from({ length: firstWeekday }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];

  const today = todayJalali();
  const years = Array.from({ length: 12 }, (_, i) => yearWindowStart + i);

  const crossfade = {
    initial: { opacity: 0, y: 4 },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0, y: -4 },
    transition: { duration: 0.15, ease: "easeOut" as const },
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        ref={anchorRef}
        type="button"
        disabled={disabled}
        onClick={toggleOpen}
        aria-haspopup="dialog"
        aria-expanded={open}
        className={
          className ??
          "field-trigger w-full rounded-xl border border-gray-200 bg-gray-100 px-3 py-2 text-right text-sm text-gray-900 outline-none transition-colors duration-150 focus:border-gray-900 focus:bg-white disabled:cursor-not-allowed disabled:bg-gray-50 disabled:text-gray-400"
        }
      >
        <span className={displayValue ? "" : "text-gray-400"}>{displayValue || placeholder}</span>
      </button>
      {/* ورودی مخفی برای حفظ رفتار required در فرم‌های HTML */}
      {required && (
        <input tabIndex={-1} aria-hidden="true" className="sr-only" required value={value} onChange={() => {}} />
      )}

      {createPortal(
      <AnimatePresence>
        {open && (
          <motion.div
            ref={popoverRef}
            style={popoverStyle}
            role="dialog"
            aria-label="انتخاب تاریخ"
            // z-[60]: بالای پوششِ مودال (z-50) چون این انتخابگر داخلِ مودال هم
            // به‌کار می‌رود، و پایینِ تولتیپ (z-[70]).
            className="z-[60] w-72 overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-float ring-1 ring-black/5"
            initial={{ opacity: 0, y: -6, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.97 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
          >
            {/* ── هدر ──
                RTL: اولین فرزند در سمت راست قرار می‌گیرد. طبق قرارداد تقویم فارسی،
                فلش سمت راست = ماه قبل و فلش سمت چپ = ماه بعد. */}
            <div className="flex items-center justify-between border-b border-gray-100 px-2 py-2">
              <button
                type="button"
                onClick={() => goMonth(-1)}
                aria-label="ماه قبل"
                className="rounded-lg p-1.5 text-gray-500 transition-colors hover:bg-gray-100 hover:text-pulse-700"
              >
                {/* فلش راست (›) — به گذشته */}
                <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M8 4l6 6-6 6" />
                </svg>
              </button>

              <div className="flex items-center gap-1 text-sm font-bold text-gray-900">
                <button
                  type="button"
                  onClick={() => setMode((m) => (m === "months" ? "days" : "months"))}
                  className="rounded-lg px-2 py-0.5 transition-colors hover:bg-pulse-50 hover:text-pulse-700"
                >
                  {JALALI_MONTH_NAMES[viewMonth - 1]}
                </button>
                <button
                  type="button"
                  onClick={() => (mode === "years" ? setMode("days") : openYears())}
                  className="rounded-lg px-2 py-0.5 transition-colors hover:bg-pulse-50 hover:text-pulse-700"
                >
                  {toPersianDigits(viewYear)}
                </button>
              </div>

              <button
                type="button"
                onClick={() => goMonth(1)}
                aria-label="ماه بعد"
                className="rounded-lg p-1.5 text-gray-500 transition-colors hover:bg-gray-100 hover:text-pulse-700"
              >
                {/* فلش چپ (‹) — به آینده */}
                <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 4l-6 6 6 6" />
                </svg>
              </button>
            </div>

            <AnimatePresence mode="wait">
              {mode === "days" && (
                <motion.div key="days" {...crossfade}>
                  <div className="grid grid-cols-7 gap-0.5 px-2 pt-2 text-center text-[11px] font-medium text-gray-400">
                    {JALALI_WEEKDAY_LABELS.map((label, i) => (
                      <div key={i}>{label}</div>
                    ))}
                  </div>
                  {/* `onKeyDown` روی خودِ شبکه می‌نشیند و نه تک‌تکِ دکمه‌ها:
                      رویداد از دکمهٔ فوکوس‌دار بالا می‌آید، پس یک شنونده کافی
                      است و با عوض‌شدنِ روزِ فعال هم جابه‌جا نمی‌شود. */}
                  <div
                    role="grid"
                    aria-label={`روزهای ${JALALI_MONTH_NAMES[viewMonth - 1]} ${toPersianDigits(viewYear)}`}
                    onKeyDown={onDayGridKeyDown}
                    className="grid grid-cols-7 gap-0.5 px-2 pb-2 pt-1"
                  >
                    {cells.map((jd, idx) => {
                      if (jd === null) return <div key={`empty-${idx}`} role="presentation" />;
                      const isSelected =
                        selectedJalali && selectedJalali.jy === viewYear && selectedJalali.jm === viewMonth && selectedJalali.jd === jd;
                      const isToday = today.jy === viewYear && today.jm === viewMonth && today.jd === jd;
                      // دقیقاً یک روز در چرخهٔ Tab است — همان روزی که کلیدهای
                      // جهت رویش ایستاده‌اند. اگر روزِ فعال از طولِ این ماه
                      // بزند بیرون (ماه که عوض می‌شود)، آخرین روز می‌ایستد تا
                      // شبکه هیچ‌وقت بی‌لنگر نماند.
                      const anchor = Math.min(activeDay, daysInMonth);
                      const isActive = jd === anchor;
                      return (
                        <button
                          key={jd}
                          ref={isActive ? activeDayRef : undefined}
                          type="button"
                          tabIndex={isActive ? 0 : -1}
                          onClick={() => pickDay(jd)}
                          onFocus={() => setActiveDay(jd)}
                          aria-label={`${toPersianDigits(jd)} ${JALALI_MONTH_NAMES[viewMonth - 1]} ${toPersianDigits(viewYear)}`}
                          aria-current={isToday ? "date" : undefined}
                          aria-pressed={Boolean(isSelected)}
                          className={`flex h-8 w-8 items-center justify-center rounded-lg text-xs transition-colors focus-visible:ring-2 focus-visible:ring-pulse-500 focus-visible:ring-offset-1 ${
                            isSelected
                              ? "bg-pulse-600 font-bold text-white"
                              : isToday
                                ? "font-bold text-pulse-700 ring-1 ring-inset ring-pulse-200"
                                : "text-gray-700 hover:bg-gray-100"
                          }`}
                        >
                          {toPersianDigits(jd)}
                        </button>
                      );
                    })}
                  </div>
                </motion.div>
              )}

              {mode === "months" && (
                <motion.div key="months" {...crossfade} className="grid grid-cols-3 gap-1 p-2">
                  {JALALI_MONTH_NAMES.map((name, i) => {
                    const m = i + 1;
                    const isCurrent = m === viewMonth;
                    return (
                      <button
                        key={name}
                        type="button"
                        onClick={() => {
                          setViewMonth(m);
                          setMode("days");
                        }}
                        className={`flex h-11 items-center justify-center rounded-xl text-sm transition-colors ${
                          isCurrent
                            ? "bg-pulse-600 font-bold text-white"
                            : "text-gray-700 hover:bg-gray-100"
                        }`}
                      >
                        {name}
                      </button>
                    );
                  })}
                </motion.div>
              )}

              {mode === "years" && (
                <motion.div key="years" {...crossfade} className="p-2">
                  <div className="mb-1 flex items-center justify-between px-1">
                    <button
                      type="button"
                      onClick={() => setYearWindowStart((s) => s - 12)}
                      aria-label="سال‌های قبل"
                      className="rounded-lg p-1 text-gray-500 transition-colors hover:bg-gray-100 hover:text-pulse-700"
                    >
                      <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M8 4l6 6-6 6" />
                      </svg>
                    </button>
                    <span className="text-xs font-medium text-gray-500">
                      {toPersianDigits(yearWindowStart)} – {toPersianDigits(yearWindowStart + 11)}
                    </span>
                    <button
                      type="button"
                      onClick={() => setYearWindowStart((s) => s + 12)}
                      aria-label="سال‌های بعد"
                      className="rounded-lg p-1 text-gray-500 transition-colors hover:bg-gray-100 hover:text-pulse-700"
                    >
                      <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M12 4l-6 6 6 6" />
                      </svg>
                    </button>
                  </div>
                  <div className="grid grid-cols-3 gap-1">
                    {years.map((y) => {
                      const isCurrent = y === viewYear;
                      return (
                        <button
                          key={y}
                          type="button"
                          onClick={() => {
                            setViewYear(y);
                            setMode("days");
                          }}
                          className={`flex h-11 items-center justify-center rounded-xl text-sm transition-colors ${
                            isCurrent
                              ? "bg-pulse-600 font-bold text-white"
                              : "text-gray-700 hover:bg-gray-100"
                          }`}
                        >
                          {toPersianDigits(y)}
                        </button>
                      );
                    })}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            <div className="flex justify-between border-t border-gray-100 px-3 py-2">
              <button
                type="button"
                onClick={() => {
                  const t = todayJalali();
                  onChange(jalaliToIso(t.jy, t.jm, t.jd));
                  setOpen(false);
                }}
                className="tap-target text-xs font-medium text-pulse-600 hover:underline"
              >
                امروز
              </button>
              {value && (
                <button
                  type="button"
                  onClick={() => {
                    onChange("");
                    setOpen(false);
                  }}
                  className="tap-target text-xs font-medium text-gray-400 hover:text-gray-600 hover:underline"
                >
                  پاک کردن
                </button>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>,
      document.body
      )}
    </div>
  );
}
