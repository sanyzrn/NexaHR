/** هیچ دکمه‌ای نباید زیرِ ۲۴ پیکسل بماند — WCAG 2.2، بند ۲٫۵٫۸ (سطح AA).
 *
 * بازبینی سه دکمه را نام برده بود («پاسخ»، «انصراف»، «علامت‌گذاری همه»)؛
 * جست‌وجوی خودکار هفت تای دیگر هم پیدا کرد. یعنی این یک اشکالِ موردی نبود،
 * یک *الگو* بود: هر جا دکمه‌ای فقط متن است و اندازه‌ای برایش تعیین نشده،
 * ارتفاعش می‌شود ارتفاعِ همان `text-xs` — حدودِ ۱۶ پیکسل.
 *
 * پس به‌جای فهرست‌کردنِ همان ده‌تا، خودِ قاعده تست می‌شود. اگر فردا کسی
 * دکمهٔ متنیِ کوچکِ تازه‌ای بنویسد، این‌جا قرمز می‌شود — نه در گزارشِ بازبینیِ
 * بعدی.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// ریشهٔ پروژه است، نه مسیرِ این فایل: vitest از `frontend/` اجرا می‌شود.
const SRC = join(process.cwd(), "src");

/** کلاس‌هایی که به دکمه اندازه می‌دهند — هر کدام باشد، دکمه از ۱۶ پیکسل بزرگ‌تر است. */
const HAS_SIZE = /\b(tap-target|h-\d|h-\[|min-h|py-|p-\d|p-\[|size-)/;
/** متنِ ریز: `text-xs` و هر `text-[N px]` تا ۱۳. */
const SMALL_TEXT = /text-(xs|\[1[0-3]px\])/;
const BUTTON_CLASS = /<button\b(?:(?!<\/?button)[\s\S])*?className=\{?"([^"]*)"/gm;

function tsxFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return tsxFiles(full);
    return name.endsWith(".tsx") && !name.endsWith(".test.tsx") ? [full] : [];
  });
}

describe("اندازهٔ هدفِ لمسی", () => {
  it("هیچ دکمهٔ متنیِ ریزی بی اندازه رها نشده", () => {
    const offenders: string[] = [];
    for (const file of tsxFiles(SRC)) {
      const source = readFileSync(file, "utf8");
      for (const match of source.matchAll(BUTTON_CLASS)) {
        const classes = match[1] ?? "";
        if (SMALL_TEXT.test(classes) && !HAS_SIZE.test(classes)) {
          const line = source.slice(0, match.index).split("\n").length;
          offenders.push(`${file.slice(SRC.length)}:${line} → "${classes.slice(0, 70)}"`);
        }
      }
    }
    expect(offenders, `دکمه‌های زیر کلاسِ \`tap-target\` (یا پدینگ) لازم دارند:\n${offenders.join("\n")}`).toEqual([]);
  });

  it("خودِ جست‌وجو کار می‌کند — وگرنه این تست همیشه سبز است", () => {
    // بی این، حذفِ تصادفیِ یک regex تست را بی‌اثر و همیشه‌سبز می‌کرد.
    const bare = '<button className="text-xs font-medium text-gray-500">پاسخ</button>';
    const sized = '<button className="tap-target text-xs font-medium">پاسخ</button>';
    const matchOf = (s: string) => [...s.matchAll(BUTTON_CLASS)][0]?.[1] ?? "";

    expect(SMALL_TEXT.test(matchOf(bare))).toBe(true);
    expect(HAS_SIZE.test(matchOf(bare))).toBe(false);
    expect(HAS_SIZE.test(matchOf(sized))).toBe(true);
  });

  it("خودِ قاعدهٔ CSS هم واقعاً ۲۴ پیکسل می‌دهد", () => {
    /* تستِ بالا فقط می‌گوید کلاس *به‌کار رفته*. اگر قاعده‌اش یک روز به صفر
       برگردد، همان تست سبز می‌ماند و هیچ دکمه‌ای بزرگ نیست. jsdom قواعدِ
       Tailwind را اعمال نمی‌کند، پس عدد از خودِ فایل خوانده می‌شود — همان
       عددی که WCAG 2.5.8 نام برده. */
    const css = readFileSync(join(process.cwd(), "src", "index.css"), "utf8");
    const rule = /\.tap-target\s*\{([^}]*)\}/.exec(css);
    expect(rule, "قاعدهٔ `.tap-target` در index.css پیدا نشد").not.toBeNull();

    const body = rule![1]!;
    const px = (prop: string) => Number(new RegExp(`${prop}:\\s*(\\d+)px`).exec(body)?.[1] ?? -1);
    expect(px("min-height")).toBeGreaterThanOrEqual(24);
    expect(px("min-width")).toBeGreaterThanOrEqual(24);
    // بی `inline-flex`، ارتفاعِ حداقلی روی یک دکمهٔ inline اثری ندارد.
    expect(body).toMatch(/display:\s*inline-flex/);
  });
});
