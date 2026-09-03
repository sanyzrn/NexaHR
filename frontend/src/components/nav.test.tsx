/** «کارنامه من» به داشتنِ پروندهٔ پرسنلی بند است، نه به نقش.
 *
 *  در جدولِ نقش‌محور فقط زیر `employee` بود، یعنی مسئولِ واحد و معاونت و
 *  مدیرعامل و کارمندِ منابع انسانی — که همه‌شان *خودشان هم ارزیابی می‌شوند* —
 *  هیچ راهی به نتیجهٔ خودشان نداشتند، در حالی که مسیرهای `/api/me` سرور از
 *  نقش گذشته بودند: سرور اجازه می‌داد و رابط نمی‌گذاشت.
 */
import { describe, expect, it } from "vitest";
import { navItemsFor } from "./nav";

const noCaps = () => false;
const allModules = () => true;

const paths = (role: string, hasPersonnel: boolean) =>
  navItemsFor(role, noCaps, allModules, hasPersonnel).map((item) => item.to);

describe("navItemsFor", () => {
  it.each(["unit_supervisor", "deputy", "ceo", "hr"])(
    "نقشِ %s با پروندهٔ پرسنلی، لینکِ کارنامهٔ خودش را دارد",
    (role) => {
      expect(paths(role, true)).toContain("/me");
    }
  );

  it.each(["unit_supervisor", "deputy", "ceo", "hr", "support"])(
    "و بی پروندهٔ پرسنلی ندارد (%s)",
    (role) => {
      expect(paths(role, false)).not.toContain("/me");
    }
  );

  it("کارمند همان یک لینک را دارد و تکراری نمی‌شود", () => {
    const employee = paths("employee", true);
    expect(employee.filter((p) => p === "/me")).toHaveLength(1);
  });

  it("لینک‌های نقش سرِ جای خودشان می‌مانند", () => {
    expect(paths("unit_supervisor", true)).toEqual([
      "/supervisor",
      "/my-scoring",
      "/improvement-plans",
      "/me",
    ]);
  });

  it("ماژولِ خاموش لینک را نمی‌سازد", () => {
    const off = (module: string) => module !== "role_analytics";
    const items = navItemsFor("deputy", noCaps, off, true).map((i) => i.to);
    expect(items).not.toContain("/my-scoring");
    expect(items).toContain("/me");
  });
});
