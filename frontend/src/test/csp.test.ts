// @vitest-environment node
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * سیاستِ CSPِ استقرار و `index.html` باید با هم بخوانند.
 *
 * سیاست `script-src` جدا نداشت، پس از `default-src 'self'` ارث می‌برد — و آن
 * اسکریپتِ درون‌خطی را ممنوع می‌کند. `index.html` یک `<script>` درون‌خطی داشت
 * که تم را *پیش از* اولین رنگ‌آمیزی تعیین می‌کرد و در `dist/index.html` هم
 * می‌ماند. یعنی زیر nginx هیچ‌وقت اجرا نمی‌شد:
 *
 *   • هر بارگذاری یک لحظه سفید می‌شد و بعد سرمه‌ای — همان «پرش»ی که کامنتِ
 *     خودِ آن بلوک می‌گفت جلویش را می‌گیرد؛
 *   • صفحهٔ عمومیِ `/verify/:token` که کلید تم ندارد، برای همیشه روشن می‌ماند؛
 *   • و هر درخواست یک نقضِ CSP در لاگ می‌گذاشت، که نقض‌های واقعی را گم می‌کند.
 *
 * در `npm run dev` هیچ CSPی نیست، پس این هرگز دیده نمی‌شد. این تست همان
 * فاصلهٔ «محیط توسعه ≠ محیط استقرار» را می‌بندد.
 */
const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");

const html = read("../../index.html");
const nginx = read("../../nginx/default.conf.template");

describe("CSP و index.html", () => {
  it("سیاست، `script-src` را صریح می‌گوید", () => {
    expect(nginx).toContain("script-src 'self'");
  });

  it("و اسکریپتِ درون‌خطی را مجاز نمی‌کند", () => {
    expect(nginx).not.toContain("'unsafe-inline'; script-src");
    const policy = /Content-Security-Policy "([^"]+)"/.exec(nginx)?.[1] ?? "";
    const scriptSrc = /script-src ([^;]+)/.exec(policy)?.[1] ?? "";
    expect(scriptSrc).not.toContain("unsafe-inline");
  });

  it("`index.html` هیچ `<script>`ِ درون‌خطیِ بدنه‌دار ندارد", () => {
    // `<script src=…>` مجاز است؛ چیزی که ممنوع است بدنهٔ درون‌خطی است.
    const inlineWithBody = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)]
      .map((match) => ({ attrs: match[1] ?? "", body: (match[2] ?? "").trim() }))
      .filter(({ attrs, body }) => !/\bsrc\s*=/.test(attrs) && body.length > 0);
    expect(inlineWithBody.map(({ body }) => body.slice(0, 80))).toEqual([]);
  });

  it("و بوت‌استرپِ تم از یک فایلِ هم‌اصل می‌آید، بی `defer`", () => {
    expect(html).toContain('<script src="/theme-init.js"></script>');
    expect(read("../../public/theme-init.js")).toContain("data-theme");
  });
});
