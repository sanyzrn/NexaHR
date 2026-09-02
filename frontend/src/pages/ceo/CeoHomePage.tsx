import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiClient, extractConflictEvaluationId, extractErrorMessage } from "../../api/client";
import { useEvaluations, usePersonnelList } from "../../api/queries";
import { EmployeeProfileModal } from "../../components/EmployeeProfileModal";
import { EvaluationActionButton, type OpenEvaluation } from "../../components/EvaluationActionButton";
import { EvaluationList } from "../../components/EvaluationList";
import { RoleOverviewCards } from "../../components/RoleOverviewCards";
import { PageHeader } from "../../ui/Card";
import { Table } from "../../ui/Table";
import { isOpenStatus, type Personnel } from "../../types";

export function CeoHomePage() {
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [startingId, setStartingId] = useState<number | null>(null);
  const [profilePerson, setProfilePerson] = useState<Personnel | null>(null);
  const navigate = useNavigate();

  // کسانی که نه مسئول واحدی بالای سرشان هست و نه معاونتی: نمره‌دهندهٔ اولشان
  // خودِ مدیرعامل است. `scored_by` را سرور می‌گوید و نه `is_manager` — آن پرچم
  // روی *پرسنل* است و شکلِ زنجیره را نمی‌گوید (صفحهٔ معاونت هنوز از آن استفاده
  // می‌کند، چون آن‌جا هر دو نشانه هم‌راستا هستند).
  const { data, error: loadError } = usePersonnelList({
    accessible_to_me: true,
    limit: 1000,
    offset: 0,
  });
  const directReports = (data?.items ?? []).filter((p) => p.scored_by === "ceo");

  // برای غیرفعال‌کردن «شروع ارزیابی جدید» وقتی ارزیابی باز از قبل هست
  const { data: myEvaluations } = useEvaluations({ limit: 200, offset: 0 });
  // `isOpenStatus` و نه `!== "finalized"`: پروندهٔ **لغوشده** پایان‌یافته است و
  // نباید جلوی شروع ارزیابی تازه را بگیرد.
  const openEvaluationByPersonnel = new Map<number, OpenEvaluation>();
  for (const e of myEvaluations?.items ?? []) {
    if (isOpenStatus(e.status)) {
      openEvaluationByPersonnel.set(e.subject_personnel_id, {
        id: e.id,
        code: e.evaluation_code,
        status: e.status,
      });
    }
  }

  async function startEvaluation(p: Personnel) {
    if (starting) return;
    setStarting(true);
    setStartingId(p.id);
    setError(null);
    try {
      const { data } = await apiClient.post("/evaluations", { subject_personnel_id: p.id });
      navigate(`/evaluations/${data.id}`);
    } catch (err) {
      // اگر ارزیابی باز از قبل وجود دارد، مستقیم به همان پرونده برو
      const existingId = extractConflictEvaluationId(err);
      if (existingId !== null) {
        navigate(`/evaluations/${existingId}`);
        return;
      }
      setError(extractErrorMessage(err));
    } finally {
      setStarting(false);
      setStartingId(null);
    }
  }

  return (
    <div className="space-y-4">
      {/* «داشبورد» بود، ولی این صفحه یک صف است نه داشبورد — تحلیل سازمان صفحهٔ
          جداگانهٔ خودش را دارد. یک کلمه برای دو چیز، انتظار غلط می‌سازد. */}
      <PageHeader
        title="صندوق تأیید نهایی"
        subtitle="پرونده‌هایی که منتظر امضای شما هستند، و نمره‌دهی افرادِ مستقیمِ خودتان"
      />
      <RoleOverviewCards />
      {loadError != null && (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
          {extractErrorMessage(loadError)}
        </p>
      )}
      {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}
      {/* بی این جدول، پروندهٔ این افراد هیچ نقطهٔ *شروعی* نداشت: صف پایین فقط
          پرونده‌های موجود را نشان می‌دهد و «ارزیابی جدید» جای دیگری نبود. */}
      {directReports.length > 0 && (
        <div className="rounded-2xl border border-gray-200 bg-white p-4">
          <h2 className="mb-4 flex items-center gap-2 text-base font-bold text-gray-900">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-pulse-50 text-pulse-600">
              <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                <path d="M10 2.5v15M2.5 10h15" />
              </svg>
            </span>
            افراد مستقیم شما (بدون مسئول واحد و بدون معاونت)
          </h2>
          <p className="mb-3 text-xs text-gray-500">
            نمره‌دهی این پرونده‌ها با شماست. پس از ثبت، پرونده برای بازبینی به منابع
            انسانی می‌رود و تأیید نهاییِ شما پایانِ زنجیره است.
          </p>
          <Table
            bordered={false}
            headers={["نام", "واحد", ""]}
            rowKeys={directReports.map((p) => p.id)}
            rows={directReports.map((p) => [
              <button
                key="name"
                onClick={() => setProfilePerson(p)}
                className="font-medium text-gray-900 underline-offset-4 transition-colors hover:text-pulse-700 hover:underline"
                title="مشاهده پروفایل و روند عملکرد"
              >
                {p.full_name}
              </button>,
              <span key="unit" className="text-gray-500">
                {p.org_unit}
              </span>,
              <EvaluationActionButton
                key="action"
                open={openEvaluationByPersonnel.get(p.id)}
                starting={starting}
                isStartingThis={startingId === p.id}
                onContinue={(id) => navigate(`/evaluations/${id}`)}
                onStart={() => startEvaluation(p)}
              />,
            ])}
          />
        </div>
      )}
      <EvaluationList
        title="پرونده‌های ارزیابی"
        tabs={[
          { key: "scoring", label: "در انتظار نمره‌دهی من", status: "draft" },
          { key: "pending", label: "در انتظار تأیید نهایی", status: "deputy_approved" },
          { key: "finalized", label: "نهایی‌شده", status: "finalized" },
          { key: "all", label: "همهٔ پرونده‌های من" },
        ]}
      />

      {profilePerson && (
        <EmployeeProfileModal
          personnelId={profilePerson.id}
          personName={profilePerson.full_name}
          onClose={() => setProfilePerson(null)}
        />
      )}
    </div>
  );
}
