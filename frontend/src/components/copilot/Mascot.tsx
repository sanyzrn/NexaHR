/** نشانِ همکار: یک موجودِ پشمالوی قرمز که نگاهش دنبالِ نشانگر می‌رود.
 *
 * چرا شخصیت و نه آیکون
 * --------------------
 * دکمهٔ شناور تنها چیزی است که همیشه روی صفحه هست و کاربر باید *خودش* تصمیم
 * بگیرد بازش کند. یک جرقهٔ انتزاعی چیزی دربارهٔ آن‌طرف نمی‌گوید؛ یک صورت
 * می‌گوید «کسی این‌جاست که می‌شود ازش پرسید».
 *
 * چرا قرمزِ برند — و چرا این‌بار درست است
 * ---------------------------------------
 * نسخهٔ قبلیِ این فایل قرمزِ برند را به مرجانی برده بود، با این استدلال که
 * «قرمز روی یک شخصیت، خطا می‌خواند نه سلام». آن استدلال برای یک ربات درست
 * بود و برای این موجود نیست: پشمِ پرحجم، چشمِ درشت و لبخند، *پیش از* رنگ
 * خوانده می‌شوند. وقتی شکل به‌روشنی «موجودِ بامزه» است، قرمز دیگر هشدار
 * نیست — و این‌طوری نشانِ همکار با خودِ برند یکی می‌شود به‌جای اینکه
 * رنگِ همسایه‌اش باشد.
 *
 * چرا SVGِ درون‌خطی و نه همان تصویرِ PNG
 * ---------------------------------------
 * چشم باید *حرکت* کند. با تصویر، تنها راهش لایه‌چینیِ چند PNG روی هم است —
 * سه تا چهار درخواستِ شبکه برای یک دکمه، بی امکانِ هم‌رنگ‌شدن با تم، و ماتی
 * در صفحه‌های پرتراکم. این‌جا کلِ شخصیت ~۴ کیلوبایت مارک‌آپ است که با
 * خودِ صفحه می‌آید.
 *
 * حرکت‌ها
 * -------
 * چهارتا، و هر کدام کارِ متفاوتی می‌کند:
 *   ۱. **نفس** (CSS، همیشه) — «زنده است».
 *   ۲. **پلک** (CSS، نامنظم) — «حواسش هست».
 *   ۳. **نگاه** (JS، فقط با `track`) — «شما را می‌بیند». تنها حرکتی که
 *      *پاسخ* است و نه چرخه.
 *   ۴. **پرش و خندهٔ باز** (CSS، روی hover/focus) — «بپرس».
 *
 * چرخه‌ها CSS خالص‌اند تا در هر رندرِ React از نو ساخته نشوند، و قاعدهٔ
 * سراسریِ `prefers-reduced-motion` در `index.css` همه‌شان را با هم خاموش
 * می‌کند. نگاه هم همان‌جا خودش را خاموش می‌کند — پایین‌تر، صریح.
 */
import { useEffect, useRef } from "react";

/** پالتِ شخصیت. یک جا، تا پشم و سایه و پا هیچ‌وقت از هم جدا نیفتند. */
const FUR = "#e01b17";
const FUR_DARK = "#a81210";
const FUR_LIGHT = "#f75a52";
const IRIS = "#4a2a1c";
const IRIS_DEEP = "#2b1710";
const MOUTH = "#5c1210";
const TONGUE = "#f4626b";

/** خطِ بیرونیِ پشم — نقطه‌به‌نقطه، نه یک دایره با فیلترِ noise.
 *
 * فیلترهای SVG (`feTurbulence` و رفقا) روی هر فریمِ انیمیشن دوباره رستر
 * می‌شوند؛ روی یک دکمهٔ همیشه‌در‌صحنه که نفس هم می‌کشد، همان چیزی است که
 * لپ‌تاپ را داغ می‌کند. این دو مسیر یک‌بار حساب شده‌اند و از آن به بعد فقط
 * یک `<path>` ساده‌اند.
 *
 * قاعدهٔ شکل، از خودِ مرجع: **دندانه‌ها باید پرشمار و کوتاه باشند.** چند
 * دندانهٔ بلند «ستاره» یا «ویروس» می‌سازد، نه پُرز. این‌جا ۴۶ و ۵۴ دندانه
 * با بلندیِ ۱٫۵ تا ۵٫۵ واحد روی شعاعِ ~۳۲ نشسته‌اند: از دور یک گویِ گرد
 * دیده می‌شود و از نزدیک، کُرک. */
