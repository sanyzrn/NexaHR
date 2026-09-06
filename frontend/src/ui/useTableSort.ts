import { useState } from "react";

export type TableSort = { column: number; direction: "asc" | "desc" } | null;
export type SortValue = string | number | boolean | null | undefined;

/** مقایسه‌گرِ فارسی، همان قاعده‌ای که سمتِ سرور `core/sorting.persian_text` دارد.
 *
 *  `sensitivity: "base"` یعنی «الف» و «أ» یکی شمرده شوند، و `numeric` یعنی
 *  «کد ۱۰» پس از «کد ۹» بیاید نه پیش از آن. نرمال‌سازیِ `ی/ك` جداگانه لازم
 *  است چون در دادهٔ واردشده از اکسل هر دو شکل هست و Collator آن دو را یکی
 *  نمی‌شمارد.
 */
const persian = new Intl.Collator("fa", { sensitivity: "base", numeric: true });
const normalize = (value: string) => value.trim().replace(/ي/g, "ی").replace(/ك/g, "ک");

/** مرتب‌سازیِ *کلاینتی* — فقط برای جدولی که کاملاً بارگذاری شده.
 *
 *  برای فهرستِ صفحه‌بندی‌شده به‌کار نبرید: مرتب‌کردنِ پنجاه ردیفِ صفحهٔ جاری
 *  جوابِ غلط می‌دهد، چون بقیهٔ ردیف‌ها اصلاً این‌جا نیستند. آن‌جا `sort_by` و
 *  `sort_dir` به سرور می‌روند.
 *
 *  `null` همیشه آخر می‌نشیند، در هر دو جهت: «ثبت‌نشده» یک مقدارِ کوچک نیست،
 *  نبودِ مقدار است — و کاربری که نزولی مرتب می‌کند دنبالِ بزرگ‌ترین‌هاست، نه
 *  دنبالِ خالی‌ها.
 */
export function sortRows<T>(
  rows: readonly T[],
  sort: TableSort,
  values: ((row: T) => SortValue)[]
): T[] {
  if (!sort) return [...rows];
  const value = values[sort.column];
  if (!value) return [...rows];
  return [...rows].sort((a, b) => {
    const left = value(a);
    const right = value(b);
    if (left == null) return right == null ? 0 : 1;
    if (right == null) return -1;
    const result =
      typeof left === "number" && typeof right === "number"
        ? left - right
        : persian.compare(normalize(String(left)), normalize(String(right)));
    return sort.direction === "asc" ? result : -result;
  });
}

/** حالتِ مرتب‌سازیِ یک جدول. کلیکِ دوباره روی همان ستون، جهت را برمی‌گرداند. */
export function useTableSort() {
  const [sort, setSort] = useState<TableSort>(null);
  function onSort(column: number) {
    setSort((previous) => ({
      column,
      direction: previous?.column === column && previous.direction === "asc" ? "desc" : "asc",
    }));
  }
  return { sort, onSort };
}
