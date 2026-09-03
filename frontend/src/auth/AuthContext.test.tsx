/** ورود و خروج باید کشِ React Query را پاک کنند.
 *
 *  کلیدهای پرس‌وجو در این برنامه به کاربر گره نخورده‌اند (`["notifications"]`،
 *  `["auth","sessions"]`، `["me","evaluations"]`)، خروج ناوبریِ SPA است و نه
 *  بارگذاریِ دوبارهٔ صفحه، و `gcTime` پیش‌فرض پنج دقیقه است. یعنی روی یک
 *  رایانهٔ مشترک، کاربرِ دومی که داخل همان پنجره وارد می‌شد، ردیف‌های کاربرِ
 *  اول را *بلافاصله* رندر می‌دید — نامِ دستگاه‌ها و IP، اعلان‌ها، کارنامه — و
 *  بعد با رسیدنِ پاسخِ تازه پرشِ محتوا.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "./AuthContext";

const get = vi.fn();
const post = vi.fn();
const tokenStore: { value: string | null } = { value: null };

vi.mock("../api/client", () => ({
  apiClient: {
    get: (...a: unknown[]) => get(...a),
    post: (...a: unknown[]) => post(...a),
  },
  authToken: {
    get: () => tokenStore.value,
    set: (v: string | null) => {
      tokenStore.value = v;
    },
  },
  refreshAccessToken: async () => null,
}));
vi.mock("../pwa", () => ({ clearAppCaches: async () => {} }));

let auth: ReturnType<typeof useAuth>;

function Probe() {
  auth = useAuth();
  return <p>{auth.user?.username ?? "-"}</p>;
}

/** کش را با یک ردیفِ «کاربرِ قبلی» پر می‌کند و برنامه را سوار می‌کند. */
async function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(["notifications"], [{ id: 1, title: "پیامِ نفرِ قبل" }]);
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(auth.loading).toBe(false));
  return client;
}

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  tokenStore.value = null;
});

describe("AuthProvider", () => {
  it("ورود، کشِ نشستِ قبلی را پاک می‌کند", async () => {
    post.mockResolvedValue({ data: { access_token: "t" } });
    get.mockResolvedValue({ data: { id: 2, username: "دومی", role: "hr" } });

    const client = await mount();
    expect(client.getQueryData(["notifications"])).toBeDefined();

    await act(async () => {
      await auth.login("دومی", "pw");
    });

    expect(client.getQueryData(["notifications"])).toBeUndefined();
  });

  it("کش *پیش از* خواندنِ کاربرِ تازه پاک می‌شود، نه بعدش", async () => {
    // ترتیب مهم است: اگر `clear()` بعد از `fetchMe` بیاید، پرس‌وجوهایی که با
    // رندرِ کاربرِ تازه شروع می‌شوند هم پاک می‌شوند و همه دوباره درخواست
    // می‌فرستند — یک طوفانِ درخواست در اولین فریمِ بعد از ورود.
    post.mockResolvedValue({ data: { access_token: "t" } });
    const client = await mount();
    let cacheAtFetchMe: unknown = "خوانده‌نشده";
    get.mockImplementation(async () => {
      cacheAtFetchMe = client.getQueryData(["notifications"]);
      return { data: { id: 2, username: "دومی", role: "hr" } };
    });

    await act(async () => {
      await auth.login("دومی", "pw");
    });

    expect(cacheAtFetchMe).toBeUndefined();
  });

  it("خروج، کش را پاک می‌کند و کاربر را برمی‌دارد", async () => {
    tokenStore.value = "t";
    get.mockResolvedValue({ data: { id: 1, username: "اولی", role: "hr" } });
    post.mockResolvedValue({ data: {} });

    const client = await mount();
    await waitFor(() => expect(auth.user?.username).toBe("اولی"));

    act(() => auth.logout());

    expect(client.getQueryData(["notifications"])).toBeUndefined();
    expect(auth.user).toBeNull();
    expect(tokenStore.value).toBeNull();
  });

  it("خطای شبکه در ابطالِ سمتِ سرور، خروجِ محلی را متوقف نمی‌کند", async () => {
    tokenStore.value = "t";
    get.mockResolvedValue({ data: { id: 1, username: "اولی", role: "hr" } });
    post.mockRejectedValue(new Error("offline"));

    const client = await mount();
    await waitFor(() => expect(auth.user?.username).toBe("اولی"));

    act(() => auth.logout());

    expect(client.getQueryData(["notifications"])).toBeUndefined();
    expect(auth.user).toBeNull();
  });
});
