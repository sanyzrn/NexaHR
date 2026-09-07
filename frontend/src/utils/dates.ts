// locale «fa-IR» به‌صورت خودکار تقویم شمسی و ارقام فارسی می‌دهد
const dateTimeFormatter = new Intl.DateTimeFormat("fa-IR", {
  dateStyle: "medium",
  timeStyle: "short",
});
const dateFormatter = new Intl.DateTimeFormat("fa-IR", { dateStyle: "medium" });

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return dateTimeFormatter.format(new Date(iso));
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return dateFormatter.format(new Date(iso));
}

/** «امروز» به شکلِ `YYYY-MM-DD`، از روی *اجزای محلیِ* تاریخ.
 *
 * `new Date().toISOString().slice(0, 10)` روزِ **UTC** را می‌دهد. بینِ ۰۰:۰۰ و
 * ۰۳:۳۰ به‌وقتِ تهران آن روز هنوز *دیروز* است، پس پیش‌فرض‌های فیلترِ تاریخ
 * («۳۰ روز»، «منقضی‌شده») یک روز عقب می‌افتادند: قراردادی که *امروز* تمام
 * می‌شود از گزارش بیرون می‌ماند، در حالی که بک‌اند — که `today_local()` دارد
 * — همان را منقضی می‌شمارد. هر شب، همان چند ساعت، دو طرف دو جواب می‌دادند.
 *
 * همان الگویی که `SubmissionDeadlineBar` از قبل برای مقایسهٔ مهلت داشت، حالا
 * یک جا و با یک نام.
 */
export function localTodayIso(base: Date = new Date()): string {
  const month = String(base.getMonth() + 1).padStart(2, "0");
  const day = String(base.getDate()).padStart(2, "0");
  return `${base.getFullYear()}-${month}-${day}`;
}

/** `localTodayIso` برای `n` روز بعد (یا قبل، با عددِ منفی). */
export function localIsoDaysFromNow(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return localTodayIso(d);
}
