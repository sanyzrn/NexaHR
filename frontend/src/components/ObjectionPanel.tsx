/** اعتراض ثبت‌شدهٔ کارمند و پاسخ منابع انسانی (P0-06).
 *
 * اعتراضی که کسی موظف به پاسخ‌گویی به آن نباشد تشریفات است؛ این پنل هم اعتراض را
 * جلوی چشم زنجیره می‌گذارد و هم به HR راه پاسخ می‌دهد. نتیجه و سند نهایی عوض
 * نمی‌شوند — اگر واقعاً باید امتیاز تغییر کند، مسیرش ارزیابی تازه است نه بازنویسی
 * سندی که هش و QR تأیید دارد.
 */
import { useState } from "react";
import { apiClient, extractErrorMessage } from "../api/client";
import { useToast } from "./Toast";
import { Button } from "../ui/Button";
import { formatDateTime } from "../utils/dates";
import type { CurrentUser, EvaluationDetail } from "../types";

/** چه کسی به این اعتراض پاسخ می‌دهد — قرینهٔ `workflow.objection_resolver_field`.
 *
 *  در حالتِ عادی منابع انسانی. برای پروندهٔ اعضای واحدِ منابع انسانی، منابع
 *  انسانی خودش طرفِ ماجراست، پس پاسخ‌دهنده صندلیِ بالادستِ نمره‌دهنده است:
 *  معاونت برای کارشناسِ HR، و مدیرعامل برای مدیرِ HR (که خودِ معاونت نمره‌اش
 *  را داده). دومی وقتی هم پیش می‌آید که پرونده معاونتی در زنجیره نداشته باشد.
 */
function resolverSeatId(evaluation: EvaluationDetail): number | null {
  if (!evaluation.hr_review_skipped) return null;
  if (evaluation.unit_supervisor_user_id === null || evaluation.deputy_user_id === null) {
    return evaluation.ceo_user_id;
  }
  return evaluation.deputy_user_id;
}

export function ObjectionPanel({
  evaluation,
  user,
  onChanged,
}: {
  evaluation: EvaluationDetail;
  user: CurrentUser;
  onChanged: () => void;
}) {
  const { showSuccess, showError } = useToast();
  const [resolution, setResolution] = useState("");
  const [busy, setBusy] = useState(false);

  if (!evaluation.objection_at) return null;

  const resolverId = resolverSeatId(evaluation);
  const canResolve =
    resolverId === null
      ? user.role === "hr" && user.personnel_id !== evaluation.subject_personnel_id
      : user.id === resolverId;
  const pendingLabel =
    resolverId === null
      ? "در انتظار پاسخ منابع انسانی…"
      : "در انتظار پاسخ مسئول بالادستِ زنجیره…";

  async function submit() {
    setBusy(true);
    try {
      await apiClient.post(`/evaluations/${evaluation.id}/resolve-objection`, { resolution });
      showSuccess("پاسخ شما ثبت و به کارمند اطلاع داده شد");
      setResolution("");
      onChanged();
    } catch (err) {
      showError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-2xl border border-amber-200 bg-amber-50/60 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-bold text-amber-900">اعتراض کارمند</h2>
        <span className="text-xs text-amber-700">{formatDateTime(evaluation.objection_at)}</span>
      </div>
      <p className="mt-2 text-sm text-amber-900">{evaluation.objection_reason}</p>

      {evaluation.objection_resolved_at ? (
        <div className="mt-4 rounded-xl bg-white/80 p-3">
          <p className="text-xs font-medium text-gray-500">
            پاسخ به اعتراض — {formatDateTime(evaluation.objection_resolved_at)}
          </p>
          <p className="mt-1 text-sm text-gray-800">{evaluation.objection_resolution}</p>
        </div>
      ) : canResolve ? (
        <div className="mt-4">
          <label htmlFor="objection-resolution" className="mb-1.5 block text-sm font-medium text-amber-900">
            پاسخ شما به این اعتراض
          </label>
          <textarea
            id="objection-resolution"
            className="w-full resize-none rounded-xl border border-amber-300 bg-white px-3 py-2 text-sm outline-none"
            rows={3}
            value={resolution}
            onChange={(e) => setResolution(e.target.value)}
            placeholder="مثلاً: با مسئول واحد بررسی شد؛ شواهد تکمیلی به پرونده افزوده شد و نتیجه بدون تغییر ماند"
          />
          <Button className="mt-3" onClick={submit} loading={busy} disabled={!resolution.trim()}>
            ثبت پاسخ
          </Button>
        </div>
      ) : (
        <p className="mt-3 text-xs text-amber-700">{pendingLabel}</p>
      )}
    </div>
  );
}
