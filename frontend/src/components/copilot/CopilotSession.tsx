/** حالتِ زندهٔ گفت‌وگوی همکار، بیرون از هر پنجره‌ای که نشانش می‌دهد.
 *
 * پیش از این همهٔ این‌ها `useState` داخلِ `CopilotPanel` بودند، و پنل با
 * `AnimatePresence` از درخت *برداشته* می‌شد. یعنی هر بستنِ پنجره — یک کلیک
 * بیرون کادر، یک Escape — کلِ گفت‌وگو را پاک می‌کرد و باز کردنِ دوباره از صفر
 * شروع می‌شد. همان اتفاق برای دکمهٔ «صفحهٔ کامل» هم می‌افتاد: پنجره بسته
 * می‌شد، مسیر عوض می‌شد، و صفحهٔ کامل با پنلِ خالی بالا می‌آمد — یعنی دکمه‌ای
 * که کارش «همین گفت‌وگو را بزرگ‌تر ببین» است، دقیقاً همان گفت‌وگو را می‌بُرد.
 *
 * تاریخچهٔ سرور جای این نیست: گفت‌وگو تنها پس از اولین پاسخِ موفق ماندگار
 * می‌شود، پس پیامِ در حالِ ارسال، خطای همین نوبت، و کارت‌های در انتظارِ تأیید
 * هیچ‌کدام از آن‌جا برنمی‌گشتند.
 *
 * ظرف بالای مسیریاب می‌نشیند (`Layout`)، پس پنجرهٔ شناور و صفحهٔ کامل *یک*
 * گفت‌وگو دارند و نه دو.
 */
import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import type { AiMessage, AiPendingAction, AiUploadInfo } from "../../types";

export interface CopilotSession {
  conversationId: number | null;
  setConversationId: (id: number | null) => void;
  messages: AiMessage[];
  setMessages: React.Dispatch<React.SetStateAction<AiMessage[]>>;
  pendingList: AiPendingAction[];
  setPendingList: React.Dispatch<React.SetStateAction<AiPendingAction[]>>;
  uploads: AiUploadInfo[];
  setUploads: React.Dispatch<React.SetStateAction<AiUploadInfo[]>>;
  /** پیش‌نویسِ نیم‌کاره هم باید بماند: بستنِ اتفاقیِ پنجره نباید متنی را ببرد
   *  که کاربر نوشته و هنوز نفرستاده. */
  draft: string;
  setDraft: (text: string) => void;
  failure: string;
  setFailure: (text: string) => void;
  reset: () => void;
}

const CopilotSessionContext = createContext<CopilotSession | null>(null);

export function CopilotSessionProvider({ children }: { children: ReactNode }) {
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [messages, setMessages] = useState<AiMessage[]>([]);
  const [pendingList, setPendingList] = useState<AiPendingAction[]>([]);
  const [uploads, setUploads] = useState<AiUploadInfo[]>([]);
  const [draft, setDraft] = useState("");
  const [failure, setFailure] = useState("");

  const value = useMemo<CopilotSession>(
    () => ({
      conversationId,
      setConversationId,
      messages,
      setMessages,
      pendingList,
      setPendingList,
      uploads,
      setUploads,
      draft,
      setDraft,
      failure,
      setFailure,
      reset: () => {
        setConversationId(null);
        setMessages([]);
        setPendingList([]);
        setUploads([]);
        setFailure("");
      },
    }),
    [conversationId, messages, pendingList, uploads, draft, failure],
  );

  return (
    <CopilotSessionContext.Provider value={value}>{children}</CopilotSessionContext.Provider>
  );
}

/** حالتِ گفت‌وگو. بیرون از ظرف خطا می‌دهد و نه یک حالتِ خالیِ ساکت: پنلی که
 *  بی‌ظرف رندر شود دوباره همان باگِ ریست‌شدن را دارد، فقط بی‌صدا. */
export function useCopilotSession(): CopilotSession {
  const value = useContext(CopilotSessionContext);
  if (value === null) {
    throw new Error("useCopilotSession باید داخل <CopilotSessionProvider> استفاده شود");
  }
  return value;
}
