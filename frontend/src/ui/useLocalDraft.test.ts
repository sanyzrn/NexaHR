/** خروج نباید ردی از فرم‌های نیمه‌تمام بگذارد.
 *
 * پیش‌نویسِ خودارزیابی عمداً در `localStorage` می‌نشیند تا یک رفرش یا یک
 * «بازگشت» اشتباهی، بیست شاخص با یادداشت را نبَرد. ولی `localStorage` با خروج
 * پاک نمی‌شود — و آن متن، شخصی‌ترین چیزی است که کسی در این سامانه می‌نویسد.
 *
 * روی یک رایانهٔ مشترک یعنی: نفرِ اول خارج می‌شود، و نوشته‌اش تا ابد روی آن
 * دستگاه می‌ماند و با devtools خواندنی است.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { DRAFT_PREFIX, clearLocalDrafts } from "./useLocalDraft";

describe("پاک‌کردنِ پیش‌نویس‌ها", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("همهٔ پیش‌نویس‌ها را برمی‌دارد، حتی وقتی چندتا باشند", () => {
    /* «چندتا» تزئینی نیست: حذف در حینِ پیمایشِ `localStorage` اندیس‌ها را
       جابه‌جا می‌کند و یکی‌درمیان از قلم می‌افتد. با یک کلید، آن اشکال دیده
       نمی‌شود. */
    for (const id of [1, 2, 3, 4, 5]) {
      window.localStorage.setItem(`${DRAFT_PREFIX}self-assessment:${id}`, '{"scores":{}}');
    }

    clearLocalDrafts();

    const left = Object.keys(window.localStorage).filter((k) => k.startsWith(DRAFT_PREFIX));
    expect(left).toEqual([]);
  });

  it("چیزی جز پیش‌نویس‌ها را دست نمی‌زند", () => {
    // تمِ انتخابیِ کاربر و وضعیتِ جمع‌شدنِ منو دادهٔ شخصی نیستند و با خروج
    // نباید بپرند؛ دفعهٔ بعد همان‌طور که گذاشته بودش باید باشد.
    window.localStorage.setItem("nexahr:theme", "dark");
    window.localStorage.setItem("nexahr:sidebar-collapsed", "1");
    window.localStorage.setItem(`${DRAFT_PREFIX}self-assessment:9`, "{}");

    clearLocalDrafts();

    expect(window.localStorage.getItem("nexahr:theme")).toBe("dark");
    expect(window.localStorage.getItem("nexahr:sidebar-collapsed")).toBe("1");
    expect(window.localStorage.getItem(`${DRAFT_PREFIX}self-assessment:9`)).toBeNull();
  });

  it("روی حافظهٔ خالی هم بی‌صدا رد می‌شود", () => {
    expect(() => clearLocalDrafts()).not.toThrow();
  });
});
