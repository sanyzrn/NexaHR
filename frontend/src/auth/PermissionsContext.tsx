/** مجوزهای کاربر و وضعیت ماژول‌ها، یک‌بار برای کل برنامه (نیمهٔ دوم P0-03).
 *
 * جای پرچم‌های ثابتِ کد را می‌گیرد. `FEATURE_PERIODS_ENABLED` یک `const` در
 * `appInfo.ts` بود: روشن‌کردنش یعنی تغییر کد، بیلد و استقرار — و برای محصولی که
 * قرار است به چند سازمان فروخته شود، هر «این بخش را نمی‌خواهیم» یک انشعاب.
 *
 * قاعدهٔ نمایش: **گزینه‌ای که اجازه‌اش را نداری، بهتر است اصلاً نباشد تا اینکه
 * باشد و کلیکش ۴۰۳ بگیرد.** ولی این فقط پوشش UI است — گاردِ واقعی سمت سرور
 * است و باید بماند؛ پنهان‌کردن یک دکمه هیچ‌کس را از صدا زدن مستقیم API باز
 * نمی‌دارد.
 */
import { createContext, useContext, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../api/client";
import { useAuth } from "./AuthContext";

export type Capability =
  | "manage_users"
  | "manage_personnel"
  | "manage_ai"
  | "manage_capabilities"
  | "manage_scoring"
  | "manage_integrations"
  | "manage_modules"
  | "view_audit_log"
  | "view_diagnostics";

interface Permissions {
  capabilities: Capability[];
  modules: Record<string, boolean>;
}

interface PermissionsValue {
  can: (capability: Capability) => boolean;
  moduleEnabled: (key: string) => boolean;
  /** هنوز از سرور نیامده — تا آن لحظه چیزی که مشروط است نشان داده نمی‌شود */
  loading: boolean;
}

/** ماژولی که سرور دربارهٔ آن چیزی نگفته، *خاموش* است — نه روشن.
 *
 *  پیش از این روشن فرض می‌شد، با این استدلال که وگرنه در فاصلهٔ بارگذاری منو
 *  بخش‌های سالم را پنهان می‌کند. آن نگرانی درست است ولی جایش `loading` است — و
 *  همهٔ فراخوان‌های حساس همان را می‌سنجند
 *  (`!permissionsLoading && moduleEnabled(...)`).
 *
 *  بهایش این بود: اگر `/administration/my-permissions` *شکست بخورد*، `loading`
 *  دیگر true نیست و `data` هم نیست، پس هر ماژولی روشن دیده می‌شد — از جمله
 *  «نمایش نتیجه به کارمند» که پیش‌فرضش خاموش است. یعنی یک درخواستِ ناموفق،
 *  نتیجهٔ ارزیابی را روی استقراری نشان می‌داد که عمداً خاموشش کرده بود.
 *  سوییچی که در حالتِ خطا باز می‌شود، سوییچ نیست.
 *
 *  سرور هم از سمتِ خودش بسته است (`ensure_module_enabled`، و گاردِ خواندنِ
 *  `/api/me/evaluations`)، پس این‌جا فقط رابط را با آن هم‌داستان می‌کند.
 *
 *  جدا و صادرشده تا خودِ این قاعده — و نه مسیرِ شبکه‌اش — تست شود.
 */
export function isModuleEnabled(
  modules: Record<string, boolean> | undefined,
  key: string
): boolean {
  return modules?.[key] ?? false;
}

const PermissionsContext = createContext<PermissionsValue | undefined>(undefined);

export function PermissionsProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();

  const { data, isPending } = useQuery({
    queryKey: ["administration", "my-permissions", user?.id],
    queryFn: async () =>
      (await apiClient.get<Permissions>("/administration/my-permissions")).data,
    enabled: user != null,
    staleTime: 60_000,
  });

  const value: PermissionsValue = {
    can: (capability) => data?.capabilities.includes(capability) ?? false,
    moduleEnabled: (key) => isModuleEnabled(data?.modules, key),
    loading: user != null && isPending,
  };

  return (
    <PermissionsContext.Provider value={value}>{children}</PermissionsContext.Provider>
  );
}

export function usePermissions(): PermissionsValue {
  const value = useContext(PermissionsContext);
  if (value === undefined) {
    throw new Error("usePermissions باید داخل PermissionsProvider استفاده شود");
  }
  return value;
}
