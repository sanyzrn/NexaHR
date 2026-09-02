/** زنجیرهٔ چهارمرحله‌ای پرونده، به‌شکل نوار.
 *
 * نام مرحلهٔ فعلی همه‌جای سامانه نوشته می‌شد — «بررسی معاونت»، «تأیید نهایی» —
 * ولی هیچ‌کس نمی‌دید *کجای کل مسیر* است. کارمند نمی‌دانست دو مرحله مانده یا سه؛
 * ارزیاب نمی‌دانست پرونده‌اش چقدر جلو رفته.
 *
 * شفافیتِ فرایند یکی از وعده‌های خودِ محصول است و داده‌اش هم از قبل وجود داشت.
 * فقط هیچ‌جا نشان داده نمی‌شد.
 */
import { STAGE_BY_STATUS, type EvaluationStage, type EvaluationStatus } from "../types";

const CHAIN: { key: EvaluationStage; short: string }[] = [
  { key: "supervisor_scoring", short: "امتیازدهی" },
  { key: "hr_review", short: "منابع انسانی" },
  { key: "deputy_review", short: "معاونت" },
  { key: "ceo_final", short: "تأیید نهایی" },
];

export function WorkflowStepper({
  status,
  returned = false,
  hrSkipped = false,
  className = "",
}: {
  status: EvaluationStatus;
  /** برگشت‌خورده: مرحلهٔ فعلی کهربایی می‌شود، نه قرمزِ «در جریانِ عادی». */
  returned?: boolean;
  /** پروندهٔ کارمندِ منابع انسانی: مرحلهٔ منابع انسانی *وجود ندارد*.
   *
   * بی این، نوار آن مرحله را سبز نشان می‌داد — یعنی «انجام شد» برای کاری که
   * هیچ‌کس انجامش نداده. نوارِ مراحل تنها جایی است که کاربر مسیرِ پرونده را
   * می‌بیند؛ دروغِ آن، دروغِ کلِ سند است. */
  hrSkipped?: boolean;
  className?: string;
}) {
  // پروندهٔ لغوشده در هیچ مرحله‌ای نیست؛ نوارِ نیمه‌پر برایش گمراه‌کننده است.
  const stage = STAGE_BY_STATUS[status];
  if (!stage) return null;

  // پروندهٔ نهایی‌شده از آخرین مرحله هم گذشته است، پس هر چهار قدم کامل‌اند.
  const currentIndex =
    status === "finalized" ? CHAIN.length : CHAIN.findIndex((s) => s.key === stage);

  return (
    <ol
      className={`flex items-center gap-1.5 ${className}`}
      aria-label="جایگاه پرونده در زنجیرهٔ تأیید"
    >
      {CHAIN.map((step, i) => {
        const skipped = hrSkipped && step.key === "hr_review";
        const done = !skipped && i < currentIndex;
        const current = i === currentIndex;
        return (
          <li key={step.key} className="flex min-w-0 flex-1 flex-col gap-1">
            <span
              aria-hidden
              /* مرحلهٔ رد‌شده نه سبز است و نه خاکستریِ «هنوز نرسیده»: خط‌چین
                 می‌گوید این‌جا مرحله‌ای هست که طی نشد، و طی هم نخواهد شد. */
              className={`h-1.5 rounded-full transition-colors ${
                skipped
                  ? "border border-dashed border-gray-300"
                  : done
                    ? "bg-green-500"
                    : current
                      ? returned
                        ? "bg-amber-500"
                        : "bg-pulse-600"
                      : "bg-gray-200"
              }`}
            />
            <span
              className={`truncate text-[11px] ${
                skipped
                  ? "text-gray-400 line-through"
                  : current
                    ? "font-bold text-gray-900"
                    : done
                      ? "text-gray-500"
                      : "text-gray-400"
              }`}
              title={skipped ? "این پرونده مرحلهٔ منابع انسانی ندارد" : undefined}
            >
              {step.short}
            </span>
            {skipped && <span className="sr-only">— بدون این مرحله</span>}
            {current && !skipped && <span className="sr-only">— مرحلهٔ فعلی</span>}
          </li>
        );
      })}
    </ol>
  );
}
