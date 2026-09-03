import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { usePermissions, type Capability } from "./PermissionsContext";
import type { UserRole } from "../types";

/** گاردِ مسیر: نقش، یا مجوز، یا هر دو.
 *
 *  `anyCapability` برای صفحه‌هایی است که کارِ روزمرهٔ یک نقش‌اند ولی مدیر سامانه
 *  هم باید به آن‌ها برسد. تا امروز فقط `allowedRoles` بود، و نتیجه‌اش این بود که
 *  حساب مدیر سامانه مجوزِ ساخت حساب را داشت ولی صفحهٔ «کاربران» او را به خانه
 *  برمی‌گرداند — سرور اجازه می‌داد و رابط نمی‌گذاشت.
 */
export function ProtectedRoute({
  allowedRoles,
  anyCapability,
  requireOwnPersonnel,
}: {
  allowedRoles?: UserRole[];
  anyCapability?: Capability[];
  /** قرینهٔ `require_own_personnel` سرور: هر کسی که پروندهٔ پرسنلی دارد.
   *
   *  برای صفحهٔ «کارنامه من». تا امروز آن مسیر `allowedRoles={["employee"]}`
   *  بود، در حالی که مسیرهای `/api/me` از نقش گذشته بودند — یعنی سرور اجازه
   *  می‌داد و رابط نمی‌گذاشت. مسئول واحد، معاونت، مدیرعامل و کارمندِ منابع
   *  انسانی هم ارزیابی می‌شوند؛ «چه کسی ارزیابی می‌شود» با «چه نقشی در
   *  زنجیره دارد» یکی نیست. */
  requireOwnPersonnel?: boolean;
}) {
  const { user, loading } = useAuth();
  const { can, loading: permissionsLoading } = usePermissions();

  if (loading) {
    return <div className="flex min-h-screen items-center justify-center">در حال بارگذاری…</div>;
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  if (requireOwnPersonnel && user.personnel_id === null) {
    return <Navigate to="/" replace />;
  }
  if (allowedRoles || anyCapability) {
    const byRole = allowedRoles?.includes(user.role) ?? false;
    // تا وقتی مجوزها نرسیده‌اند نمی‌شود «ندارد» گفت؛ وگرنه یک رفرشِ ساده کاربرِ
    // مجازِ مجوزدار را به صفحهٔ خانه پرت می‌کند.
    if (!byRole && anyCapability && permissionsLoading) {
      return <div className="flex min-h-screen items-center justify-center">در حال بارگذاری…</div>;
    }
    const byCapability = anyCapability?.some(can) ?? false;
    if (!byRole && !byCapability) return <Navigate to="/" replace />;
  }
  return <Outlet />;
}
