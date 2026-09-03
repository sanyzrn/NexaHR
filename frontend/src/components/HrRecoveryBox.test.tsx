/** ابزارِ بازتخصیص نباید مرحله‌ای را پیشنهاد بدهد که در این پرونده وجود ندارد.
 *
 * سرور چنین درخواستی را با ۴۰۰ رد می‌کند، پس گزینه‌ای که به آن‌جا می‌رسد فقط
 * وقتِ منابع انسانی را می‌گیرد: مرحله را انتخاب می‌کند، کاربر را انتخاب می‌کند،
 * دلیل می‌نویسد، و بعد خطا می‌گیرد — روی پرونده‌ای که همین حالا «گیر کرده» است
 * و برای نجاتش آمده.
 */
import { describe, expect, it } from "vitest";
import { reassignableStages } from "./HrRecoveryBox";

const chain = (unitSupervisor: number | null, deputy: number | null) => ({
  unit_supervisor_user_id: unitSupervisor,
  deputy_user_id: deputy,
  ceo_user_id: 9,
});

const fields = (e: Parameters<typeof reassignableStages>[0]) =>
  reassignableStages(e).map((o) => o.field);

describe("reassignableStages", () => {
  it("زنجیرهٔ کامل هر سه مرحله را دارد", () => {
    expect(fields(chain(1, 2))).toEqual([
      "unit_supervisor_user_id",
      "deputy_user_id",
      "ceo_user_id",
    ]);
  });

  it("مسیر «مدیر»: «مسئول واحد» پیشنهاد نمی‌شود", () => {
    expect(fields(chain(null, 2))).toEqual(["deputy_user_id", "ceo_user_id"]);
  });

  it("زنجیرهٔ بی‌معاونت: «معاونت» پیشنهاد نمی‌شود", () => {
    // همان شکلی که فرمِ دسترسی صریحاً پیشنهادش می‌دهد («بدون معاونت — مستقیم
    // زیر نظر مدیرعامل») و تا امروز در این فهرست می‌ماند.
    expect(fields(chain(1, null))).toEqual(["unit_supervisor_user_id", "ceo_user_id"]);
  });

  it("مستقیمِ مدیرعامل: فقط مدیرعامل می‌ماند — و فهرست هرگز تهی نمی‌شود", () => {
    // `options[0]` بی‌قید خوانده می‌شود، پس فهرستِ تهی یعنی صفحه می‌شکند.
    // صندلیِ مدیرعامل در دیتابیس NOT NULL است و همیشه یک گزینه باقی می‌گذارد.
    expect(fields(chain(null, null))).toEqual(["ceo_user_id"]);
  });
});
