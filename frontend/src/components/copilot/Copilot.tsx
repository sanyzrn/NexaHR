import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { apiClient } from "../../api/client";
import type { AiStatus } from "../../types";
import { CopilotPanel } from "./CopilotPanel";
import { useFocusTrap } from "../../ui/focusTrap";
import { Mascot } from "./Mascot";

/**
 * ورودیِ همکار: دکمهٔ شناور + پنجرهٔ کنارِ صفحه.
 *
 * «در دسترس هست یا نه» یک *حالت* است، نه یک استثنا: پیش از ساختنِ دکمه
 * پرسیده می‌شود؛ دکمه‌ای که تنها پاسخش «در دسترس نیست» باشد، از نبودنش بدتر است.
 * حالتِ «فعال ولی بدون دسترسیِ تغییر» هم دکمه دارد — فقط شکلش فرق می‌کند.
 */
/** وضعیتِ همکار — یک کوئری، دو مصرف‌کننده.
 *
 *  `Layout` هم باید بداند همکار دیده می‌شود یا نه (تا برای دکمه‌اش در
 *  پاصفحه جا باز کند). کلیدِ کوئری یکی است، پس React Query همان پاسخ را
 *  می‌دهد و درخواستِ دومی به سرور نمی‌رود. */
export function useAiStatus() {
  return useQuery({
    queryKey: ["ai", "status"],
    queryFn: async () => (await apiClient.get<AiStatus>("/ai/status")).data,
    // فعال‌سازی دستیار از پنل مدیریت یا تب دیگری باید بدون تأخیر دیده شود.
    staleTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: true,
  });
}

