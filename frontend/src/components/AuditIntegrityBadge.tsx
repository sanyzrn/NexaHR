/** وضعیت یکپارچگی زنجیرهٔ لاگ حسابرسی (P1-09، لنگر در فازِ ۳پ).
 *
 * زنجیرهٔ هش بدون راهی برای *دیدن* نتیجه‌اش، فقط چند ستون بی‌استفاده است. این نشان
 * به HR می‌گوید لاگ بازمحاسبه شد و با آن‌چه ذخیره شده می‌خواند — یعنی می‌تواند به
 * آن به‌عنوان مدرک استناد کند، نه صرفاً مستندات.
 *
 * از فازِ ۳پ، بررسیِ پیش‌فرض **از لنگر به بعد** است و نه از ابتدای تاریخ: بررسیِ
 * کامل هزینه‌ای دارد که هرگز کوچک نمی‌شود، و جایش جاروی شبانه است.
 *
 * و همین‌جاست که این نشان باید صادق باشد. «سبزِ سریع» با «سبزِ کامل» یکی نیست:
 * بررسیِ از لنگر به بعد، دست‌بردن در ردیف‌های *پیش از* لنگر را نمی‌بیند. پس متنِ
 * نشان می‌گوید تا کِی کامل سنجیده شده، و دکمه‌ای کنارش هست که همان بررسیِ کامل را
 * همین حالا می‌زند.
 */
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { apiClient } from "../api/client";
import { formatDateTime } from "../utils/dates";

interface Integrity {
  ok: boolean;
  checked: number;
  broken_at_id: number | null;
  reason: string | null;
  full: boolean;
  anchor_log_id: number | null;
  anchor_verified_at: string | null;
}

const fa = (n: number) => n.toLocaleString("fa-IR");

export function AuditIntegrityBadge() {
  const [full, setFull] = useState(false);
  const { data, isPending, isFetching, error } = useQuery({
    queryKey: ["audit-log", "integrity", full],
    queryFn: async () =>
      (await apiClient.get<Integrity>("/audit-log/integrity", { params: { full } })).data,
    // پاسخ سریع کهنه نمی‌شود، و بررسیِ کامل اصلاً نباید خودبه‌خود تکرار شود
    staleTime: 60_000,
  });

  if (isPending || error) return null;

  if (!data.ok) {
    return (
      <span
        className="inline-flex items-center gap-1.5 rounded-full bg-red-50 px-3 py-1 text-xs font-medium text-red-700"
        title={`${data.reason ?? ""} — نخستین ردیف ناسازگار: #${data.broken_at_id}`}
      >
        <svg viewBox="0 0 20 20" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
          <path d="M10 6v5m0 3h.01" />
          <circle cx="10" cy="10" r="7.5" />
        </svg>
        زنجیرهٔ یکپارچگی شکسته است
      </span>
    );
  }

  /* عددِ «بررسی‌شده» به‌تنهایی گمراه‌کننده است: در حالتِ سریع فقط رویدادهای پس از
     لنگر را می‌شمارد، و کاربری که دیروز «۲۵٬۰۰۰ رویداد» دیده و امروز «۱۲» می‌بیند
     حق دارد فکر کند چیزی پاک شده. پس هر دو عدد گفته می‌شوند. */
  const anchored = !data.full && data.anchor_verified_at !== null;
  const label = data.full
    ? `یکپارچگی تأیید شد (${fa(data.checked)} رویداد، از ابتدا)`
    : anchored
      ? `یکپارچگی تأیید شد (${fa(data.checked)} رویداد تازه)`
      : `یکپارچگی تأیید شد (${fa(data.checked)} رویداد)`;

  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <span
        className="inline-flex items-center gap-1.5 rounded-full bg-green-50 px-3 py-1 text-xs font-medium text-green-700"
        title={
          anchored
            ? `${fa(data.checked)} رویداد پس از آخرین بررسی کامل بازمحاسبه و تأیید شد`
            : `${fa(data.checked)} رویداد از ابتدای زنجیره بازمحاسبه و تأیید شد`
        }
      >
        <svg viewBox="0 0 20 20" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 10.5l3.5 3.5L16 6" />
        </svg>
        {label}
      </span>

      {anchored && (
        <span className="text-[11px] text-gray-500">
          آخرین بررسی کامل: {formatDateTime(data.anchor_verified_at)}
        </span>
      )}

      {!data.full && (
        <button
          type="button"
          onClick={() => setFull(true)}
          disabled={isFetching}
          className="tap-target rounded-full border border-gray-300 px-2.5 py-1 text-[11px] text-gray-600 transition hover:bg-gray-50 disabled:opacity-50"
        >
          {isFetching ? "در حال بررسی…" : "بررسی کامل از ابتدا"}
        </button>
      )}
    </span>
  );
}
