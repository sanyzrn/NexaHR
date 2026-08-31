import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { apiClient } from "../../api/client";
import type { AiStatus } from "../../types";
import { CopilotPanel } from "./CopilotPanel";
import { Mascot } from "./Mascot";

/**
 * ورودیِ همکار: دکمهٔ شناور + پنجرهٔ کنارِ صفحه.
 *
 * «در دسترس هست یا نه» یک *حالت* است، نه یک استثنا: پیش از ساختنِ دکمه
 * پرسیده می‌شود؛ دکمه‌ای که تنها پاسخش «در دسترس نیست» باشد، از نبودنش بدتر است.
 * حالتِ «فعال ولی بدون دسترسیِ تغییر» هم دکمه دارد — فقط شکلش فرق می‌کند.
 */
export function Copilot() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  const { data: status } = useQuery({
    queryKey: ["ai", "status"],
    queryFn: async () => (await apiClient.get<AiStatus>("/ai/status")).data,
    // فعال‌سازی دستیار از پنل مدیریت یا تب دیگری باید بدون تأخیر دیده شود.
    staleTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: true,
  });

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
        /* روی لبهٔ بالای پاصفحه می‌ایستد، دقیقاً بالای امضای «Developed by…».
           عددها اندازه‌گیری‌شده‌اند، نه حدسی:

             bottom = فاصلهٔ پاصفحه از کفِ پنجره (pb-3 → ۱۲، lg:pb-4 → ۱۶)
                      + بلندیِ پاصفحه (۵۰، در همهٔ عرض‌ها) − ۴
             ۴ همان فضای خالیِ زیرِ پاست در viewBox ۶۴‌تایی، وگرنه پا کمی
             بالاتر از سطح می‌ایستد و شخصیت شناور به‌نظر می‌رسد.

             left   = مرکزِ افقیِ همان امضا − نصفِ دکمه (۳۲)
             و مرکزِ امضا با padding افقیِ پوسته و پاصفحه جابه‌جا می‌شود:
             ۱۲+۱۶ در پایه، ۱۲+۲۴ از sm، ۱۶+۲۴ از lg.

           پاصفحه در هیچ عرضی دو خطی نمی‌شود (تا ۳۹۰ پیکسل هم سنجیده شد)، پس
           بلندی‌اش ثابت است و همین سه حالت کافی است. */
        className="mascot-host group fixed bottom-[58px] left-[73px] z-40 h-16 w-16 transition-transform hover:scale-105 focus-visible:outline-none sm:left-[81px] lg:bottom-[62px] lg:left-[85px]"
      >
        <Mascot className="h-16 w-16 drop-shadow-[0_5px_12px_rgba(0,0,0,0.22)]" />
        {/* نشانِ «اجازهٔ پیشنهادِ تغییر دارد».
            گوشهٔ پایین‌ـ‌ابتدا، چون تنها گوشه‌ای است که شخصیت خالی گذاشته؛ بالای
            سر روی صورت می‌افتاد و در ۶۴ پیکسل، با چشم‌ها رقابت می‌کرد. */}
        {status.allow_write_actions && (
          <span
            className="absolute bottom-1.5 end-0.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-green-500"
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
              role="dialog"
              aria-label="همکار هوشمند"
              className="fixed bottom-4 left-4 z-50 flex h-[min(680px,calc(100vh-2rem))] w-[min(560px,calc(100vw-2rem))] flex-col overflow-hidden rounded-3xl border border-gray-200 bg-white shadow-float"
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
