No PostgreSQL server in this environment (no root). The frontend CI job doesn't need it, so I'll run that fully and try a portable Postgres for the rest. Starting installs now:

Now let me read the core files for my review angle. Starting with React Query setup, API client, and auth/permissions:

The focusTrap hook has a suspicious "ref" pattern — let me check its consumers for stale-closure impact:

Now let me compare frontend validation with the backend's rules — the paired invariant `compute\_result` vs `computePreview` and evidence rules:

While tests run, let me try to get a portable PostgreSQL so I can also run the backend/e2e jobs:

While the CI job runs, continuing the review — PWA and theme:

Background jobs are being killed. Running the frontend job in foreground:

Frontend job fully green (lint 0/0, 270/270 tests, build OK). Now the backend setup for e2e:

The sandbox injects a `DATABASE\_URL` env var that overrides the repo default. Overriding it:

Backend: \*\*1035/1035 passed\*\*. Now launcher tests and e2e:

All four CI jobs pass locally. Now checking whether backend 422 validation errors (FastAPI `detail` arrays) are renderable by the frontend's `extractErrorMessage`:

Let me empirically test the `sr-only` required-input pattern used by JalaliDatePicker in a real browser:

Empirical result confirmed: submit is blocked and focus jumps to the invisible 1×1 input. Now checking a suspected cross-tab session-mixing path — token TTL and refresh behavior:

Confirmed. Now reading the rest of EvaluationDetailPage (stage actions, error states) and the objection/recovery panels:

\## Verdict — 3 lines

The frontend is unusually disciplined: cache boundaries on login/logout, fail-closed permission gating, and the focus-trap/aria work are real, not decorative, and all four CI jobs pass green locally (1035 backend + 89 launcher + 270 frontend tests + e2e). The defects that remain are concentrated in two spots: a session-identity gap that lets a second tab's login hijack an idle tab's API identity on shared machines, and a set of verified WCAG failures (danger-button contrast, light-theme gray-400 text, one suppressed focus indicator) that survive despite the otherwise strong a11y investment. Six findings total, every one reproducible against source or runtime.



\## Findings — severity | file:line | what breaks | how to reach it | fix



1\. \*\*HIGH\*\* | `frontend/src/api/client.ts:47-67` (with `refreshAccessTokenOnce` at 26-35) + `backend/app/api/routers/auth.py:90-107` | A tab silently switches user identity after a refresh. The refresh cookie is one jti per browser profile; `login` overwrites it (`\_issue\_login\_response` → `\_set\_refresh\_cookie`). Tab 1 (user A) idles past the 30-min access-token TTL (`access\_token\_expire\_minutes=30`); user B logs in in tab 2; A's tab stays open. Any next request in tab 1 gets 401 → interceptor refreshes \*\*with B's cookie\*\* → receives B's access token → retries the original request as B. A's screen still shows A's name and A's cached React Query data, now interleaved with B's fresh data (notifications, queue, scores), and any write A makes is executed and audited as B. | Shared machine: A logs in, walks away without closing the tab; B opens a new tab and logs in; A returns and clicks anything. Verified in code: the interceptor only does `original.headers.Authorization = Bearer ${newToken}; return apiClient(original)` — no identity re-check; `AuthContext` fetches `/auth/me` only on mount and login. | In `refreshAccessTokenOnce()`, after obtaining the token, call `/auth/me` and compare `id` with the tab's current user (AuthContext already holds it — expose it to `client.ts` via a module-level setter like `authToken`). On mismatch: clear the query cache and `window.location.replace("/login")`. (Alternative: have the refresh response include the user id — it already returns the token whose JWT payload carries `sub` — and decode/compare client-side.)



