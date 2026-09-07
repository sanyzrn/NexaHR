/** کنترستِ متنِ راهنما در تمِ *روشن*.
 *
 * تم تیره با نسبت‌های محاسبه‌شده و مستند ساخته شده — کامنت‌های `index.css`
 * عددشان را می‌نویسند: «از ۴٫۸۵:۱ برای کم‌رنگ‌ترین تا ۱۴٫۲۲:۱ برای عنوان‌ها».
 * تم روشن هیچ‌کدام از توکن‌های خاکستری را بازتعریف نکرده بود، پس مقدارِ
 * پیش‌فرضِ تیلویند می‌ماند: `gray-400` = #9ca3af، که روی سفید **۲٫۵۴:۱** است.
 *
 * و این رنگ تزئینی نیست. با همین کلاس نوشته شده‌اند: راهنمای مسیرِ اعتراض
 * («اگر به این نتیجه اعتراض دارید…» — تنها اشاره به آن مسیر)، یادداشتِ
 * محرمانگیِ خودارزیابی، و متنِ حالت‌های خالی. کسی که کم‌بینا است دقیقاً همان
 * جمله‌هایی را از دست می‌دهد که *حقوقش* را توضیح می‌دهند.
 *
 * این تست فایلِ CSS را می‌خواند و نسبت را با فرمولِ خودِ WCAG می‌سنجد، تا اگر
 * فردا کسی توکن را عوض کرد این‌جا بشکند نه روی صفحهٔ یک کاربر.
 */
/// <reference types="node" />
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const CSS = readFileSync(join(__dirname, "..", "index.css"), "utf8");

/** روشناییِ نسبیِ WCAG 2.1 (بند ۱٫۴٫۳). */
function luminance(hex: string): number {
  const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const linear = channels.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * linear[0]! + 0.7152 * linear[1]! + 0.0722 * linear[2]!;
}

function ratio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
}

/** آخرین تعریفِ توکن *پیش از* بلوکِ تم تیره — یعنی مقدارِ تم روشن. */
function lightToken(name: string): string {
  const light = CSS.split('[data-theme="dark"]')[0]!;
  const matches = [...light.matchAll(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`, "g"))];
  expect(matches.length, `توکنِ --${name} در تمِ روشن تعریف نشده است`).toBeGreaterThan(0);
  return matches[matches.length - 1]![1]!;
}

describe("کنترستِ تم روشن", () => {
  it("متنِ راهنما روی سفید آستانهٔ AA را می‌گذراند", () => {
    // #9ca3af (پیش‌فرضِ تیلویند) این‌جا ۲٫۵۴ می‌داد.
    expect(ratio(lightToken("color-gray-400"), "#ffffff")).toBeGreaterThanOrEqual(4.5);
  });

  it("و روی کارتِ خاکستریِ ملایم هم", () => {
    // `bg-gray-50` زیرِ خیلی از همان متن‌ها نشسته.
    expect(ratio(lightToken("color-gray-400"), "#f9fafb")).toBeGreaterThanOrEqual(4.5);
  });

  it("تم تیره — که از قبل محاسبه شده بود — همچنان می‌گذراند", () => {
    const dark = CSS.split('[data-theme="dark"]')[1]!;
    const value = dark.match(/--color-gray-400:\s*(#[0-9a-fA-F]{6})/)![1]!;
    // زمینهٔ کارت در تم تیره.
    expect(ratio(value, "#1b2031")).toBeGreaterThanOrEqual(4.5);
  });
});
