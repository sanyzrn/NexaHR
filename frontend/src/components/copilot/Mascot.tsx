/** نشانِ همکار: یک شخصیتِ کوچکِ متحرک، به‌جای آیکونِ جرقه.
 *
 * چرا شخصیت و نه آیکون
 * --------------------
 * دکمهٔ شناور تنها چیزی است که همیشه روی صفحه هست و کاربر باید *خودش* تصمیم
 * بگیرد بازش کند. یک جرقهٔ انتزاعی چیزی دربارهٔ آن‌طرف نمی‌گوید؛ یک صورت
 * می‌گوید «کسی این‌جاست که می‌شود ازش پرسید». همین تفاوت است بین دکمه‌ای که
 * دیده می‌شود و دکمه‌ای که کلیک می‌شود.
 *
 * SVG درون‌خطی و نه فایلِ تصویر: انیمیشن باید بخشی از خودِ شکل باشد (پلک،
 * نفس، آنتن)، رنگ‌ها از پالت برند بیایند، و در هیچ اندازه‌ای مات نشود.
 *
 * رنگ
 * ---
 * قرمزِ برند (#db1a18) روی یک شخصیت، «خطا» می‌خواند نه «سلام». پس همان رنگ
 * به سمتِ مرجانی/گِلی برده شده — گرم و هم‌خانواده با برند، ولی بی‌هشدار. صورت
 * زغالی است با چشم‌های نعنایی، تا در هر دو تم روشن و تیره خوانا بماند.
 *
 * دو اندازه، دو جزئیات
 * --------------------
 * `Mascot` کلِ شخصیت است و برای ۴۰ پیکسل به بالا ساخته شده. زیر آن، دست و پا
 * به چند پیکسلِ درهم تبدیل می‌شوند، پس `MascotFace` فقط سر را می‌کشد — همان
 * تصمیمی که آیکون‌های سیستمی در اندازه‌های کوچک می‌گیرند.
 *
 * حرکت
 * ----
 * انیمیشن‌ها CSS خالص‌اند (نه Framer Motion) چون بی‌وقفه اجرا می‌شوند و نباید
 * در هر رندرِ React دوباره ساخته شوند. قاعدهٔ سراسریِ `prefers-reduced-motion`
 * در `index.css` همه‌شان را با هم خاموش می‌کند.
 */

/** پالتِ شخصیت. یک جا، تا سر و تن و سایه هیچ‌وقت از هم جدا نیفتند. */
const SKIN = "#e0705a";
const SKIN_DARK = "#c25844";
const SKIN_LIGHT = "#ef8f79";
const PANEL = "#2a2d31";
const EYE = "#5ee6c8";

