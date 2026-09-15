import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../api/client";
import { PageHeader } from "../ui/Card";
import type { AiStatus } from "../types";
import { CopilotPanel } from "../components/copilot/CopilotPanel";

/**
 * همکار در صفحهٔ کامل — همان گفت‌وگو، با جای نفس‌کشیدن بیشتر:
 * تاریخچه همیشه دیده می‌شود و جدول‌های گزارش جا دارند.
 *
 * چیدمانش با بقیهٔ صفحه‌ها فرق دارد و عمداً: این صفحه نباید *اسکرول* شود.
 * ستونِ تاریخچه و جعبهٔ نوشتن باید سرِ جایشان بمانند و فقط فهرستِ پیام‌ها
 * بلغزد — همان رفتاری که از یک پنجرهٔ گفت‌وگو انتظار می‌رود.
 *
 * پیش از این ارتفاعِ قاب `calc(100vh-14rem)` بود، با یک `min-h-[480px]`.
 * دو خرابی داشت و هر دو را کاربر دید:
 *
 * ۱. «۱۴rem» حدسِ ارتفاعِ نوارِ بالا و فاصله‌های پوسته بود. هر تغییری در
 *    آن‌ها، بی هیچ نشانه‌ای، قاب را بلندتر یا کوتاه‌تر از ناحیهٔ محتوا
 *    می‌کرد.
 * ۲. `min-h-[480px]` در پنجرهٔ کوتاه *بزرگ‌تر* از فضای موجود می‌شد، پس کلِ
 *    صفحه اسکرول می‌گرفت و جعبهٔ نوشتن از پایینِ نما بیرون می‌رفت. یعنی
 *    کاربر برای تایپ‌کردن باید اسکرول می‌کرد.
 *
 * حالا عددی در کار نیست: قاب با `h-full` دقیقاً به قدِ ناحیهٔ محتوا می‌شود
 * (زنجیره‌اش در `Layout` کامل شده) و `min-h-0` اجازه می‌دهد کوچک‌تر از
 * محتوایش بشود — همان چیزی که یک ناحیهٔ اسکرول‌شونده لازم دارد.
 */
export default function CopilotPage() {
  const { data: status } = useQuery({
    queryKey: ["ai", "status"],
    queryFn: async () => (await apiClient.get<AiStatus>("/ai/status")).data,
    staleTime: 0,
    refetchOnMount: "always",
  });

  return (
    <div className="flex flex-col gap-4 lg:h-full lg:min-h-0">
      <div className="shrink-0">
        <PageHeader title="همکار هوشمند" subtitle="همان اختیاراتِ خودتان، در یک گفت‌وگو" />
      </div>
      {/* زیر `lg` ارتفاعِ معین در کار نیست (پوسته خودش اسکرول می‌شود)، پس
          آن‌جا قاب یک بلندیِ معقولِ ثابت می‌گیرد. */}
      <div className="flex h-[70dvh] min-h-0 flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm lg:h-auto lg:flex-1">
        <CopilotPanel status={status} variant="page" />
      </div>
    </div>
  );
}
