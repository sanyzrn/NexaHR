/* تم پیش از اولین رنگ‌آمیزی — همگام و بی وابستگی.
 *
 * چرا فایلِ جدا و نه `<script>` درون‌خطیِ index.html: سیاستِ CSPِ استقرارِ nginx
 * `script-src` جدا ندارد، پس از `default-src 'self'` ارث می‌برد — و آن،
 * اسکریپتِ درون‌خطی را ممنوع می‌کند. یعنی همان بلوکی که «پرش» را حل می‌کرد،
 * در محیطِ واقعی *اجرا نمی‌شد*: هر بارگذاری یک لحظه سفید می‌شد و بعد سرمه‌ای،
 * صفحهٔ عمومیِ `/verify/:token` (که کلید تم ندارد) برای همیشه روشن می‌ماند، و
 * هر درخواست یک نقضِ CSP در لاگ می‌گذاشت که نقض‌های واقعی را زیر خودش گم
 * می‌کند. در `npm run dev` هیچ CSPی نیست، پس هیچ‌وقت دیده نمی‌شد.
 *
 * فایلِ هم‌اصل با `default-src 'self'` مجاز است و هیچ هشِ build-time لازم
 * ندارد — هشی که با یک اصلاحِ فاصله بی‌صدا از کار می‌افتد، همان خرابی است با
 * یک لایهٔ اضافه.
 *
 * منطقش در `src/ui/theme.ts` تکرار شده که مرجع است؛ این‌جا فقط همان یک کار.
 */
(function () {
  try {
    var stored = localStorage.getItem("nexahr:theme");
    var dark =
      stored === "dark" ||
      (stored !== "light" &&
        window.matchMedia &&
        window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", dark ? "#0b0e17" : "#b61615");
  } catch {
    document.documentElement.setAttribute("data-theme", "light");
  }
})();