2\. \*\*MEDIUM\*\* | `frontend/src/ui/Button.tsx:21` (`danger: "… bg-amber-600 … text-white …"`) | White on `#d97706` is \*\*3.19:1\*\* — below WCAG AA 4.5:1 for the 14px button label. This is not a stray styling: the `danger` variant is the confirm button of every irreversible action (`ConfirmDialog.tsx:64`): "حذف کن" (delete user), "بستن دوره" (close evaluation period), and the self-assessment "ثبت نهایی" (`OpenCaseCard.tsx:170-176`, `danger: true`). The code comments meticulously verify pulse-600 (6.74:1) but amber-600 was never measured. Same failure in both themes (dark theme redefines amber-50/100/200/700/800/900 but not 600). | Any HR user opens the delete-user or close-period confirm; the destructive action label — the exact element the flow is designed to make deliberate — fails contrast for low-vision users. | Darken the danger background to amber-700 (#b45309, 4.52:1 with white) for the filled variant, or switch the confirm button to `bg-charcoal-900 text-white` (14.2:1) and keep amber only for the warning panel.



3\. \*\*MEDIUM\*\* | `frontend/src/index.css:195-306` (light theme keeps Tailwind default `--color-gray-400: #9ca3af`) with consumers e.g. `components/ScoreForm.tsx:420` (WordCounter), `components/employee/OpenCaseCard.tsx:62-63`, `ui/JalaliDatePicker.tsx:158` (placeholder), `components/NotificationBell.tsx:130` | `text-gray-400` on white/gray-50 is \*\*2.54:1 / 2.43:1\*\* — fails WCAG AA for text. The dark theme fixed exactly this variable (`--color-gray-400: #858ca6`, 4.85:1, with a comment citing "۴٫۸۵:۱ برای کم‌رنگ‌ترین"), but the light theme never got the same treatment; 144 usages across 49 files carry \*meaningful\* text, not decoration: the word-counter that tells an evaluator "X از ۴۰ واژه" against a server-enforced rule, "امتیازها تا پیش از تأیید نهایی قطعی نیستند و نمایش داده نمی‌شوند" on the employee's open case, notification timestamps, the date-picker placeholder. | Light theme (the default), normal vision at typical viewing: the evidence word-count guidance and employee status text are at half the required contrast. | Override `--color-gray-400` in `:root` to `#6b7280` (4.83:1) or switch meaningful-text usages to `text-gray-500`; keep the old value only for decorative separators.



4\. \*\*MEDIUM\*\* | `frontend/src/components/copilot/Copilot.tsx:76` (`focus-visible:outline-none` on the floating mascot button) | The copilot entry point has \*\*no visible keyboard focus indicator\*\*. Verified in the compiled CSS: `.focus-visible\\:outline-none:focus-visible{--tw-outline-style:none;outline-style:none}` overrides the global `:focus-visible{outline:2px solid var(--color-pulse-violet-500)…}` (higher specificity), and the button has no ring/border alternative — only `hover:scale-105`, which never triggers on keyboard focus. WCAG 2.4.7 failure on a primary feature entry (the AI copilot that can execute writes). | Tab through any page until focus reaches the mascot: nothing on screen changes. | Remove the `focus-visible:outline-none` class, or add `focus-visible:ring-2 focus-visible:ring-pulse-500` like `SectionTabs.tsx:30` already does.



5\. \*\*LOW\*\* | `frontend/public/sw.js:97-108` | The navigation branch caches \*\*any\*\* navigation response under `/` without checking `response.ok` (the asset branch does check at line 86). A transient 500/502 from nginx or the upstream gets stored in `SHELL\_CACHE\["/"]` and is then served as the offline fallback — a user who opens the app offline after such a blip gets the error page as the app shell instead of the cached SPA. Self-heals on the next successful online navigation. | Deploy momentary 500 on `/` → user navigates (network-first, caches the 500) → network drops → offline navigation serves the 500 HTML from cache. | Wrap the `cache.put` in `if (response.ok) { … }` exactly like the immutable-asset branch.



6\. \*\*LOW\*\* | `frontend/src/ui/JalaliDatePicker.tsx:161-163` (the `required` hidden input) + consumers `frontend/src/pages/hr/PeriodsPage.tsx:142,146` | The required-date constraint is delegated to a controlled `sr-only`, `tabIndex={-1}`, `aria-hidden="true"` input. Verified in headless Chromium against the exact DOM: with the name filled and dates empty, clicking "آغاز دوره" \*\*cancels submit\*\* (the form's `onSubmit` never fires, so the modal's own `{error \&\& …}` UI can never engage), moves focus to a 1×1 px invisible element (bounding rect `\[1189, 28, 1, 1]`), and the only feedback is the native bubble anchored to a clipped, `aria-hidden` control — which screen readers are told to ignore. Chrome shows the bubble; other engines are not verified here (see below). An element with focus must not be `aria-hidden`. | HR → دوره‌های ارزیابی → آغاز دوره ارزیابی جدید → fill name, leave one date empty, click "آغاز دوره". | Do the date check in `createPeriod()` (mirror the server's `PeriodCreate.\_dates\_in\_order` and empties) and set the existing `error` state; drop the hidden input or make it a visible-but-clipped, non-`aria-hidden` validity anchor.



\## Verified correct

\- \*\*React Query cache boundaries, single-tab\*\*: `AuthContext.tsx:53` clears the cache on login and `:73` on logout — \*before\* the next user's `fetchMe`, so the second user never renders even one frame of the first user's rows. Access token lives only in module memory (`client.ts:6-13`); refresh cookie is HttpOnly; the 401→refresh-fail path does `window.location.href = "/login"` (full reload, zero memory carry-over). No component persists user data to `localStorage` — the only draft persistence is `useLocalDraft` keyed by evaluation id (`nexahr:self-assessment:${evaluationId}`), which cannot collide across users because an evaluation id belongs to one subject; and it is deleted after submit (`OpenCaseCard.tsx:193`).

\- \*\*Service worker data hygiene\*\*: `sw.js` never touches `/api/` or `/verify/` (`isNeverCached`), caches only hashed `/assets/\*` + `/icons/\*` cache-first, network-first for navigations, purges old-version caches on activate, `GET` only, and the `controllerchange` reload is loop-guarded (`pwa.ts:38-43`). Logout calls `clearAppCaches()` (`AuthContext.tsx:77`).

\- \*\*PermissionsContext is genuinely fail-closed\*\*: `isModuleEnabled` returns `?? false` (`PermissionsContext.tsx:58-63`), `can()` returns `?? false` (`:79`), the query is keyed per user id (`:71`), `ModuleRoute` renders `DisabledFeature` when the module is off \*or\* when the permissions call errored, and `AdministrationPage` additionally gates its own sections on `can()` with the loading state (`:148-157`). `ProtectedRoute` waits for `permissionsLoading` before denying a capability route (`ProtectedRoute.tsx:45-47`) — the documented inverse pattern. Frontend module keys (`periods`, `improvement\_plans`, `role\_analytics`) match `backend/app/core/modules.py` `MODULE\_KEYS` exactly.

\- \*\*Overlay keyboard paths\*\*: `Modal`, the mobile drawer (`Layout.tsx:48`), and the copilot panel (`Copilot.tsx:32-36`, `lockScroll:false` on purpose) all share `useFocusTrap` — initial focus, Tab/Shift+Tab cycle, Escape via a ref, scroll lock, and focus restoration to the opener on cleanup. `Modal` uses `role="dialog"` + `aria-modal` + `aria-labelledby` with `useId` (ReactNode titles included) and portals to `body`. The drawer closes on route change.

\- \*\*Form validation matches the server\*\* (checked pairwise, not by trusting comments): `computePreview` ≡ `compute\_result` including per-indicator weights, weight renormalization across present sections, the zero-weight-sum fallback, and `base\_weighted\_pct` semantics (`ScoreForm.tsx:153-197` vs `backend/app/services/evaluation.py:199-289`); evidence rules (min words only for scheme-required scores, max words for all) mirror `validate\_evidence` and read from the \*per-record\* `evaluation.scoring\_rules`, not today's scheme (`EvaluationDetailPage.tsx:70-89`); bonus checks (min reason length from config, max points, non-negative) mirror `validate\_bonus`; `DEFAULT\_APP\_CONFIG` equals `LEGACY\_RULES` (3/40/\[1,5], 0.6/0.4, 5/10). FastAPI 422 arrays are translated to Persian server-side (`app/core/validation\_errors.py`), so `extractErrorMessage`'s string-only handling is safe. Password rules: server `change\_password` enforces min-10 + not-current + not-username (`auth.py:254,262`); frontend `checkPassword` mirrors all three and is \*stricter\* than the server on account creation — the safe direction. `generatePassword` uses `crypto.getRandomValues` + Fisher–Yates.

\- \*\*Paired invariants checked and agreeing\*\*: frontend `resolverSeatId` ≡ backend `objection\_resolver\_field` (deputy, unless manager-path or deputy-skip → ceo); frontend scorer-seat logic ≡ `\_scorer\_seat` for all three chain shapes including `rankOf` ownership; `/me/evaluations` module-off returns an empty page and `MyEvaluationsPage` distinguishes "module off" from "no results" with distinct copy (`:352-359`).

\- \*\*Concurrent refresh safety\*\*: `rotate\_session` has a reuse-grace window, so two tabs refreshing the same jti simultaneously do not trip `RefreshReuseError`/session revocation (`backend/app/services/sessions.py:99-104`) — multi-tab \*same-user\* is handled; only cross-user (finding 1) leaks.

\- \*\*Error/empty states\*\*: `EvaluationList` (error line, skeletons, `EmptyState`, seat-filter banner with removal), `MyScoringPage` (error/skeleton/empty), `VerifyPage` (loading/invalid/valid, respects `valid:false`, documents the empty-hash case), `PdfDownloadButton` (popup-blocked fallback + error toast, sync `window.open`), `ExcelExportButton` (error toast, busy state), login error box.

\- \*\*Running it\*\*: all four CI jobs green locally — backend `ruff` + \*\*1035/1035 pytest\*\* (real PostgreSQL 17.2), launcher `ruff` + \*\*89/89\*\*, frontend oxlint 0/0 + \*\*270/270 vitest\*\* + `tsc -b \&\& vite build`, e2e API scenario "ALL PASSED" on a freshly dropped/created DB, and `scripts/ci-local.sh --check-drift` clean. `prefers-reduced-motion` is honored globally (`index.css:521-530`); skip-link present (`Layout.tsx:84-89`); mobile score buttons are 44px (`min-h-11`) with a `role="radiogroup"`, and the desktop slider is a proper `role="slider"` with arrows/Home/End and `aria-valuetext`; `motion.tr` keys, `aria-current` via `NavLink`, theme respects live system changes (`ThemeToggle.tsx:48-55`).



\## Could not check, and why

\- \*\*Safari/iOS behavior of finding 6\*\*: only Chromium is available here, so the "no native bubble at all" scenario on Safari (which lacks validation UI) is unverified; the verified facts (submit blocked, focus on invisible `aria-hidden` input) are engine-independent.

\- \*\*A real screen-reader pass\*\* (NVDA/VoiceOver with RTL): all ARIA conclusions are code-level and compiled-CSS-level; I did not run an AT.

\- \*\*Production PWA behavior on a deployed HTTPS origin\*\*: `sw.js` registers only in PROD builds; I verified the code and the local build output, but not installed-app offline flows, update prompts, or nginx CSP interplay in a real deployment.

\- \*\*UI-driven end-to-end flows\*\*: `run\_e2e.sh --api-only` exercises the API scenario (which I ran green); no headless-browser scenario drives the logged-in UI through login → queue → scoring, so behavioral verification of full flows rests on the 270 unit tests, targeted code reading, and the one browser repro I ran.

\- \*\*Dark theme on real hardware\*\*: contrast ratios are computed from the token values in `index.css`, not measured on screens; also did not audit chart SVG internals (Recharts tooltips) pixel-by-pixel in both themes.