/** کلِ شخصیت — برای دکمهٔ شناور و صفحهٔ خوشامد. */
export function Mascot({ className = "", idle = true }: { className?: string; idle?: boolean }) {
  return (
    <svg
      viewBox="0 0 64 64"
      className={`${className} ${idle ? "mascot" : ""}`}
      fill="none"
      aria-hidden
    >
      {/* آنتن. نبضش تنها نشانهٔ «روشن است» روی خودِ شخصیت است.
          میله باید *دیده* شود: با ساقهٔ کوتاه، گویِ نعنایی بالای سر شناور
          می‌ماند و به شخصیت نمی‌چسبد. */}
      <g className="mascot-antenna">
        <rect x="30.8" y="1.5" width="2.4" height="8" rx="1.2" fill={SKIN_DARK} />
        <circle cx="32" cy="2.4" r="2.6" fill={EYE} className="mascot-spark" />
      </g>

      <g className="mascot-body">
        {/* دست‌ها پشتِ تنه می‌نشینند تا لبهٔ تنه نشکند، و به آن *می‌چسبند*:
            با فاصله، دو میلهٔ جدا کنارِ شخصیت به‌نظر می‌رسند نه دست. */}
        <rect x="10.5" y="34" width="6" height="13" rx="3" fill={SKIN_DARK} />
        <rect
          x="47.5"
          y="34"
          width="6"
          height="13"
          rx="3"
          fill={SKIN_DARK}
          className="mascot-arm"
        />

        {/* پاها */}
        <rect x="20" y="52" width="9" height="8" rx="3.5" fill={SKIN_DARK} />
        <rect x="35" y="52" width="9" height="8" rx="3.5" fill={SKIN_DARK} />

        {/* تنه، با نشانهٔ خط فرمان: این همکار با داده کار می‌کند، نه با جادو. */}
        <rect x="16" y="32" width="32" height="23" rx="9" fill={SKIN} />
        <rect x="21" y="38" width="22" height="11" rx="4" fill={SKIN_DARK} opacity="0.45" />
        <path
          d="M25.5 41.5l2.6 2.1-2.6 2.1M31.5 46h6"
          stroke="#ffe9e2"
          strokeWidth="1.9"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* سر: ابری/گرد، نه یک مربع. گوشهٔ تیز روی صورت، «ماشین» می‌خواند. */}
        <g className="mascot-head">
          <path
            d="M32 5c7.2 0 12 2.6 15.2 6.3C51.6 12.1 55 15.6 55 20.4c0 3.1-1.2 5.6-3 7.3v2.6c0 3.4-2.8 6.2-6.2 6.2H18.2C14.8 36.5 12 33.7 12 30.3v-2.6c-1.8-1.7-3-4.2-3-7.3 0-4.8 3.4-8.3 7.8-9.1C20 7.6 24.8 5 32 5z"
            fill={SKIN}
          />
          {/* برجستگیِ نور از بالا-چپ: بدونش سر یک لکهٔ تخت است. */}
          <path
            d="M32 5c-7.2 0-12 2.6-15.2 6.3C12.4 12.1 9 15.6 9 20.4c0 1.6.3 3 .9 4.3C11.4 15 20.6 8.8 32 8.8V5z"
            fill={SKIN_LIGHT}
            opacity="0.75"
          />

          {/* صورت */}
          <rect x="17" y="13" width="30" height="19" rx="7" fill={PANEL} />
          <g className="mascot-eyes">
            <path
              d="M23 22.5c1.2-2.4 4.4-2.4 5.6 0"
              stroke={EYE}
              strokeWidth="2.6"
              strokeLinecap="round"
            />
            <path
              d="M35.4 22.5c1.2-2.4 4.4-2.4 5.6 0"
              stroke={EYE}
              strokeWidth="2.6"
              strokeLinecap="round"
            />
          </g>
          {/* لُپ‌ها. کلِ «گوگولی» بودن به همین دو نقطه است. */}
          <circle cx="20.5" cy="27" r="2" fill={SKIN_LIGHT} opacity="0.55" />
          <circle cx="43.5" cy="27" r="2" fill={SKIN_LIGHT} opacity="0.55" />
        </g>
      </g>
    </svg>
  );
}

/** فقط سر — برای جاهایی که شخصیتِ کامل به چند پیکسلِ درهم تبدیل می‌شود. */
export function MascotFace({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 46 34" className={`${className} mascot`} fill="none" aria-hidden>
      <path
        d="M23 1c6.4 0 10.7 2.3 13.5 5.6C40.4 7.3 43.4 10.4 43.4 14.7c0 2.7-1 5-2.7 6.5v2.3c0 3-2.4 5.5-5.5 5.5H10.8c-3 0-5.5-2.4-5.5-5.5v-2.3c-1.6-1.5-2.7-3.8-2.7-6.5 0-4.3 3-7.4 6.9-8.1C12.3 3.3 16.6 1 23 1z"
        fill={SKIN}
      />
      <rect x="9" y="8" width="28" height="17" rx="6.5" fill={PANEL} />
      <g className="mascot-eyes">
        <path d="M14.6 16.4c1.1-2.2 4-2.2 5.1 0" stroke={EYE} strokeWidth="2.4" strokeLinecap="round" />
        <path d="M26.3 16.4c1.1-2.2 4-2.2 5.1 0" stroke={EYE} strokeWidth="2.4" strokeLinecap="round" />
      </g>
      <circle cx="12" cy="21" r="1.7" fill={SKIN_LIGHT} opacity="0.55" />
      <circle cx="34" cy="21" r="1.7" fill={SKIN_LIGHT} opacity="0.55" />
    </svg>
  );
}
