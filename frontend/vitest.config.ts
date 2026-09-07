import { readFileSync } from "node:fs";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// همان `define` که `vite.config.ts` دارد.
//
// vitest پیکربندی خودش را می‌خواند، پس بدون این خط `__APP_VERSION__` در تست
// تعریف‌نشده می‌ماند و هر فایلی که `appInfo` را وارد کند اصلاً بارگذاری نمی‌شود —
// و چون آن فایل «۰ تست» گزارش می‌شود، در شمارشِ کلی به‌چشم نمی‌آید.
const pkg = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8"));

export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // ساعتِ تست، ساعتِ سازمان است.
    //
    // بک‌اند `ORG_TIMEZONE` دارد (پیش‌فرض `Asia/Tehran`) و کلِ محصول برای یک
    // سازمانِ ایرانی است. بی این، تستِ تاریخ به منطقهٔ زمانیِ ماشینی بند است
    // که اجرایش می‌کند: روی CI (UTC) یک جواب و روی لپ‌تاپِ توسعه‌دهنده جوابِ
    // دیگر — و اشکالی مثل «روزِ UTC به‌جای روزِ محلی» فقط در یکی از آن دو
    // دیده می‌شود. همان اشکالی که در فیلترهای تاریخِ گزارش‌ها بود و هیچ
    // تستی نمی‌گرفتش.
    //
    // این‌جا و نه در اسکریپتِ npm: `TZ=… vitest` روی ویندوز کار نمی‌کند و
    // راه‌اندازِ همین مخزن ویندوزی است.
    env: { TZ: "Asia/Tehran" },
  },
});