const BODY_FUR =
  "M82.1 52 L86 54.4 L82.1 56.4 L86 59.4 L81.1 60.6 L84.6 64.2 L78.8 64.4 L81.2 68 " +
  "L77.8 68.7 L79.2 72.4 L75.2 72.3 L74.8 74.9 L71.8 75.1 L71.7 78.4 L68.5 77.9 " +
  "L68.4 82 L64.5 79.6 L63.6 83.1 L60.6 81.6 L59.9 87 L56.6 83.3 L54.6 85.4 L52.2 84 " +
  "L50 85.6 L47.8 83.7 L45.4 85.3 L43.6 82.4 L40.1 86.8 L39.4 81.5 L36.4 83.1 " +
  "L35 80.6 L31 82.9 L31.7 77.7 L26.7 80.3 L28.1 75.2 L23.8 76.2 L25.5 71.8 L19.9 73 " +
  "L22.5 68.6 L17.3 68.8 L20.2 64.8 L17.4 63.5 L19.3 60.5 L16.6 58.9 L18.7 56.3 " +
  "L16.4 54.3 L18.2 52 L14.5 49.6 L18.9 47.8 L14.9 44.8 L19.4 43.5 L17.4 40.5 " +
  "L20.3 39.2 L18.8 36 L22.8 35.7 L21.3 31.9 L25 31.9 L25.4 29.2 L27.8 28.4 " +
  "L28.8 26.2 L31.4 25.9 L31.1 21.2 L35.5 24.4 L35.6 19.1 L39.3 22.3 L40.4 18.1 " +
  "L43.6 21.6 L45.4 19 L47.8 20.8 L50 15.5 L52.2 20.8 L54.9 16.5 L56.6 20.5 " +
  "L59.9 16.9 L60.7 22.3 L63.8 20.5 L64.7 23.8 L68.8 21.4 L68.2 26.5 L72.8 24.3 " +
  "L72.1 28.6 L76.7 27.3 L74.4 32.4 L80.1 31 L76.9 35.8 L80.8 36.2 L79.5 39.3 " +
  "L84.6 39.8 L80.6 43.5 L86 44.6 L81.8 47.7 L84.5 49.7 Z";

const BACK_FUR =
  "M83.5 53 L88 55.4 L83.5 56.9 L85.2 59.2 L82.4 60.6 L85.5 63.7 L80.9 64.1 " +
  "L81.6 66.6 L78.5 67.2 L80.5 70.7 L77.1 70.8 L77.5 73.7 L74.3 73.6 L74.8 76.9 " +
  "L71.8 76.5 L73.1 81.5 L68.3 78.4 L69.4 84.1 L64.7 79.9 L65.1 85.4 L61.6 82.3 " +
  "L60.1 84.4 L57.7 83.2 L56.4 86.9 L53.9 84.1 L52 86.1 L49.9 83.9 L47.7 88.7 " +
  "L46 83.8 L43.6 86 L42.3 82.5 L38.8 87.4 L38.5 81.8 L34.5 86.1 L35.1 79.9 " +
  "L30.8 83.4 L31.3 78.7 L26.8 81.4 L28.8 75.7 L24.9 77 L26 73.1 L20.8 74.9 " +
  "L23.2 70.5 L17.5 71.9 L21.1 67.3 L15.9 67.7 L18.8 64.1 L16.2 63 L17.8 60.4 " +
  "L12.2 59.7 L17 56.6 L13.8 55.1 L16.8 52.8 L11.9 50.9 L16.9 49.1 L12.8 46.7 " +
  "L17 45.2 L13.8 42.5 L18.4 41.7 L14.7 38.3 L18.8 37.7 L17.6 35 L21.2 34.6 " +
  "L17.8 30.1 L23.1 31.3 L22.4 28.2 L26.1 28.8 L24 23.9 L28.6 25.9 L28 22 " +
  "L31.8 23.8 L31.3 19.1 L34.9 21.4 L35.7 18.4 L38.8 20.6 L38.9 14.4 L42.2 18.6 " +
  "L44 17.1 L46.2 18.3 L47.9 14.1 L50.1 18.3 L52.3 13.9 L54 17.9 L56.6 15 " +
  "L57.8 19.2 L60.3 17.4 L61.4 20.4 L64.2 19 L64.9 22.1 L68 20.6 L68.7 23.3 " +
  "L72.2 21.8 L71.8 25.6 L76.6 23.5 L74.7 28.3 L77 28.9 L77.3 31.1 L79.6 32 " +
  "L79.3 34.5 L84.3 34.2 L81 38 L84.4 38.8 L81.6 41.8 L84.4 43.1 L83.2 45.3 " +
  "L85.7 47 L83.5 49.1 L86.1 51.1 Z";

