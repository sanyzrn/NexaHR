/** «امروز» باید روزِ *محلی* باشد، نه روزِ UTC.
 *
 * `new Date().toISOString().slice(0, 10)` بینِ ۰۰:۰۰ و ۰۳:۳۰ به‌وقتِ تهران
 * هنوز *دیروز* را می‌دهد. پیش‌فرض‌های فیلترِ تاریخ («۳۰ روز»، «منقضی‌شده») از
 * همان می‌آمدند، پس قراردادی که *امروز* تمام می‌شود از گزارش بیرون می‌ماند —
 * در حالی که بک‌اند (`today_local()`) همان را منقضی می‌شمارد. هر شب، همان چند
 * ساعت، دو طرف دو جواب می‌دادند.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { localIsoDaysFromNow, localTodayIso } from "./dates";

afterEach(() => vi.useRealTimers());

describe("localTodayIso", () => {
  it("در ۰۰:۳۰ تهران، «امروز» است و نه دیروزِ UTC", () => {
    vi.useFakeTimers();
    // ۲۰۲۵-۱۲-۳۱ ساعت ۲۱:۰۰ UTC = ۲۰۲۶-۰۱-۰۱ ساعت ۰۰:۳۰ تهران
    vi.setSystemTime(new Date("2025-12-31T21:00:00Z"));
    expect(new Date().toISOString().slice(0, 10)).toBe("2025-12-31"); // رفتارِ قبلی
    expect(localTodayIso()).toBe("2026-01-01");
  });

  it("ماه و روزِ یک‌رقمی صفر می‌گیرند", () => {
    expect(localTodayIso(new Date(2026, 0, 5, 12))).toBe("2026-01-05");
  });
});

describe("localIsoDaysFromNow", () => {
  it("از همان روزِ محلی می‌شمارد", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2025-12-31T21:00:00Z"));
    expect(localIsoDaysFromNow(30)).toBe("2026-01-31");
    expect(localIsoDaysFromNow(0)).toBe("2026-01-01");
  });
});
