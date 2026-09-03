import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// بدون globals در vitest، پاک‌سازی خودکار testing-library فعال نمی‌شود؛
// بین تست‌ها DOM باید خالی شود تا رندرها روی هم انباشته نشوند.
afterEach(() => {
  cleanup();
});

// jsdom پیاده‌سازی matchMedia ندارد. بدون این، هر کامپوننتی که به عرض صفحه واکنش
// نشان می‌دهد (فرم امتیازدهی: کارت روی موبایل، جدول روی دسکتاپ) در تست می‌ترکد.
// پیش‌فرض «برقرار نیست» یعنی تست‌ها نسخهٔ پهن را می‌بینند؛ تستِ نسخهٔ باریک خودش
// این مقدار را عوض می‌کند.
//
// شرطِ `typeof window` برای فایل‌هایی است که با `@vitest-environment node` اجرا
// می‌شوند — مثل تستِ پیکربندیِ Vite، که اصلاً DOM لازم ندارد. این فایل برای همهٔ
// تست‌ها اجرا می‌شود، پس نبودِ این گارد یعنی چنین تستی پیش از شروع می‌شکند.
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

// jsdom چیدمان ندارد، پس `scrollIntoView` را هم پیاده نمی‌کند. هر کامپوننتی که
// خودش را داخل دید می‌آورد — گفت‌وگوی همکار پس از هر پیام — بدون این در تست
// می‌ترکد، و شکست چیزی دربارهٔ خودِ رفتار نمی‌گوید.
if (typeof Element !== "undefined" && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