/** بیشترین جابه‌جاییِ مردمک، در واحدِ viewBox.
 *
 * ۳٫۴ از روی خودِ شکل آمده و نه از سلیقه: کاسهٔ چشم ۷ واحد شعاع دارد و
 * سفیدی ۱۲٫۵؛ بیشتر از این، مردمک به لبهٔ سفیدی می‌چسبد و نگاه از
 * «دنبال‌کردن» به «چپ‌شدن» تبدیل می‌شود. */
const GAZE = 3.4;

/** فاصله‌ای که تا آن، نگاه به حداکثر می‌رسد (پیکسلِ صفحه). نزدیک‌تر از این،
 *  نگاه نرم‌تر می‌شود — همان کاری که چشمِ واقعی با چیزی که بیخِ گوشش است
 *  می‌کند. */
const GAZE_REACH = 260;

/** چشم را دنبالِ نشانگر می‌بَرد، *بی* رندرِ دوبارهٔ React.
 *
 * `setState` در هر `pointermove` یعنی یک رندرِ کاملِ درخت در هر فریم، برای
 * تغییرِ دو عدد در یک `transform`. این‌جا مقدار مستقیم روی گره نوشته
 * می‌شود: React اصلاً خبردار نمی‌شود، و حرکت در `requestAnimationFrame`
 * به فریمِ نمایشگر گره می‌خورد نه به نرخِ رویدادِ ماوس (که روی موس‌های
 * ۱۰۰۰ هرتزی چند برابرِ فریم است).
 */
