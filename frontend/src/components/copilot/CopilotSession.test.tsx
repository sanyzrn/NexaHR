/** گفت‌وگو نباید با بسته‌شدنِ پنجره‌ای که نشانش می‌دهد از بین برود.
 *
 * پنجرهٔ شناور با `AnimatePresence` از درخت *برداشته* می‌شود، پس هر حالتی که
 * داخلِ خودِ پنل باشد با یک کلیک بیرون کادر پاک می‌شود. دکمهٔ «صفحهٔ کامل» هم
 * همین کار را می‌کرد: پنجره را می‌بست و مسیر را عوض می‌کرد، و صفحهٔ کامل با
 * پنلِ خالی بالا می‌آمد — یعنی دکمه‌ای که کارش «همین گفت‌وگو را بزرگ‌تر ببین»
 * است، دقیقاً همان گفت‌وگو را می‌بُرد.
 *
 * این تست‌ها به خودِ ظرف می‌پردازند و نه به پنل: قرارداد همین است که حالت
 * *بیرون* از هر چیزی که unmount می‌شود زندگی کند.
 */
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { CopilotSessionProvider, useCopilotSession } from "./CopilotSession";
import type { AiMessage } from "../../types";

const message = (id: number, content: string): AiMessage => ({
  id,
  role: "assistant",
  content,
  actions: [],
});

/** یک «پنل» ساختگی که مثل پنجرهٔ شناور unmount و دوباره mount می‌شود. */
function FakePanel() {
  const { messages, setMessages, conversationId, setConversationId, draft, setDraft, reset } =
    useCopilotSession();
  return (
    <div>
      <p data-testid="messages">{messages.map((m) => m.content).join("|")}</p>
      <p data-testid="conversation">{String(conversationId)}</p>
      <p data-testid="draft">{draft}</p>
      <button
        onClick={() => {
          setConversationId(9);
          setMessages((prev) => [...prev, message(prev.length + 1, "پاسخ")]);
          setDraft("نیمه‌کاره");
        }}
      >
        گفت‌وگو کن
      </button>
      <button onClick={reset}>گفت‌وگوی تازه</button>
    </div>
  );
}

function Host() {
  const [open, setOpen] = useState(true);
  return (
    <CopilotSessionProvider>
      <button onClick={() => setOpen((v) => !v)}>toggle</button>
      {open && <FakePanel />}
    </CopilotSessionProvider>
  );
}

describe("CopilotSession", () => {
  it("گفت‌وگو با بسته و باز شدنِ پنجره از بین نمی‌رود", () => {
    render(<Host />);
    act(() => screen.getByText("گفت‌وگو کن").click());
    expect(screen.getByTestId("messages").textContent).toBe("پاسخ");
    expect(screen.getByTestId("conversation").textContent).toBe("9");

    // بستنِ پنجره — همان کاری که کلیک بیرون کادر می‌کند
    act(() => screen.getByText("toggle").click());
    expect(screen.queryByTestId("messages")).toBeNull();

    act(() => screen.getByText("toggle").click());
    expect(screen.getByTestId("messages").textContent).toBe("پاسخ");
    expect(screen.getByTestId("conversation").textContent).toBe("9");
  });

  it("پیش‌نویسِ نفرستاده هم می‌ماند", () => {
    render(<Host />);
    act(() => screen.getByText("گفت‌وگو کن").click());
    act(() => screen.getByText("toggle").click());
    act(() => screen.getByText("toggle").click());
    expect(screen.getByTestId("draft").textContent).toBe("نیمه‌کاره");
  });

  it("«گفت‌وگوی تازه» همچنان همه‌چیز را پاک می‌کند", () => {
    render(<Host />);
    act(() => screen.getByText("گفت‌وگو کن").click());
    act(() => screen.getByText("گفت‌وگوی تازه").click());
    expect(screen.getByTestId("messages").textContent).toBe("");
    expect(screen.getByTestId("conversation").textContent).toBe("null");
  });

  it("پنل بیرون از ظرف خطا می‌دهد و بی‌صدا حالتِ خالی نمی‌سازد", () => {
    // حالتِ خالیِ ساکت یعنی همان باگِ ریست‌شدن، فقط بی‌آنکه کسی بفهمد.
    expect(() => render(<FakePanel />)).toThrow(/CopilotSessionProvider/);
  });
});