export function Copilot() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const panelRef = useRef<HTMLElement>(null);

  // کشو یک لایهٔ روی‌هم است با پردهٔ کلیک‌گیر روی تمامِ صفحه، پس باید مثل
  // `Modal` رفتار کند: `aria-modal` تا صفحه‌خوان بقیهٔ صفحه را «پشتِ پرده»
  // اعلام کند، و قفلِ فوکوس تا کاربرِ کیبورد با Tab از کشویِ *باز* به
  // فهرستی که نمی‌بیند نرود (WCAG 2.1، بند ۲٫۴٫۳). پیش‌تر فقط
  // `role="dialog"` داشت — یعنی نقش را ادعا می‌کرد و رفتارش را نداشت.
  //
  // `lockScroll` خاموش است: کشو خودش اسکرولِ داخلی دارد و صفحهٔ زیرش هم
  // کار می‌کند؛ همکار برای *همراهیِ* همان صفحه باز می‌شود، نه جای آن.
  // Escape از همین‌جا می‌بندد، پس `CopilotPanel` نسخهٔ خودش را ندارد.
  useFocusTrap(panelRef, {
    active: open,
    onEscape: () => setOpen(false),
    lockScroll: false,
  });

  const { data: status } = useAiStatus();

  if (!status?.available) return null;

  return (
    <>
      {/* شخصیت خودش شکلِ دکمه است و دیگر داخل یک دایرهٔ رنگی نمی‌نشیند: قابِ
          گرد، سر و دست و پا را می‌بُرید و چیزی جز یک لکه باقی نمی‌گذاشت. جای
          دایره، یک هالهٔ نرم زیر پا نشسته تا شخصیت روی هر زمینه‌ای جدا شود. */}
      <motion.button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="همکار هوشمند"
        title="همکار هوشمند"
        initial={{ scale: 0.8, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ delay: 0.3, duration: 0.3 }}
        /* کنارِ پاصفحه می‌ایستد، نه شناور در فضا.
           مختصات از روی *همان* padding‌هایی می‌آید که پوستهٔ برنامه دارد
           (`Layout`: `px-3 pb-3` / `lg:p-10` / `xl:p-12`)، پس لبهٔ چپ و
           کفِ دکمه دقیقاً روی لبهٔ چپ و کفِ قابِ پاصفحه می‌افتند — در هر
           عرضی، بی هیچ عددِ جادویی.

           نسخهٔ قبلی سه عددِ دست‌چین داشت (`bottom-[58px] left-[73px]` و
           دو حالتِ دیگر) که از «مرکزِ افقیِ امضای توسعه‌دهنده» حساب شده
           بودند. هر تغییری در متنِ آن امضا یا در padding پوسته، بی‌صدا
           از تراز خارجشان می‌کرد.

           جای خالی‌اش را خودِ پاصفحه می‌دهد (`Footer roomForCopilot`)، پس
           این دکمه روی چیزی نمی‌افتد و لازم نیست نیمه‌شفاف باشد. */
        className="mascot-host group fixed bottom-3 left-3 z-40 h-14 w-14 focus-visible:outline-none sm:h-16 sm:w-16 lg:bottom-10 lg:left-10 xl:bottom-12 xl:left-12"
      >
        {/* `track` فقط این‌جا روشن است: آواتارهای داخلِ گفت‌وگو هم همین
            شخصیت‌اند و اگر همه‌شان به نشانگر گوش بدهند، یک حرکتِ ماوس
            ده‌ها محاسبهٔ مستقل می‌شود. */}
        <Mascot track className="h-full w-full drop-shadow-[0_6px_14px_rgba(168,18,16,0.32)]" />
        {/* نشانِ «اجازهٔ پیشنهادِ تغییر دارد».
            گوشهٔ پایین‌ـ‌ابتدا: تنها گوشه‌ای که پشم خالی گذاشته. بالای سر
            روی کاکل می‌افتد و کنارِ صورت با چشم‌ها رقابت می‌کند. */}
        {status.allow_write_actions && (
          <span
            className="absolute bottom-0.5 end-0 h-2.5 w-2.5 rounded-full border-2 border-white bg-green-500 shadow-sm"
            title="اجازهٔ پیشنهادِ تغییر دارد"
          />
        )}
      </motion.button>

      <AnimatePresence>
        {open && (
          <>
            <motion.div
              className="fixed inset-0 z-40 bg-gray-900/30 backdrop-blur-[2px]"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setOpen(false)}
            />
            <motion.section
              ref={panelRef}
              role="dialog"
              aria-modal="true"
              aria-label="همکار هوشمند"
              tabIndex={-1}
              /* بالای سرِ نشان می‌ایستد و نه رویش.
                 پیش از این هر دو `bottom-4 left-4` بودند، یعنی پنجره دقیقاً
                 روی شخصیت می‌افتاد و تا وقتی گفت‌وگو باز بود دیده نمی‌شد.

                 `--copilot-lift` = ارتفاعِ نشان + فاصله‌اش از کف + ۱۲ پیکسل
                 نفس، و از همان کلاس‌های خودِ دکمه چند خط بالاتر می‌آید:
                   پایه   ۱۲ + ۵۶ + ۱۲ = ۸۰
                   sm     ۱۲ + ۶۴ + ۱۲ = ۸۸
                   lg     ۴۰ + ۶۴ + ۱۲ = ۱۱۶
                   xl     ۴۸ + ۶۴ + ۱۲ = ۱۲۴
                 یک متغیر و نه دو عدد: `bottom` و `height` باید *با هم* عوض
                 شوند، وگرنه پنجره از بالای نما بیرون می‌زند.

                 لبهٔ چپ هم با خودِ نشان تراز است، پس ستونِ عمودیِ گوشه یک
                 خط دارد: نشان، پنجره، پاصفحه. */
              className="fixed left-3 z-50 flex flex-col overflow-hidden rounded-3xl border border-gray-200 bg-white shadow-float [--copilot-lift:80px] sm:[--copilot-lift:88px] lg:left-10 lg:[--copilot-lift:116px] xl:left-12 xl:[--copilot-lift:124px] bottom-[var(--copilot-lift)] h-[min(680px,calc(100dvh-var(--copilot-lift)-1rem))] w-[min(560px,calc(100vw-1.5rem))]"
              initial={{ opacity: 0, y: 24, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 16, scale: 0.98 }}
              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            >
              <CopilotPanel
                status={status}
                variant="drawer"
                onClose={() => setOpen(false)}
                onExpand={() => {
                  setOpen(false);
                  navigate("/copilot");
                }}
              />
            </motion.section>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