function useGaze(
  host: React.RefObject<SVGSVGElement | null>,
  pupils: React.RefObject<SVGGElement | null>,
  face: React.RefObject<SVGGElement | null>,
  active: boolean,
) {
  useEffect(() => {
    if (!active) return;
    // همان کاربری که «حرکت کمتر» را روشن کرده، دقیقاً از این جنسِ حرکت
    // اذیت می‌شود. قاعدهٔ CSS چرخه‌ها را می‌گیرد و این یکی را نمی‌گیرد،
    // چون JS است — پس این‌جا صریح پرسیده می‌شود.
    const calm = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (calm?.matches) return;

    let frame = 0;
    let pending: { x: number; y: number } | null = null;

    const apply = () => {
      frame = 0;
      const point = pending;
      const svg = host.current;
      if (!point || !svg) return;
      const box = svg.getBoundingClientRect();
      if (!box.width) return;

      const dx = point.x - (box.left + box.width / 2);
      const dy = point.y - (box.top + box.height * 0.42); // مرکزِ چشم‌ها، نه مرکزِ شکل
      const distance = Math.hypot(dx, dy) || 1;
      const pull = Math.min(1, distance / GAZE_REACH);
      const x = (dx / distance) * pull;
      const y = (dy / distance) * pull;

      pupils.current?.setAttribute(
        "transform",
        `translate(${(x * GAZE).toFixed(2)} ${(y * GAZE * 0.8).toFixed(2)})`,
      );
      // سر هم کمی همراه می‌شود. بی این، چشم‌ها در یک صورتِ بی‌حرکت
      // می‌لغزند و نتیجه‌اش عروسکی است، نه زنده.
      face.current?.setAttribute(
        "transform",
        `translate(${(x * 1.2).toFixed(2)} ${(y * 0.9).toFixed(2)})`,
      );
    };

    const onMove = (event: PointerEvent) => {
      pending = { x: event.clientX, y: event.clientY };
      if (!frame) frame = requestAnimationFrame(apply);
    };

    // صفحه که اسکرول می‌شود، نشانگر تکان نخورده ولی *دکمه* جابه‌جا شده.
    // بی این، نگاه تا حرکتِ بعدیِ ماوس به جای اشتباه خیره می‌ماند.
    const onScroll = () => {
      if (pending && !frame) frame = requestAnimationFrame(apply);
    };

    window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("scroll", onScroll, { passive: true, capture: true });
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("scroll", onScroll, true);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [host, pupils, face, active]);
}

/** کلِ شخصیت — برای دکمهٔ شناور و صفحهٔ خوشامد.
 *
 *  `track` عمداً پیش‌فرضِ خاموش دارد: چند نسخه از این شخصیت هم‌زمان روی
 *  صفحه‌اند (آواتارِ پیام‌ها)، و اگر همه‌شان به نشانگر گوش بدهند، یک حرکتِ
 *  ماوس ده‌ها محاسبهٔ مستقل می‌شود. فقط دکمهٔ شناور نگاه می‌کند. */
export function Mascot({
  className = "",
  idle = true,
  track = false,
}: {
  className?: string;
  idle?: boolean;
  track?: boolean;
}) {
  const svg = useRef<SVGSVGElement>(null);
  const pupils = useRef<SVGGElement>(null);
  const face = useRef<SVGGElement>(null);
  useGaze(svg, pupils, face, track);

  return (
    <svg
      ref={svg}
      viewBox="0 0 100 100"
      className={`${className} ${idle ? "mascot" : ""}`}
      fill="none"
      aria-hidden
    >
      <defs>
        {/* نورِ بالا-چپ. بی این، حجمِ کُرویِ پشم تخت می‌شود. */}
        <radialGradient id="mascot-fur" cx="34%" cy="28%" r="78%">
          <stop offset="0%" stopColor={FUR_LIGHT} />
          <stop offset="58%" stopColor={FUR} />
          <stop offset="100%" stopColor="#c2140f" />
        </radialGradient>
        <radialGradient id="mascot-iris" cx="38%" cy="32%" r="72%">
          <stop offset="0%" stopColor="#6b3d28" />
          <stop offset="62%" stopColor={IRIS} />
          <stop offset="100%" stopColor={IRIS_DEEP} />
        </radialGradient>
      </defs>

      <g className="mascot-body">
        {/* پاها *زیر* بدن و پیش از آن کشیده می‌شوند تا خطِ پشم رویشان
            بیفتد؛ برعکسش، دو لکه به تنه چسبیده به‌نظر می‌رسد. */}
        {/* پاها تا نیمه زیرِ تنه می‌روند. جدا که بایستند، «کفش» خوانده
            می‌شوند نه پا — همان چیزی که مرجع هم با فرو بردنشان در پشم حل
            کرده. */}
        <g className="mascot-feet">
          <ellipse cx="37" cy="85.5" rx="8.6" ry="5.4" fill={FUR_DARK} />
          <ellipse cx="63" cy="85.5" rx="8.6" ry="5.4" fill={FUR_DARK} />
        </g>

        {/* لایهٔ عمق: همان شکل، کمی بزرگ‌تر و تیره‌تر، با زاویهٔ متفاوت.
            دو لایهٔ دندانه‌دار روی هم، چیزی می‌سازد که مغز «پُرز» می‌خواند. */}
        {/* `strokeLinejoin="round"` روی *همان* مسیر، نوکِ تیزِ هر دندانه را
            گرد می‌کند. بی آن، خطِ بیرونی «خارپشت» خوانده می‌شود نه «کُرک» —
            و این تفاوت با یک صفت حل می‌شود، نه با دو برابر کردنِ نقطه‌ها. */}
        <path
          d={BACK_FUR}
          fill={FUR_DARK}
          stroke={FUR_DARK}
          strokeWidth="2.2"
          strokeLinejoin="round"
          opacity="0.5"
        />

        {/* کاکل. تنها عضوی که جهت دارد، پس تنها جایی که «باد» دیده می‌شود. */}
        <g className="mascot-tuft">
          <path
            d="M49 24 C47 14 51 7 60 2 C57 9 57.5 14 60 18 C56.5 16.5 53.5 18 52 22 Z"
            fill={FUR}
          />
          <path
            d="M55 25 C55.5 17 59 11 66 7 C63 13 63 17 64.5 20.5 C61 19.5 58 21 56.5 25 Z"
            fill={FUR_LIGHT}
            opacity="0.85"
          />
        </g>

        <path
          d={BODY_FUR}
          fill="url(#mascot-fur)"
          stroke="url(#mascot-fur)"
          strokeWidth="2.6"
          strokeLinejoin="round"
        />

        {/* تارهای پشمِ شکم: سه قوسِ کم‌رنگ. جهتشان رو به پایین است چون
            کلِ حجم از بالا نور می‌گیرد و پشم به سمتِ پا می‌خوابد. */}
        <g stroke={FUR_DARK} strokeWidth="1.2" strokeLinecap="round" opacity="0.16" fill="none">
          <path d="M28 62 C31 70 34 76 38 81" />
          <path d="M36 66 C38 73 40 78 43 82" />
          <path d="M45 68 C46 74 46.5 79 47 83" />
          <path d="M55 68 C54 74 53.5 79 53 83" />
          <path d="M64 66 C62 73 60 78 57 82" />
          <path d="M72 62 C69 70 66 76 62 81" />
        </g>

        {/* صورت: چشم‌ها و دهان با هم جابه‌جا می‌شوند، چون با هم یک واحدند. */}
        <g ref={face} className="mascot-face">
          <g className="mascot-eyes">
            {/* سفیدیِ چشم با یک هالهٔ تیرهٔ نازک: بی آن، سفیدِ خالص روی
                قرمزِ اشباع می‌لرزد (هم‌جواریِ رنگِ مکمل). */}
            <ellipse cx="38.6" cy="50" rx="11.2" ry="12.2" fill="#ffffff" />
            <ellipse cx="61.4" cy="50" rx="11.2" ry="12.2" fill="#ffffff" />
            <ellipse
              cx="38.6"
              cy="50"
              rx="11.2"
              ry="12.2"
              fill="none"
              stroke={FUR_DARK}
              strokeWidth="0.7"
              opacity="0.3"
            />
            <ellipse
              cx="61.4"
              cy="50"
              rx="11.2"
              ry="12.2"
              fill="none"
              stroke={FUR_DARK}
              strokeWidth="0.7"
              opacity="0.3"
            />

            {/* مردمک‌ها — تنها گروهی که JS دست می‌زند. */}
            <g ref={pupils} className="mascot-pupils">
              <circle cx="38.6" cy="51" r="6.8" fill="url(#mascot-iris)" />
              <circle cx="61.4" cy="51" r="6.8" fill="url(#mascot-iris)" />
              {/* برقِ چشم. همیشه بالا-چپ می‌ماند چون منبعِ نور ثابت است —
                  با مردمک می‌چرخد ولی جای خودش را در آن نگه می‌دارد. */}
              <circle cx="36.2" cy="48" r="2.3" fill="#ffffff" />
              <circle cx="59" cy="48" r="2.3" fill="#ffffff" />
              <circle cx="41.2" cy="54" r="1" fill="#ffffff" opacity="0.5" />
              <circle cx="64" cy="54" r="1" fill="#ffffff" opacity="0.5" />
            </g>
          </g>

          {/* دو دهان، و CSS انتخاب می‌کند کدام دیده شود: لبخندِ بسته در
              حالتِ عادی، خندهٔ باز وقتی نشانگر روی دکمه است. همان تفاوتِ
              «این‌جا هستم» و «بپرس». */}
          <path
            className="mascot-smile"
            d="M44.5 67 C46.8 70.6 53.2 70.6 55.5 67"
            stroke={MOUTH}
            strokeWidth="2.4"
            strokeLinecap="round"
            fill="none"
          />
          <g className="mascot-grin">
            <path d="M43.5 65.5 C45.8 73 54.2 73 56.5 65.5 Z" fill={MOUTH} />
            <path d="M47 71 C48.2 74 51.8 74 53 71 Z" fill={TONGUE} />
          </g>
        </g>
      </g>
    </svg>
  );
}

/** فقط سر — برای جاهایی که شخصیتِ کامل به چند پیکسلِ درهم تبدیل می‌شود.
 *
 *  پا و کاکل حذف شده‌اند و چشم‌ها نسبت به سر درشت‌ترند: همان کاری که
 *  آیکون‌های سیستمی در اندازه‌های کوچک می‌کنند — جزئیات کم، نشانه پررنگ. */
export function MascotFace({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 100 100" className={`${className} mascot`} fill="none" aria-hidden>
      <defs>
        <radialGradient id="mascot-face-fur" cx="34%" cy="28%" r="78%">
          <stop offset="0%" stopColor={FUR_LIGHT} />
          <stop offset="58%" stopColor={FUR} />
          <stop offset="100%" stopColor="#c2140f" />
        </radialGradient>
      </defs>
      <path
        d={BACK_FUR}
        fill={FUR_DARK}
        stroke={FUR_DARK}
        strokeWidth="2.2"
        strokeLinejoin="round"
        opacity="0.5"
      />
      <path
        d={BODY_FUR}
        fill="url(#mascot-face-fur)"
        stroke="url(#mascot-face-fur)"
        strokeWidth="2.6"
        strokeLinejoin="round"
      />
      <g className="mascot-eyes">
        <ellipse cx="37.5" cy="49" rx="12.6" ry="13.6" fill="#ffffff" />
        <ellipse cx="62.5" cy="49" rx="12.6" ry="13.6" fill="#ffffff" />
        <circle cx="38" cy="50.5" r="7.8" fill={IRIS} />
        <circle cx="63" cy="50.5" r="7.8" fill={IRIS} />
        <circle cx="35.2" cy="47.2" r="2.6" fill="#ffffff" />
        <circle cx="60.2" cy="47.2" r="2.6" fill="#ffffff" />
      </g>
      <path
        d="M44 67.5 C46.8 71.5 53.2 71.5 56 67.5"
        stroke={MOUTH}
        strokeWidth="2.8"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}
