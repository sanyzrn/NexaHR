/** شمارندهٔ نویسه برای فیلدهای متنیِ سقف‌دار.
 *
 * `maxLength` به‌تنهایی کافی نیست: مرورگر بی هیچ توضیحی تایپ را قطع می‌کند و
 * کاربر فکر می‌کند صفحه‌کلید گیر کرده. شمارنده می‌گوید چرا.
 *
 * عمداً تا نزدیکِ سقف ساکت است — شمارنده‌ای که از نویسهٔ اول رخ نشان می‌دهد،
 * نوشتن را به شمردن تبدیل می‌کند. آستانه ۸۰٪ است، و در ۱۰۰٪ رنگ عوض می‌شود.
 */
import { toPersianDigits } from "../utils/jalali";

/** از چند درصدِ سقف به بعد شمارنده دیده شود. */
const VISIBLE_FROM = 0.8;

export function CharCounter({ value, max }: { value: string; max: number }) {
  const used = value.length;
  if (used < max * VISIBLE_FROM) return null;

  const full = used >= max;
  return (
    <p
      // خواندنی برای صفحه‌خوان، ولی نه با هر نویسه: `polite` یعنی وقتی کاربر
      // مکث کرد خوانده می‌شود، نه وسطِ تایپ.
      aria-live="polite"
      className={`mt-1 text-xs ${full ? "font-medium text-amber-700" : "text-gray-400"}`}
    >
      {toPersianDigits(used)} از {toPersianDigits(max)} نویسه
      {full ? " — به سقف رسید" : ""}
    </p>
  );
}
