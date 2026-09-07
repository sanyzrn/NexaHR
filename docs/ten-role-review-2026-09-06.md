# NexaHR — 10-Role Full-System Review (Compact, Unlimited)

Repo: https://github.com/sanyzrn/NexaHR | Base branch: `main`
Review branch: `review/ten-role-full-system` | **Reviewed commit SHA: `fc4f3fe9e5ea6fa412a16b0bbc287fb24dfe18a9`** (merge commit, dated 2026-09-06 22:07:00 +0330)
Review date: 2026-09-06/07, reviewer environment documented in each role and below.
Role 04 (AI Copilot) intentionally skipped per the review contract: `backend/app/services/ai/**`, AI orchestration, context construction, confirmation UX, prompt injection, tool selection, memory and AI cost/evaluation quality are out of scope. Shared authorization, workflow, module, scoring, database, privacy and business-rule code was reviewed through normal API/UI paths.

## Environment, commands and inventory (evidence)

**Environment adaptations (behavior-neutral, per review contract):** Python 3.12.14 locally (CI: 3.11); portable PostgreSQL **16.4 with ICU** at `localhost:5434` (user `nexahr`, trust auth; CI: `postgres:16` docker on 5432 with password — the local `fa-x-icu` collation was verified present and functioning); Node v24.19.0 (CI: 20). No root access; no system PostgreSQL. All application code ran unmodified from the reviewed commit.

**CI-equivalent commands executed (mirroring `.github/workflows/ci.yml` exactly, verified via `scripts/ci-local.sh --check-drift`: all 10 commands match, no drift):**

| CI job | Commands run | Result |
|---|---|---|
| drift | `scripts/ci-local.sh --check-drift` | all 10 commands present in `ci.yml` |
| backend | `ruff check .` | All checks passed |
| backend | `pytest -q` | **1131 passed, 0 failed, 0 skipped, 0 xfailed** (6m12s) |
| launcher | `ruff check tools` | All checks passed |
| launcher | `python -m pytest tools/tests -q` | **89 passed** |
| frontend | `npm run lint` (oxlint) | 0 warnings, 0 errors (158 files) |
| frontend | `npm test` (vitest) | **285 tests / 47 files, all passed** (49.6s) |
| frontend | `npm run build` | success (index 379.01 kB / gzip 114.48; PersonCharts 381.36 kB / gzip 108.66; all routes lazy) |
| e2e-api | `alembic upgrade head` (fresh `nexahr` DB) | 57 migrations applied, single head |
| e2e-api | `python3 e2e/setup_e2e.py` | OK (evaluators, ai_hr, defective workbook seeded) |
| e2e-api | `bash e2e/run_e2e.sh --api-only` | **"E2E API FLOW: ALL PASSED"** (12 steps + double-confirm 409) |

A first backend run on a **non-ICU** PostgreSQL produced 21 failures, all `collation "fa-x-icu" ... does not exist` — purely environmental; re-run on the ICU instance: 1131/1131 green. Not an application defect.

**Inventory at the reviewed commit (verified, not from docs):** 57 Alembic revisions, single head `c1e5a9d2f70b` (linear chain, every revision has a real `downgrade()`); backend 1131 tests collected/passed, 0 skipped/xfailed; frontend 285 tests / 47 files; launcher 89 tests; e2e = 1 API scenario in CI (`e2e_api_test.py`, ALL PASSED) + browser scenario (`e2e_browser.py`) **not** in CI; CI jobs actually defined: `backend`, `launcher`, `e2e-api`, `frontend` (commands above; `paths-ignore` for docs-only pushes); snapshot version `SNAPSHOT_VERSION = 6` (`services/snapshot.py:28`); audit-event catalogue `EVENT_LABELS` = **81 entries** (`services/audit_events.py:17`). **Remote CI status for this commit could NOT be verified** (GitHub API rate-limited); a passing local run is not proof remote CI ran or passed.

**Finding inventory across the ten roles: 0 CRITICAL · 5 HIGH · 17 MEDIUM · 24 LOW (46 verified findings), plus 21 pooled proposals.** Every finding below carries its evidence status (`REPRODUCED` = executed demonstration on a disposable database / executed vitest / executed migration cycle; `SOURCE-PROVEN` = complete reachable failure established from source, callers and invariants with no unresolved runtime assumptions). All reproduction used disposable per-role databases and temporary test files that were deleted afterwards; every role verified `git status --porcelain` / `git diff` clean at the end; nothing was committed; controlled mutations (Role 11) were all restored and re-verified green.

---

## Executive Verdict

**Overall health: strong.** This codebase is engineered with unusual discipline for its size: a declarative workflow state machine whose status column is written in exactly one place; per-row `FOR UPDATE` locking on every evaluation mutation path; an audit hash chain serialized by a transaction-scoped advisory lock that could not be forked under 7 concurrent writers; a migration chain that replays cleanly from empty and showed **zero semantic model↔DB drift** across 292 columns, 44 indexes, 54 foreign keys and 15 unique constraints; UTC storage with a single, loud timezone boundary module; a test suite built on real-PostgreSQL savepoints with real tamper/race tests. All 1505 tests across four suites pass, and the CI script is provably drift-free against the workflow file.

**But green CI did not catch the two worst production defects, and that is the story of this review.** The single worst verified defect is a pair of independent bypasses of the `employee_evaluation_visibility` module — the switch whose accepted purpose is to gate *server reads* of an employee's own results and which is **OFF by default**: the plain evaluations list (FND-01-01) and the official PDF endpoint's subject branch (FND-05-01). With the default configuration, an employee who learns a record id (three independent discovery routes, one of them a 403-message oracle) can download the complete hashed legal document — per-indicator scores, the evaluator's written evidence, the evaluator's free-text comment, all stage comments — while `/api/me/evaluations` correctly answers empty and the UI hides everything. Role 11 proved by controlled mutation that these passed CI because the employee branches of exactly these two endpoints have no module-OFF test and no content assertions (FND-11-01, FND-11-02): adding the missing gate as a mutation survived 117 and 85 tests respectively. The fixes are small (a gate + a field-trim + two regression tests), but until they land, a fully green CI is actively misleading about a core privacy promise.

**Release readiness: NO-GO.** Three verified HIGH production defects block release (FND-01-01, FND-05-01, FND-02-01) and two verified HIGH test gaps (FND-11-01, FND-11-02) mean the fixes would not be validated by the existing suite either — both must be closed together. FND-02-01 is a workflow dead-end in the product UI: in the legal no-deputy chain shape, a case at `hr_approved` is on the CEO's desk by the backend's own transition table, but no button, queue, or recovery path in the UI can advance it — the approval chain stalls silently for a supported chain shape.

**Worst verified defects (release blockers):**
1. **FND-05-01 + FND-01-01 (HIGH, REPRODUCED)** — the employee-results module is bypassed by two independent server paths; full legal document disclosure to the evaluated employee in the default configuration.
2. **FND-02-01 (HIGH, SOURCE-PROVEN, API half reproduced)** — no-deputy chains dead-end at `hr_approved` in the product UI; CEO cannot finalize or return.
3. **FND-11-01 / FND-11-02 (HIGH, REPRODUCED by mutation)** — the test gaps that let the above pass CI and would let their fixes pass unvalidated.

**Immediate priorities (ordered):** (1) one shared "subject may read own result" gate applied to the list endpoint, the PDF subject branch, acknowledge and objection paths, plus the field-trim serialization for the list branch (FND-01-01/FND-05-01; Proposal CP-1); (2) module-OFF + content-semantics regression tests for both endpoints (FND-11-01/02); (3) frontend finalize/return gating on the backend's own rule — `(deputy_approved || (hr_approved && deputy_user_id === null))` — plus the CEO home pending tab and stage labels (FND-02-01; Proposal CP-2); (4) the manager-path dialog wording fix (FND-09-01) and self-assessment reachability (FND-09-06) in the same chain-shape pass; (5) the improvement-plan row lock (FND-07-01) and downgrade-path guards (FND-06-01) as fast follows.

**Material verification gaps (not hiding known defects, but bounding what "verified" means):** remote CI status for this commit is unverifiable (API rate limit); no real browser was available, so all frontend layout/visual/focus findings rest on source + jsdom vitest evidence (each such finding is labeled); no multi-instance deployment was tested (accepted single-instance); no live SMTP/SMS channel was exercised; PDF visual layout was verified at the HTML/byte layer, not visually; mutation-survival claims beyond the executed targeted selections are labeled UNVERIFIED in Role 11's limitations.

---

# ROLE 01 — Authz & Session

Repo: `/home/z/my-project/NexaHR`, branch `review/ten-role-full-system`, commit `fc4f3fe9e5ea6fa412a16b0bbc287fb24dfe18a9`.
Scope: the two-axis authorization model (UserRole chain position vs Capability administrative power), row-level visibility (`scope_evaluations_for_role`, `_can_view_personnel`), JWT + `token_version` revocation, refresh cookies/sessions, forced password change, account lockout, per-IP rate limits, and what `/metrics`, `/docs` and the public `/api/verify/{token}` expose. AI Copilot (`backend/app/services/ai/**`, AI orchestration/tool wiring) is out of scope per instructions; the shared `scope_evaluations_for_role` was examined via its normal API path.

All findings below were verified against server behavior with direct API calls (TestClient), independent of any frontend. Evidence was produced with a temporary pytest file (`backend/tests/test_review_tmp_r01.py`, 22 tests, all assertions as described) that was deleted after the run; `git status --porcelain` is empty.

## Verdict

The authorization architecture is unusually disciplined for this codebase: capabilities are re-read from the DB on every guarded request, the evaluation workflow uses a declarative transition table with per-seat assignee checks and row locks, unknown roles fail closed, and the session subsystem (rotation, reuse detection, revocation, lockout) is complete and tested. However, I found and **reproduced one HIGH access-control failure**: the `employee_evaluation_visibility` module — whose accepted purpose is to gate *server reads* of the employee's own results, and which is OFF by default — is bypassed by the plain `GET /api/evaluations` list endpoint, which returns the employee's own finalized record with the full chain-side schema. A second reproduced defect (MEDIUM) is the missing uniqueness invariant on `users.personnel_id`, which lets several accounts act as the same person in every `/api/me` subject path. A third, source-proven LOW defect is that `auth_sessions` rows are never purged. Everything else on the checklist checked out, including all the classic bypass attempts (path normalization on the forced-password-change allowlist, refresh-token reuse, token_version revocation, cross-seat approvals, capability-less accounts, deactivated accounts).

## Findings

### Top findings

**FND-01-01 | HIGH | REPRODUCED | backend/app/api/routers/evaluations.py:608-615, 629-696 | The `employee_evaluation_visibility` module gate is bypassed by `GET /api/evaluations`, disclosing finalized results (and the evaluator's summary comment) to the evaluated employee while the module is OFF.**

- **Roles/capabilities involved:** any authenticated user with `UserRole.employee` and a personnel link (the standard employee account).
- **Initial state:** module `employee_evaluation_visibility` OFF — this is the *default* (`core/modules.py:64-69`, `default_enabled=False`; no `ModuleSetting` row exists on a fresh install, and `module_states()` then takes the default). An evaluation for the linked personnel is `finalized`.
- **Action:** `GET /api/evaluations` with the employee's valid bearer token.
- **Observed (wrong):** HTTP 200 with the employee's own finalized record, serialized with the full chain-side `EvaluationRead` schema (`schemas/evaluation.py:130-176`): `general_score_pct`, `specialized_score_pct`, `final_weighted_pct`, `recommendation`, `base_weighted_pct`, `bonus_points`, `bonus_reason`, **`evaluator_comment`**, `hr_username`/`hr_display_name`, `unit_supervisor_user_id`/`deputy_user_id`/`ceo_user_id`, objection fields, `finalized_at`.
- **Expected:** the module gates *server reads* of the subject's own result (accepted decision: “employee_evaluation_visibility intentionally gates server reads, not just UI”). With the module OFF, `GET /api/me/evaluations` correctly returns `{"total": 0, "items": []}` (`me.py:69-84`) and `GET /api/evaluations/{id}` correctly 403s the subject via `ensure_not_deciding_about_oneself` — only the list endpoint leaks. The dedicated employee view `MyEvaluationRead` (`schemas/evaluation.py:244-268`) deliberately omits `evaluator_comment` and chain identity fields; me.py:1-13 states chain-internal comments stay private from the subject.
- **How to reach it:** any employee with a token calls `/api/evaluations` directly (curl); no frontend page is needed — the frontend's employee page uses the gated `/me/evaluations` (`frontend/src/api/queries.ts:348`). The leak also hands out the record `id`, which unlocks the (deliberately open) subject PDF download `GET /api/evaluations/{id}/summary.pdf` (evaluations.py:1577-1588, `is_subject` branch), compounding the disclosure — under module-off the employee otherwise has no way to learn the id.
- **Guards searched:** `list_evaluations` applies only `scope_evaluations_for_role` + filters — no module check (evaluations.py:646-666); the employee branch of `scope_evaluations_for_role` (608-615) has no module check either; no middleware inspects modules; existing tests only exercise the module gate on `/api/me` (`tests/test_module_switches.py:130-157`), and `tests/test_employee_self_view.py:89-118` (which runs with the module *on* via the `employee_view_on` fixture) asserts only that *other people's* records are excluded, not that the module gates this route.
- **Evidence:** temp test `test_r01_employee_result_leak_via_list_endpoint` (REPRODUCED): with the module explicitly OFF, `/api/me/evaluations` → `total == 0`, while `/api/evaluations` → the employee's own record with `final_weighted_pct != None` and `evaluator_comment == "نظر محرمانه ارزیاب"` (a comment the supervisor wrote via `PATCH /api/evaluations/{id}/evaluator-comment`); detail endpoint → 403. Companion test confirmed no cross-person leak (only own id in the list).
- **Fix:** (a) gate the employee branch — in `list_evaluations` (or by giving `scope_evaluations_for_role` a `db` argument) return an empty page for `UserRole.employee` unless `is_module_enabled(db, "employee_evaluation_visibility")`, mirroring `me.py:74`; (b) serialize employee-visible rows with the reduced `MyEvaluationRead` field set (at minimum drop `evaluator_comment`, `hr_username`, chain seat user ids) so the two employee read paths cannot disagree again. Add a regression test with the module off against `/api/evaluations`.

**FND-01-02 | MEDIUM | REPRODUCED | backend/app/api/routers/users.py:156-203 (create), 253-260 (update); models/user.py:25-28; migration d7e3c81f6a94 | No uniqueness invariant on `users.personnel_id` — multiple accounts can be linked to the same person and all of them act as that person in every subject (“/api/me”) path.**

- **Roles/capabilities involved:** any `manage_users` holder (default HR accounts; also any `support` account granted `manage_users`).
- **Inputs:** `POST /api/users {"username": "second", "password": ..., "role": "employee", "personnel_id": P}` where personnel P already has a linked account; or `PATCH /api/users/{id} {"personnel_id": P}` re-pointing an existing account onto an already-linked personnel.
- **Initial state:** personnel P with one linked active account.
- **Action:** the two calls above, through the normal API.
- **Observed (wrong):** both succeed silently (201/200). Verified three accounts simultaneously linked to one personnel. Every linked account then passes `require_own_personnel` (deps.py:88-127) and the subject match `record.subject_personnel_id == current_user.personnel_id` (`me.py:308-338`), so *any* of them can: view the person's finalized results (`/api/me/evaluations`), see the open case (`/api/me/evaluations/open`), **submit the one-shot self-assessment** (`POST /api/me/evaluations/{id}/self-assessment`), **acknowledge the result** (official “employee has seen the result” record), and **file/miss the objection** within the window. Whoever acts first consumes the one-shot actions; the real person's own view is silently represented by someone else.
- **Expected:** one person — one account. A second link must be rejected (400/409) exactly like duplicate usernames are (users.py:162-166) and duplicate personnel codes are in the import path.
- **Guards searched:** the only link guard is `ensure_user_link_is_not_self_evaluation` (`services/self_evaluation.py:286-315`), which blocks only the evaluator↔subject overlap; there is no unique constraint on `users.personnel_id` in the model, in any migration (d7e3c81f6a94 adds only the FK), or in `create_user`/`update_user`; `personnel_import.py` cannot produce the state (it creates accounts only for newly created personnel, lines 574-636); `POST /api/personnel` with account creates the personnel fresh. No test covers duplicate linkage.
- **Evidence:** temp test `test_r01_two_accounts_can_link_to_same_personnel` (REPRODUCED): second `POST /api/users` → 201, third via `PATCH` → 200, `SELECT users WHERE personnel_id = P` returns 3 rows, and `/api/me/evaluations/open` works from the first account after a case is opened (all three would behave identically).
- **Fix:** in `create_user` and `update_user`, reject `personnel_id` values already linked to another *active* user with a clear Persian 400 (“این پروندهٔ پرسنلی به حساب دیگری متصل است”); optionally back it with a partial unique index on active rows. Audit already records the link change (`user_updated` old/new values include `personnel_id`).

### Additional verified findings

**FND-01-03 | LOW | SOURCE-PROVEN | backend/app/services/sessions.py:109-117; backend/app/services/scheduled.py:280-291 | `auth_sessions` rows are never purged — unbounded growth and indefinite retention of per-session IP and user-agent.**

- Every refresh rotation inserts a new `AuthSession` row and keeps the rotated parent (`sessions.py:109-117`); revoked and expired rows are likewise retained. Exhaustive search over all `AuthSession` usages in the backend shows exactly one deletion site: `users.py:373`, which only runs when an account is *deleted* (accounts with audit history can never be deleted, users.py:360-370). The scheduled sweep purges `login_attempts` (`scheduled.py:291`) but has no `auth_sessions` job; nothing else removes rows.
- Consequence: (a) unbounded table growth — access tokens expire after 30 minutes (`core/config.py:30`), so an active device rotates its refresh session whenever the access token lapses, producing up to dozens of rows per user per day; (b) each row stores `ip` and `user_agent` (`models/auth_session.py:33-37`) that are retained forever after the session is dead — a data-minimization gap for a system holding employee data.
- **Fix:** extend the sweep (or rotate-time cleanup) to delete rows where `expires_at < now() - interval` or `revoked_at/rotated_at` is older than a retention window (e.g., 90 days), and log the count like `stale_login_attempts_purged`.

## Verified correct

Mapped to the role checklist; each item states the check and the evidence (my temp tests are referenced by name; all 22 passed before deletion; the baseline suite of 1131 tests was green per the worklog).

1. **Two-axis model — chain role vs administrative capability.**
   - Guards: `require_roles` (deps.py:130-139), `require_chain_stage` via `may_act_at` (deps.py:142-166), `require_capability` (deps.py:169-193), `require_role_or_capability` (deps.py:196-221), `audit_log_reader` (deps.py:234-260). Capabilities are read from the DB on every guarded request (`authorization.capabilities_of`), so grants/revocations take effect immediately.
   - Fail-closed for the `support` role: `GET /api/evaluations` → 403 (`scope_evaluations_for_role` raises for unknown roles, evaluations.py:616-619), `GET /api/personnel` → 200 with `total == 0` (personnel.py:216-222 returns empty when the role has no access column), `GET /api/audit-log` and `/api/users` → 403 (temp test `test_r01_support_role_fail_closed`). A support account *with* a personnel link still gets 403 on `/api/me/*` (deps.py:111-118; temp test).
   - HR without capabilities is refused on capability-gated routes (`/api/users`, `/api/audit-log` → 403; temp test `test_r01_hr_without_capability_is_refused_but_legit_granted`), while `require_role_or_capability` is deliberately OR — HR keeps its daily job (personnel/access chain writes succeed, 200) and a capability-less `support` account is refused (403) (temp test `test_r01_cross_seat_and_capability_negative`). Employee-role users cannot hold capabilities at all (administration.py:172-176; baseline `test_capabilities.py`).
   - Baseline HR capabilities are exactly `manage_users, manage_personnel, manage_scoring` (`authorization.py:12-18`, migration f2a7d3c9e861) — the audit log and modules are administrative powers that must be granted explicitly; the frontend hides those menu items behind `my-permissions` (nav.tsx:212-215 requires `view_audit_log`/`view_diagnostics`). Consistent, deliberate design.
2. **Complete route inventory + public-route statement.** Enumerated all routes via the app's route table (dependencies introspected programmatically at the reviewed commit). **Public routes, and only these:** `/api/health` (liveness, no deps), `/api/health/ready` (readiness; no auth — returns DB pool stats, migration head, last sweep timestamp), `/api/auth/login` (rate-limited 10/min/IP), `/api/auth/refresh` (30/min/IP, requires valid refresh cookie), `/api/auth/logout` (requires only the refresh cookie to do anything), `/api/verify/{token}` (30/min/IP, only finalized records, non-sensitive fields), `/metrics` (404 when `METRICS_TOKEN` unset; otherwise Bearer-token gated), and `/docs`, `/redoc`, `/openapi.json` (present only when `ENVIRONMENT != "production"`, main.py:60-68). Every other route requires `get_current_user` or a stronger guard:

   | Router | Endpoints (method + path, abbreviated) | Guard |
   |---|---|---|
   | auth | POST login/refresh/logout; POST change-password; GET me, sessions; DELETE sessions/{id} | public / AUTH (row-checked: sessions matched to `current_user.id`, 404 otherwise) |
   | users | GET “”, export.xlsx; POST “”; PATCH {id}; POST {id}/unlock; DELETE {id} | CAP(manage_users) |
   | administration | GET my-permissions; separation, capabilities(+PUT), modules(+PUT), policy(+PUT), integrations(+PUT,+test) | AUTH / CAP(manage_capabilities) / CAP(manage_modules) / CAP(manage_integrations) |
   | admin | run-scheduled-jobs, scheduler-runs, delivery-queue | CAP(view_diagnostics) |
   | personnel | GET “” (row-scoped); GET {id} (row-scoped via `_can_view_personnel`); org-units, sites, export.xlsx, import*, POST “”, PATCH {id}, invite-self-assessment, {id}/access GET/PUT | AUTH / ROLECAP(hr, manage_personnel) |
   | evaluation_access (nested under /api/personnel/{id}/access) | GET, PUT | ROLECAP(hr, manage_personnel) |
   | evaluations | GET “” (row-scoped via `scope_evaluations_for_role`); GET {id} (row-scoped via `_ensure_can_view`); export.xlsx ROLE(hr); POST “”, submit STAGE(unit_supervisor); hr-approve/claim/handover ROLE(hr); deputy-approve STAGE(deputy); ceo-finalize STAGE(ceo); return/cancel/extend/reassign/resolve-objection ROLE(hr,deputy,ceo); PUT scores, PATCH evaluator-comment/special-score AUTH (+ `_is_the_scorer`); GET summary.pdf AUTH (+ subject/HR rule); POST comments AUTH (+ stage/owner rules) | see notes |
   | me | evaluations GET, open GET, self-assessment GET/POST, object POST, acknowledge POST, improvement-plans GET | `require_own_personnel` + own-record 404 + module gates (visibility/ack/objections/self_assessment) |
   | dashboard | overview/pipeline/period-trend/stage-stats/expiring-contracts/reports ROLE(hr); personnel/{id}/radar|trend|in-progress AUTH + `_can_view_personnel`; role-overview AUTH (role-scoped; self cards module-gated) | mixed |
   | analytics | my-scoring ROLE(unit_supervisor, deputy); executive ROLE(ceo, deputy) | roles + cohort suppression |
   | reports (dashboard/report/*) | summary, indicator/{id}, employee-vs-unit, export.xlsx | ROLE(hr) |
   | improvement_plans | list/detail ROLE(hr,sup,dep,ceo) (row-scoped: owner or hr); create/patch/cancel/complete/goals ROLE(hr); goal PATCH owner-scoped | mixed |
   | indicators | GET “” AUTH; POST/PATCH/DELETE/reorder/replace/framework CAP(manage_scoring) | mixed |
   | scoring_schemes | all | CAP(manage_scoring) |
   | periods | all | ROLE(hr) (+ module gate `periods`) |
   | org_units | all | ROLECAP(hr, manage_personnel) |
   | audit_log | GET “” audit_log_reader (view_audit_log full / view_diagnostics system-events only); integrity, export.xlsx CAP(view_audit_log) | mixed |
   | notifications | list/read/read-all/preferences | AUTH (rows matched to `current_user.id`) |
   | config | GET | AUTH |
   | verify | GET {token} | public, rate-limited |
   | ai | (out of scope) chat/conversations/etc. AUTH; settings/access CAP(manage_ai) | — |
3. **JWT + `token_version` revocation.** `get_current_user`: signature + `type=="access"` + numeric `sub` (fail-closed 401, no 500 on tampered sub — verified with a hand-built token), user existence, `is_active`, and `tv == user.token_version` (deps.py:52-67). Password reset by HR bumps `token_version`, revokes all sessions and sets `must_change_password` (users.py:272-279) — verified: the old access token 401s **and** the old refresh cookie 401s (temp test `test_r01_token_version_bump_revokes_access_and_refresh`). Self password change does the same (auth.py:267-271; baseline `test_session_security.py`). Personnel separation bumps `token_version` + revokes sessions + deactivates (personnel.py:586-590). The token's `role` claim is never used for authorization (grep over `app/` — only `tv`, `type`, `sub`, `jti` are read), so stale claims cannot grant anything.
4. **Deactivation & role changes.** `is_active` and `role` are re-read from the DB on every request: deactivating an account kills its live access token and refresh immediately (401s; temp test), and a role change is reflected on the live token at once (`/api/auth/me` returned the new role; temp test `test_r01_role_change_takes_effect_on_live_token`). `ensure_no_open_chain_seat` blocks role changes/deactivation of users holding open-case seats with a 409 naming the cases (evaluation.py:106-131; baseline tests).
5. **Refresh cookies & session subsystem.** Cookie: `HttpOnly`, `SameSite=strict`, `Path=/api/auth`, `Secure` in production, 7-day max-age (auth.py:75-86) — attributes verified on the Set-Cookie header. Rotation issues a new jti and marks the parent rotated with a 60s grace; reuse of a rotated/revoked/unknown token revokes the whole family (sessions.py:87-104; baseline `test_auth_sessions.py` + temp test: revoked session → 401). Logout revokes only the cookie's session and deletes the cookie with the matching path (auth.py:229-237). `GET /api/auth/sessions` lists only the caller's live sessions; `DELETE /api/auth/sessions/{id}` 404s for other users' sessions (auth.py:294-337; baseline `test_session_visibility.py`). `refresh` checks user existence, `is_active` and `token_version` before rotating (auth.py:198-206) — a revoked-token-version user cannot mint new access tokens.
6. **Forced password change.** Server-side allowlist of exactly three paths (deps.py:17-36); verified: `/api/auth/me` and `/api/administration/my-permissions` → 200 while `/api/evaluations`, `/api/users`, `/api/personnel` → 403; escaping via `POST /api/auth/change-password` works and clears the flag (temp tests). **Bypass attempts:** trailing slash `/api/auth/me/` → 307 redirect to the exempt route (the request that executes is the exempt path); `//api/auth/me`, `/api/auth//me`, `/api/auth/me%00`, `/API/AUTH/ME`, `/api/auth/%2e/me` → 404 (never reach an endpoint); percent-decoded variants like `/api/au%74h/me` decode to the exempt path itself, which both the router and the guard see as the same `scope["path"]` string — structurally, routing and the allowlist can never disagree, so no normalization bypass exists. Accounts created by HR or by import always start with `must_change_password=True` (users.py:189, personnel_import.py:633); login works for them and returns the flag.
7. **Account lockout.** Per-username DB counter with atomic upsert + `FOR UPDATE` (login_guard.py:76-93) — shared across workers and restarts. Verified: 5 wrong passwords → account locked; the *correct* password is then refused with 429 + `Retry-After` (checked before password verification, auth.py:121-130); unknown usernames are counted identically (no timing oracle; dummy-hash equalization for missing users); unlock via `POST /api/users/{id}/unlock` (manage_users) is audited and restores login; a successful login clears the counter (temp tests + baseline `test_login_lockout.py`, 14 tests incl. concurrency).
8. **Per-IP rate limits.** `slowapi` with `get_remote_address`: login 10/min, refresh 30/min, verify 30/min (AI chat 20/min, out of scope). 429 handler increments a metric and returns a Persian message + `Retry-After` (main.py:77-84). In-process storage is an accepted decision (single-instance); production config forbids `FORWARDED_ALLOW_IPS="*"` so X-Forwarded-For spoofing cannot bypass per-IP limits behind a trusted proxy (config.py:230-242).
9. **`/metrics`.** Returns 404 when `METRICS_TOKEN` is unset (endpoint effectively does not exist), 401 on wrong token, 200 with the correct token — compared with `secrets.compare_digest` (constant time; main.py:214-232; temp test `test_r01_metrics_token_gate`). Cardinality discipline: path *templates* not raw ids; unknown paths collapse to `<unmatched>`; labels never contain scores/names/ids (metrics.py).
10. **`/docs`, `/redoc`, `/openapi.json`.** Disabled entirely in production (`_docs_disabled`, main.py:60-68); verified open (200) in development. Exposure is environment-gated, as documented.
11. **Public `/api/verify/{token}`.** Token is `secrets.token_urlsafe(24)` (192-bit) minted only at finalization (evaluations.py:983-985), never the sequential `evaluation_code` (enumeration explicitly avoided); only `finalized` records match; response contains only non-sensitive summary fields (verify.py:15-50); 30/min/IP rate limit; 404 for unknown/non-finalized (verified). This is the QR-code verification surface and is deliberately public.
12. **Row-level visibility — evaluations.** `scope_evaluations_for_role` is an allowlist that raises 403 for unknown roles (support), scopes supervisor/deputy/ceo to their seat, gives HR everything except (a) their own subject record and (b) open records of the HR unit (`IS_SHIELDED_FROM_HR_PANEL`, mirroring the in-body guard `hr_panel_is_shielded`), and gives employees only their own *finalized* records (evaluations.py:579-619). Verified: supervisor A sees only their seat's case (supervisor B sees an empty list; deputy/ceo see their seat); employee sees only own id; the same scope is applied to `export.xlsx` (evaluations.py:699-746). Detail endpoint `_ensure_can_view` blocks the subject (403) and non-seat roles; the subject PDF download is deliberately allowed (documented decision, evaluations.py:1566-1588).
13. **Row-level visibility — personnel/dashboard.** `_can_view_personnel` (personnel.py:120-140): HR all; others only if seated in the personnel's current access or in a historic record seat; used by `GET /api/personnel/{id}` and the dashboard radar/trend/in-progress endpoints (dashboard.py:494-582) — all 403 otherwise. `GET /api/personnel` list for non-HR roles joins the role's access column and returns an empty page for employee/support (personnel.py:213-239). Improvement plans are owner-or-HR scoped (improvement_plans.py:89-94, 167-168). Notifications rows are matched to `current_user.id` (mark-read 404 otherwise).
14. **Workflow authorization.** Declarative `TRANSITIONS` with per-seat `assignee_field` + `may_act_at` rank rule; only the HR queue seat is claimable-if-unassigned; every HR transition re-applies `ensure_hr_may_handle` inside `apply_transition` so the AI path cannot skip it (workflow.py:493-517). Verified negative cases: CEO (rank above deputy but not seated) → 403 on deputy-approve; deputy → 403 on hr-approve; a supervisor who is not the scorer → 403 on score writes; employee → 403 on create/submit/approve/finalize/scores. Verified positive cases: deputy opens and scores a manager-path case (201); supervisor with a personnel link uses `/api/me/evaluations/open` (200). Self-evaluation guards (evaluator≠subject) are enforced at access-write time, user-link time, and by DB triggers (c3e8b1a76d94); redundant-seat pairs rejected (self_evaluation.py:57-107).
15. **Audit-log access split.** `view_audit_log` = full log; `view_diagnostics` = system events only, with a second belt (`evaluation_record_id IS NULL`) so even misclassified events can't leak evaluation content (audit_log.py:194-201); export/integrity require `view_audit_log` (audit_log.py:225-256). Security events (login success/failure, lockout, unlock, password change, session revocation, user CRUD, capability changes, module toggles) are all logged with actor ids.
16. **Login endpoint.** Lock checked before password verification; distinct messages for unknown username vs wrong password (accepted decision); inactive accounts → 403 after successful verification (temp test); dummy-hash verification for unknown users to equalize timing.

Coverage bounds: single-process TestClient runs against a disposable migrated DB (`nexahr_r01`); no multi-worker deployment tests; AI-copilot-only paths skipped per instructions; frontend consulted only to confirm which endpoints the employee UI calls.

## Could not check, and why

1. **Multi-instance rate-limit/lockout behavior (N workers, shared `RATE_LIMIT_STORAGE_URI`).** Reason: only a single-process TestClient was run; the accepted decision states in-process counters are fine for single-instance deployment. Potential impact if deployed multi-instance without the URI: per-IP limits scale by worker count. Concrete check needed: run 2 uvicorn workers behind a load balancer with and without `RATE_LIMIT_STORAGE_URI` and confirm the login limit stays 10/min globally (lockout is DB-based and unaffected).
2. **Raw-network path normalization against uvicorn/nginx.** TestClient/httpx normalizes some paths client-side (e.g. `/api/auth/./me`), so that variant could not be exercised as a raw request. The structural argument stands (router and guard read the identical `scope["path"]`), but a belt-and-braces check would be `curl --path-as-is` against a live server plus an nginx that does not merge slashes. Potential impact: none identified — any mismatch would have to make the router match a non-exempt route while the guard sees an exempt string, which requires two different strings for the same request.
3. **Timing side-channel of login responses.** The dummy-hash equalization (auth.py:157) is verified in source, but no statistical timing measurement was performed. Potential impact: negligible-to-none; a concrete check would be a micro-benchmark of 401 latencies for existing vs non-existing usernames.
4. **AI Copilot authorization surfaces** (`services/ai/**`, `routers/ai.py`, confirmations, tool wiring). Out of scope per instructions; only the shared `scope_evaluations_for_role` and `apply_transition` guards (which the AI path also routes through) were reviewed. Potential impact: un-reviewed AI-specific guards; a concrete check would be a dedicated AI-path review (another role).
5. **Frontend token storage / XSS-to-token surface** (`api/client.ts`). Out of this role's scope (frontend correctness roles). Server-side mitigations that were checked: refresh cookie is HttpOnly+SameSite=strict+path-scoped, so an XSS cannot steal the refresh token; access tokens are 30-minute short-lived. A concrete check for the frontend role: confirm the access token lives only in memory (not localStorage).
6. **`ai_encryption_key` / JWT-secret rotation procedures.** Deployment/crypto-ops topic; the production guard for JWT secret length was verified in source (config.py:200-217), but no rotation drill was run.

## Proposals

1. **Throttle `POST /api/auth/change-password`** — outcome: an attacker holding a stolen (30-minute) access token cannot use the endpoint's 400 responses to brute-force the user's *current* password at line speed; the verification cost then rests on Argon2 alone. Change: add `@limiter.limit("10/minute")` (same pattern as login) and/or count failures via `login_guard.record_failure`. Files: `backend/app/api/routers/auth.py`. Surface: `POST /api/auth/change-password` (currently unthrottled and uncounted — wrong current-password attempts are not tracked by the lockout, unlike login). Risks: a legitimate user mistyping their current password several times gets briefly throttled; mitigate with a lenient limit. Compat: none (additive decorator). Priority: LOW-MEDIUM.
2. **Slim the anonymous `/api/health/ready` response.** Outcome: an unauthenticated network probe learns only “ready/not-ready”, not pool occupancy, migration head hash, or sweep freshness. Change: keep the status code semantics (503 when unhealthy) but move `db_pool`/`migration_head`/`last_successful_sweep` details behind the metrics token or the `view_diagnostics` capability. Files: `backend/app/main.py` (ready endpoint). Surface: `GET /api/health/ready`. Risks: dashboards that scrape these fields must switch to `/metrics`; Kubernetes/liveness probes only need the status code. Compat: additive if the fields move rather than disappear. Priority: LOW.

# ROLE 02 — Workflow State Machine

Reviewed commit: `fc4f3fe9e5ea6fa412a16b0bbc287fb24dfe18a9` (branch `review/ten-role-full-system`).
Scope: `backend/app/services/workflow.py` (TRANSITIONS / `ensure_transition_allowed` / `apply_transition`), all transition endpoints in `backend/app/api/routers/evaluations.py`, `models/chain.py`, `models/evaluation.py`, supporting services (`evaluation`, `self_evaluation`, `evaluation_window`, `bulk_evaluation`, `scheduled`, `personnel` separation path), and the frontend status→action mapping. AI Copilot (`services/ai/**`) excluded as instructed, although it shares `apply_transition` (its guards therefore run inside the shared function).

**Chain shapes covered.** The review context names three legal shapes (full chain / manager path / CEO-direct), but the codebase explicitly supports a fourth legal shape and a cross-cutting HR-subject dimension; all were exercised:

| shape | supervisor | deputy | hr stage | notes |
|---|---|---|---|---|
| A full chain | ✔ | ✔ | ✔ | `test_workflow.py`, `test_end_to_end_chain.py` |
| A′ full chain, HR subject | ✔ | ✔ | ✖ (`hr_review_skipped`) | `test_hr_subject_chain.py` |
| B manager path | ✖ | ✔ | ✔ | `test_manager_path_hr_review.py` |
| B′ manager path, HR subject | ✖ | ✔ | ✖ | `test_hr_subject_chain.py` |
| C CEO-direct | ✖ | ✖ | ✔ (HR finalizes) | `test_ceo_only_chain.py`, `test_direct_ceo_hr_finalization.py` |
| C′ CEO-direct, HR subject | ✖ | ✖ | ✖ | `test_direct_ceo_hr_finalization.py::test_an_hr_unit_subject_still_ends_with_the_ceo` |
| D no-deputy | ✔ | ✖ | ✔ | `test_no_deputy_chain.py` — legal, creatable via UI and API |
| D′ no-deputy, HR subject | ✔ | ✖ | ✖ | reachable via `submit_hr_subject` → `hr_approved` → CEO finalizes |

## Verdict

The declarative transition table is **fundamentally sound**. Exhaustive mapping of every (chain shape × status × actor × action) combination found **no backend state-machine defect**: no transition is reachable in a wrong shape, no stage can be double-completed, no terminal state can be escaped, no record can get stuck without a legal backend action, and ownership/seat rules are enforced consistently by `ensure_transition_allowed`. Three real defects were found at the **edges between layers**: one frontend gating bug that stalls the approval chain in the product UI (legal shape D), one HTTP-layer routing asymmetry that hides a legal transition from a legitimately seated actor, and one notification gap. All three are reproduced or source-proven with defensible failure paths.

Transition map verified as correct (shape → status → who may act → next state):

| status | A / A′ | B / B′ | C / C′ | D / D′ |
|---|---|---|---|---|
| `draft` | sup `submit`/`submit_hr_subject` → `submitted`/`hr_approved` | dep `manager_submit`/`manager_submit_hr_subject` → `submitted`/`deputy_approved` | ceo `ceo_submit`/`ceo_submit_hr_subject` → `submitted`/`deputy_approved` | sup `submit`/`submit_hr_subject` → `submitted`/`hr_approved` |
| `submitted` | HR queue `hr_approve` → `hr_approved`; `hr_return` → `draft` | HR `hr_approve_manager` → `deputy_approved`; `hr_return` → `draft` | HR `hr_finalize_direct_ceo` → `finalized`; `hr_return` → `draft`; CEO `ceo_return_ceo_only` → `draft` | HR `hr_approve` → `hr_approved`; `hr_return` → `draft` |
| `hr_approved` | dep `deputy_approve` → `deputy_approved`; `deputy_return`→`submitted` (A) / `deputy_return_hr_subject`→`draft` (A′) | unreachable | unreachable | CEO `ceo_finalize` → `finalized` (guard `deputy_user_id is None`, workflow.py:309-322) |
| `deputy_approved` | CEO `ceo_finalize` → `finalized`; `ceo_return` → `hr_approved` (A) / → `hr_approved` then dep-return-to-scorer (A′) | CEO `ceo_finalize`; `ceo_return_manager` → `submitted` (B) / `ceo_return_manager_hr_subject` → `draft` (B′) | CEO `ceo_finalize` → `finalized`; `ceo_return_ceo_only` → `draft` (C′; C legacy) | unreachable |
| `finalized` / `cancelled` | terminal — no outgoing transition, all mutation endpoints refuse (reproduced) | same | same | same |

Findings: **1 HIGH, 1 MEDIUM, 1 LOW** (all in UI/HTTP edge layers; zero in TRANSITIONS itself).

## Findings

### Top findings

**FND-02-01 | HIGH | SOURCE-PROVEN (frontend) + backend half REPRODUCED | `frontend/src/pages/EvaluationDetailPage.tsx:241-245` (with `frontend/src/pages/ceo/CeoHomePage.tsx:137-142`, `frontend/src/components/WorkflowStepper.tsx:12-17`, backend counterpart `backend/app/services/workflow.py:309-322`)**
*What breaks:* In the legal no-deputy chain shape (supervisor + CEO, `deputy_user_id IS NULL` — shape D, supported and tested by `test_no_deputy_chain.py`), a case parked at `hr_approved` is legally on the **CEO's desk for finalization** (`ceo_finalize` accepts `hr_approved` when `deputy_user_id is None`). The frontend, however, gates the only "تأیید نهایی" button in the entire app on `evaluation.status === "deputy_approved" && evaluation.stage === "ceo_final"` (`canCeoFinalize`, EvaluationDetailPage.tsx:241-245) and shows the `ReturnBox` only when an approve-button exists (line 528). For this state the API returns `status="hr_approved"`, `stage="deputy_review"`, `deputy_user_id=null` (reproduced in temp test `test_no_deputy_chain_hr_approved_feeds_the_ui_wrong_gate_inputs`), so no button of any kind renders for the CEO. Compounding it: the CEO home "در انتظار تأیید نهایی" tab filters `status: "deputy_approved"` only (CeoHomePage.tsx:139), so the case is not listed there either, and the stage stepper/labels say "بررسی معاونت" for a chain that has no deputy (status→stage map `STAGE_BY_STATUS`, `frontend/src/types.ts:330-336`, mirror of `schemas/evaluation.py:20-28`).
*Actor/chain/initial state/action:* CEO user, chain shape D (supervisor + CEO, HR review present), record at `hr_approved`, action = "finalize" (or "return").
*Observed (source-proven):* detail page renders no finalize, no return, no recovery box (HR-only) — the approval chain is dead-ended in the product UI. The SLA sweeper even notifies the CEO to act (`scheduled._current_owner_ids` correctly maps `hr_approved` to `owner_after_hr_review` = CEO) and links to this very buttonless page.
*Expected:* CEO sees the finalize (and return) action at `hr_approved` when `deputy_user_id === null`, exactly as the backend transition table and `test_no_deputy_chain.py::test_the_ceo_finalises_straight_from_hr_approval` define.
*How to reach it:* HR saves an access row with supervisor + empty deputy (the UI chain editor explicitly allows it — `PersonnelPage.tsx:203-205,243-244`, only a note when *both* middle seats are empty, line 186); supervisor scores and submits; HR approves (`hr_approve` guard `not is_manager_path` passes) → `hr_approved`. From here no UI action can advance the case (HR's recovery box can only cancel; reassign of the deputy seat is refused with a misleading "مسیر «مدیر»" message because `previous_user_id is None`, evaluations.py:1498-1502 — this chain is *not* the manager path).
*Evidence:* backend legality: repo test + my temp test (API `POST /ceo-finalize` → 200 from `hr_approved` in shape D); UI inputs reproduced (`status`/`stage`/`deputy_user_id` as above); frontend grep shows `/ceo-finalize` is called from exactly one place (EvaluationDetailPage.tsx:652) gated by `canCeoFinalize`.
*Fix:* gate the CEO actions on the same rule the backend uses: allow finalize when `(status === "deputy_approved" || (status === "hr_approved" && deputy_user_id === null)) && ceo_user_id === user.id`; make the pending tab, stage label and stepper chain-shape-aware (no deputy ⇒ no "معاونت" step), and fix the reassign error message for the no-deputy shape.

**FND-02-02 | MEDIUM | REPRODUCED | `backend/app/api/routers/evaluations.py:1015-1019` (and `:1661-1665`)**
*What breaks:* The return endpoint maps action by **role**, while approvals map by **chain seat** (`require_chain_stage` + TRANSITIONS). A user whose account role is `ceo` but who is legitimately seated in the **deputy seat** (explicitly supported: `upsert_access` accepts it because `may_act_at(ceo, deputy)` is True, `backend/app/api/routers/evaluation_access.py:42`; `deputy-approve` endpoint uses `require_chain_stage(UserRole.deputy)` which passes for role `ceo`) can **approve** a case at `hr_approved` (reproduced: 200) but **cannot return** it: `/return` picks `ceo_return` for them (`_RETURN_ACTION_BY_ROLE[ceo]`), which is only legal from `deputy_approved` → 403, while the state machine itself permits `deputy_return` for exactly this user (reproduced: `ensure_transition_allowed(record, "deputy_return", CurrentUser(id=…, role=ceo))` returns the spec). The same role-keyed table also blocks them from leaving a stage comment (`add_comment`'s `stage_by_role` routes role `ceo` to `ceo_final`/`deputy_approved`, evaluations.py:1661-1665).
*Actor/chain/initial state/action:* CEO-role user seated as deputy, any chain with a filled deputy seat (full chain A/A′ are the realistic cases), record at `hr_approved`, action = POST `/return` (and POST `/comments`).
*Observed:* 403 "این ارزیابی در مرحله تأیید نهایی توسط شما نیست" for a user for whom `deputy_approve` succeeds one endpoint earlier.
*Expected:* the return endpoint should resolve the action by the seat the user occupies (try the seat-derived transition, as `submit`/`hr-approve` do), so an actor who can approve can also reject.
*How to reach it:* PUT `/api/personnel/{id}/access` with `deputy_user_id` = a `ceo`-role account (200, reproduced), run the chain to `hr_approved`, POST `/return` as that account.
*Evidence:* temp test `test_ceo_role_user_seated_as_deputy_can_approve_but_cannot_return` (approve 200, return 403, direct `ensure_transition_allowed("deputy_return")` passes).
*Fix:* in `return_evaluation`, derive the action from the caller's seat rather than role alone (e.g. if `current_user.id == record.deputy_user_id` and status is `hr_approved`, route to `deputy_return`; keep role fallbacks for the CEO seat), and mirror that in `add_comment`.

**FND-02-03 | LOW | REPRODUCED | `backend/app/api/routers/evaluations.py:1210-1214`**
*What breaks:* `extend-submission` builds its notification target list as the 1-tuple `(record.unit_supervisor_user_id or record.deputy_user_id,)` — for a CEO-direct chain both are `None`, so the extension succeeds (200) but **nobody is notified**, and the only person who must now submit before the new deadline — the CEO, who is the first scorer — never learns the deadline changed.
*Actor/chain/initial state/action:* HR, CEO-direct chain (C) at `draft` (period-bounded), action = POST `/extend-submission`.
*Observed:* 0 notifications of type `submission_window_extended` for the CEO-scorer (reproduced); control direction: supervisor-scorer chain produces exactly 1.
*Expected:* notification target = the actual scorer (`scorer_field(...)` → `ceo_user_id` in shape C), same rule used everywhere else (`scheduled._current_owner_ids`, `notify_for_workflow_action`).
*Fix:* `targets = [getattr(record, scorer_field(record.unit_supervisor_user_id, record.deputy_user_id))]`.
*Impact:* deadline change silently invisible to the sole submitter; state itself remains correct (window math is right), hence LOW.

### Additional verified findings

No further verified defects. Candidate issues investigated and dropped for lack of a defensible failure path:
- `hr_return` in the CEO-direct chain (HR sends the case back to the CEO-scorer from `submitted`) — intentional, mirrored by `ceo_return_ceo_only`, both tested (`test_ceo_only_chain.py`).
- `hr_claim` on records at `draft`/`hr_approved`/`deputy_approved` (stages where HR has no action) — sets an owner early; queue lockout is the documented claim semantics, no wrong state results.
- Scores/evaluator-comment autosave still allowed after the submission window closes — harmless by design: the window gates only `submit` and self-assessment (me.py:212), and nothing can reach `finalized` without `submit` (verified by the window test).
- Period `close` not gating submissions — explicitly documented trade-off (`periods.py:253-278` warning with `force`).
- Threaded comment replies allowed on finalized/cancelled cases — by design for objection dialogue; the archived PDF renders from the immutable `final_snapshot` (documents.py:55), so the signed document cannot change.

## Verified correct

All of the following were verified by direct code tracing **and** executable tests (repo suite: 1131 passing; my temporary suite: 11 passing, listed below), across all chain shapes and the HR-subject dimension:

1. **Single source of truth for status writes.** `EvaluationRecord.status` is assigned in exactly one place — `apply_transition` (workflow.py:580). No router, service, sweep or script mutates it directly (grep-verified). Everything goes through TRANSITIONS, including separation auto-cancel (personnel.py:584).
2. **Terminal states are airtight.** From `finalized` and from `cancelled`, all 15 mutation endpoints refuse (submit, hr-approve, deputy-approve, ceo-finalize, return, cancel, reassign, hr-claim, hr-handover, extend-submission, scores, evaluator-comment, special-score — reproduced in both directions). Double-cancel → 400; a replacement case can be opened after cancel/finalize (unique partial index frees the slot, `uq_open_evaluation_per_personnel`).
3. **Shape guards are complete on every submit/approve transition.** `submit`/`submit_hr_subject`/`manager_submit`/`manager_submit_hr_subject`/`ceo_submit`/`ceo_submit_hr_subject` partition the (shape × hr_review_skipped) space with mutually exclusive guards; the router's action selection (evaluations.py:890-897) matches the table exactly. Wrong-shaped actors are refused (reproduced: supervisor/deputy cannot open or submit a CEO-direct case; deputy cannot approve its own manager-path scoring; CEO cannot sign its own CEO-direct work).
4. **No deputy-stage bypass.** `ceo_finalize`'s guard (workflow.py:313-316) refuses `hr_approved` whenever a deputy exists (repo test `test_a_chain_with_a_deputy_still_has_to_go_through_them`), and `deputy_approve` is unreachable when `deputy_user_id IS NULL` (assignee check denies everyone).
5. **`hr_approve` / `hr_approve_manager` / `hr_finalize_direct_ceo` partition `submitted` correctly** — including the subtle `not hr_finalizes_record` clause in `hr_approve_manager` that keeps CEO-direct cases out of a nonexistent `deputy_approved` desk. HR finalization in CEO-direct stamps the same finalization seal (snapshot, verify token, `finalized_at`), is recorded on the HR seat, and is invisible to the CEO's own finalize path (repo tests + my matrix).
6. **Return destinations are shape-correct one-step-back** for every shape: A deputy→HR queue; A′ deputy→scorer (`deputy_return_hr_subject`); B CEO→HR queue (`ceo_return_manager`); B′ CEO→scorer; C/C′ CEO or HR→scorer (`ceo_return_ceo_only`, `hr_return`); returned cases keep scores, re-enter at the right stage, and `was_returned` survives to `finalized`. (repo `test_return_flow.py`, `test_hr_subject_chain.py`, `test_manager_path_hr_review.py` + my matrices).
7. **Stage ownership & seat identity.** Every approver/return transition requires `current_user.id == <seat id>` (plus `may_act_at` rank); HR-only queue semantics with `claimable_if_unassigned`, implicit claim on first action, explicit `hr-claim` (409 if owned), `hr-handover` (open records only, active HR-role target, not the subject, not the current owner). Claim locks other HR users out of approve/return (reproduced).
8. **HR-subject shield and self-decision guards.** `ensure_hr_may_handle` (in `apply_transition` for every `allowed_role=hr` transition, plus routers) blocks HR view/claim/handover/cancel/extend/reassign/objection-resolution on open HR-unit cases; `ensure_may_administer` opens the deputy-in-chain and CEO exactly and only for shielded cases (reproduced cancel matrix: HR 403 / seated deputy 200 / CEO 200 on shielded; deputy/CEO 403 on ordinary cases; HR 200 on ordinary).
9. **Separation auto-cancel** uses the shield-bypassing `cancel_on_separation` twin under a row lock, keeps scores/comments, deactivates the account, and notifies about vacated seats (`personnel.py:530-610`, `test_recovery_after_departure.py`, `test_vacated_seats_notice.py`).
10. **Submission window.** Window = period `ends_on`, extended only forward, only at `draft`; submit and self-assessment refuse after close with the date in the message; per-case HR (or shielded-case deputy/CEO) extension re-opens exactly that case; approval stages are deliberately un-gated (documented rationale; reproduced end-to-end including late HR/deputy/CEO approvals after a closed-then-extended window).
11. **Finalization integrity.** `apply_transition` refuses `finalized` without computed results (`final_weighted_pct` + ≥1 score) and without `final_snapshot` (built in `before` by both finalization paths via the single `_stamp_finalization`); `stage_entered_at` resets on every transition (SLA sweep measures per-stage age); audit `status_changed` events on every transition; `single_decider` disclosure computed from real seats.
12. **Reassignment semantics.** Open records only; only existing seats; role-matched, active, non-subject, non-redundant replacements; scores preserved; notifications to the new owner (repo `test_cancel_and_reassign.py` + `test_recovery_after_departure.py`).
13. **Frontend/backend parity (besides FND-02-01):** `STAGE_BY_STATUS` mirrors `_STAGE_BY_STATUS`; `hrClosesTheCase` mirrors `hr_finalizes` (CEO-direct HR-finalize button correctly relabeled and danger-flagged); `canHrApprove`/`canDeputyApprove`/`canComment` mirror the server's status+seat rules for the three legal shapes they cover; objection-resolver mirror (`ObjectionPanel.resolverSeatId` ≡ `workflow.objection_resolver_field`); supervisor scoring page handles manager-path and CEO-direct scorer identity correctly (`isManagerPath`/`isCeoOnlyPath` in EvaluationDetailPage.tsx:210-224).
14. **No stuck (shape × status) pair in the backend.** Every reachable state has at least one legal actor+action (matrix in Verdict); the only UI-level dead-end is FND-02-01.

Temporary reproduction suite (deleted after the run; 11/11 passed on disposable DB `nexahr_r02`):
`test_ceo_role_user_seated_as_deputy_can_approve_but_cannot_return`, `test_no_deputy_chain_hr_approved_feeds_the_ui_wrong_gate_inputs`, `test_extension_of_ceo_direct_case_notifies_no_one`, `test_finalized_case_blocks_every_workflow_endpoint`, `test_cancelled_case_blocks_every_workflow_endpoint`, `test_window_blocks_submit_extension_recovers_and_late_approvals_pass`, `test_ceo_direct_chain_actor_matrix`, `test_manager_path_actor_matrix`, `test_hr_subject_full_chain_matrix`, `test_cancel_actor_matrix`, `test_hr_claim_locks_the_queue_to_the_claimer`.

## Could not check, and why

- **Live browser behavior of the frontend** (FND-02-01 rendered outcome, WorkflowStepper visuals): no browser test run was performed; the frontend conclusions rest on component-source gating plus the exact API inputs the components consume (status/stage/deputy_user_id), and on the repo's own vitest suite passing (285 tests). A dedicated vitest case for shape D would raise FND-02-01 from SOURCE-PROVEN to fully reproduced.
- **AI Copilot transitions** (`services/ai/**`): out of scope per instructions. Its actions route through the shared `apply_transition`, so the state-machine guards apply; parity specifics were not re-verified here (covered by `test_ai_workflow_parity.py` in the green baseline).
- **Concurrency/races** (double-click approvals, handover/claim races, FOR UPDATE lock behavior): explicitly Role 07's territory. I verified only the *semantic* layer (which transitions are legal, who owns what afterwards) and the presence of row locks on every transition path.
- **Legacy pre-migration data** (e.g. records that reached now-unreachable states such as a CEO-direct HR-subject case sitting at `submitted`, or manager-path records at `hr_approved` from before migration `a7f3c9b52d18`): no such rows can be produced through the current API, so unreachable-state handling (e.g. `hr_approve` guards) was checked by source only, not by seeded reproduction.
- **Rate-limiting, session, and audit-chain integrity**: other roles' scope; not exercised here beyond reading.

# ROLE 03 — Scoring & the Legal Document

Reviewed commit `fc4f3fe9e5ea6fa412a16b0bbc287fb24dfe18a9` (branch `review/ten-role-full-system`).
Scope: `compute_result` / scoring schemes / preview parity / final snapshot / documents / PDF / QR
verification / finalized-record readers / boundary conditions. AI copilot (`backend/app/services/ai/**`)
out of scope. All work done read-only on the repo; reproduction ran on a disposable DB
(`nexahr_r03`, alembic head `c1e5a9d2f70b`, WeasyPrint available) via a temporary pytest file
(20 tests, all passing, file deleted afterwards, `git status --porcelain` clean).

## Verdict

The scoring engine and the finalized-document pipeline are fundamentally sound: `compute_result`
applies indicator weights to both numerator and ceiling, redistributes absent-section weight,
caps the result at 100, bounds the bonus by the scheme cap and the remaining room to 100, and
derives the recommendation from half-open threshold bands that cover [0, 100] with no gap.
Scheme versioning is real: records are stamped at creation, open records keep their own rules
across a mid-cycle activation (reproduced), active/retired versions are immutable, and the
reclassification preview runs the actual `compute_result` without writing. The snapshot is
written only inside the finalization transition, is guarded by `apply_transition` (no snapshot /
no computed result → no finalization), freezes identity, signatories, scores, comments and
self-assessment, and survives personnel renames and evaluator deactivation byte-for-byte. The
archived PDF is hashed, served byte-stable, and the public QR/verify page reports the frozen
identity plus the archived document's sha256, refusing sequential evaluation codes.

Three defects found (1 MEDIUM, 2 LOW), none of which corrupt a finalized record's state, score,
identity or timestamp:

1. A legal-but-rare chain shape (CEO seated as supervisor of a directly-reported employee —
   explicitly allowed by migration `e9c47b3f1a52` and accepted by the access API with 200)
   produces an official document whose signature block lists the **same person twice**, which
   `document_signatories`' own docstring explicitly promises never happens.
2. The frontend score preview rounds ties differently from the server (`Math.round` half-up vs
   Python's banker's rounding), so on exact `.25`/`.75` midpoints the evaluator previews a
   number 0.1 away from the one that is finalized (reproduced with the real `computePreview`
   through vitest: preview 46.3/51.8 vs stored 46.2/51.7).
3. Both chain models declare a `supervisor <> ceo` CHECK constraint that the database does not
   have and whose policy the migration deliberately contradicts — schema drift invisible to the
   `test_model_schema_parity` guard because alembic's autogenerate ignores CHECK constraints.

## Findings

### Top findings

**FND-03-01 | MEDIUM | REPRODUCED | backend/app/services/workflow.py:656-688 (`document_signatories`)**

- **Actor:** any HR user with `manage_personnel` (PUT `/api/personnel/{id}/access`), then the CEO
  of the resulting chain.
- **Initial state:** one CEO user, one deputy, one HR user, one personnel "directly under the CEO".
- **Inputs:** `PUT /api/personnel/{id}/access` with `unit_supervisor_user_id = ceo.id`,
  `deputy_user_id = dep.id`, `ceo_user_id = ceo.id` (accepted, 200 — `may_act_at` lets a CEO sit
  in the supervisor seat and `_REDUNDANT_PAIRS` deliberately does not reject the (supervisor, ceo)
  pair; migration `e9c47b3f1a52` documents this shape as legal and disclosed via `single_decider`).
- **Action:** create the evaluation, score it, `submit` (CEO in supervisor seat), `hr-approve`,
  `deputy-approve`, `ceo-finalize`.
- **Observed (reproduced in `test_review_tmp_r03.py::test_supervisor_ceo_chain_double_signs_the_final_document`):**
  the final snapshot's `signatories` contains four entries with
  `[sup, HR, dep, ceo]` user ids where `signatories[0].user_id == ceo.id` and
  `signatories[3].user_id == ceo.id` — the official, hashed, QR-verifiable document prints
  **two signature lines («امضای مسئول واحد» and «امضای مدیرعامل») for one physical person**,
  implying two signatories.
- **Expected:** the docstring at workflow.py:674-675 states "در `single_decider` مدیرعامل یک بار
  می‌آید، نه دو بار: او یک نفر است و یک امضا دارد" — the CEO should appear once, with the
  dual role disclosed by the `single_decider` sentence (which *is* printed correctly).
- **Impact:** misleading signature block on the legal employment document; mitigated by the
  printed single-decider disclosure sentence and by the shipped UI (PersonnelPage filters the
  supervisor picker to `role === "unit_supervisor"`, so the shape is API-reachable rather than
  UI-reachable). No state/score/identity corruption; snapshot remains internally consistent.
- **Fix:** in `document_signatories`, de-duplicate by `user_id` (keep the higher seat's label, or
  emit one line labelled by both seats) whenever the same user occupies the supervisor and CEO
  seats; add the shape to `test_document_signatures.py` SHAPES.

**FND-03-02 | LOW | REPRODUCED | frontend/src/components/ScoreForm.tsx:177 (`round1`) vs backend/app/services/evaluation.py:267-268, 293, 311**

- **Actor:** the first-line evaluator filling the scoring form.
- **Initial state:** an active scheme giving one general indicator weight 5 (weights are a
  first-class scheme feature, `SchemeInput.indicator_weights`).
- **Inputs:** 12 general indicators: ten 1s, one 2 (weight 1 each), one 5 (weight 5) →
  `20 * 37 / 80 = 46.25` exactly (binary-exact midpoint); 8 specialized indicators all 3 → 60.0.
- **Action:** fill the form (live preview) and submit.
- **Observed (reproduced: server API stored `general_score_pct = 46.2`,
  `final_weighted_pct = 51.7`; the real `computePreview` executed through vitest returned
  `general_pct = 46.3`, `final_pct = 51.8`):** the preview the evaluator decides on differs from
  the finalized/stored number by 0.1.
- **Root cause:** Python `round()` uses round-half-to-even on exact midpoints; JS
  `Math.round(v * 10) / 10` rounds half up. All other math (indicator weights in numerator and
  ceiling, absent-section redistribution, zero-weight simple average, bonus handling) is a
  faithful mirror.
- **Expected:** identical numbers, per the module's own contract ("پیش‌نمایش محاسبه امتیازها با
  همان فرمول سرور").
- **Impact:** preview-only divergence (the stored value and the official document are
  server-computed and correct); with custom threshold bands (e.g. an upper bound of 46.3) the
  preview could show a different recommendation band than the one that gets finalized.
- **Fix:** implement round-half-even in `round1` (e.g. an explicit tie-break on
  `v * 10 === Math.floor(v * 10) + 0.5`), or have the backend send its rounding rule in
  `AppConfig` and use it.

**FND-03-03 | LOW | SOURCE-PROVEN (verified against the live DB catalog, migrations and model metadata) | backend/app/models/evaluation.py:243-246 and backend/app/models/evaluation_access.py:44-46**

- **What breaks:** both models declare `ck_evaluation_records_supervisor_not_ceo` /
  `ck_evaluation_access_supervisor_not_ceo` (`unit_supervisor_user_id IS NULL OR
  unit_supervisor_user_id <> ceo_user_id`), but the database has no such constraint — migration
  `e9c47b3f1a52` deliberately created only the (supervisor ≠ deputy) and (deputy ≠ ceo) checks
  and its docstring declares supervisor == CEO **legal** ("بیان دیگری ندارد… مجاز، ولی افشا
  می‌شود"). Verified with `pg_constraint` on a freshly migrated DB: only
  `ck_*_supervisor_not_deputy` and `ck_*_deputy_not_ceo` exist, while `Base.metadata` for both
  tables declares the third.
- **How it hides:** `tests/test_model_schema_parity.py` uses alembic `compare_metadata`, which
  does not compare CHECK constraints, so the drift cannot fail the parity suite (reproduced by
  inspection: the parity test is green while the catalog differs).
- **Failure path:** any future tooling that builds or validates the schema from model metadata
  (a `create_all`-based harness, an ORM-level `bulk_insert` with constraint checking, or a
  hand-written migration that "fixes" the drift) would silently outlaw a chain shape the system
  treats as legal and that real data may already use, turning existing rows into constraint
  violations on the next `UPDATE` of those rows (e.g. `reassign`).
- **Expected:** the model declares exactly the constraints the DB enforces — the declared
  invariant should either exist in both places or in neither.
- **Fix:** drop the two phantom `CheckConstraint` declarations from the models (preferred —
  matches the enforced policy and `single_decider`'s existence), or, if the policy is to forbid
  the shape, add the constraint via migration **plus** an API-level 400 in
  `ensure_chain_stages_are_not_redundant` and remove `single_decider`/its tests.

### Additional verified findings

No further verified defects. Candidate issues investigated and **dropped** as intentional or
unreachable:
- `PUT /access` with (supervisor == deputy) / (deputy == ceo) → clean guided 400s (controls in
  the reproduction run); (supervisor == ceo) does **not** 500 — it is accepted (see FND-03-01/03).
- Bonus stored raw (e.g. 4 on a base of 100) while the document omits the zero-applied bonus and
  `/api/me` shows the raw number: intended per the extensive comments in
  `snapshot.py`/`models/evaluation.py` (raw value kept for audit; only the *applied* value is
  printed, and the three printed numbers always add up — reproduced).
- Concurrent `next_version()` scheme creation could collide on the unique `version` (theoretical
  IntegrityError under true concurrency, no test harness for it here) — not reported as a defect.
- `fa_digits` prints `۱۰۰٫۰` for 100.0 (trailing decimal zero) — cosmetic, consistent, not reported.

## Verified correct

**Score computation (`services/evaluation.py`)**
- Indicator weights multiply both the score and the section ceiling (a weight-10 indicator
  cannot push a section past 100 — reproduced). Absent-section weight is redistributed between
  present sections (general-only framework with all 5s → 100 / top band, not 60 — reproduced);
  zero weight for all present sections falls back to the simple average (reproduced).
- Threshold bands are half-open (`<` upper_exclusive), ascending, gapless over [0, 100]; last
  band must exceed 100 (`SchemeInput`); boundary values 59.9/60.0/74.9/75.0/89.9/90.0/100.0/0.0
  all resolve to the documented band (reproduced).
- Bonus: `validate_bonus` rejects negative, above-scheme-cap, and reason-less bonuses at write
  time; `applied_bonus` is bounded by the scheme cap AND the remaining room to 100 (accepted
  design); `final = base + applied ≤ 100` always; the raw value stays on the record and in the
  audit trail (reproduced, incl. the 100-base case).
- `finalize_scoring` requires every indicator of the record's own framework to be scored, and
  validates evidence rules from the record's scheme; empty score sets are refused with the
  Persian completion error (reproduced); score inputs 0/6 are rejected by the schema; duplicate
  indicator rows and indicators outside the record's framework are rejected (reproduced).

**Scoring schemes (versioning)**
- New records are stamped with the *active* scheme; `rules_for_record` reads the stamped version
  for validation, computation, special-score limits and improvement-plan thresholds.
- Mid-cycle activation: an open record validated/scored/submitted under its own v1 rules after a
  stricter scheme (evidence rules changed, `bonus_max_points = 0`) was activated — bonus still
  allowed and result computed under v1 (reproduced).
- Activated/retired versions are immutable: re-activation refused (400), deletion only for
  drafts, retired-on-activation, single active scheme enforced by the partial unique index
  `uq_single_active_scheme`; two-person activation (creator ≠ activator) enforced inside
  `activate()`.
- Migration `e2b4a71c8d35` seeds v1 from the frozen legacy constants and stamps every existing
  record; migration `d5a91f37c2e8` backfills `bonus_max_points = 5` on existing schemes and
  leaves old records NULL (= "no bonus").
- `/api/scoring-schemes/preview` runs the real `compute_result` on up to 200 finalized records
  with the record's own bonus, writes nothing, names no individuals.

**Frontend/backend preview parity**
- `computePreview` (ScoreForm.tsx) mirrors `compute_result` structurally: per-indicator weights
  on numerator and ceiling, present-section weight normalization, zero-weight simple-average
  fallback; the form's `config` comes from the record's own `scoring_rules`
  (`AppConfig.from_rules(rules_for_record(...))`) so open forms validate under the record's
  scheme, matching the server; bonus is deliberately added separately and the ring is capped at
  100 like the server. Persian/Arabic-digit input for the bonus is converted
  (`toMachineNumber`). Only the tie-break rounding differs (FND-03-02).

**Snapshot & finalization**
- `final_snapshot` is written only in `_stamp_finalization`, invoked from both finalization paths
  (`ceo_finalize`, `hr_finalize_direct_ceo`); `apply_transition` refuses finalization without a
  snapshot and without a computed result/scores; a second `ceo-finalize` is refused (reproduced).
- Snapshot v6 freezes personnel identity, evaluator username **and display name** with the
  correct seat label for every chain shape (full / manager / CEO-direct / HR-subject variants —
  all reproduced, including the CEO-direct evaluator «مدیرعامل» and the HR-subject CEO-direct
  `single_decider = True` with a single signatory), `single_decider`, `signatories`
  (real seats, HR skipped for shielded records), all scores with evidence, stage comments, the
  self-assessment comparison block, and UTC ISO timestamps.
- Deleted indicators are impossible for scored rows (`delete_indicator` refuses with 409), and
  the snapshot keeps a labelled fallback row anyway.
- Immutability: after finalization, score upsert / special-score attempts are 403 (reproduced);
  renaming the subject and deactivating the evaluator afterwards leaves the archived PDF
  byte-identical and the public verify page still showing the frozen identity (reproduced).

**Documents, PDF, QR verification**
- `archive_final_pdf` is idempotent, handles the render race with a SAVEPOINT + unique
  constraint, and renders from the frozen snapshot; the download endpoint serves the archived
  bytes byte-stably (reproduced: two downloads identical, `sha256 == hashlib.sha256(bytes)`,
  and `/api/verify/{token}` returns exactly that hash with `document_ready = true`).
- The QR URL is built from the random `verify_token` (unique, set only at finalization,
  migration-backfilled for legacy rows); the public verify endpoint 404s unknown tokens,
  sequential `EVL-` codes, and non-finalized records, is rate-limited 30/min, and returns only
  non-sensitive fields; `PUBLIC_BASE_URL` localhost/http values are refused in production by the
  settings validator.
- PDF hardening: Jinja autoescape on (user evidence/comments cannot inject HTML), URL fetcher
  restricted to the templates dir (no file/http), both Vazirmatn halves embedded (no
  system-font fallback), fixed table layout with repeating headers, `table-layout: fixed`.
- Dates: `to_jalali` converts via the org timezone; the day flips exactly at Tehran midnight
  (UTC 20:30) — reproduced for both sides of the boundary; snapshot timestamps are stored UTC
  ISO and the verify/template path renders the URL/QR block only when a QR exists.
- Historical versions: the template branches on key presence — v1 snapshots (no bonus keys)
  skip the bonus block, v≤4 snapshots keep the legacy signature block, `stage_labels` translates
  raw stage values at render time; `verify.py` uses `.get` defaults for old snapshots; the
  backfill sweep skips records without a snapshot (byte-stability preserved).

**Finalized-record readers**
- `reports.py`, `dashboard.py`, `analytics.py`, `stage_stats.py`, `excel.py`, improvement plans
  and `/api/me` read the live record columns (`final_weighted_pct`, `recommendation`,
  `finalized_at`) — which are immutable post-finalization (terminal-state mutation batteries,
  Role 02 + my 403 reproductions) — or the snapshot for identity; `stage_stats` derives dwell
  times from the audit log; `analytics.executive` builds the recommendation ladder from all
  scheme versions so legacy labels stay ordered.
- Improvement-plan eligibility (`< threshold`, SQL coalesce with the record's scheme) and
  `create_plan` (`>= threshold` via `rules_for_record`) agree exactly at the boundary
  (reproduced: final 75.0 → not eligible + create 400; just below → eligible + create 201).
- Excel exports: same filters and role scoping as the list, formula-injection neutralized,
  audit-logged, bonus shown as its own column.

## Could not check, and why

- **Visual PDF layout** (font rendering, table page-breaks in the real WeasyPrint output beyond
  byte-level equality): no visual inspection tooling in the sandbox; the repo's
  `test_pdf_table_layout.py` / `test_document_fonts.py` cover it and are green in the baseline.
- **Decoding the QR from the archived PDF binary**: verified that the template embeds a
  `data:image/png` QR of the verify URL and prints the URL text next to it; decoding the
  QR pixels out of the compressed PDF stream was not attempted.
- **Scheduler backfill sweep in production conditions** (`run_document_backfill_sweep`):
  source-verified only (scheduler disabled in tests); the sweep correctly skips snapshot-less
  records and is idempotent.
- **Real historical v1–v5 snapshots**: no production data available; old-shape compatibility is
  covered by the repo's legacy-render tests plus my reading of every `final_snapshot` consumer.
- **True-concurrency scheme creation** (`next_version` unique-version collision) and concurrent
  PDF archival beyond the SAVEPOINT race already covered by `test_documents.py`: no multi-process
  harness used.
- **AI copilot scoring paths** (`app/services/ai/**`): out of scope per the review contract.

# ROLE 05 — Privacy & Disclosure

Scope: commit `fc4f3fe9e5ea6fa412a16b0bbc287fb24dfe18a9` (branch `review/ten-role-full-system`). Backend privacy surfaces only — AI Copilot (`backend/app/services/ai/**`, AI tools, AI-only paths) excluded per instructions. All findings were verified against a disposable DB (`nexahr_r05`) via a temporary pytest file (`backend/tests/test_review_tmp_r05.py`, 14 tests, all green, file deleted afterwards); repo left clean (`git status --porcelain` empty).

## Verdict

**The privacy architecture is fundamentally sound, with one significant module-gate escape hatch around the employee's own final document.** Cohort suppression is applied at every aggregate call site I could find and counts people, not rows; HR-panel shielding of HR-unit records is enforced in list, detail, and Excel export and lifts exactly at finalization; the audit log is capability-gated with a system-events-only allowlist for diagnostics holders; all Excel exports sit behind role/capability guards and reuse the same visibility scope as the on-screen lists; notifications are strictly per-user and the subject-facing texts are themselves gated by `employee_evaluation_visibility`.

The exceptions both sit on the subject's **own finalized record** and both contradict the same accepted product decision — "`employee_evaluation_visibility` intentionally gates **server reads**, not just UI" (default OFF). ROLE 01 already caught the list endpoint (FND-01-01, not re-reported here). My fresh sweep of the surrounding surface found that the **official PDF endpoint has its own, independent bypass of that module** (FND-05-01): the subject's right-to-their-document branch checks no module at all, so with the module OFF — the default install state — an employee who learns a record id receives the *entire* evaluation document (per-indicator scores, the evaluator's written evidence, the evaluator comment, the HR/deputy/CEO stage comments, and the self-assessment comparison) while `/api/me/evaluations` correctly answers empty and the frontend hides the section. The id is obtainable via FND-01-01's list leak, via a 403-message oracle on the detail endpoint (FND-05-02), or by plain sequential-id scanning (no rate limit on that route). Fixing FND-01-01 alone does **not** close this — it is a separate code path with a separate fix.

No broad uncontrolled leakage (data of person X reaching persons who are neither X nor authorized evaluators/HR) was found: every cross-person surface I tested returns 403/404/empty correctly.

Findings: **1 HIGH (new) + 1 LOW (new)**, plus a cross-reference analysis of FND-01-01 (ROLE 01) documenting exactly which fields leak through it and which additional path it unlocks.

## Findings

### Top findings

**FND-05-01 | HIGH | REPRODUCED | backend/app/api/routers/evaluations.py:1577-1593 (`evaluation_summary_pdf`, subject branch) | The subject's full official evaluation PDF is downloadable with the `employee_evaluation_visibility` module OFF, bypassing the module that exists precisely to keep the employee from reading their result.**

- **Acting role:** any authenticated user whose `personnel_id` equals the record's `subject_personnel_id` (tested with `UserRole.employee`; the branch is role-independent — a unit supervisor or deputy who is themselves evaluated gets the same).
- **Initial state:** fresh install semantics — `employee_evaluation_visibility` OFF (`app/core/modules.py:65-69`, `default_enabled=False`, no `ModuleSetting` row). One `finalized` record for the employee's personnel (full chain: supervisor scores + submit + HR/deputy approve + CEO finalize → `final_snapshot` + `verify_token` written).
- **Action (exact):** `GET /api/evaluations/{evaluation_id}/summary.pdf` with the employee's bearer token.
- **Observed (wrong):** HTTP **200**, `content-type: application/pdf`, ~50 KB document. The archived document renders (per `app/services/snapshot.py` + `app/templates/evaluation_summary.html:144-227`): every indicator score **with the evaluator's `evidence_text` narratives**, `evaluator_comment`, all stage comments (`hr_review` / `deputy_review` / `ceo_final`), the self-assessment side-by-side block and its note, bonus/recommendation, and the signatories. Meanwhile, in the same state: `GET /api/me/evaluations` → `{"total": 0, "items": []}` (me.py:74-75 module check) and the frontend hides the whole "my evaluations" section (`frontend/src/pages/employee/MyEvaluationsPage.tsx:322-327` gates on `moduleEnabled("employee_evaluation_visibility")`). The finalize notification to the subject is likewise suppressed when the module is off (`services/notifications.py:443-459`, `employee_results_are_visible`).
- **Expected:** the module gates server reads of the subject's own result (accepted decision); the subject branch of this endpoint must be gated the same way. The HR branch (archival/reporting duty after finalization) must stay open.
- **How to reach it (three independent routes):**
  1. Via FND-01-01 (ROLE 01): the employee-branch list response contains the record `id`.
  2. Via FND-05-02 below: the detail endpoint's distinct 403 message identifies which sequential ids are the caller's own records.
  3. Plain scanning: evaluation ids are small sequential integers; there is **no rate limiter on the evaluations router** (no `@limiter` anywhere in `evaluations.py`), foreign ids return 403/404 and the own id returns 200.
- **Guards hunted:** the subject branch (`evaluations.py:1577-1588`) skips `_ensure_can_view` entirely (by design, "سوژهٔ پرونده حق دارد سندِ مربوط به خودش را داشته باشد") and no `is_module_enabled` / `employee_results_are_visible` check exists anywhere between the branch and `archive_final_pdf` (1590-1625). The module *is* enforced on the three other subject read paths (`me.py:74`, `dashboard._gated_self_cards` at `dashboard.py:604-621`, `notifications.py:451`) — this endpoint is the odd one out, exactly the "inconsistent enforcement across endpoints" the accepted decisions declare reportable.
- **Evidence (REPRODUCED):** temp test `test_r05_subject_pdf_download_bypasses_visibility_module` on `nexahr_r05`: module OFF, `/api/me/evaluations` → `total == 0`; `/api/evaluations/{id}/summary.pdf` as the subject → **200 + PDF bytes**; a different employee (not in chain, not subject) → **403**; unknown id → **404**. Companion test `test_r05_subject_pdf_visible_when_module_on` (with `employee_view_on`) confirms the subject legitimately gets the document when the module is ON — so the fix must not remove the subject branch, only gate it.
- **Fix:** in `evaluation_summary_pdf`, require `employee_results_are_visible(db)` inside the `is_subject` branch before serving (HR branch untouched); ideally via one shared helper ("subject may read own result") so the acknowledge/objection paths in `me.py` cannot drift from it again. Cross-reference FND-01-01: applying ROLE 01's fix (a) to the list endpoint does not close this endpoint.

### Additional verified findings

**FND-05-02 | LOW | REPRODUCED | backend/app/api/routers/evaluations.py:157-172 (`_ensure_can_view`) | Distinguishable 403 bodies on `GET /api/evaluations/{id}` give employees an id-ownership oracle over sequential evaluation ids — an id-discovery path for FND-05-01 that works even after FND-01-01 is fixed.**

- **Acting role:** any authenticated employee.
- **Initial state:** ≥2 finalized records (one own, one foreign), employee linked to own personnel.
- **Action (exact):** `GET /api/evaluations/{id}` with ids probed sequentially.
- **Observed (reproduced):** own record → 403 `"این پروندهٔ ارزیابیِ خودِ شماست؛ رسیدگی به آن باید توسط کاربر دیگری از منابع انسانی انجام شود."`; someone else's record → 403 `"شما به این ارزیابی دسترسی ندارید"`; non-existent → 404. Three distinguishable outcomes ⇒ the caller can map which ids are their own records (including *open/draft* ones — the own-case message fires for any status) and confirm the existence of foreign record ids. me.py deliberately chose 404-over-403 for exactly this reason ("پروندهٔ دیگران عمداً 404 برمی‌گردند (نه 403) تا وجودش هم لو نرود", me.py:313), so the two read paths disagree.
- **Expected:** uniform 403 (or 404) for a non-authorized viewer regardless of subject-ness; the "own case" wording is meant for the HR-deciding-about-oneself context (`self_evaluation.py:171-197`), not for the employee panel.
- **Impact bound:** on its own it discloses only id ownership/existence metadata (ids are sequential anyway, and the employee's own *open* case id is already sanctioned knowledge via `/api/me/evaluations/open`). Its real weight is as the cheapest discovery route for FND-05-01's PDF bypass.
- **Evidence (REPRODUCED):** temp test `test_r05_detail_error_oracle_own_vs_other`: statuses `(403, 403, 404)` with two different `detail` strings, printed both messages.
- **Fix:** in `_ensure_can_view`, for `current_user.role != hr` who is the subject, raise the generic 403 (or 404) instead of letting `ensure_hr_may_handle`'s own-case message surface; keep the specific message for the HR-role self-review case where it is actionable.

### Cross-reference — FND-01-01 (ROLE 01, HIGH): what exactly leaks, and what it unlocks (not re-reported as new)

ROLE 01 found the employee branch of `GET /api/evaluations` returning the subject's own finalized record without the `employee_evaluation_visibility` check. Re-verified from the privacy angle on a fresh DB; the measurable delta against the sanctioned `MyEvaluationRead` view (`schemas/evaluation.py:244-268`) — i.e. what `EvaluationRead` (`schemas/evaluation.py:130-193`) adds — is:

- **`evaluator_comment`** — the supervisor's free-text narrative about the employee (the single most sensitive string in the record; asserted by value in my repro).
- Chain identity: **`unit_supervisor_user_id`, `deputy_user_id`, `ceo_user_id`, `hr_user_id`, `hr_username`, `hr_display_name`** — who judged you.
- Workflow internals: **`single_decider`, `hr_review_skipped`, `was_returned`, `status`/`stage`, `submission_deadline` + `submission_deadline_extended` + `submission_extension_reason`** (the HR extension *reason* text), `created_at`.
- (Objection fields are present in both schemas; scores/evidence/comments are **not** leaked here — detail `GET /api/evaluations/{id}` correctly 403s the employee, and `scope_evaluations_for_role` correctly excludes other people's records.)

Through the leaked `id`, the employee then reaches FND-05-01 (full PDF) — the combination is the worst case: evaluator narratives + chain comments with the org switch turned off.

## Verified correct

Mapped to the mandatory checklist; each item was either executed in my temp suite, covered by an existing green test I read, or traced end-to-end through source with all call sites enumerated.

1. **Cohort suppression (privacy.py) — every call site.** `rg suppressed_avg|cohort_size|is_below_cohort` over `backend/app` yields exactly: `reports.py` (summary 139-157, indicator 237-252, employee-vs-unit 326-338, export via `_summary_data`), `dashboard.py` (overview unit rows 199-218 incl. the two sub-scores — "دو عددِ جزء همان چیزی را لو می‌دادند", by_evaluator 240-254, indicator stats 274-290, period-trend 406-420), `analytics.py` (my-scoring 139-208 incl. distribution shares and per-indicator gaps, executive 274-323). Threshold counts **distinct people**, not rows (`privacy.py:26-42`; `test_cohort_counts_people.py` proves 1 person × 5 periods stays suppressed while 5 people publish). Counts themselves are intentionally visible (privacy.py docstring); `lowest_by_unit` ranks only unsuppressed rows (dashboard.py:300-306); the person-named exception (summary overall average) applies only when the caller explicitly passes `personnel_id` (reports.py:136-140). Excel report marks suppressed cells with an explicit marker (excel.py:278-284, tested by `test_cohort_suppression.py`). Per-site evaluation-record weighting in executive is the accepted decision; suppression there still counts people (analytics.py:316-329).
2. **HR-panel shielding (`hr_panel_is_shielded`/`IS_SHIELDED_FROM_HR_PANEL`).** List: `scope_evaluations_for_role` (evaluations.py:586-601) excludes shielded open records **and** the HR viewer's own record; detail and every HR action path route through `ensure_hr_may_handle` (`self_evaluation.py:200-229`) — comments (evaluations.py:1659), cancel/extend/claim/handover/reassign via `ensure_may_administer` (`self_evaluation.py:232-263`); **`export.xlsx` applies the same scope** (evaluations.py:715-730) — reproduced: shielded record absent from list, detail 403, and absent from the Excel sheet while open, and *present again* for the same HR viewer after finalization (the intended archive window); HR's own record stays hidden even after finalization (temp test; also `test_hr_own_case.py`). Notifications: the HR queue excludes the subject (`_hr_queue_ids`, notifications.py:108-130), shielded vacated seats are routed to that record's deputy/CEO instead of HR (notifications.py:293-340).
3. **Self-assessment visibility.** `VIEWER_ROLES = {hr}` (`self_assessment.py:91`); the full-record `EvaluationDetail.self_assessment` is populated only when `may_view_self_assessment(record, role)` (evaluations.py:251-255) — the first scorer (supervisor/deputy) never sees the employee's self-assessment, matching the documented intent; the employee sees only their own via `/api/me/evaluations/{id}/self-assessment` (`_my_record_or_404`, 404 for others).
4. **Evaluation visibility per role.** `scope_evaluations_for_role` is a role allowlist with fail-closed default (unknown role → 403; employee without personnel link → `sa_false()`); supervisor/deputy/CEO scoped to their seats; detail requires seat membership or HR; employees with the module ON see only own finalized records (`test_employee_self_view.py`), and my repro confirmed no cross-person leakage with it OFF.
5. **Personnel visibility (`_can_view_personnel`, personnel.py:120-140).** `GET /api/personnel` for non-HR roles is restricted to personnel whose access chain names them (employee → empty page, `_ACCESS_COLUMN_BY_ROLE` has no employee key, personnel.py:216-222); detail/radar/trend/in-progress all call `_can_view_personnel` (HR: all; chain members: their people; others 403). `/org-units`, `/sites`, `export.xlsx`, import, and chain editing (`evaluation_access.py`) are behind `require_role_or_capability(UserRole.hr, Capability.manage_personnel)`.
6. **Audit logs (audit_log.py).** Route entry requires `view_audit_log` **or** `view_diagnostics` (deps.py:234-260); default HR accounts hold neither (migration f2a7d3c9e861 grants only manage_users/personnel/scoring) → 403 (reproduced). `view_diagnostics` holders get the `SYSTEM_EVENT_TYPES` allowlist **plus** the second belt `evaluation_record_id IS NULL` (audit_log.py:194-201) — reproduced with live `score_submitted`/`status_changed` rows in the log: the diagnostics viewer saw only login events, no record-linked rows. `score_submitted` rows do embed the full computed result (workflow.py:781-784) — reachable only by `view_audit_log` holders; `/export.xlsx` requires `view_audit_log` (diagnostics-only → 403, reproduced). Hash chain + `/integrity` behind the same capability.
7. **Excel exports.** evaluations (HR only, scope-aware incl. shielded/own exclusions, audited `excel_exported`); personnel (HR/`manage_personnel`, audited); users (`manage_users`); audit log (`view_audit_log`); HR report (HR); improvement plans (HR, audited). Formula-injection neutralized at the sheet layer for every export (`_SafeSheet`, excel.py:63-103; `test_excel_formula_injection.py`).
8. **Notification bodies & isolation.** Listing filtered by `user_id`; mark-read ownership-checked (404, reproduced + `test_notification_isolation.py`); texts carry only evaluation code + subject full name to **chain participants/HR** (by design); the subject-facing texts ("نهایی شد", "پاسخ اعتراض") are created only when `employee_results_are_visible` (notifications.py:443-459, evaluations.py:1440-1453); outbound email/SMS only for the action-type subset, one individual message per recipient (delivery.py `enqueue_for`, channels build single-recipient messages) — no cross-recipient exposure.
9. **Server logs / error surfaces.** Request log records method + URL **path** (ids visible, no query strings, no bodies, no usernames; main.py:100-132); metrics use route **templates** (main.py:87-97) and `/metrics` is token-gated with constant-time compare (main.py:214-232); unhandled errors return only a request id (main.py:108-120); `/docs`/`/redoc`/`/openapi.json` disabled in production (main.py:60-68); `RequestValidationError` mapped to concise Persian messages (`core/validation_errors.py`).
10. **Employee-facing `/api/me`.** Own records only (404 for others by design); `my_evaluations` module-gated (returns empty page, not 403); `/evaluations/open` is status-only (no scores/comments — schema `MyOpenEvaluation`); improvement-plans: own open plans read-only.
11. **Aggregate endpoints & inference surface.** `role-overview` employee branch gated on *both* `employee_overview_cards` and `employee_evaluation_visibility` (dashboard.py:604-636) — reproduced both directions (empty with OFF, avg card with ON); `my-scoring` requires supervisor/deputy **and** the `role_analytics` module, org-side values (avg, distribution shares, per-indicator org averages) suppressed below cohort while the evaluator's own stats stay (reproduced); `executive` is CEO/deputy + module, contains no person names anywhere (reproduced; supervisor/employee → 403); dashboard `overview`/`pipeline`/`stage-stats`/`expiring-contracts`/`period-trend` are `require_roles(hr)`; `periods/*` HR-only. Remaining inferables are the accepted "counts are visible" class (`org_people_count`, per-unit counts, `recommendation_mix` shares, `outcome_mix.people_counted`).
12. **`/api/verify/{token}` (public).** Lookup by 192-bit random token (not the enumerable `evaluation_code` — the docstring records that exact attack), 404 for unknown tokens, 30/min rate limit, and the payload contains only name/unit/final pct/recommendation/sha256/finalized_at — no evaluator or chain identity (reproduced).
13. **Low-priv endpoints.** `/api/config` (any auth): scoring rules only, no personal data; `/api/periods`, `/api/org-units`, `/api/personnel/org-units|sites`: HR/capability; `/api/indicators` (any auth): catalogue only; `/api/scoring-schemes*`: `manage_scoring`; administration (modules/policy/integrations/capabilities/separation): per-capability guards; `/api/administration/my-permissions`: own permissions only; `/api/auth/sessions` + revoke: own sessions only (404 on others', `test_session_visibility.py`).
14. **PDF hardening (relevant to the leaked document itself).** Jinja autoescape on (pdf.py:70-73) and a URL fetcher restricted to the templates dir + data URIs (pdf.py:105-113, `test_pdf_security.py`) — the document FND-05-01 exposes is at least injection-safe.
15. **Both directions tested throughout** — hidden data stays hidden (foreign employees 403/404 on detail/PDF; shielded records invisible to HR while open; other users' notifications absent) while permitted users receive required data (HR sees the record after finalization; subject gets the PDF when the module is ON; full audit-log reader sees score-bearing events).

## Could not check, and why

- **Live outbound channel content in transit** (SMTP/SMS): no real mail/SMS provider is configured in the sandbox; source shows one message per recipient with the same text the in-app notification carries, but actual provider-side handling (e.g., logging by a third-party SMS gateway) is outside the repo.
- **Multi-instance production posture**: in-process rate-limit counters are an accepted decision; `/metrics` token configuration and production log aggregation (log shipping, retention) are deployment-level and not verifiable from this checkout.
- **Timing side-channel on `/api/verify/{token}`**: token lookup is a single indexed equality; I did not attempt timing measurements — the 30/min limit and 192-bit random tokens make enumeration implausible, but no formal analysis was done.
- **Frontend rendering parity for every schema field**: pages were read for the key gates (`MyEvaluationsPage`, `PermissionsContext`, audit/personnel pages) but no browser session was run; API-level enforcement (which is what this role audits) was verified directly.
- **AI Copilot surfaces**: excluded by instructions; noted only that the AI evaluations tool reuses `scope_evaluations_for_role` (the same allowlist as the human list endpoint).
- **Long-term data-retention sweep coverage beyond `auth_sessions`** (FND-01-03, ROLE 01): `audit_log` growth is bounded by the truncate-guard migration (c1e5a9d2f70b); no exhaustive retention audit of every table was performed.

## Proposals

**P1 — One gate for "the subject may read their own result" (closes FND-05-01; hardens FND-01-01's family).**
User-visible outcome: with "نتیجه و وضعیت پروندهٔ کارمند" turned off, an employee calling `GET /api/evaluations/{id}/summary.pdf` for their own finalized record gets 403 — exactly like `/api/me/evaluations` — instead of the full signed document; with the module on, nothing changes.
Change: add `if is_subject and not employee_results_are_visible(db): raise 403` in `evaluation_summary_pdf` (evaluations.py:1581); extract the check into one helper (e.g. `services/notifications.employee_results_are_visible` reused, or `authorization.ensure_subject_may_read_result`) and call it from the PDF subject branch, `me.acknowledge_evaluation` and `me.file_objection` so the four subject read/write paths cannot drift apart again.
Files: `backend/app/api/routers/evaluations.py`, `backend/app/api/routers/me.py`. Surface: one endpoint + two. Risks: orgs that deliberately keep visibility off but want subjects to fetch the PDF lose that (that combination is precisely what the module promises to prevent); none for HR. Compat: module-ON behavior identical (verified by test). Priority: **high**.

**P2 — Kill the 403-message oracle (closes FND-05-02).**
User-visible outcome: employees probing `GET /api/evaluations/{id}` can no longer tell their own record ids from foreign ones by the error text.
Change: in `_ensure_can_view` (evaluations.py:157-172), let `ensure_hr_may_handle` run only for `UserRole.hr`; for non-HR callers raise the generic 403 (or 404, matching me.py's convention) regardless of subject-ness.
Files: `backend/app/api/routers/evaluations.py`. Surface: detail endpoint only. Risks: the actionable "your own case" message remains available to HR users where it belongs. Compat: message-only. Priority: medium.

**P3 — Trim `PersonnelRead` for non-HR chain viewers.**
User-visible outcome: a unit supervisor / deputy / CEO listing "my people" no longer receives each member's `separation_reason` (e.g. dismissal vs resignation), `separation_date`, or `account_username`; HR/manage_personnel viewers keep the full row (the Excel export and HR pages are unaffected).
Change: blank those fields in `_with_accounts`/serialization when the requester is not HR/`manage_personnel` (personnel.py:143-187, schemas/personnel.py:69-106).
Files: `backend/app/api/routers/personnel.py`, `backend/app/schemas/personnel.py`. Surface: `GET /api/personnel` for non-HR roles. Risks: minimal — supervisors don't act on those fields; `open_evaluation_id`/`scored_by`/`self_assessment_state` stay (operationally needed). Priority: low.

**P4 — Enforce module `requires` server-side.**
User-visible outcome: an admin can no longer create the self-contradictory configuration "اعتراض به نتیجه / ثبت رؤیت" ON while "نتیجه و وضعیت پروندهٔ کارمند" is OFF via the API (today `PUT /api/administration/modules/{key}` accepts it — the dependency is only a UI hint, `blocked_by`).
Change: in `toggle_module` (administration.py:256-300), reject enabling a module whose `requires` entries are disabled (and cascade-disable dependents on disable, or reject, with a clear Persian message).
Files: `backend/app/api/routers/administration.py`. Surface: module toggle API. Risks: slightly stricter admin UX; a migration/one-time cleanup is not needed since the runtime guards already treat such states as broken configs. Priority: low.

# ROLE 06 — Data Integrity & Migrations

Scope: Alembic graph integrity, full replay, model-vs-DB drift, enums, partial unique
indexes, FK/ON DELETE behavior, audit append-only triggers + hash chain, seed/data
migration idempotency on realistic data, defaults, DB-vs-Python constraint
enforcement, nullability. Repo at commit `fc4f3fe9e5` (branch
`review/ten-role-full-system`), read-only; all experiments on disposable databases
(`nexahr_r06a` fresh replay, `nexahr_r06b` realistic-data + downgrade/upgrade cycles)
on the local PostgreSQL 16.4/ICU instance, dropped afterwards. Repo left clean
(`git status --porcelain` empty).

## Verdict

Forward migrations are in unusually good shape for a system of this maturity: the
graph is a clean linear chain (57 revisions, single head `c1e5a9d2f70b`, no merges,
no loops), a full replay from empty DB succeeds in ~1.1 s, `alembic check` reports no
drift, and a systematic column/type/nullability/index/unique/FK comparison between
SQLAlchemy metadata and the migrated DB found **zero semantic drift** on all of those
axes. The data-transforming migrations (scheme/framework stamping, hash-chain
backfill, HR-unit flagging, text truncation) all behaved correctly on a database
pre-loaded with realistic data, and the audit append-only guard (UPDATE/DELETE
blocked, TRUNCATE blocked incl. `CASCADE`, row verified intact) works exactly as
declared.

The defects I found all live on the **downgrade side** of the chain: downgrades of
data-bearing migrations destroy data (scoring-scheme provenance, verify tokens,
org-unit catalogue) that the subsequent re-upgrade silently re-derives or re-stamps
wrong, and the seed-indicator downgrade makes `downgrade base` impossible on any DB
that has evaluation scores. None of these corrupt data on the normal upgrade path;
all were reproduced by executed downgrade/upgrade cycles on a disposable DB with
realistic data.

Constraint-drift extent (extending prior FND-03-03, not re-reporting it): of the 10
model-declared CHECK constraints, **2 are missing from the DB entirely**
(`ck_evaluation_access_supervisor_not_ceo`,
`ck_evaluation_records_supervisor_not_ceo` — the FND-03-03 finding), **4 exist as
`NOT VALID`** (deliberate, per `e9c47b3f1a52`'s documented rationale; they *are*
enforced on new writes — verified by insert attempts), and 4 are fully validated.
`alembic check`/`compare_metadata` remain blind to all CHECK drift, and also to
server-default drift (a set of DB-side defaults on `ai_*`/misc tables that the models
mirror only as Python defaults — values verified equal, so cosmetic).

Findings: 1 MEDIUM, 3 LOW — all REPRODUCED.

## Findings

### Top findings

**FND-06-01 | MEDIUM | REPRODUCED | `backend/alembic/versions/e2b4a71c8d35_versioned_scoring_schemes.py:124-131` (stamp), `:134-138` (downgrade); same pattern in `b7d4e2a91c68_indicator_framework_versions.py:74-81` / `:84-86`**
What breaks: a downgrade→re-upgrade cycle **silently rewrites the scoring-scheme
(and indicator-framework) provenance of every evaluation record**. The downgrade of
`e2b4a71c8d35` drops the `scoring_schemes` table, destroying every version other
than the constants v1 encodes; on re-upgrade, migration creates v1 and stamps *all*
records with `scoring_scheme_id IS NULL` to v1. Records genuinely created and scored
under a later active scheme (v2+) end up pointing at v1, so the P1-04 invariant the
column exists for ("محاسبه همیشه از این می‌خواند، نه از طرحِ فعال" — computation
always reads the record's own version, precisely so later rule changes can't rewrite
history) is broken by the migration cycle itself. Open records recompute live under
the wrong weights; finalized records keep their stored snapshot but their recomputed
thresholds/recommendation paths change. `b7d4e2a91c68` does the same to
`indicator_framework_id`.
How to reach it (executed on `nexahr_r06b`): create scheme v2 (retire v1), stamp
finalized record `EVL-0001` → `scoring_scheme_id=2`; `alembic downgrade
d7e3c81f6a94`; `alembic upgrade head`. Result: `EVL-0001` → `scoring_scheme_id=1`,
scheme table contains only v1 (`active`). No warning is printed at any step.
Fix: make the downgrades of `e2b4a71c8d35`/`b7d4e2a91c68` fail loudly (like
`e4b8d03ca712` does for the partial index) when any non-v1 scheme/framework exists or
any record references one, instead of dropping the table; or have the upgrade stamp
only records created before the migration's introduction (e.g. by `created_at`
cutoff), and log a warning when re-stamping records that previously lost their
stamp.

### Additional verified findings

**FND-06-02 | LOW | REPRODUCED | `backend/alembic/versions/b28cc6abdf2a_phase5_verify_token.py:42-54` (backfill), `:57-59` (downgrade drops column)**
What breaks: a downgrade past `b28cc6abdf2a` destroys the `verify_token` column;
re-upgrade backfills **fresh random tokens** for all finalized records. Every
previously printed PDF/QR whose public verification URL (`/api/verify/{token}`)
carried the old token silently 404s — directly contradicting the migration's own
stated intent that the backfill exists "تا سند/QR چاپی قدیمی هم بی‌اعتبار نشود".
How to reach it (executed): set `EVL-0001.verify_token='tok_original_AAA'`; downgrade
to `f1c93b7ad025`; upgrade head. Token is now `LmAyfd0iBdBd8UJXMxMTve4wMQbqqjWS`.
Fix: same class as FND-06-01 — refuse the downgrade when finalized records carry
tokens, or emit a migration-time warning that all issued verify URLs are
invalidated.

**FND-06-03 | LOW | REPRODUCED | `backend/alembic/versions/ddafefc08701_org_unit_catalogue.py:54-79` (re-derivation), `:82-83` (downgrade drops table)**
What breaks: the downgrade drops the `org_units` catalogue; re-upgrade re-populates
it **only from `personnel.org_unit` strings**. Catalogue rows that had no personnel
yet (a unit created for the first upcoming hire), and any manual
`display_order`/`is_active` edits, are silently lost.
How to reach it (executed on `nexahr_r06b`): catalogue contained `فروش`,
`منابع انسانی`, and `استخدام (site=دفتر مرکزی)` with no personnel; after a
downgrade past `ddafefc08701` + upgrade, `استخدام` is gone (only units referenced by
personnel survive).
Fix: downgrade should preserve catalogue rows (rename table / dump-and-restore
pattern), or fail-loudly when non-derivable rows exist; re-upgrade should warn about
re-derivation.

**FND-06-04 | LOW | REPRODUCED | `backend/alembic/versions/65a700d744d4_seed_indicators.py:88-93` (downgrade DELETE)**
What breaks: `downgrade base` (or any downgrade below revision 3) is **impossible on
a DB with evaluation data**: the seed's downgrade deletes *all* indicators in
sections `general`/`specialized` — including org-custom ones, not just the seeded 20
— and fails with `ForeignKeyViolation` from `evaluation_scores_indicator_id_fkey`
when scores reference them. The failure is loud and the per-migration transaction
rolls back (no data loss; `alembic_version` pinned at `65a700d744d4`), but the
operator gets an IntegrityError instead of a downgrade.
How to reach it (executed): `alembic downgrade base` on `nexahr_r06b` with 2 score
rows → `psycopg.errors.ForeignKeyViolation … Key (id)=(1) is still referenced from
table "evaluation_scores"`.
Fix: the downgrade only needs to make the eventual `drop_table` in `0e25894e177a`
safe; delete nothing (or delete only the exact 20 seeded (category, description)
pairs, which still needs the FK removed first). Also narrow the delete to the exact
seeded rows so an org's custom indicators in those sections don't die.

## Verified correct

### 1. Alembic graph & replay (checklist 1, 2, 3)

- 57 revision files, single head `c1e5a9d2f70b`; graph is a **linear chain** — no
  merge nodes, no multiple heads, no missing parents, every revision reachable from
  the head, `alembic history` shows an unbroken `<base> → head` chain.
- Every migration defines a real (non-empty) `downgrade()` — no `pass`-only bodies
  except two *documented* no-ops (`d7a2c91fb480` — PG cannot remove enum values;
  `a1d7f4e9b602` — re-enabling public-password demo accounts would be a security
  regression).
- Full replay from empty DB on `nexahr_r06a`: **success** (57 migrations, ~1.1 s,
  `transaction_per_migration=True`).
- `alembic check` on the migrated DB: **"No new upgrade operations detected"** —
  no model/DB drift in what autogenerate compares (tables, columns, nullability,
  types, indexes, uniques, FKs). Re-run on the realistic-data DB `nexahr_r06b` after
  all cycles: same result.
- Enum-in-transaction hazard handled correctly: `d7a2c91fb480` adds `cancelled` to
  `evaluation_status` and the *next* migration (`e4b8d03ca712`) uses it in the
  partial-index predicate — this works precisely because `env.py` sets
  `transaction_per_migration=True`; `e2c9a4b7f351` (capability enum additions) does
  an explicit mid-migration `COMMIT` to make new values usable, with
  `ADD VALUE IF NOT EXISTS` making re-runs safe after partial failure.

### 2. Model ↔ DB drift — systematic comparison (checklist 5, 12)

Script outside the repo (`/home/z/my-project/scripts/r06_drift.py`): imports the app
models, connects SQLAlchemy inspector to the migrated DB, and compares tables,
columns (presence / compiled type / nullability / defaults), indexes (columns,
uniqueness, `WHERE`), unique constraints, PKs, FKs (incl. `ON DELETE`), CHECK
constraints (via `pg_constraint` — the axis autogenerate ignores) and PG enum types
(values). Run on both the fresh DB and the realistic-data DB. Drift table:

| Axis | Model | DB (after `upgrade head`) | Drift |
|---|---|---|---|
| Tables | 31 | 32 (= 31 + `alembic_version`) | none (expected) |
| Columns (presence/type/nullability) | 292 | — | **none** (types compared by compiling both sides on the PG dialect; the `timestamptz`/enum "diffs" from naive `str()` comparison were reflection artifacts — `information_schema` confirms 59 `timestamptz` columns, 0 plain `timestamp`, and 12 native enum-typed columns) |
| Nullability | — | — | **none** (no column where code assumes NOT NULL but DB allows NULL, or vice versa) |
| Indexes | 44 declared | 91 total (44 declared + 32 PK + 15 unique-constraint-backed) | **none** (naming noise only: DB unique constraints surface as "db-only indexes" in naive comparison; column sets and uniqueness identical) |
| Unique constraints | 15 named + column-level `unique=True` | 15 | **none** (same columns; anonymous-vs-named difference is cosmetic) |
| Foreign keys | 54 | 54 | **none** — including all 10 `ON DELETE CASCADE` FKs (`ai_*`, `user_capabilities.user_id`, `notification_deliveries.notification_id`, `evaluation_comments.parent_comment_id`) present in DB with CASCADE (verified directly against `pg_constraint`; the inspector's `ondelete` key needs `options` — a naive read falsely reports `None`) |
| CHECK constraints | 10 declared | 8 present | **2 missing** (`ck_evaluation_access_supervisor_not_ceo`, `ck_evaluation_records_supervisor_not_ceo` — prior FND-03-03, cross-referenced); **4 present but `NOT VALID`** (deliberate per `e9c47b3f1a52`; enforcement on new writes verified below); 4 validated (bonus ≥ 0, bonus-needs-reason, score range ×2) |
| Enum types | 12 columns over 12 PG types | same 12 | value **sets identical** for all; `capability` **value order differs** (PG append order vs Python declaration order — no app code orders by this column, grep-verified; cosmetic) |
| Server defaults | Python-side on ai_*/misc | DB-side equivalents | **no value conflicts** (e.g. `ai_settings.max_tokens` 4000 = 4000); one-directional presence drift invisible to `alembic check` because `compare_server_default` is off in `env.py` — benign since raw-SQL inserts get the same values the ORM would write |

### 3. Audit append-only guard + hash chain (checklist 8)

- Both triggers exist in the migrated DB: `trg_audit_log_append_only` (`BEFORE
  UPDATE OR DELETE ... FOR EACH ROW`) and `trg_audit_log_no_truncate` (`BEFORE
  TRUNCATE ... FOR EACH STATEMENT`, migration `c1e5a9d2f70b`).
- Executed against the DB with a row present: `UPDATE` → **blocked**
  (`audit_log is append-only: UPDATE is not permitted`), `DELETE` → **blocked**,
  `TRUNCATE` → **blocked**, `TRUNCATE ... CASCADE` → **blocked** (statement-level
  trigger fires even though `audit_log` is FK-referencing, not referenced), `INSERT`
  → allowed, row verified intact afterwards. (On an empty table UPDATE/DELETE are
  no-ops — row-level triggers don't fire on 0 rows — which is correct trigger
  semantics, not a hole: any actual mutation of a row is refused.)
- Hash chain DDL: `prev_hash`/`entry_hash` `NOT NULL VARCHAR(64)` present; backfill
  in `e8f4b127d905` chains **pre-existing** rows (inserted 3 audit rows at the
  pre-chain revision `d2f75a9c31e8`, upgraded → all 3 chained
  `000000…→aa5ad1→e87049→9e69b3`), and the app's own `verify_chain` returns
  `{'ok': True, checked: 3}` both full and windowed (`limit=2`). The chain also
  re-backfilled correctly after two full downgrade/re-upgrade cycles.
- The chain's advisory lock (`pg_advisory_xact_lock(774120559)`) is taken in
  `log_event` before reading the last hash (concurrency covered by ROLE 07).

### 4. Partial unique indexes (checklist 6)

- `uq_open_evaluation_per_personnel`: created in `b41c07a9d2e1`
  (`WHERE status != 'finalized'`), `cancelled` enum value added by `d7a2c91fb480`,
  predicate rebuilt by `e4b8d03ca712` to `WHERE status NOT IN ('finalized',
  'cancelled')` — final DB DDL matches the model declaration exactly.
- **Semantics executed** on `nexahr_r06b`: new open record for a personnel with only
  a finalized record → **allowed**; second open record → **rejected**
  (`UniqueViolation uq_open_evaluation_per_personnel`); after cancelling the open
  record, a replacement → **allowed** (the "replacement after cancel" feature).
- Python parity: `workflow.OPEN_STATUSES = {draft, submitted, hr_approved,
  deputy_approved}` is exactly the complement of `{finalized, cancelled}` — the code
  check (`evaluations.py:411` pre-check + `IntegrityError` fallback at `:454` with
  winner re-fetch) and the DB predicate agree; `status != finalized` legacy
  comparisons were consolidated into `IS_OPEN_RECORD` (single source, comment
  documents the 8 sites that were wrong when `cancelled` was added).
- `uq_single_open_period` (`evaluation_periods`, `WHERE status='open'`) and
  `uq_single_active_scheme` (`scoring_schemes`, `WHERE status='active'`) both exist
  and match their models.
- `e4b8d03ca712`'s **downgrade safe-fail verified as documented**: with a personnel
  holding both a cancelled and an open record (legal at head), rebuilding the old
  predicate fails with `UniqueViolation` and the migration aborts cleanly — the
  intentional "refuse rather than silently corrupt" guard.

### 5. Python enums vs PG enums; string comparisons (checklist 4)

- All 12 PG enum types carry **exactly the same value sets** as the Python enums
  (`user_role` incl. `employee`/`support`, `evaluation_status` incl. `cancelled`,
  `separation_reason`, `scheme_status`, `delivery_status` incl. `abandoned`,
  `capability` ×9, etc.). `EvaluationStage` exists only in Python (API-derived from
  `status`) — correctly not a stored type.
- Grep for raw-string status comparisons (`== "draft"| "submitted"|
  "hr_approved"|…`): **zero hits on enum-typed columns** — evaluation status is
  always compared through `EvaluationStatus`. The string comparisons that do exist
  (`AiPendingAction.status == "pending"`, `SchedulerRun.status == "succeeded"` /
  `"skipped_locked"`) are on `String` columns by design — type-consistent.
- Only residual: PG `capability` enum value **order** differs from the Python
  declaration order (append-history vs declaration) — no reachable failure in app
  code (no `ORDER BY capability` anywhere); noted as cosmetic drift.

### 6. FK / ON DELETE behavior vs code expectations (checklist 7)

- Personnel: **no delete path exists** — separation (`PATCH /api/personnel` →
  `inactive`) cancels open records, closes the account, bumps `token_version`
  (backend test suite green; separation columns from `f7b3c5c8a294` nullable-by-
  design so legacy rows aren't fabricated reasons). `evaluation_records.
  subject_personnel_id` FK is NO ACTION — raw deletes of referenced personnel are
  impossible, matching "personnel are separated, never deleted".
- Users: delete endpoint manually removes `auth_sessions`/`notifications`/
  `user_capabilities` and converts residual `IntegrityError` into a clean 409 with
  guidance; DB-side CASCADEs on `ai_*` and `user_capabilities` match the models.
  Audit-history users are refused up front (409) so the append-only log keeps its
  actors.
- Periods: deletion refused in code while records reference the period (409 with
  count and guidance); `fk_evaluation_records_period_id` is NO ACTION, so the DB
  agrees even for raw SQL.
- Self-evaluation guard is **DB-enforced** via 3 triggers (`c3e8b1a76d94`), all
  present; executed: linking an evaluator user to their subject personnel →
  blocked (`self-evaluation is not allowed…`); linking a non-evaluator → allowed.
- No orphan-producing path found: every referencing FK is NO ACTION or an explicit
  CASCADE that the models declare.

### 7. Seeds and data-transforming migrations on realistic data (checklist 9, 10)

Executed scenario on `nexahr_r06b`: upgrade to `d2f75a9c31e8` (pre-hash-chain),
insert users/personnel/access/records (finalized with pct, submitted, manager-path
`hr_approved`), 6000-char evidence, 3 audit rows; upgrade to `ddafefc08701`, insert
org units (incl. an HR-named unit and a personnelless unit); upgrade to head:

- `e8f4b127d905` hash backfill chains pre-existing audit rows; `verify_chain` ok.
- `c4a1f0e93b57` truncates the 6000-char evidence to **2000** via
  `postgresql_using=left(...)` — migration survives long data by design.
- `e2b4a71c8d35` stamps **all** records to scheme v1 (correct on first upgrade);
  `b7d4e2a91c68` stamps framework v1 (with the `COALESCE(jsonb_agg…, '[]')` NOT-NULL
  guard for empty indicator sets).
- `a7f3c9b52d18` moves the manager-path `hr_approved` record to `draft` **and logs a
  warning naming the count** — verified in upgrade output ("۱ پروندهٔ بازِ مسیر
  «مدیر»…").
- `a7d3e0c194bf` stamps `hr_review_skipped=true` **only** for the personnel whose
  org unit is HR-flagged (via the `org_units` join with site/name reconstruction);
  sales personnel stay false.
- `ddafefc08701` re-populates the org catalogue from personnel (self-healing for
  referenced units; see FND-06-03 for the unreferenced-row loss on cycles).
- Seed idempotency: `65a700d744d4` bulk-inserts without re-run guards but is only
  reachable after its own (destructive) downgrade → FND-06-04;
  `1eaa459f4dde` gated by `SEED_DEMO_DATA` (default `False` in
  `config.py:109`, production-guarded at `config.py:223`) and only inserts demo
  accounts; `f2a7d3c9e861` is idempotent (`ON CONFLICT DO NOTHING`, deletes only
  non-baseline caps deliberately); `a1d7f4e9b602` only deactivates accounts whose
  password still verifies as the published demo password, bumps `token_version`,
  no-op downgrade (documented); `d5b1f3e7c920` is pure index DDL.
- Defaults (checklist 10): `b4f1c62ad8e9` raises the DB server default
  `ai_settings.max_tokens` 1200→4000 and updates only rows still sitting at 1200
  (hand-tuned values preserved); model default (`ai.py:72 default=4000`) matches —
  no consistency drift. `scoring_schemes.bonus_max_points` (5), `improvement_plan_
  max_pct` (75), ai-table defaults and `notification_deliveries.status` all match
  between model Python-defaults and DB server-defaults (drift table above).
- CHECK enforcement on new writes (the `NOT VALID` set): inserts with
  supervisor==deputy → **rejected** (`ck_evaluation_access_supervisor_not_deputy`);
  deputy==ceo → **rejected**; supervisor==ceo → **accepted** (the missing
  constraint, corroborating FND-03-03 with direct DB evidence on both
  `evaluation_access` and `evaluation_records`); bonus −1 → rejected; bonus without
  reason → rejected; bonus 0 without reason → allowed; score 6 → rejected.
- `pg_dump` of a `NOT VALID` check emits `ADD CONSTRAINT … NOT VALID` (verified with
  the PG 16.4 pg_dump on the migrated DB) — so dump/restore does **not** validate
  legacy rows and cannot fail on them; the "never validated" state is
  dump-stable (the restore-failure hypothesis was tested and disproven).
- `f2c8b41e07d9`/`a83f61b0d472` enum additions and `e2c9a4b7f351`'s mid-migration
  `COMMIT` pattern verified working in replay (see §1).

### 8. DB-enforced vs Python-only constraints (checklist 11)

**DB-enforced (verified in the migrated DB):** one open evaluation per personnel
(partial unique index); one open period; one active scoring scheme; evaluation_code
unique; verify_token unique (nullable — multiple NULLs fine, matching
"set only at finalize"); (record, indicator) uniques on scores and
self-assessment scores; `evaluation_access.personnel_id` unique; `users.username`,
`personnel.personnel_code`, org-unit (site, name), scheme/framework version, user
capability (user, capability) uniques; score range 1–5 (both score tables); bonus ≥
0 and bonus-needs-reason; supervisor≠deputy and deputy≠ceo on both chain tables
(new writes); append-only audit (triggers incl. TRUNCATE); hash chain columns NOT
NULL; self-evaluation ban (3 triggers); all FKs; text length ceilings as
`varchar(n)` (`c4a1f0e93b57`, values mirror `app/core/text_limits.py`, guarded by
`test_text_limits.py`).

**Python-only (no DB enforcement) — with risk notes:** the `supervisor≠CEO` seat
rule (missing constraint — FND-03-03's territory; the app *permits* it deliberately
as the CEO-direct shape, but the model *declares* the constraint, so the drift is
real); full chain-shape legality (manager path / CEO-direct / deputy-less combos
beyond the two enforced inequalities); status transition legality (state machine —
appropriate in code); one-notification-per-sweep dedup (non-unique
`ix_notifications_dedup`; mitigated by `notify_once` + leader-locked sweeps, ROLE
07); separation-reason-presence for inactive personnel (deliberate: fabricating
legacy reasons would be forgery); `personnel.org_unit` ↔ `org_units` catalogue
consistency (string, no FK — deliberate per `ddafefc08701`); scoring-scheme
lifecycle (only "at most one active" is DB-backed); `hr_review_skipped` consistency
with org membership at creation time. None of these Python-only rules showed an
executable DB-bypass defect within this role's scope beyond the cross-referenced
findings.

## Could not check, and why

- `b41c07a9d2e1`'s `recommendation` backfill on legacy NULL rows: could not be
  exercised without destroying the later-added test data (it runs at revision 6);
  logic is a simple source-visible `CASE` over `final_weighted_pct` — source-proven
  only.
- Migration performance on production-sized tables: all backfills/stamps
  (`e2b4a71c8d35`, `b7d4e2a91c68`, `a7d3e0c194bf`, `e8f4b127d905`,
  `c4a1f0e93b57`) are full-table scans/updates; verified correct but not timed on
  large row counts (no large fixture available).
- `e2c9a4b7f351`'s "dedicated admin" branch (granting `_ADMIN_ONLY` capabilities to
  a `support` account and stripping them from chain roles): executed only its
  no-op branch (no support account with `manage_capabilities` in the fixture); the
  data-moving branch is source-read only.
- `SEED_DEMO_DATA=true` path of `1eaa459f4dde` (actual demo account creation): not
  executed — demo seeding is an accepted decision and the gate + production guard
  were verified by source.
- Full logical dump/restore round-trip of a populated DB: only the schema-level
  `NOT VALID` preservation was verified; a data-level restore was out of time
  budget.
- Per-revision downgrade stops for each of the 55 intermediate revisions with data:
  the chain was exercised en masse (head → revision 2 with data, then targeted
  cycles past `e2b4a71c8d35`, `b28cc6abdf2a`, `ddafefc08701`, `e4b8d03ca712`);
  individual one-step-downgrade checks at every revision were not all run.
- Environmental note (not a repo issue): a concurrently running sibling reviewer
  instance caused intermittent `database "nexahr_r06b" does not exist` /
  `role "nexahr" does not exist` errors on `psql`/socket connections to the shared
  local server; all verification was re-run through a retrying psycopg helper, and
  every reported result above was captured successfully.

# ROLE 07 — Concurrency & Scheduling

Repo: NexaHR @ fc4f3fe9e5ea6fa412a16b0bbc287fb24dfe18a9 (branch review/ten-role-full-system).
Scope per task: races & transaction boundaries, audit hash-chain serialization, HR claim/handover,
double-submit, scheduler/sweeps, delivery queue, session/engine config. AI copilot (`backend/app/services/ai/**`,
`app/api/routers/ai.py`) out of scope. All reproduction was done on a disposable DB `nexahr_r07`
(alembic head c1e5a9d2f70b, dropped afterwards) with real concurrent SQLAlchemy sessions (two+ connections,
entry-barrier threads) calling the actual router functions — the same pattern as `tests/test_score_write_lock.py`.
No repo files were modified; reproduction harness deleted after the run.

## Verdict

The concurrency core of this system is genuinely solid — unusually so. Every workflow mutation path
(transition, claim, handover, reassign, extend, objection, comment, score write, self-assessment,
objection, acknowledgement, separation cancel, period delete) reads its row under
`SELECT … FOR UPDATE OF evaluation_records`, the one-open-evaluation invariant is backed by a partial
unique index with a handled `IntegrityError → 409`, the audit hash chain is serialized by a
transaction-scoped advisory lock that I could not fork even with 7 concurrent writers (including one
rolling back), evaluation codes come from a real PostgreSQL sequence, and the scheduler uses a
session-scoped advisory leader lock on a dedicated connection with a 409 on manual/scheduler overlap.
Login-failure counting is atomically create-then-lock. I reproduced the intended-safety of all of these
rather than taking comments at face value.

What remains is the periphery: the improvement-plan endpoints are the one state machine that never got
the row lock the evaluation state machine has — double-click/double-actor complete/cancel both succeed
and write contradictory permanent audit history (REPRODUCED, 20/20 natural trials). Two check-then-insert
endpoints (user create, first-time access upsert) surface raw `IntegrityError` → HTTP 500 under
duplicate concurrency instead of their clean sequential 400 (REPRODUCED). The outbound delivery sweep
sends messages before committing their `sent` status, so a crash mid-sweep re-sends (at-least-once,
SOURCE-PROVEN). None of these corrupt evaluation data or attribute a workflow action to the wrong person.

Findings: 0 CRITICAL, 1 MEDIUM, 3 LOW. All four defects are outside the evaluation-record core.

## Findings

### Top findings

**FND-07-01 | MEDIUM | REPRODUCED | backend/app/api/routers/improvement_plans.py:386-408 (`complete_plan`), :411-433 (`cancel_plan`), via `_get_plan_or_404` (db.get, no lock), :58-65 `_ensure_plan_open`**

What breaks — read-decide-write with no row lock, on a terminal state transition:

* T1: `POST /api/improvement-plans/{id}/complete` — `_get_plan_or_404` reads `status = open` → `_ensure_plan_open` passes → sets `status = completed`, `completed_at`, `log_event("improvement_plan_completed")` → commit.
* T2: `POST /api/improvement-plans/{id}/cancel` — reads the same row *before T1's commit* → sees `status = open` → passes → sets `status = cancelled`, `log_event("improvement_plan_cancelled")` → commit.
* Interleaving (observed): both SELECTs happen before either COMMIT (the window contains ≥2 more DB roundtrips: the audit advisory lock + INSERT flush + UPDATE + COMMIT).
* Wrong final state: **both requests return 200**; the DB holds one terminal status (last committer wins — in my run `completed`), but `audit_log` permanently contains **both** `improvement_plan_completed` (actor hr1) **and** `improvement_plan_cancelled` (actor hr2) for the same plan (audit ids 22 & 23 in my run). One actor received a success response for an outcome that does not exist in the final state. The plan is "مبنای تصمیم قرارداد" (contract-decision basis) per its own model docstring, so contradictory terminal history on it is an evidentiary defect, not just noise.

The same race in the double-click form (same endpoint, two rapid requests) is even easier: my un-instrumented
run of 20 synchronized double-`complete` trials **accepted both requests 20/20 times**, producing 41
`improvement_plan_completed` audit events for 21 legal completions.

How to reach it: two HR users completing/cancelling at the same moment, or one user double-clicking /
double-tabbing the "تکمیل" or "لغو" button (requests < ~50 ms apart interleave inside the read→commit window).
Contrast: the identical double-click on evaluation transitions is guarded — `evaluations._get_record_or_404_for_update`
exists precisely for this (its comment: "دوبار کلیک روی «تأیید»"), and the e2e suite asserts double-confirm → 409.

Fix: load the plan with `with_for_update()` (mirroring `_get_record_or_404_for_update`), so the loser blocks
until the winner commits, re-reads the terminal status and gets the existing clean 400 «این برنامه دیگر باز نیست».

### Additional verified findings

**FND-07-02 | LOW | REPRODUCED | backend/app/api/routers/users.py:162-192 (`create_user`)**

* T1: `POST /api/users` {username: "dup"} — duplicate-name SELECT sees nothing → INSERT → flush → …
* T2: same payload concurrently — its SELECT also sees nothing (T1 uncommitted) → INSERT → **blocks on `users.username` unique index** → T1 commits → T2's INSERT raises `sqlalchemy.exc.IntegrityError`.
* Wrong final state: the loser returns **HTTP 500 Internal Server Error** (raw exception; only `RequestValidationError`/`RateLimitExceeded` have handlers in `main.py`), while the sequential duplicate case returns a clean 400 «نام کاربری تکراری است». No corruption (transaction rolled back), but a server-crash response + stack trace for an ordinary double-submit, from two HR admins racing on the same username.
* Reproduced: outcomes `['IntegrityError']` from two concurrent real sessions.
* Fix: catch `IntegrityError` on the flush → rollback → 400/409, the exact pattern already used by `create_evaluation` (evaluations.py:452-471) and `create_period` (periods.py:81-89).

**FND-07-03 | LOW | REPRODUCED | backend/app/api/routers/evaluation_access.py:107-136 (`upsert_access`)**

* T1: `PUT /api/personnel/{id}/access` (first-ever row for that person) — SELECT finds no access row → constructs + INSERTs `EvaluationAccess` → `log_event` flush → …
* T2: same PUT concurrently — SELECT also finds none → INSERT → blocks on `uq_evaluation_access_personnel_id` → T1 commits → T2 raises raw `IntegrityError`.
* Wrong final state: **HTTP 500** for a request that is idempotent (200) when repeated sequentially; exactly one access row survives (constraint works), but the second admin sees a server error on the chain-configuration screen.
* Reproduced: outcomes `['IntegrityError']`, 1 access row.
* Fix: `INSERT … ON CONFLICT (personnel_id) DO UPDATE`, or catch `IntegrityError` → re-read and update.

**FND-07-04 | LOW | SOURCE-PROVEN | backend/app/services/delivery.py:158-195 (`run_delivery_sweep`) + backend/app/services/scheduled.py:280-298 (`run_all_sweeps` final `db.commit()`)**

* T1 (sweep): for a pending delivery row: `channel.send(Message)` **inside the transaction** (delivery.py:161-168), then `status = sent`, `sent_at` set — but the commit happens only at the end of the whole sweep (scheduled.py:298).
* Interleaving: process is killed / DB connection lost between `channel.send` and the commit (the sweep holds SMTP/SMS roundtrips for up to `delivery_batch_size` rows — a genuinely wide window).
* T2 (sweep after restart): the row is still `pending`/`failed` with `last_attempt_at` unset or old → `_is_due` → **sends the same message again**.
* Wrong final state: duplicate outbound SMS/email of an action-required notification (e.g. "پرونده … در انتظار تأیید شماست"); there is no idempotency key at the channel level to dedupe. At-least-once semantics on the crash window — a defensible tradeoff (commit-before-send would risk *losing* action-required notifications), but it is currently undocumented and unbounded (a crash mid-batch re-sends the whole sent-so-far batch).
* Fix: commit each row's `sent` state before (or immediately after) its send, or carry a per-notification idempotency token into the channel adapters; at minimum document the at-least-once contract.

## Verified correct

All of the following were verified by source **and** (where marked) executed under real concurrent DB
sessions on the disposable DB; compensating locks/constraints were hunted before accepting each claim.

1. **Audit hash-chain serialization** (`services/audit.py:75-107`): `log_event` takes `pg_advisory_xact_lock(774_120_559)` *before* reading `_last_hash`, and the lock is transaction-scoped — a waiter proceeds only after the holder's COMMIT, and its `_last_hash` SELECT (new READ COMMITTED snapshot) then sees the committed row. REPRODUCED: 6 concurrent committers + 1 concurrent roller-back → chain verifies `ok`, 0 forked `prev_hash` values (group-by check), the rolled-back writer left no row; whole-DB `verify_chain` over all 66 rows produced by the entire experiment session stayed `ok`. Grep confirms no `AuditLog` writer bypasses `log_event`, so the lock is universal; nested `log_event` calls in one transaction (claim + status_changed) chain correctly because the transaction sees its own uncommitted insert. `verify_chain` is read-only and takes no locks (safe vs. concurrent appends).
2. **Workflow transition double-submit** (`routers/evaluations.py:115-133 _get_record_or_404_for_update`, all transition endpoints): every mutation path reads the record `FOR UPDATE OF evaluation_records` first; a blocked second request re-reads the post-commit status (READ COMMITTED row-lock re-fetch) and fails cleanly. REPRODUCED (E2): double `POST /submit` → one 200, one 403; status advanced exactly once; exactly one `score_submitted` audit event. Same protection covers deputy-approve, ceo-finalize, return, cancel, extend, resolve-objection, comments (`add_comment` claims the HR seat under the same lock), and is additionally covered by the real two-connection tests in `tests/test_score_write_lock.py` (score/comment/self-assessment paths).
3. **Competing HR claims** (`workflow.claimable_if_unassigned`, evaluations.py:907-951, 1233-1273): REPRODUCED (E3): two HR users calling `hr-approve` on the same unassigned case → one 200 / one 400; `hr_user_id` set to exactly the winner; exactly one `hr_case_claimed{implicit: true}` + one `status_changed` audit row — the audit attributes the claim to the actual actor. REPRODUCED (E4): `hr-claim` racing `hr-approve` → serialized, one 403/409 clean error, coherent state (either claim-then-owner-mismatch, or approve-then-409 "در اختیار کاربر دیگری"). `hr-handover`/`reassign` use the same lock (`evaluations.py:1290, 1484`), so handover-vs-claim and reassign-vs-submit serialize identically (source-verified).
4. **One-open-evaluation invariant under concurrent creation** (`models/evaluation.py:272-277` partial unique index, evaluations.py:411-471): REPRODUCED (E5): two concurrent `POST /api/evaluations` for the same person → one 201-record, one **409** carrying the winner's `evaluation_id` — the `IntegrityError` is caught, rolled back and re-fetched (the sequential pre-check returns 409 too). No 500. `bulk_evaluation.execute` (savepoint per record, `blocked_conflict` outcome) handles the same race for cohorts. `evaluation_code` comes from `nextval('evaluation_code_seq')` (services/evaluation.py:140-142) → no duplicate-code race.
5. **Self-assessment double-submit** (`routers/me.py:308-338 _my_record_or_404(for_update=True)`, submit/object/acknowledge all use it): REPRODUCED (E9): two concurrent submissions → one 200, one 400 «خودارزیابی شما قبلاً ثبت شده»; one `self_assessment_submitted` audit event; `uq_self_assessment_record_indicator` backs it up.
6. **Login-failure counting under concurrency** (`services/login_guard.py:45-113`): atomic create-and-lock — `INSERT … ON CONFLICT DO UPDATE` (locks/creates the row even against a rolling-back competitor) followed by `SELECT … FOR UPDATE` with `populate_existing` (identity-map staleness defeated), then in-place increment. Covered by the two-connection tests in `tests/test_login_guard_concurrency.py` (no lost counts, no 500 on concurrent inserts, threshold not stretched). Counting + audit + HR notification commit atomically with the failed login attempt (auth.py:132-149).
7. **Scheduler leadership & overlap** (`services/scheduler_lock.py:32-98`, `core/scheduler.py:34-44`): `pg_try_advisory_lock` on a **dedicated connection** (the M-10 fix — lock survives mid-sweep session commits and is released by Postgres on process death); the in-process loop is sequential (`await asyncio.to_thread` then sleep), the manual `POST /api/admin/run-scheduled-jobs` goes through the same lock and 409s when the scheduler holds it (covered by `tests/test_scheduler_reliability.py` with real second connections). Every run (succeeded/failed/skipped_locked) is recorded in `scheduler_runs`; failures roll back to a clean `failed` row.
8. **Sweep idempotency**: `notify_once` windows keyed per (user, dedup_key incl. status/date) prevent re-creation on repeated sweeps; same-key collisions across the serialized sweep runner and request-path callers don't overlap in practice (sweep keys `sla:/orphaned:/contract_expiry:/improvement_review:` vs. request-path `seats_vacated:`/`lockout:`). `run_document_backfill_sweep` is bounded (batch 20) and guarded by the `evaluation_documents.evaluation_record_id` unique index; `archive_final_pdf` (documents.py:79-87) explicitly handles the background-task vs. download vs. sweep race with a SAVEPOINT + re-read fallback — the exact double-render window its comment describes. `purge_stale` and `run_delivery_sweep` retry/backoff (exponential `_retry_delay`, abandon on non-retryable or max attempts) are idempotent re-runs.
9. **Separation vs. finalize race** (`routers/personnel.py:555-584`): the departure close-out locks the open evaluation row `FOR UPDATE` before `cancel_on_separation`, so a concurrent CEO finalize cannot leave a finalized-then-cancelled (signed document invalidated) record — the lock-order comment at personnel.py:548-554 is accurate. `periods.delete_period` likewise locks the period row `FOR UPDATE` (periods.py:192-194) between count and delete; `create_period` handles the open-period unique-index race → 400.
10. **Lock ordering / deadlock freedom between row locks and the chain lock**: every `FOR UPDATE` acquisition (evaluation rows, login_attempt row, period row) happens *before* the first `log_event` in its transaction, and nothing takes the chain advisory lock and then a row lock — so there is no lock-order inversion; empirically no deadlock among 7 concurrent chain writers. The advisory locks live in disjoint key spaces (774_120_559 chain, 815_243_907 sweep).
11. **Session/engine config** (`db/session.py`): `autocommit=False, autoflush=False`; transactions begin on first statement; `get_db` closes the session in `finally` (close ⇒ implicit rollback of uncommitted work on exception — no partial commits leak from failed requests); each router commits exactly once at the end of its unit of work (exceptions between mutation and commit roll back mutation + audit + notifications atomically — verified for the transition paths, login, refresh); the only loop-commit service (`personnel_import.commit_import`) commits once after the whole import; engine uses `pool_pre_ping` + explicitly sized pool with documented rationale. `bulk_evaluation` uses per-record savepoints, not per-record commits.
12. **Refresh-token rotation race (two tabs refreshing simultaneously)**: `rotate_session` is read-then-write without a row lock, so two concurrent refreshes on the same jti can both rotate and leave two live sessions. This matches the explicit design intent of the 60-second rotation grace («دو تب هم‌زمان که هر دو refresh می‌زنند نباید کاربر را از سیستم بیرون بیندازند») — accepted behavior, not reported as a defect. Sequential reuse outside grace still triggers family revocation.

## Could not check, and why

- **True multi-instance deployment**: everything scheduler-related was reviewed under the single-instance assumption stated in the task; the advisory leader lock is designed for replicas and unit-tested with two connections, but no real 2-process uvicorn deployment was run.
- **Live channel delivery under crash injection** (FND-07-04): no SMTP/SMS endpoint was exercised with a process kill mid-send; the finding is source-proven (send-before-commit ordering is unambiguous in the code), not crash-reproduced.
- **Process-kill during PDF background archival**: the SAVEPOINT + unique-index design in `archive_final_pdf` was reviewed and its dedicated tests read (`test_documents.py`), but I did not kill the process mid-WeasyPrint-render.
- **AI copilot paths** (`services/ai/**`, `routers/ai.py` — including their many `db.commit()` sites and confirmations): out of scope per task.
- **Frontend double-submit guards** (button disabling, draft autosave interleaving with submit): client-side behavior is outside this backend-concurrency role; the server-side lock makes it non-critical.
- **`pg_advisory_unlock` timing under connection-pool recycle** (scheduler_lock M-10 scenario): verified by the dedicated connection design and its tests; not re-verified under forced pool recycle.
- **Personnel-import concurrent runs**: single-commit design reviewed by source; not raced (two concurrent imports of the same rows would surface as duplicate `personnel_code` 500s of the FND-07-02 class, but import is a rare, single-operator operation and was left at source-level inspection).

# ROLE 08 — Persian, RTL, Jalali & Time

Repo: NexaHR @ fc4f3fe9e5ea6fa412a16b0bbc287fb24dfe18a9 (branch `review/ten-role-full-system`). AI copilot out of scope. All verification on disposable DB `nexahr_r08` (ICU PostgreSQL 16.4 @ localhost:5434, dropped afterwards) + vitest with `TZ=Asia/Tehran`; temp test files deleted; `git status` clean of my files.

## Verdict

**The Persian/RTL/Jalali/time architecture is fundamentally sound and unusually well-engineered.** Storage is UTC everywhere (`DateTime(timezone=True)` on every timestamp column, `datetime.now(UTC)` at every write site, zero `date.today()`/`utcnow()` remnants in app code); the single UTC↔local crossing lives in `core/clock.py`, which fails loudly on a bad `ORG_TIMEZONE`, uses the tz database (no hardcoded +03:30), and provides local-day boundaries that **all** date-range filters use (evaluations list + xlsx export, reports ×3 endpoints, audit log list + export, AI analytics tool). The legal PDF renders `finalized_at`/`evaluation_started_at` in org-local Jalali with Persian digits; the frontend's independent Birkesh/Jalaali algorithm agrees with backend `jdatetime` on **every month start of 1402–1408** (incl. leap years 1403/1408, Esfand 29/30, Nowruz edges) — executed, not assumed. Enum→Persian label maps are complete on both sides (statuses incl. `cancelled`, stages, separation reasons, roles incl. `support`, 81/81 audit event labels). RTL CSS is logical-first (`insetInlineStart`, deliberate RTL popover anchoring, flipped pagination/calendar chevrons, `dir="ltr"` isolation for codes/usernames/IPs/URLs), and unhandled 500s surface as Persian text with a request ID.

The defects are on the periphery of this discipline, in the layer *between* the well-localized surfaces: backend-authored Persian message bodies carry **Latin digits** and **Gregorian dates** (one of which lands verbatim in the legal document's comment table), two frontend preset helpers anchor "today" to the **UTC** day (the exact bug class `clock.py` documents eliminating), the public verify page renders the document timestamp in the **viewer's** timezone rather than the org's, and two switch controls on the same page move their knobs in opposite directions for the same state.

Counts: 2 MEDIUM (FND-08-01, FND-08-02), 3 LOW (FND-08-03, FND-08-04, FND-08-05); 0 CRITICAL/HIGH.

## Findings

### Top findings

**FND-08-01 | MEDIUM | REPRODUCED | backend/app/api/routers/evaluations.py:1196,1222; backend/app/services/evaluation_window.py:104**
What breaks: Gregorian ISO dates printed inside Persian user-facing sentences, on three surfaces — (a) the submission-extension comment recorded on the case: «تمدید مهلت ثبت تا 2026-01-05 — دلیل: …»; (b) the extension notification: «مهلت ثبت پروندهٔ EVL-… تا 2026-01-05 تمدید شد» (in-app bell + outbound email/SMS body); (c) the expired-window 400 detail shown to a late submitter: «مهلت ثبت این دوره در 2026-01-01 به پایان رسیده است…». Worst case (a): `snapshot.py` collects **all** `EvaluationComment` rows (lines 59–61) and `evaluation_summary.html` renders `comment_text` verbatim in the «کامنت‌های مراحل بررسی» table — so a Latin Gregorian date is printed **on the hashed legal document**, whose own dates (`تاریخ شروع ارزیابی`, `تاریخ نهایی‌شدن`) are rendered in Jalali with Persian digits by the same template. This contradicts the repo's own documented standard (`pdf.fa_digits`: mixed digits were treated as a defect «روی مدرکی که امضا و بایگانی می‌شود»), and the same deadline is displayed in Jalali everywhere else in the UI (`SubmissionDeadlineBar`, `OpenCaseCard`, Excel export).
How to reach it: HR extends a deadline on a draft case (POST `/api/evaluations/{id}/extend-submission`) → comment + notification created; case is later finalized → snapshot includes the comment → PDF prints it. The 400 error is returned by any score/self-assessment submit after the deadline. Reproduced: rendered `evaluation_summary.html` with the exact f-string output the endpoint writes and asserted it appears in the document HTML («تمدید مهلت ثبت تا 2026-01-05» present next to «۱۴۰۴/۱۰/۱۱ ساعت ۰۰:۳۰»); endpoint→snapshot→template chain source-proven with no unresolved assumptions.
Fix: format these three sites with a date-only Jalali helper (e.g. `jdatetime.date.fromgregorian(...).strftime("%Y/%m/%d").translate(_PERSIAN_DIGITS)`, extracted next to `to_jalali` so `pdf.py`, `excel.py` and messages share it). Keep audit `old_value/new_value` ISO (machine data), translate only human text.

**FND-08-02 | MEDIUM | REPRODUCED | frontend/src/pages/hr/AuditLogPage.tsx:53-55; frontend/src/pages/hr/ReportsSection.tsx:428-430**
What breaks: `todayIso()` — `new Date().toISOString().slice(0, 10)` — anchors the contract-expiry filter presets («۳۰ روز», «۶۰ روز», …, «منقضی‌شده») to the **UTC day**, not the org-local day. Between 00:00 and 03:29 Tehran the presets' "today" is yesterday: at 01:00 org-local, «منقضی‌شده» sets `contract_end_to` to the previous day, so contracts ending *today* are excluded from the report, while the backend (`dashboard.py:454` `today = today_local()`, `scheduled.run_contract_expiry_sweep`) counts them as expiring — the two disagree every night. This is the exact bug class `core/clock.py` was written to eliminate («مهلتی که دیشب تمام شده بود همچنان باز به‌نظر می‌رسید»), surviving in the frontend.
How to reach it: any HR user opens Reports or Audit-Log between 00:00–03:29 Tehran and clicks a date preset. Reproduced: vitest with `vi.setSystemTime(new Date("2025-12-31T21:00:00Z"))` under `TZ=Asia/Tehran` (= 2026-01-01 00:30 org-local): the exact function body returns `"2025-12-31"` while the local-day key is `"2026-01-01"`.
Fix: derive the ISO key from local components (the same pattern `SubmissionDeadlineBar.tsx:39-42` already uses for `todayKey`), ideally as one shared `localTodayIso()` in `utils/dates.ts` replacing both private copies. Workaround exists (the resulting range is shown in the Jalali pickers and is editable), hence MEDIUM not HIGH.

**FND-08-03 | LOW | REPRODUCED | backend/app/services/scheduled.py:70,136,214; backend/app/services/notifications.py:204,264,327; backend/app/api/routers/me.py:385; backend/app/services/personnel_import.py:450,490,503**
What breaks: Latin digits inside backend-authored Persian text that reaches users — notification/SMS/Email bodies and error details. Reproduced message texts: «قرارداد «کارمند مرزی» **3** روز دیگر به پایان می‌رسد…» (contract sweep), «پرونده EVL-… (…) بیش از **3** روز است در همین مرحله منتظر اقدام شماست» (SLA sweep), plus the same pattern in «و **12** مورد دیگر» and «در **2** پروندهٔ باز» (`notifications._seat_list` / `notify_vacated_seats`), «(**7** روز پس از مشاهدهٔ نتیجه)» (objection-window error, `me.py`), and «(ردیف **5** همین فایل)» / «دست‌کم **8** نویسه» (import row errors). These flow to the in-app `NotificationBell` (renders `n.message` raw), the outbound SMTP/SMS channel bodies, API 400/404 details, and the import preview dialog. Inconsistent with the system's own convention: the PDF Persianizes every number, and the frontend renders every count via `toLocaleString("fa-IR")` (~40 call sites grep-verified).
How to reach it: run the scheduler (or click «اجرای یادآوری‌های خودکار» on the HR dashboard) with any expiring contract or stalled case. Reproduced on `nexahr_r08`: executed `run_contract_expiry_sweep` and `run_sla_sweep`, asserted the stored `Notification.message` matches `[0-9]` and contains no `۳`.
Fix: reuse the `_PERSIAN_DIGITS` translation (move `fa_digits` to a shared core module) at message-construction time, or apply it once at the `notify()`/`notify_once()`/channel boundary (messages only — never dedup keys). Numbers stay correct, so LOW severity (readability/consistency, not correctness).

### Additional verified findings

**FND-08-04 | LOW | SOURCE-PROVEN | frontend/src/pages/hr/AdministrationPage.tsx:461 vs :560**
What breaks: the two switch controls on the same Administration page move their knobs in **opposite** directions for the same semantic state. Module toggle (`role="switch"`, h-6 w-11, knob 20px): `enabled → "right-0.5"` = ON knob at physical **right** (start side in RTL); policy-field toggle (w-14, knob 24px): `true → "right-7"` = ON knob at physical **left** (end side). The RTL-mirrored switch convention (and the second switch's own behavior) is OFF at start / ON at end — the module toggle inverts it, so an administrator flipping both sees contradictory affordances on one page. Geometry is deterministic from the class strings (no runtime assumptions). Mitigated by track color (`bg-pulse-600` vs gray) and `aria-checked`.
How to reach it: HR → مدیریت → ماژول‌ها vs تنظیمات سیاست (same page).
Fix: one convention via logical positioning (`start-*`/`end-*`) — extract a shared `Switch` component, the same consolidation the codebase already did for `SearchInput`/`Table`/popovers.

**FND-08-05 | LOW | REPRODUCED | frontend/src/pages/VerifyPage.tsx:128**
What breaks: the public (unauthenticated, QR-scanned) verify page renders `finalized_at` with `formatDateTime` → `Intl.DateTimeFormat("fa-IR")` in the **viewer's browser timezone**, while the printed document shows the same instant in Tehran time (`to_jalali` → `to_local`). Demonstrated with the exact formatter the component calls: instant `2025-12-31T21:00:00Z` prints as «۱۴۰۴/۱۰/۱۱ ساعت ۰۰:۳۰» in the PDF, but renders as «۱۰ دی ۱۴۰۴، ۱۶:۰۰» in a UTC−4 environment — the authenticity page shows a **different Jalali day** than the legal document it vouches for. Tehran-based viewers match; anyone verifying from outside the org timezone (auditor, VPN) sees a mismatched date beside the SHA-256 and validity claim.
How to reach it: scan the QR of any finalized document from a device outside UTC+3:30.
Fix: pass `timeZone: "Asia/Tehran"` (org timezone, already a backend setting) to the Intl formatter used by this page — the public page should be anchored to the document's timezone, not the viewer's (see Proposal P1).

## Verified correct

**Backend time core**
- `core/clock.py`: UTC storage; `to_local` (naive→UTC assumption explicit); `now_local`/`today_local`; `local_day_start/day_end` (upper bound exclusive, day-inclusive); invalid `ORG_TIMEZONE` raises `RuntimeError` instead of silently falling back to UTC; `ZoneInfo` throughout — no hardcoded +03:30 anywhere in `backend/app` (grep-verified); Tehran's no-DST status handled by the tz database, nothing assumes DST transitions.
- Every timestamp column is `DateTime(timezone=True)` (all 40+ model sites grep-verified) and every write site uses `datetime.now(UTC)`; no `date.today()`/`datetime.utcnow()` in app code. API datetimes serialize **aware** (offset present — reproduced via TestClient: `created_at` ends with `+00:00`/`Z`), so the frontend's `new Date(iso)` always gets an unambiguous instant; `date` fields (deadlines, contract dates) serialize as plain `YYYY-MM-DD`.
- Date-range filters use local-day boundaries at **every** site: `evaluations.py` `_apply_evaluation_filters` (shared by list and `export.xlsx` — the export shows exactly what HR filtered), `reports.py` `_record_conditions` (summary, by-unit, by-indicator) and the xlsx report (lines 286–288), `audit_log.py` (list + export, 104–107), `ai/tools/analytics.py` (out-of-scope area, also correct). `analytics.py` router has no date-range filters. Verified with a New-Year edge: `local_day_start(2026-01-01) == 2025-12-31T20:30Z`, `local_day_end == 2026-01-01T20:30Z`.
- Submission window: deadline DATE compared against `today_local()`; open through the last local minute, closed the next local day, `days_left == -1` (boundary reproduced); no-period records unlimited; extension only ever lengthens (`window_for`). The deadline reaches the UI both as `submission_deadline` (list + detail) and in Jalali.
- Objection window: elapsed-instant comparison (`acknowledged_at + timedelta` vs `datetime.now(UTC)`) — timezone-independent by construction, correct.
- Sweeps: run every `scheduler_interval_seconds=300` under the advisory leader lock (the doc-comments calling them «جاروی شبانه» are an anachronism — cadence is 5 minutes, with `notify_once` dedup windows preventing spam; more frequent is strictly better for orphan detection, no defect). Date horizons use `today_local` (contract expiry, improvement review); SLA cutoff is elapsed time (correct); document backfill orders by `finalized_at` and is capped per run.
- Dashboard `expiring-contracts`: `today_local` horizon; `days_remaining` against local today; frontend renders it with Persian digits (`toLocaleString("fa-IR")`, DashboardPage:773).

**Jalali correctness (executed)**
- `pdf.to_jalali`: converts to org-local **before** `jdatetime` conversion — boundary reproduced: `2025-12-31T21:00:00Z` → «۱۴۰۴/۱۰/۱۱ ساعت ۰۰:۳۰» and one minute earlier → «۱۴۰۴/۱۰/۱۰ ساعت ۲۳:۵۹»; ISO-string snapshots (incl. `+00:00`) parse via `fromisoformat`; invalid values pass through untouched so old snapshots still render.
- Frontend `utils/jalali.ts` (independent Birkesh/Jalaali implementation) **matches backend `jdatetime` on all 84 Jalali month starts for 1402–1408** (both directions), on the leap-day boundaries (1403/12/30 ↔ 2025-03-20, 1402/12/29 ↔ 2024-03-19, Nowruz 1403/1404), on leap-year classification (1403, 1408 leap; 1402, 1407 not), and on month lengths — executed as a vitest with a jdatetime-generated reference table. The e2e conversion case 1406/06/01 ↔ 2027-08-23 verified. `isoToJalali`'s date-part regex is only ever fed date-only strings (JalaliDatePicker values); the timestamp-rendering path uses `Intl`, so no UTC-date-part Jalali bug exists (`formatJalali` is export-only, unused in app code).
- `personnel_import.parse_flexible_date`: accepts Jalali/Gregorian, Persian **and** Arabic-Indic digits, `-`/`.`/`/` separators, and pre-converted Excel datetimes; year ≤ 1500 disambiguates Jalali; **rejects Esfand 30 in non-leap years** (1402/12/30 → `None`, reproduced); template row ships Persian-digit Jalali dates. Excel export↔import round-trip reproduced including the leap day («۱۴۰۳/۱۲/۳۰» → 2025-03-20 → back).
- JalaliDatePicker: weekday grid starts شنبه in the rightmost column; month navigation follows the Persian calendar convention (right chevron = previous, documented); Persian digits throughout; portal-based popover with RTL-aware right-edge anchoring and two-sided viewport clamping (`useAnchoredPopover` uses `a.right - width`, not translateX — the documented RTL trap).

**PDF / fonts / bidi**
- Template is `lang="fa" dir="rtl"`; every business date passes the `jalali` filter (org-local), every number the `fa` filter (Persian digits, `٫` decimal separator); identifiers (evaluation code, personnel code, username) deliberately stay Latin — with the Latin half of the same font family (existing tests prove only Vazirmatn/Vazirmatn-Latin embed, no DejaVu fallback, and the Latin half is actually used; `url_fetcher` blocks everything outside `templates/` except data URIs; autoescape on).
- Raw enum values never print on the document: `snapshot.comments` stores the raw stage but the template maps through `_STAGE_LABELS` (hr_review/deputy_review/ceo_final — complete vs the backend `CommentStage` enum) at render time so old snapshots stay stable.
- Bidi: Persian sentences with Latin codes/URLs render as isolated LTR runs (verify URL is terminal in its block); `+۳` resolves correctly in RTL context; WeasyPrint complex shaping covered by the existing PDF suite.
- `text-align: right` in the PDF's RTL document context is start-alignment — correct.

**Persian digits / localization maps**
- Frontend renders every number via `toLocaleString("fa-IR")` or `toPersianDigits` (pagination, score form incl. slider labels and word counters, charts, badges, dashboard, notification counters, import dialogs — grep-verified, no raw `{number}` in Persian text found).
- Enum label maps are complete on both sides (script-compared against backend enums): `EvaluationStatus` 6/6 incl. `cancelled` (STATUS_LABELS, Excel `_STATUS_LABELS` — the previously-missing `cancelled` is fixed in both), `CommentStage` 3/3, `SeparationReason` 5/5, `UserRole` 6/6 incl. `support`, `ImprovementPlanStatus` 3/3, `PersonnelStatus`; **audit event labels: backend 81 = frontend 81, zero diff**.
- No stray English UI strings: full-source scan for multi-word English in user-visible strings found none (all Persian; `APP_NAME`/"Developed by DbsStudio" are deliberate isolated `dir="ltr"` branding); ErrorBoundary is fully Persian.
- Server errors reaching users: the http middleware converts **unhandled** exceptions (incl. the raw IntegrityErrors of FND-07-02/03) into a Persian 500 detail with a request ID; `RequestValidationError` and 429 have Persian handlers; frontend `extractErrorMessage` falls back to Persian. No English error-text path to the Persian UI found.

**RTL CSS audit (complete sweep of physical left/right classes)**
- Logical-first where it matters: `useAnchoredPopover` (RTL anchor + edge clamping), `plot.tsx` (`insetInlineStart`, with a comment explaining why `translateX` breaks in RTL), chart colors via CSS variables (dark-theme safe), `ms-2` in SubmissionDeadlineBar, `border-s` in plot reference marks.
- Every remaining physical class reviewed and correct for a fixed-RTL app: search icon `right-3`+`pr-9` (start side), password eye `left-2`+`pl-11` (end side), select chevrons `left-2` (end side), mobile drawer `right-3` + `x:"100%"` (start side, slides from right), Toast `left-1/2 -translate-x-1/2` (centered — RTL-safe), bell/profile popovers `left-0` with the buttons at the header's end (extend inward), Sidebar/RoleOverviewCards accent bars `right-0/right-1` (start side), comment threads `border-r-2 pr-3` (start side), `dir="ltr"`+`text-left` for LTR numerics/emails/IPs/usernames (MyScoringPage, DashboardPage, AdministrationPage, NotificationPreferencesPage, VerifyPage hash), actions column `text-left` at the end of RTL rows (IndicatorsPage/ImprovementPlans), mobile-card `dd text-left` (label-at-start / value-at-end layout).
- Directional icons flip correctly: PaginationControls (previous = right chevron, next = left chevron); JalaliDatePicker month/year arrows follow the Persian calendar convention; score slider gradient `to left` with RTL-consistent dot/thumb/label positions (documented in source).
- The only directional inconsistency is FND-08-04 (the two switches).

**Dark theme**
- Variable-override architecture (`[data-theme="dark"]`) covers text grays (source-stated 4.85:1–14.22:1 on card surface), pulse tints, chart/plot variables, the `bg-white` variant patch list (incl. `focus:`/`hover:`/opacity variants), modal scrim, native `select` options, `ring-white`, `text-pulse-600` — Persian text color/legibility handled at the token level; light theme untouched by construction.

## Could not check, and why

- **Visual RTL/dark rendering in a real browser** — no browser in the sandbox; RTL layout, chevron appearance and dark-mode Persian legibility assessed via source reading, existing component tests (285 vitest) and the CSS token audit above.
- **PDF text-layer extraction** — no `pdfminer`/`pypdf` in the backend venv; Jalali-on-document assertions were made at the rendered-HTML layer (identical strings flow into WeasyPrint) plus the existing byte-stability/font-embedding tests for real PDF output.
- **Live SMS/Email rendering of Persian** — no live provider; channel code reviewed in source (UTF-8 JSON body, `set_content` charset detection, percent-encoding for URL templates; `_render` explicitly handles the «پرونده EVL-0007 (نام فارسی)» case).
- **Non-Tehran browser behavior in production** — the org is Tehran-only by design, so date-only `formatDate` shifting one day for negative-offset browsers (`new Date("2026-08-23")` = UTC midnight → «۳۱ مرداد» in a NY browser vs «۱ شهریور» in Tehran, demonstrated programmatically) and `todayJalali()`'s browser-local anchor are recorded as a proposal/limitation, not a defect.
- **Jalali algorithm agreement beyond 1402–1408** — both implementations are the standard Birkesh family with breaks covering 1178–3178; the 7-year executable cross-check (incl. two leap years) plus boundary days is the practical envelope.
- **Frontend copilot UI RTL specifics** — out of scope per instructions.
- **Scheduler cadence under real multi-replica deployment** — leader lock and sweep concurrency already covered by ROLE 07.

## Proposals

**P1 — Anchor user-visible timestamps to the org timezone** | Outcome: any viewer, anywhere, sees the org's wall clock — the public verify page stops showing a different Jalali day than the printed legal document, and traveling/VPN staff see Tehran time on all records. | Change: pass `timeZone: "Asia/Tehran"` (expose `org_timezone` via the existing config endpoint or a build-time constant) to the `Intl.DateTimeFormat` instances in `frontend/src/utils/dates.ts`; apply globally or at minimum to `VerifyPage.tsx`. | Files: `frontend/src/utils/dates.ts`, `frontend/src/pages/VerifyPage.tsx`, `backend/app/api/routers/config.py`. | Surface: all timestamp displays; public verify page. | Risks: users who preferred their local timezone lose it (single-org Tehran deployment — acceptable); needs the tz name to reach the frontend. | Compat: additive. | Priority: medium.

**P2 — One `localTodayIso()` helper for date presets** | Outcome: filter presets never anchor to the UTC day; the night-shift HR report matches the backend's local-day math; one implementation instead of two private copies. | Change: add `localTodayIso()` to `utils/dates.ts` (local components, like `SubmissionDeadlineBar.todayKey`) and replace both `todayIso()` copies. | Files: `frontend/src/pages/hr/AuditLogPage.tsx`, `frontend/src/pages/hr/ReportsSection.tsx`, `frontend/src/utils/dates.ts`. | Surface: audit-log and reports date presets. | Risks: none (pure function swap); pairs with the FND-08-02 fix. | Priority: medium.

**P3 — Persian digits + Jalali dates in backend-authored messages** | Outcome: notification, SMS and email bodies and API error details match the system's own Persian-digit/Jalali convention; the legal document never again carries a Gregorian date in its comment table. | Change: move `fa_digits`/a date-only Jalali formatter to a shared core module and apply at message construction: `scheduled.py` (days), `notifications.py` (seat counts), `me.py:385` (objection window), `evaluations.py:1196,1222` + `evaluation_window.py:104` (Jalali deadline), `personnel_import.py` (row numbers / min length). Never translate dedup keys or audit `old_value/new_value`. | Files: listed call sites + new `app/core/persian.py` (or reuse `app/services/pdf.py` helpers). | Surface: in-app notifications, outbound email/SMS, 400 error details, import preview, legal PDF comment table. | Risks: tests asserting exact message strings need updating; keep dedup keys ASCII (they are length-capped at 120 chars — Persian digits are also single chars, so length is safe). | Compat: message-text only. | Priority: medium.

**P4 — Shared `Switch` component with logical positioning** | Outcome: one knob-direction convention across the app; the module and policy toggles stop contradicting each other on the same page. | Change: extract a `role="switch"` component using `start-*`/`end-*` (or one fixed physical convention) and replace both AdministrationPage implementations. | Files: `frontend/src/pages/hr/AdministrationPage.tsx` (2 sites), new `frontend/src/ui/Switch.tsx`. | Surface: admin module + policy toggles. | Risks: visual-only; track color already disambiguates state. | Compat: additive. | Priority: low.

# ROLE 09 — Frontend Correctness & Accessibility

Repo: NexaHR @ fc4f3fe9e5ea6fa412a16b0bbc287fb24dfe18a9 (branch `review/ten-role-full-system`), frontend only (AI Copilot components out of scope per Role 04 exclusion).
Method: full source read of `frontend/src` (pages, components, auth, api, ui, utils, index.css, public/sw.js) cross-checked against backend `TRANSITIONS` / routers / schemas / `text_limits.py` / `core/modules.py`; baseline suite (285 tests / 47 files) + lint + build all green before and after; 8 temporary vitest tests written in `frontend/src/pages/` to REPRODUCE findings (all 8 passed, file deleted afterwards, `git status --porcelain` clean). Evidence statuses: REPRODUCED = executed vitest; SOURCE-PROVEN = complete reachable failure from source.

Cross-referenced, NOT re-reported: FND-02-01 (no-deputy chain at `hr_approved` dead-ends UI finalize, misleading "deputy review" stage label), FND-02-02 (return/comment act by role not seat), FND-03-02 (computePreview rounding divergence), FND-01-01/FND-05-01 (server-side module/read enforcement), FND-08-02 (todayIso UTC-day presets), FND-08-04 (AdministrationPage switch direction), FND-08-05 (VerifyPage tz).

## Verdict

The frontend is unusually deliberate: token-in-memory auth with single-flight refresh, query cache cleared on both login and logout, fail-closed module gating, focus traps, skip link, reduced-motion support, a service worker that never caches `/api`, and per-case scoring rules/indicators. The 285-test suite is real behavior testing, not smoke. The defects concentrate in exactly two places: **chain-shape coverage** (the action gating and confirm-dialog/stepper/label texts know the "full chain" shape but not the manager-path / CEO-only / HR-subject shapes the backend explicitly supports — 4 findings, incl. two server-legal workflow actions with no product UI) and **light-theme contrast of hint text** (one systemic WCAG AA failure). No data-corrupting or cross-user-leak frontend defect was found.

Counts: **5 MEDIUM, 3 LOW; 0 HIGH, 0 CRITICAL.**

## Findings

### Top findings

**FND-09-01 | MEDIUM | REPRODUCED | frontend/src/pages/EvaluationDetailPage.tsx:563-571 (dialog), :229-232 (hrClosesTheCase), frontend/src/components/WorkflowStepper.tsx:12-17, frontend/src/types.ts:611 (STATUS_LABELS)**
What breaks: on the **manager path** (no unit-supervisor seat; the deputy is the first scorer), HR's approve confirm-dialog says «پرونده به مرحله بررسی معاونت منتقل می‌شود» ("the case moves to deputy review") — but the backend transition is `hr_approve_manager`: `submitted → deputy_approved`, i.e. straight to the CEO-final stage, because the deputy has *already scored* (workflow.py:282-300, evaluations.py:945-947). The same chain-shape blindness makes `STATUS_LABELS.deputy_approved = «تأییدشده توسط معاونت»` claim a deputy approval that never happened, and the WorkflowStepper paint the «معاونت» step green-done (consumed/nonexistent) for manager-path and CEO-only chains (only `hr_review` has a skip flag). HR approves believing a second reviewer (deputy) still stands between them and the CEO's signature — for the organization's most sensitive evaluations (managers), there is none.
How to reach: any manager-path case (personnel with no supervisor, e.g. `is_manager` scored by deputy) reaches `submitted`; HR opens the detail page and clicks «تأیید (منابع انسانی)». Reproduced: vitest rendered the page for a manager-path evaluation and asserted the dialog shows «مرحله بررسی معاونت منتقل می‌شود».
Fix: branch the dialog label/description on `isManagerPath` (`unit_supervisor_user_id === null && deputy_user_id !== null`) → «پرونده به تأیید نهایی مدیرعامل منتقل می‌شود» (mirror the existing `hrClosesTheCase` third branch); add a `deputySkipped`/`deputyConsumed` prop to WorkflowStepper (dashed step like `hrSkipped`), and qualify the deputy_approved status label for these chains.

**FND-09-02 | MEDIUM | REPRODUCED | frontend/src/pages/EvaluationDetailPage.tsx:241-245 (canCeoFinalize) + :528 (ReturnBox gating) vs backend/app/services/workflow.py:393-403 (ceo_return_ceo_only accepts `submitted`)**
What breaks: a CEO on the **CEO-only chain** (they scored the case themselves, `ceo_submit`) cannot retract their own submission while it sits in the HR queue. The backend deliberately allows `ceo_return_ceo_only` from **`submitted`** — its own comment calls this «پنجرهٔ *اصلیِ* اصلاح» (the main correction window), because once HR finalizes (hr_finalize_direct_ceo) the case never passes `deputy_approved` again. The frontend renders the ReturnBox only for `canHrApprove || canDeputyApprove || canCeoFinalize`, and `canCeoFinalize` requires `status === "deputy_approved"`, so at `submitted` the CEO (who *can* view the case — `_ensure_can_view` chain seats) gets no return control at all; `isEditableScoring` is also draft-only. The server-legal correction window is unreachable in the product UI.
How to reach: CEO-only chain case at `submitted`; CEO opens `/evaluations/{id}`. Reproduced: vitest asserted no «برگشت پرونده به مرحله قبل» control and no «تأیید نهایی» button is rendered.
Fix: render the ReturnBox for the CEO on ceo-only chains also at `status === "submitted"` (condition: `user.role === "ceo" && ceo_user_id === user.id && isCeoOnlyPath && status === "submitted"`); the backend already routes to `ceo_return_ceo_only` → `draft`.

**FND-09-03 | MEDIUM | REPRODUCED | frontend/src/pages/EvaluationDetailPage.tsx:249-252 (canRecoverStuckCase = role==="hr" only), :548-555 (HrRecoveryBox render), frontend/src/components/SubmissionDeadlineBar.tsx:45 (canExtend = isHr) vs backend/app/api/routers/evaluations.py:1094-1096,1144-1146,1476-1479 (cancel/extend-submission/reassign all `require_roles(hr, deputy, ceo)` + `ensure_may_administer`)**
What breaks: for **shielded HR-subject cases** (`hr_review_skipped`), the server grants the entire rescue toolbox — cancel (`cancel_hr_subject`), extend-submission, stage-owner reassign — to deputy/CEO, precisely because the HR shield (`ensure_may_administer`/`hr_panel_is_shielded`) blocks HR from those cases (backend comments: without this "پروندهٔ بازِ عضوِ HR با صندلیِ خالی هیچ راهِ خروجی نداشت"). The frontend renders `HrRecoveryBox` (cancel/handover/reassign) and the deadline-extend button **only for `user.role === "hr"`** — the one actor the server will 403. The designed deadlock-escape for HR-subject cases is unreachable in the product UI; the only exit left is a direct API call.
How to reach: any `hr_review_skipped` case stuck with a vacant/unreachable seat; the seated deputy (or CEO) opens the detail page. Reproduced: vitest rendered a shielded HR-subject case at `hr_approved` for the seated deputy — approve button present, but no «پروندهٔ گیرکرده» box, no «لغو پرونده», no «تمدید مهلت».
Fix: extend `canRecoverStuckCase` and `canExtend` to the server-allowed actors on shielded cases (deputy/CEO seated in that chain, mirroring `ObjectionPanel.resolverSeatId` which already does exactly this for resolve-objection); hide the HR-only handover sub-tool for them.

**FND-09-06 | MEDIUM | REPRODUCED | frontend/src/pages/employee/MyEvaluationsPage.tsx:322-329 (open-case cards gated on `employee_evaluation_visibility`) + no consumer of the `?self-assessment=` query param anywhere in `frontend/src` vs backend/app/api/routers/me.py:87-110 (`/me/evaluations/open` served with no module gate) + app/core/modules.py (`self_assessment` default ON, `employee_evaluation_visibility` default OFF) + app/services/self_assessment.py `invite()` (notification links to `/me?self-assessment={id}`)**
What breaks: the employee self-assessment feature is unreachable in the default configuration. The open-case card (status + the only self-assessment form entry) renders only when `employee_evaluation_visibility` is ON (default OFF), while the backend serves `/me/evaluations/open` **unconditionally** — its own doc comment says knowing a case is open "هیچ ربطی به دیدن نمرهٔ پیش‌نویس ندارد" — and gates only the *submit* on the separate `self_assessment` module (default ON). Out of the box: HR sends the «دعوت به خودارزیابی» invite (server sends the notification with `link="/me?self-assessment={id}"`), the employee clicks it, lands on `/me`… where the card is suppressed; the deadline passes silently and the employee's independent perspective is lost. Even with visibility ON, the deep-link parameter is ignored — nothing in the frontend reads `?self-assessment=`, so the form never auto-opens from the invite.
How to reach: default module config, any employee with an open case; or HR's invite notification link. Reproduced: vitest (a) with `self_assessment=true, employee_evaluation_visibility=false` and `/me/evaluations/open` returning an open case → no «پروندهٔ در جریان» card rendered; (b) with visibility ON at `/me?self-assessment=1` → card renders but the form is not opened by the link.
Fix: gate the open-case card on the `self_assessment` module (matching the server semantics), keep results/acknowledge/objections on `employee_evaluation_visibility`; read the `self-assessment` query param on mount to auto-open (and focus) the form for that case. (The server-side module-enforcement inconsistency itself is FND-01-01/FND-05-01 cross-ref, out of scope here.)

**FND-09-05 | MEDIUM | REPRODUCED (WCAG relative-luminance formula) | frontend/src/index.css (light `gray-400` not overridden → Tailwind default #9ca3af) + 145 non-test usages of `text-gray-400`, e.g. frontend/src/pages/employee/MyEvaluationsPage.tsx:205, frontend/src/components/employee/OpenCaseCard.tsx:62, frontend/src/pages/EvaluationDetailPage.tsx:331/415/443, frontend/src/ui/Table.tsx:181**
What breaks: in the **light theme**, `text-gray-400` (#9ca3af) on white/gray-50 cards computes to **2.54:1**, failing WCAG 2.1 AA (4.5:1 normal text) by a wide margin. It is not decorative-only: it carries the objection-rights signpost («اگر به این نتیجه اعتراض دارید، پس از ثبت مشاهده…» — the only pointer to the objection path), the open-case privacy notice, comment/empty-state/table-empty texts. The dark theme remaps `--color-gray-400: #858ca6` = 4.81:1 (passes, measured in the CSS comments), so the defect is light-specific. Low-vision users lose guidance text precisely where it explains legal remedies.
How to reach: open any list/detail page in light theme. Reproduced: vitest computing the WCAG ratio (light 2.54 < 4.5, dark 4.8 ≥ 4.5).
Fix: raise the light hint tone to `gray-500` (#6b7280 = 4.77:1) for text usage, or define a semantic `--color-hint` used by text (leaving borders/dots at 400); add a source-scanning test in the style of `darkTheme.test.ts` forbidding `text-gray-400` on body/guidance strings.

### Additional verified findings

**FND-09-04 | LOW | REPRODUCED | frontend/src/pages/EvaluationDetailPage.tsx:234 (canHrApprove), :254-257 (canComment)**
When another HR user owns the case (`hr_user_id` set to someone else), the page simultaneously renders the owner bar «— تأیید و برگشت این پرونده با ایشان است» *and* the «تأیید (منابع انسانی)» button, comment box, and ReturnBox; clicking yields a 403 with the Persian owner message. Contradicts the codebase's own stated rule (PermissionsContext: «گزینه‌ای که اجازه‌اش را نداری، بهتر است اصلاً نباشد تا اینکه باشد و کلیکش ۴۰۳ بگیرد»). Reproduced: vitest asserted both the button and the owner-bar render for a non-owner HR user. Fix: gate on `evaluation.hr_user_id === null || evaluation.hr_user_id === user.id` (keeping the claim-from-shared-queue flow when unassigned).

**FND-09-07 | LOW | SOURCE-PROVEN | frontend/src/auth/PermissionsContext.tsx:70-76 + frontend/src/main.tsx:33-34 (global `refetchOnWindowFocus: false`, no interval; single permanent observer in the provider; no invalidation on 403)**
The `my-permissions` query has `staleTime: 60s` but no refetch trigger ever fires after first load: window-focus refetch is globally off, no `refetchInterval`, the provider is the only observer (never remounts), and a 403 response does not invalidate it. Capability/module revocation done by *another* admin leaves the affected user's sidebar and module-gated controls stale until a full page reload; clicks then 403 (fail-safe direction — server enforces — but the "hidden = server rules" UX contract is broken for the rest of the session, including long-lived tabs). Fix: `refetchInterval: 120_000` (cheap endpoint), or invalidate `["administration","my-permissions"]` from the axios interceptor on any 403.

**FND-09-08 | LOW | SOURCE-PROVEN | frontend/src/pages/EvaluationDetailPage.tsx:488-496 («پاسخ» reply trigger), frontend/src/components/NotificationBell.tsx:112 («علامت‌گذاری همه…»), frontend/src/components/EvaluationList.tsx:322-326 (tab pills ~30px OK), frontend/src/ui/Table.tsx:58-71 (sort buttons ~24px, borderline)**
A handful of text-only buttons have no vertical padding and `text-xs` (≈16px rendered height): the comment «پاسخ» trigger and the bell's mark-all-read. That is below the WCAG 2.2 AA 2.5.8 minimum target size (24×24 CSS px) — a motor-impaired pointer user can reliably miss them. Severity LOW (few controls, functional, keyboard-reachable). Fix: add `min-h-6 min-w-6` (ideally 32–44px) padding to text-only triggers.

## Verified correct

- **Axios client / auth plumbing** (`api/client.ts`): access token in memory only (no localStorage/sessionStorage — no XSS token theft, no shared-machine residue); refresh via HttpOnly cookie with single-flight `refreshPromise`; auth-endpoint 401s excluded from refresh (login errors preserved); `_retry` guard prevents loops; failed refresh → hard redirect `/login` (full reload ⇒ cache reset); `extractErrorMessage` handles string `detail` and `{message}` objects with a Persian fallback; backend `validation_errors.py` translates 422s to Persian field-labeled strings, so no English-leak path found.
- **React Query hygiene** (`main.tsx`, `api/queries.ts`): every filter/sort/page/seat param inside the `queryKey` (no stale-filter collisions; `undefined`/empty normalized by hashing); `keepPreviousData` on paginated lists; debounced search (300ms); retry policy skips all 4xx (no double rate-limit consumption); `staleTime 30s` global; notifications poll 5s visible / 60s background with focus refetch.
- **Cache boundaries**: `queryClient.clear()` on **both** login and logout (cross-user leakage on shared machines prevented — the code comments even document the pre-fix leak); `clearAppCaches()` deletes all SW caches on logout; `PermissionsContext` query key includes `user?.id`.
- **Invalidation coverage after mutations** (45 sites audited): workflow actions invalidate detail + lists (`refetchType: "all"`, fixing the mount-race documented in-code) + notifications + whole `dashboard` tree; `acknowledge`/`object` invalidate `me`+`dashboard`; scoring-scheme changes invalidate `scoring-schemes` **and** `config` (form rules follow the active scheme); indicator edits invalidate `evaluation` details (per-case forms re-check); personnel/org-unit edits invalidate both trees; Administration mutations invalidate `["administration"]` which prefix-matches the acting user's own `my-permissions`. Autosave writes the *server response* into the cache (`setQueryData`, not optimistic guess; no rollback debt — no optimistic mutations exist outside Copilot scope).
- **Fail-closed module gating** (`PermissionsContext`, `App.tsx` ModuleRoute, `MyEvaluationsPanel`): `isModuleEnabled` returns false for unknown/unloaded modules; every sensitive consumer checks `!loading && moduleEnabled(...)`; a failed `/administration/my-permissions` fetch renders modules OFF (switch that fails open is not a switch — documented and tested in `PermissionsContext.test.tsx`).
- **Router/guards**: `ProtectedRoute` renders a loading state while auth resolves (fail-closed, no flash of denied content); `anyCapability` waits for permissions; `requireOwnPersonnel` for `/me` mirrors `require_own_personnel`; unauthorized deep links redirect to the role home; catch-all `*` → `/` (no 404 page by design; module-off routes render a friendly `DisabledFeature` instead); `must_change_password` force-redirect; per-route keyed `ErrorBoundary` (render errors reset on navigation) + global boundary.
- **Status/action-map parity vs backend TRANSITIONS** (full matrix over all 6 chain shapes): full-chain approve/return/comment gating matches seat ownership and stage exactly (incl. `RANK` mirroring `_CHAIN_RANK` for higher-rank substitution); `STAGE_BY_STATUS` mirrors `_STAGE_BY_STATUS` (cancelled → no stage); `STATUS_LABELS` covers all 6 statuses; comment endpoints' role/status/claim semantics (incl. implicit `hr_case_claimed`) match `canComment`; queue tabs map all statuses incl. the cancelled tab; deputy-in-supervisor-seat and CEO-as-scorer editing conditions match `may_act_at` + assignee rules; submit routing (4 chain shapes × hr-subject) handled by one endpoint the frontend calls uniformly. Gaps found are FND-09-01/02/03 (+ cross-refs FND-02-01/02-02).
- **Forms parity**: password min-length 10 both sides with honest required/optional rule split (no fake composition rules that would ban Persian); bonus cap/min-reason read from the **case's** `scoring_rules` (P1-04 parity); evidence word-count clamp + per-config required scores; employee-role ⇒ personnel link required client and server; 409 duplicate-open-case auto-navigates to the existing case; Persian/Arabic digit input normalized (`toMachineNumber`) so Persian keyboards don't produce "not a number".
- **a11y infrastructure**: Modal + mobile drawer share `useFocusTrap` (Tab/Shift-Tab cycling, Escape, scroll lock, focus restore, `aria-modal`/`aria-labelledby` via id); skip-link to main content; global `:focus-visible` outline (contrast raised to 4.06:1 in-code); `aria-sort` on sortable `<th>`; `role="tablist"/"tab"` + `aria-selected`; toasts use `role="alert"/"status"`; bell button `aria-label` with unread count, Escape closes and refocuses; `prefers-reduced-motion` kills all animations; JalaliDatePicker is a labeled `dialog` with `aria-expanded` trigger and month/year nav labels; **zero `onClick` on non-interactive elements** (div/span/li/tr audit clean); RTL icons directionally correct with in-code rationale; Latin codes/usernames wrapped `dir="ltr"`; Persian digits via `toLocaleString("fa-IR")` throughout.
- **Responsive/mobile**: `Table` converts to definition-list cards below `md` (single view rendered, not CSS-hidden duplicates — screen readers don't double-read); mobile sort controls preserved; scoring form switches to `ScoreCardList` on narrow viewports; sticky action bar; horizontal scroll intentionally visible for wide tables.
- **PWA/service worker** (`public/sw.js`, `pwa.ts`): `/api/**` and `/verify/**` never cached; hashed `/assets` cache-first; navigations network-first with a 503 RTL Persian offline shell; `controllerchange` reload guarded against loops; registration prod-only; `CACHE_VERSION` bump policy documented; `clearAppCaches()` on logout. Deployment-after-upgrade concerns are handled (index.html never cache-first).
- **Dark theme**: implemented by CSS variable overrides with a source-scanning coverage test (`darkTheme.test.ts`) that caught the `focus:bg-white`/`bg-white/90` class variants; explicit rules for scrim, `ring-white`, native select popups, brand-text vs brand-surface split; dark text tones documented as contrast-measured.
- **Persian long text**: comment/evidence bodies use `whitespace-pre-wrap` where structure matters; badges `whitespace-nowrap`; stepper labels truncate; code strings short. (No visual verification possible — see limitations.)

## Could not check, and why

- **No real browser available**: visual layout, real-DOM focus order/focus trap behavior beyond unit tests, actual rendered contrast, mobile widths and table overflow at real breakpoints, RTL visual flow, font rendering, motion behavior, real service-worker install/update lifecycle, real 401-refresh races under latency. All of these were verified by source + jsdom unit tests only.
- **Focus traps in real DOM** — asserted via `focusTrap.test.tsx`/`Modal.test.tsx` (Tab cycling logic tested in jsdom), not a real screen reader.
- **Actual touch-target rendering** (FND-09-08 sizes are class-derived, not measured in a browser).
- **Copilot UI** — excluded by role assignment.
- **Personnel import / bulk-create Excel flows** — source-read + existing unit tests; no real workbook round-trip in this role (Role 08 executed the backend side).
- **Cross-tab / multi-window cache behavior** — no browser; single-tab semantics only.
- **Live notification polling timing** (5s/60s) — verified in source; not observable without a browser.

## Proposals

- **P1 — One chain-shape module for action gating & texts** | Outcome: every chain shape (full / no-deputy / manager / manager-hr-subject / ceo-only / ceo-only-hr-subject) sees correct next-stage wording, reachable return/finalize/rescue actions, and an honest stepper; no more "stage that never was". | Change: extract `isManagerPath/isCeoOnlyPath/isCeoOnlyHrSubject/hrClosesTheCase` into a shared module (mirroring backend `workflow.py`), consume it in `canCeoFinalize`/ReturnBox gating/`canRecoverStuckCase`/dialog texts/WorkflowStepper (deputy step dashed when consumed)/status label qualifiers. | Files: `frontend/src/pages/EvaluationDetailPage.tsx`, `frontend/src/components/WorkflowStepper.tsx`, `frontend/src/types.ts`, new `frontend/src/utils/chain.ts`. | Surface: evaluation detail + home queues. | Risks: low — pure predicate extraction; covered by the existing evaluation-page test patterns. | Priority: high.
- **P2 — Employee self-assessment reachability** | Outcome: with the default module config, an invited employee lands on `/me` with the open-case card visible and the form auto-opened/focused; deadlines stop passing silently. | Change: gate open-case cards on the `self_assessment` module; read `?self-assessment={id}` on mount to open that case's form; (optionally) surface a badge on the nav «کارنامه من» while a self-assessment is open. | Files: `frontend/src/pages/employee/MyEvaluationsPage.tsx`, `frontend/src/components/employee/OpenCaseCard.tsx`. | Surface: employee scorecard + supervisor "my self-assessment" tab. | Risks: none server-side (endpoint already ungated); keep results-gated sections on the visibility module. | Priority: high.
- **P3 — Client-side length parity with `text_limits.py`** | Outcome: users learn the 4000/1000/2000-char limits while typing (with a live counter), not from a post-submit 422 — even though that error is already Persian and field-labeled. | Change: add `maxLength` (+ optional counters) to evaluator comment, chain comments, return/cancel/handover/reassign reasons, objection text/resolution, self-assessment notes, matching `COMMENT_MAX/EVALUATOR_COMMENT_MAX/REASON_MAX/OBJECTION_MAX/SELF_ASSESSMENT_*`. | Files: `EvaluationDetailPage.tsx`, `ObjectionPanel.tsx`, `MyEvaluationsPage.tsx`, `HrRecoveryBox.tsx`, `SubmissionDeadlineBar.tsx`, `OpenCaseCard.tsx`. | Surface: all free-text decision fields. | Risks: none; keep limits in one shared constant module. | Priority: medium.
- **P4 — Refresh `my-permissions` during long sessions** | Outcome: capability/module revocations reflect in nav and module-gated UI within ~2 minutes (or immediately after any 403), keeping "hidden = server rules" true for the session. | Change: `refetchInterval: 120_000` on the permissions query, and/or invalidate `["administration","my-permissions"]` in the axios response interceptor on 403. | Files: `frontend/src/auth/PermissionsContext.tsx`, `frontend/src/api/client.ts`. | Surface: sidebar, module routes, employee page gating. | Risks: trivial load; no behavior change when permissions unchanged. | Priority: medium.
- **P5 — Light-theme hint-text contrast pass** | Outcome: guidance/meta text in light theme meets AA (4.5:1) for low-vision users; dark theme unchanged. | Change: introduce `--color-hint` (= gray-500-level for text) and swap `text-gray-400` on content-bearing strings; keep 400 for borders/dots; add a `theme.test.ts`-style source scan forbidding `text-gray-400` adjacent to guidance strings. | Files: `frontend/src/index.css` + the ~15 content-bearing sites (not all 145 — many are borders/icons). | Surface: whole light theme. | Risks: visual tone shift; do with the design token, not per-site edits. | Priority: medium.
- **P6 — Minimum target size for text-only triggers** | Outcome: «پاسخ», mark-all-read, and similar mini-buttons become reliably hittable (≥24×24, ideally 32–44px). | Change: add `min-h-6 min-w-6` (or padding) to text-only buttons; audit with a class scan for `text-xs` buttons without height/padding. | Files: `EvaluationDetailPage.tsx`, `NotificationBell.tsx`. | Surface: comments, notifications. | Risks: none. | Priority: low.

# ROLE 10 — Performance

Scope: cost & scaling inside the real product constraints — one Iranian org, single-instance PostgreSQL 16, FastAPI + SQLAlchemy 2 (sync sessions), Persian-first RTL SPA. AI Copilot backend (`app/services/ai/**`) excluded. Repo at `fc4f3fe9e5` (branch `review/ten-role-full-system`), read-only; all scripts under `/home/z/my-project/scripts/` (`r10_seed.py`, `r10_measure.py`, `r10_phaseB.py`, `r10_capture.py`, `r10_explain.sql`, `r10_explain2.sql`, `r10_sweep.py`).

**Measurement environment** (every number below comes from these runs):
- Portable PostgreSQL 16.4, `localhost:5434`, dedicated DB `nexahr_r10`, 57 alembic migrations applied, collation `fa-x-icu`.
- Backend venv Python 3.12.14, in-process `fastapi.testclient.TestClient` (no network hop), `ENABLE_SCHEDULER=false`.
- SQL statements counted per request with an SQLAlchemy `before_cursor_execute` listener on the app's engine (BEGIN/COMMIT/SAVEPOINT excluded). Timings = median of 5 repetitions after 1 warm-up call (3 reps for PDF/exports/integrity); single-user, warm caches.
- **Workload phase A** (≈ org year 1–2): 201 personnel / 3 sites / 8 units, 12 chain users + 100 employee accounts, 3 periods, **602 evaluation records** (400 finalized past + 202 current-period mixed incl. 36 `evaluation_returned`-flagged), 10,560 score rows, 1,024 comments, 57 final snapshots, 240 notifications, **8,791 audit rows** with a valid hash chain.
- **Workload phase B** (≈ 5-year history of the same 200-person org): **4,220 evaluation records**, **82,800 score rows**, 12 closed periods, **50,821 audit rows**, 178 notifications created by one measured sweep. All inserts used the app's own models/`build_final_snapshot`/hash-chain canonical function.

## Verdict

**Sound where it matters most day-to-day.** Every list surface — evaluations, personnel, users, audit log, notifications, improvement plans — issues a **constant** number of SQL statements (4–6) regardless of page size (50→200) and of table growth (602→4,220 records): pagination, `was_returned` enrichment, and per-row name lookups are all joins/batch queries, not per-row loops. Dashboard, analytics, executive and report endpoints are SQL-aggregated with fixed query counts. Index coverage matches the live query set; the audit-log page query stays 0.13 ms at 50k rows. PDF is one-time-rendered then served archived (404 ms first render, ~12 ms after); exports build in-memory but scale linearly without failure; the scheduler sweep is bounded (20 PDFs/run).

**Three defects a real HR org will feel as history accumulates** (all reproduced on the 5-year workload): the audit-integrity check recomputes the whole hash chain in Python per request (1.3 s at 50.8k rows, auto-fetched on the audit-log page, growing ~forever); the HR dashboard overview runs the same heavy indicator aggregate 4 times (346 ms at 5-year scale, disk-spilling sorts); `/api/improvement-plans/eligible` is an unbounded 625 KB / 3,354-row payload rendered as one DOM table. Plus three LOW findings (repeated full-table subquery scans in my-scoring/report, uncapped evaluations Excel export, one cache-wide React Query invalidation).

No HIGH findings: nothing times out or fails at realistic single-org scale.

## Findings

### Top findings

**FND-10-01 | MEDIUM | REPRODUCED | backend/app/services/audit.py:130–171 (+ routers/audit_log.py:225–240, frontend/src/components/AuditIntegrityBadge.tsx:18–23)**
`GET /api/audit-log/integrity` loads **every** `audit_log` row into ORM objects and re-hashes each in Python (`verify_chain`), on every request. `audit_log` is append-only and grows with every login (seeded 8.8k rows for ~1 year; 50.8k for ~5 years).
- Measured: **257 ms @ 8,791 rows → 1,307 ms @ 50,821 rows** (median of 3; TestClient, 3 SQL statements — the cost is the Python loop: **~25.7 µs/row**, linear, no cap). At the same growth rate 100k rows ≈ 2.6 s, 200k ≈ 5 s.
- It is not a rare manual action: `AuditIntegrityBadge` auto-fetches it whenever the HR audit-log page mounts (staleTime 60 s), so the audit-log page itself drags a request that grows for the life of the system, occupying a worker thread the whole time.
Fix: anchor-and-suffix verification — persist a `verified_up_to (id, entry_hash, checked_at)` checkpoint advanced only after a full verify (nightly sweep); the endpoint verifies only rows after the anchor and reports `verified_up_to` alongside `full: false`. Deep full-chain check stays available as an explicit action.

**FND-10-02 | MEDIUM | REPRODUCED | backend/app/api/routers/dashboard.py:261–298 (`_indicator_stats` called 4× at 295–298)**
`GET /api/dashboard/overview` (the HR landing page) executes the same 3-table aggregate (indicators × evaluation_scores × evaluation_records, `GROUP BY indicator` + `count(DISTINCT subject_personnel_id)` + `ORDER BY avg LIMIT 5`) **four times** — weakest/strongest × general/specialized.
- Measured endpoint: **40.4 ms @ 602 records → 346.5 ms @ 4,220 records** (14 queries, constant count; growth is per-query row volume).
- EXPLAIN (ANALYZE, BUFFERS) on one of the four, at 82,800 score rows: **92.8–103.8 ms**, `Sort Method: external merge Disk: 8864kB`, `temp read=1108 written=1110` — `count(DISTINCT …)` forces a full sort of the 48,924-row join **per call**, spilling to disk at default `work_mem`. 4 × ~90 ms ≈ the whole endpoint.
- Linear extrapolation at 10-year / 800-person scale (~16k records, 320k scores): ≈ 1.4 s per dashboard load.
Fix: one pass — a single `GROUP BY indicators.id, section` query (20 rows) computing avg + cohort size; pick top/bottom-5 per section in Python. Same numbers, one scan instead of four, no disk spill. (The `by_org_unit`/`by_evaluator`/window-function queries are already fine: 4.8–6.6 ms each.)

**FND-10-03 | MEDIUM | REPRODUCED | backend/app/api/routers/improvement_plans.py:108–152 (+ frontend/src/pages/hr/ImprovementPlansPage.tsx:183–213)**
`GET /api/improvement-plans/eligible` has **no limit/offset** — it returns every finalized-below-threshold record without a plan, with subject names, and `ImprovementPlansPage` renders the whole list as one `<table>` (`eligible.map(...)`, no pagination on that card).
- Measured @ 4,220 records (5y): **3,354 items, 625,349 bytes JSON, 167.3 ms** server-side (2 queries — the payload, not N+1, is the problem), plus ~3.3k table rows (≈13k DOM nodes) in the browser.
- Grows linearly with org history: every finalized low-score record without a plan stays eligible forever (eligible only shrinks as plans get created). At 10-year scale expect ~1.3 MB payloads and multi-second page loads.
Fix: paginate the endpoint (`limit/offset` + optional `q`) and give the "نیازمند برنامه بهبود" card the same `PaginationControls` used on the plans list below it; optionally default to the latest period.

### Additional verified findings

**FND-10-04 | LOW | REPRODUCED | backend/app/api/routers/analytics.py:108–241 (+ api/routers/reports.py:124–179)**
The same heavy subquery is re-executed several times per request (constant count, linear row growth per redundant scan):
- `GET /api/analytics/my-scoring` (supervisor): the "everyone else's scores" join (`evaluation_scores × evaluation_records WHERE supervisor != me`) is compiled into **5 separate statements** (count, count-distinct-people, avg, per-score distribution, per-indicator aggregate). Measured: **27.9 ms @ 602 → 137.9 ms @ 4,220 records**; EXPLAIN: 22.6 ms per plain count scan + 87.3 ms for the by-indicator variant (external merge, 1.5 MB disk) at 82.8k score rows.
- `GET /api/dashboard/report/summary`: the shared `base` subquery is run 3× (count, avg, cohort size) + one 4-way indicator aggregate (EXPLAIN: **120 ms**, 2 MB disk spill) → endpoint **18.1 → 84.0 ms**.
Fix: materialize once (`WITH … AS MATERIALIZED` / `.cte()` with combined aggregates), or collapse count/avg/distinct into one grouped statement. Keeps the pages flat as history grows.

**FND-10-05 | LOW | REPRODUCED | backend/app/api/routers/evaluations.py:699–746 (+ services/excel.py:123–141)**
`GET /api/evaluations/export.xlsx` streams nothing and caps nothing: it loads every matching record (`db.scalars(...).all()`, subject join included) and builds the whole openpyxl workbook + `BytesIO` in RAM before responding. Measured: **261 ms @ 602 records → 934 ms @ ~4,066 exported rows (0.23 ms/row, linear; 208 KB file)**. SQL is only 4.3 ms of that — the rest is Python workbook building (incl. `to_jalali` per row). The audit-log export deliberately caps at 5,000 rows; this one does not (10-year scale ≈ 2.3 s, still no failure). Fix: a row cap consistent with the audit export (with a truncation notice in the audit event it already logs), or openpyxl `write_only` mode.

**FND-10-06 | LOW | SOURCE-PROVEN | frontend/src/components/copilot/CopilotPanel.tsx:196**
The AI-panel confirm handler calls `queryClient.invalidateQueries()` **with no key** — this marks the entire React Query cache stale and refetches every mounted query (notifications, evaluations, dashboard, personnel, config…) after a single copilot action confirmation. Reachable from the floating Copilot panel on any page for users with AI access. (AI backend is out of scope; this is the frontend cache layer.) Fix: invalidate the specific families the action can touch, as every other mutation in the codebase already does — e.g. `["evaluations"]`, `["dashboard"]`, `["notifications"]`.

## Verified correct

Measurement table (TestClient, warm, median; **q** = SQL statements per request; phase A = 602 records/8,791 audit rows, phase B = 4,220 records/50,821 audit rows):

| Endpoint (caller) | q @ 602 | ms @ 602 | q @ 4,220 | ms @ 4,220 | Pattern |
|---|---|---|---|---|---|
| `GET /api/evaluations?limit=50` (HR) | 4 | 12.9 | 4 | 19.4 | **constant** (1 auth + 1 count + 1 page + 1 `was_returned` batch) |
| `GET /api/evaluations?limit=200` (HR) | 4 | 23.9 | 4 | 28.8 | constant; payload 53.7→214.7 KB for 50→200 items |
| `GET /api/evaluations?limit=50&offset=250` | 4 | 16.6 | 4 | 20.5 | constant (SQL limit/offset, deep page no worse) |
| `…&was_returned=true` | 4 | 11.9 | 4 | 13.7 | constant; EXISTS filter 0.93–1.3 ms via `ix_audit_log_event_type` (plan verified) |
| `…&q=<name>` / `&status=` / `&org_unit=` / `&seat_user_id=` | 4 | 11.6–13.9 | 4 | 11.3–28.7 | constant count; all filters in SQL |
| `GET /api/evaluations/{id}` (detail) | 8 | 9.6 | 8 | 10.3 | constant |
| `GET /api/dashboard/overview` (HR) | 14 | 40.4 | 14 | 346.5 | constant count, **linear time** (FND-10-02) |
| `GET /api/dashboard/overview?site=کارخانه` | 15 | 35.2 | 15 | 253.0 | constant count, linear time |
| `GET /api/dashboard/pipeline` | 2 | 4.0 | 2 | 5.2 | constant, single aggregate |
| `GET /api/dashboard/period-trend` | 2 | 5.3 | 2 | 8.1 | constant |
| `GET /api/dashboard/stage-stats` | 4 | 12.3 | 4 | 32.7 | constant count; time-limited by `stage_stats_window_days` |
| `GET /api/dashboard/expiring-contracts` | 2 | 6.0 | 2 | 6.0 | constant; 135 rows / 24.9 KB @ 5y |
| `GET /api/dashboard/role-overview` (hr/sup/dep/emp) | 2–5 | 3.7–6.9 | 2–5 | 3.7–6.9 | constant; 3–5 COUNTs per role, no loops |
| `GET /api/dashboard/report/summary` | 6 | 18.1 | 6 | 84.0 | constant count, linear time (FND-10-04) |
| `GET /api/audit-log?limit=50` (+event_type filter) | 5 | 7.7–9.7 | 5 | 7.7–9.5 | **constant** — page query 0.13 ms at 50.8k rows via `ix_audit_log_created_at` |
| `GET /api/notifications?limit=15` (poll) | 4 | 5.8 | 4 | 6.0 | constant; 0.026 ms page plan via `ix_notifications_user_read` |
| `GET /api/personnel?limit=50` / `limit=1000` | 6 | 11.7 / 23.3 | 6 | 12.3 / 23.0 | constant — `_with_accounts` enrichment is 3 batch queries (usernames, open records, access) |
| `GET /api/users?limit=50` | 4 | 7.6 | 4 | 12.4 | constant |
| `GET /api/periods` / `/api/improvement-plans?limit=50` | 2 / 3 | 4.5 / 5.2 | 2 / 3 | 4.4 / 6.1 | constant |
| `GET /api/analytics/executive` (CEO) | 17 | 16.2 | 17 | 28.0 | constant count; Python-side median/p90 over all finalized rows is 2.1 ms SQL |
| `GET /api/analytics/my-scoring` (sup) | 14 | 27.9 | 14 | 137.9 | constant count, linear time (FND-10-04) |
| `GET /api/me/evaluations`, `/open` (employee) | 2 / 4 | 4.0 / 6.3 | 2 / 4 | 3.8 / 6.1 | constant; per-person bounded |
| `GET /api/evaluations/{id}/summary.pdf` (archived) | 8 | 12.8 | 8 | 11.4 | constant; archived bytes served from DB |
| `GET /api/evaluations/export.xlsx` | 5 | 260.8 | 5 | 933.8 | constant count, linear rows (FND-10-05) |
| `GET /api/personnel/export.xlsx` | 5 | 59.4 | 5 | 40.5 | see scaling below |
| `GET /api/audit-log/export.xlsx` (cap 5,000) | 6 | 576.8 | 6 | 565.8 | **capped** — constant at 5y; SQL 5.1 ms, rest is workbook building |
| `GET /api/dashboard/report/export.xlsx` | 9 | 27.8 | 9 | 104.3 | mirrors report/summary |

Additional verified-correct items from the role checklist:

- **No N+1 anywhere measured.** Evaluation list enrichment is: `subject`/`hr_user` as `lazy="joined"` (single page query with LEFT JOINs — plan shows hash/limit, 4.0 ms), `was_returned` via one batch `IN`-list query (0.16 ms; comment in code explicitly documents the N+1 fix); detail page's per-record `_was_returned`/`window_for`/`indicator_ids` are single-row lookups on indexed keys. Personnel list `_with_accounts`, users export, improvement-plans export all use the documented pre-fetched dicts. `_outcome_mix` fetches only `rank = 1` rows (201) to Python.
- **Pagination at SQL level everywhere listed**: evaluations (limit ≤ 200), personnel (≤ 1000), users, audit log (≤ 200), notifications (≤ 100), improvement plans (≤ 200) — no Python slicing of full tables found. The two unbounded-by-design reads are `/api/me/evaluations` (per-person, small) and FND-10-03.
- **`was_returned` filter & flag are index-backed**: both query forms use `ix_audit_log_event_type` (index scan, 0.16 ms batch / 1.3 ms semi-join at 50.8k rows). A composite `(event_type, evaluation_record_id)` would be marginally better but the measured plans are already sub-millisecond — not worth a finding.
- **Index coverage vs query set** (checked `pg_indexes` on the seeded DB): evaluation_records has 11 indexes all mapped to live query paths (`status+created_at` composite for list filters, `subject`/`supervisor`/`deputy`/`ceo`/`hr_user` for scoping, `final_pct` for pct filters & lowest-20, `stage_entered_at` for SLA sweep, partial `open_objection`, partial unique open-evaluation guard); audit_log 3 indexes all used (event_type, record, created_at for ORDER BY); notifications `user_id+read_at` composite + `user_id+dedup_key+created_at` for `notify_once`. No unused/write-only index found by code-reading; `users.role` and `personnel.contract_end_date` lack indexes but measured full-table costs at 5y scale are 6.4 ms / trivial (201–5,000-row tables) — not defects at this scale.
- **Per-row scalar-subquery loops: absent.** `is_module_enabled`/`stored_module_state` use `db.get` (identity-map cached; measured 1–2 module queries per request, not per row); `module_states` for the administration page is one SELECT; `User.personnel_full_name` is a correlated scalar subquery inside the single users SELECT.
- **PDF in request path: bounded and acceptable for single-org.** First render (WeasyPrint, in-request only when the document isn't archived yet): median **404 ms** (min 362, max 480, n=5, ~39 KB output, 10 queries) — the finalization endpoint itself already moved rendering to a background task (P2-05), and the download path archives idempotently; archived serves in ~12 ms. Sweep backfill is capped at **20 documents/run**; measured full `run_all_sweeps` on the 5-year DB: **9.8 s wall, 778 statements, docs 5→25, 143 SLA + 35 contract notifications created, then one commit** — background, bounded, single transaction ~10 s every 5 minutes is fine for a single instance.
- **Excel personnel export scaling** (measured by inserting real rows): 201 rows → 41 ms warm; 1,000 → 200 ms; 5,000 → 851 ms (851 KB… 229 KB file). Linear, in-memory, no failure — acceptable for a single org; the synthetic rows were removed afterwards.
- **Frontend bundle & loading**: every route except LoginPage is `lazy()` (App.tsx) — each page its own chunk; Recharts lives only in the `PersonCharts` chunk (381.36 kB / gzip 108.66) imported by `PersonScorecard` (dashboard analysis tab) and `EmployeeProfileModal`, not in the entry; entry `index` 379.01 kB (gzip 114.48) = app shell (Layout/auth contexts/EvaluationList/shared UI) + react-query + router, with react-dom split into a 121 kB vendor chunk; Vazirmatn self-hosted, unicode-range subset (arabic/latin/latin-ext × 3 weights), `font-display: swap`; whole `dist/` 2.0 MB. No monolithic bundle problem.
- **React Query defaults are sane**: global `staleTime: 30_000`, `refetchOnWindowFocus: false` (main.tsx:33–34) — no focus refetch storms; invalidations across the app are scoped by key family (`["evaluations"]`, `["personnel"]`, `["users"]`…); the one unscoped call is FND-10-06. Chart components (`PersonCharts`, `PeriodTrendChart`) re-render only when their query data changes (no polling on dashboard queries; charts don't remount on unrelated refetches) — memoization absence is harmless at these data sizes (≤ 20 radar points / 12 trend points).
- **Polling**: notifications poll 5 s visible / 60 s hidden per tab (`queries.ts:338`); measured server cost per poll: 4 queries, ~6 ms, 3 KB. 30 concurrently-online users ≈ 6 req/s ≈ 24 indexed queries/s on the single instance — trivial, and the interval is an explicit, documented freshness decision. The live-indicators 15 s poll only runs on the open self-assessment form (`OpenCaseCard`), payload = 20 rows.
- **Login cost** (Argon2 verify) measured 84–91 ms — expected for the KDF choice, not a defect.

## Could not check, and why

- **Production index usage (`pg_stat_user_indexes`)** — no live deployment exists in this environment; index usage was assessed by matching every declared index to at least one reachable query path in source plus EXPLAIN plans on the seeded DB.
- **Concurrent multi-user behaviour** — TestClient executes serial requests in-process; the numbers are single-user. Concurrent-worker contention (Argon2 CPU saturation, advisory-lock queuing on `log_event`) was not measured; the advisory lock serialization is by design for chain integrity (single instance accepted).
- **Browser-side rendering cost of 3,354-row tables / recharts** (FND-10-03's DOM side) — no browser profiling in this role; payload size and row counts are measured, DOM impact assessed from source.
- **AI Copilot backend performance** — explicitly out of scope (`backend/app/services/ai/**` skipped); only the frontend cache invalidation defect (FND-10-06) is reported from that surface.
- **Real-network latency / gzip transfer sizes** — measurements bypass HTTP; gzip figures quoted from the baseline `npm run build` output in the worklog.
- **`_outcome_mix`'s Python-side counting at very large orgs** (>5k personnel) — outside the stated product scale (single org, hundreds of personnel); at 200 people it fetches 201 rows.

## Proposals

Ranked by (value to a real HR user)/(implementation surface).

**P1 — Anchor-and-suffix verification for the audit hash chain** *(user outcome: the audit-log page's integrity badge stays instant for the life of the system instead of degrading past 1.3 s at year 5 and ~5 s later | change: new small table `audit_chain_anchor(id, verified_to_id, head_entry_hash, checked_at)` maintained by the existing nightly sweep; `verify_chain` verifies only rows `> verified_to_id` (plus the anchor link) and returns `full: false` + `verified_up_to`; full recompute stays behind an explicit deep-check action | files: `backend/app/services/audit.py`, `backend/app/services/scheduled.py`, `backend/app/api/routers/audit_log.py`, one alembic migration, `frontend/src/components/AuditIntegrityBadge.tsx` (tooltip text) | surface: `GET /api/audit-log/integrity` | risks: anchor must only advance after a successful full verify — a broken chain must freeze it; keep the response schema backward-compatible by adding fields | compat: additive | priority: high).*

**P2 — Single-pass indicator stats on the dashboard overview** *(user outcome: HR dashboard loads ~4× faster as history accumulates (346 ms → ~90 ms at 5-year scale; ~1.4 s → ~0.35 s at 10-year) | change: replace the 4 `_indicator_stats` queries with one `GROUP BY indicators.id, category, description, section` query (avg + cohort size, all 20 rows returned), choose weakest/strongest-5 per section in Python; identical numbers out | files: `backend/app/api/routers/dashboard.py:261–298` | surface: `GET /api/dashboard/overview` | risks: none behavioral — same aggregates, same suppression; add a parity test asserting the previous 4-query output | compat: response schema unchanged | priority: high).*

**P3 — Paginate `/api/improvement-plans/eligible`** *(user outcome: the improvement-plans page loads flat (page-sized payload + ≤ page-size rows in the DOM) instead of 625 KB / 3,354 rows at 5 years and growing | change: add `limit/offset` (+ optional `q` subject-name filter) to the endpoint; give the "نیازمند برنامه بهبود" card `PaginationControls` like the plans table below it; optionally default the view to the latest period | files: `backend/app/api/routers/improvement_plans.py:108–152`, `frontend/src/api/queries.ts:400`, `frontend/src/pages/hr/ImprovementPlansPage.tsx:183–213` | surface: GET + page | risks: the count in the card title needs the total from a count query; picker UX must stay one-click for the common fresh case (latest period) | compat: additive query params | priority: medium-high).*

**P4 — Deduplicate the repeated aggregate scans in my-scoring / report summary** *(user outcome: supervisor "mirror" and HR report pages stay flat as years accumulate (my-scoring 138 ms → ~50 ms at 5-year scale) | change: materialize the shared "other scores" / "base" subquery once (SQLAlchemy `cte()` or a single grouped statement) and derive count/avg/cohort/distribution from one pass | files: `backend/app/api/routers/analytics.py:108–241`, `backend/app/api/routers/reports.py:124–179` | surface: `GET /api/analytics/my-scoring`, `GET /api/dashboard/report/summary` | risks: cohort-suppression parity (P1-08) must be asserted by existing tests | compat: response schemas unchanged | priority: medium).*

**P5 — Cap (or stream) the evaluations Excel export** *(user outcome: export stays a bounded, predictable request even at 10-year history (~2.3 s today's shape → capped ~1 s) | change: mirror the audit-log export's 5,000-row cap (log truncation in the `excel_exported` audit event it already writes), or switch to openpyxl `write_only` streaming | files: `backend/app/api/routers/evaluations.py:699–746`, `backend/app/services/excel.py` | surface: `GET /api/evaluations/export.xlsx` | risks: truncated exports must be visible to HR (notice in log + response header) | compat: file format unchanged | priority: low).*

**P6 — Scope the copilot confirm invalidation** *(user outcome: confirming an AI-suggested action no longer refetches every query in the app (notifications/evaluations/dashboard/personnel…) | change: replace the bare `queryClient.invalidateQueries()` with the specific families the confirmed action can affect | files: `frontend/src/components/copilot/CopilotPanel.tsx:196` | surface: copilot confirm | risks: none — matches the pattern every other mutation uses | compat: trivial | priority: low).*

# ROLE 11 — Test Quality

Review of NexaHR at commit `fc4f3fe9e5ea6fa412a16b0bbc287fb24dfe18a9` (branch `review/ten-role-full-system`), Test Quality angle: I audited the tests themselves — backend `backend/tests` (109 files, 1131 tests), frontend vitest (47 files, 285 tests), launcher `tools/tests` (89 tests), e2e (`e2e/e2e_api_test.py` + `e2e_browser.py`). All verification ran on a disposable DB `nexahr_r11` on the local PostgreSQL 16.4 (ICU) instance; no repo files were committed, all temporary mutations were restored (verified by empty `git status --porcelain` / `git diff` at the end), and the temporary probe test file was deleted. Seven controlled mutations were executed (R11-1 … R11-7); each is recorded below with outcome and restoration.

## Verdict

The suite is genuinely strong by industry standards: a real-PostgreSQL savepoint/rollback harness, real audit-chain tamper tests (trigger disabled to simulate a DB-level attacker), real two-connection row-lock races, a behavioral delivery-channel double covering retry/backoff/abandon, byte-stable legal-PDF archival tests, and a full-Excel-injection round-trip. Baseline reproduced exactly on my own DB: **1131 passed / 0 failed / 0 skipped** backend, **285/285** frontend, **89/89** launcher.

However, the audit found **two HIGH test gaps on exactly the axis where two real HIGH production defects already slipped through CI** (cross-ref FND-01-01/FND-05-01 from Roles 01/05): the `employee_evaluation_visibility` module gate and the response content of the **employee/subject branches of `GET /api/evaluations` and `GET /api/evaluations/{id}/summary.pdf`** have no module-OFF test and no field-level assertions. I proved both gaps by *implementing the missing gate* as controlled mutations and showing the suite stays green (R11-1: 117 tests across 11 suites; R11-2: 85 tests across 6 suites). Two more MEDIUM gaps: the unhandled-error middleware in `main.py` (safe Persian 500 + X-Request-ID) has zero tests (R11-4: a leak-internals mutation survives), and `test_the_background_helper_swallows_a_render_failure` is **vacuous** — it monkeypatches a failing render but passes a nonexistent record id, so the render is never called (R11-6: removing the error swallow entirely keeps 34 tests green). Four LOW findings: missing midpoint rounding parity in `computePreview` (why FND-03-02 passed CI), 31 success-path status-code-only tests, one tautological SQL test, and minor shared-DB residue from real-commit tests.

The three historical leads all checked out as already fixed/deliberate: the UTC-timestamps-in-legal-PDF test bug was fixed and is regression-guarded (`test_pdf_security.py:126` documents the old wrong expectation); `af_race_*` is a deliberate, documented real-commit concurrency test that cleans up everything except a uuid-suffixed user (by design); `pytestmark = usefixtures("employee_view_on")` is deliberate and documented — the remaining masking is precisely findings FND-11-01/02 (endpoints whose module-OFF behavior *no* test covers).

## Findings

### Top findings

**FND-11-01 | HIGH | REPRODUCED | backend/tests/test_employee_self_view.py:89-118 (and backend/tests/test_module_switches.py:130-157)**
The only test of the employee branch of `GET /api/evaluations` (`test_employee_list_evaluations_no_leak`) asserts **record ids only** (`my_final in ids`, `other_final not in ids`, orphan `total == 0`) and always runs with `employee_view_on` (module ON). Nothing asserts (a) the module-OFF behavior of this branch, or (b) the response *schema* — items are full `EvaluationRead` (evaluator_comment, chain user ids, extension reason, was_returned…) instead of the trimmed `MyEvaluationRead` that `/api/me/evaluations` serves and whose field-trim *is* asserted (test_employee_self_view.py:86). `test_module_switches::test_visibility_off_hides_the_result_from_its_subject` covers module-OFF only on `/api/me/evaluations`, never on `/api/evaluations`. This is the test gap through which FND-01-01 (Role 01, HIGH — employee-results module bypass on this very endpoint) and its field-delta leak (Role 05 cross-ref) passed a fully green CI.
- Mutation R11-1: added the missing gate in `app/api/routers/evaluations.py::list_evaluations` (employee + `not is_module_enabled(db, "employee_evaluation_visibility")` → empty page). Expected detection: any test covering module-OFF or field semantics for this branch. Actual: **SURVIVED** — 117 tests green across 11 suites (`test_module_switches`, `test_employee_self_view`, `test_rbac`, `test_session_visibility`, `test_role_overview`, `test_subject_of_any_role`, `test_employee_voice`, `test_end_to_end_chain`, `test_special_score`, `test_cohort_suppression`, `test_notifications`). Restored; `git diff` empty; baseline re-verified.
- Fix: add a test that, with the module OFF, asserts `total == 0`/empty items on `GET /api/evaluations` for an employee (mirroring the `/api/me` test), plus a field-level assertion that employee-branch items exclude internal fields (same style as line 86). When the production gate is fixed (Role 01's remit), the same test locks it in both directions.

**FND-11-02 | HIGH | REPRODUCED | backend/tests/test_employee_self_view.py:281-291 and backend/tests/test_subject_of_any_role.py:84-97**
The subject branch of `GET /api/evaluations/{id}/summary.pdf` (evaluations.py:1577-1588) is covered only by (a) a bare `assert … status_code == 200` with a comment declaring it "deliberately open (P0-06)" and (b) `test_a_subject_of_any_role_can_download_its_own_document`, which asserts `content[:4] == b"%PDF"` — again under `employee_view_on` (module ON). **No test asserts module-OFF behavior for the subject branch, and no test asserts document content semantics** (that the subject gets the trimmed result view rather than the full legal document with per-indicator scores, evidence_text, evaluator_comment and stage comments). This is the gap through which FND-05-01 (Role 05, HIGH — full legal document served to the subject with `employee_evaluation_visibility` OFF, the default) passed CI; the 200-only assertion actively locks in the defect as "intended".
- Mutation R11-2: added `if is_subject and not is_module_enabled(db, "employee_evaluation_visibility"): raise 403` to the subject branch. Expected detection: any module-OFF or content-semantics test on this endpoint. Actual: **SURVIVED** — 85 tests green across 6 suites (`test_documents`, `test_pdf_security`, `test_subject_of_any_role`, `test_employee_self_view`, `test_employee_voice`, `test_module_switches`). Restored; `git diff` empty.
- Fix: with module OFF, assert the subject gets either 403 or a trimmed document (per whatever the privacy policy decision is — cross-ref FND-05-01/P1); with module ON, assert the served PDF does not contain chain-internal content (e.g. extract text and assert the evidence table is absent), so the "subject branch" semantics are pinned rather than merely its 200.

**FND-11-03 | MEDIUM | REPRODUCED | backend/app/main.py:100-132 vs backend/tests/ (no reference anywhere)**
The unhandled-error middleware — the system's production guarantee that a crash yields a safe Persian 500, an `X-Request-ID` header echoed in the detail, no internal detail leak, and a 500-counted metric — has **no test at all** (rg over `tests/` finds no reference to `request_context`, `X-Request-ID` or the unhandled-error path; the only 500-asserting test, `test_pdf_security.py:65-72`, tests a deliberately raised `HTTPException(500)`, which FastAPI handles before the middleware's catch).
- Mutation R11-4: replaced the safe 500 body with `{"detail": f"MUTATION R11-4 leaked: {exc!r}"}` (internal exception repr leaked to the client). Expected detection: any test of the safe-500 contract. Actual: **SURVIVED** — 25 tests green (`test_observability`, `test_audit_pass`, `test_rate_limit`). A temporary probe test (written outside the suite, then deleted) asserting 500 + header + id-in-detail + no-internal-leak **killed** the mutation (1 failed), proving the behavior is real and testable — I also confirmed the *unmutated* middleware passes the probe (verified-correct behavior, untested by the suite).
- Fix: add a permanent middleware test: `TestClient(app, raise_server_exceptions=False)`, override a dependency to raise `RuntimeError("secret")`, assert 500, `X-Request-ID` header, request-id inside the Persian detail, and that "secret" does not appear.

**FND-11-04 | MEDIUM | REPRODUCED | backend/tests/test_load_shape.py:189-199**
`test_the_background_helper_swallows_a_render_failure` is **vacuous for its stated purpose**: it monkeypatches `documents.render_evaluation_summary_pdf` to raise `RuntimeError("boom")` and then calls `archive_final_pdf_detached(10**9)` — a record id that does not exist, so the function returns at the `record is None` early-exit **before ever invoking render**. The monkeypatch is dead code; the test silently re-tests the missing-record path already covered by the test above it. The actually-claimed behavior — background archival swallows a render failure, rolls back, and leaves the finalized record untouched (documents.py:111-113) — is untested, as is the sibling in-request `except RuntimeError → return None` branch of `archive_final_pdf` (documents.py:54-64: finalize still succeeds; `pdf_renders` outcome="failed"). No other test monkeypatches a failing render with WeasyPrint available.
- Mutation R11-6: deleted the `except Exception: rollback + warning` from `archive_final_pdf_detached` (errors now propagate out of the background helper). Expected detection: the render-failure swallow test. Actual: **SURVIVED** — 34 tests green across 4 suites (`test_load_shape`, `test_documents`, `test_ceo_only_chain`, `test_direct_ceo_hr_finalization`), including the vacuous test itself. Restored; `git diff` empty; `test_load_shape` re-verified green.
- Fix: build a committed finalized record via a dedicated engine (the `test_score_write_lock` `committed_draft` pattern), monkeypatch the render to raise, call `archive_final_pdf_detached(record_id)` and assert: no exception, no `EvaluationDocument` row, record still finalized. Same for the in-request branch (finalize response 200, no document, sweep later retries).

### Additional verified findings

**FND-11-05 | LOW | REPRODUCED | frontend/src/components/ScoreForm.test.tsx:251-319**
All `computePreview` tests use exact values (60/20/44/56/100) that avoid the rounding midpoints; there is no parity test against the backend's half-even `round()`. This is why FND-03-02 (Role 03 — `Math.round` half-up vs backend `round()` half-even → 0.1 preview/store divergence on exact .25 midpoints) passed CI with a green vitest run.
- Mutation R11-3: replaced `round1 = (v) => Math.round(v*10)/10` with a banker's-rounding implementation (the backend-parity fix — changes behavior **only** on exact midpoints). Expected detection: any midpoint case or parity test. Actual: **SURVIVED** — 34 frontend tests green (`ScoreForm.test.tsx` 20, `ScoreFormMobile.test.tsx` 8, `MyScoringPage.test.tsx` 6). Restored; `git diff` empty.
- Fix: add midpoint cases to the `computePreview` describe block (e.g. weights producing 44.25 → expect 44.2), or extract a shared rounding util with explicit half-even tests mirroring `services/evaluation.py`.

**FND-11-06 | LOW | REPRODUCED | backend/tests/test_rbac.py:64-74 (representative; 31 tests total, list in evidence)**
An AST scan of all 1131 backend tests found 136 status-code-only tests; the benign majority are negative guards (401/403/404/422) where the status **is** the access decision. The risky subset is **31 tests asserting a success status (200/201) with no content assertion at all** — e.g. `test_only_hr_sees_full_user_list` (asserts 200, never checks the list is full/scoped), `test_personnel_detail_requires_relevant_access` (200, no payload check), `test_the_admin_can_set_an_evaluation_chain`, `test_an_open_case_keeps_the_rules_it_was_opened_under`.
- Mutation R11-7: made `GET /api/users` return an empty `UserPage` for every caller. Actual: `test_rbac.py` stayed green (its two users-list assertions are 403/200 only) — **SURVIVED for the named weak tests**; the mutation was KILLED by compensating content tests elsewhere (`test_audit_pass::test_users_is_active_filter_and_export`, `test_user_display_name::test_search_finds_a_user_by_name_not_only_username`). This is the honest picture: per-route compensation usually exists, but the rbac file's promises ("sees full list") are not kept by its own assertions. Restored; `git diff` empty.
- Fix: in the success-path branches of these 31 tests, add one content assertion each (total/items count, a returned field, a scope check). The full list was captured by scanning `assert` expressions per test (no `json`/`content`/`scalar`/`len(`/`headers`/`text` references).

**FND-11-07 | LOW | REPRODUCED | backend/tests/test_workflow_concurrency.py:36-45**
`test_row_lock_clause_is_present_in_generated_sql` builds **its own** `select(...).with_for_update(of=EvaluationRecord)` statement and asserts `"FOR UPDATE" in compiled_sql` — it tests SQLAlchemy's compiler, not application code. It cannot fail for any regression in `_get_record_or_404_for_update` (the production helper it claims to guard); the file's other test calls the helper but only checks `record.id`.
- Mutation R11-5: removed `.with_for_update(of=EvaluationRecord)` from the production helper `_get_record_or_404_for_update` (used by all 15 transition/mutation endpoints plus `upsert_scores`). Actual: **KILLED** by `test_score_write_lock` (2 real-race failures: `test_score_write_racing_a_submit_sees_the_new_status_and_is_rejected`, `test_comment_write_uses_the_row_lock`) — proving the lock IS behaviorally guarded — while `test_workflow_concurrency`'s both tests **still passed** under the mutation, proving the tautology. Restored; re-run green.
- Fix: delete the tautological test (its guarantee is already delivered by `test_score_write_lock`), or compile the *helper's* statement instead of a hand-built one.

**FND-11-08 | LOW | REPRODUCED | backend/tests/test_login_guard_concurrency.py:60-80 and backend/tests/test_scheduler_reliability.py:135-164**
Tests that intentionally escape the savepoint harness with their own engines leave real residue in the shared DB (verified by direct psql inspection of a fresh DB after a full 1131-test run): `login_attempts` rows `race-existing`/`race-missing` (never cleaned; only `race-threshold` is `_fresh`'d at the end) and one `skipped_locked` `scheduler_runs` row per run from `test_a_second_instance_skips_instead_of_duplicating_work` (committed on the follower's real session). The residue is currently inert (full suite green with it present; `last_successful_sweep` filters skipped runs — that's the point of `test_observability.py:165`), but the empty-history precondition of that test (`assert last_successful_sweep(db_session) is None`) is preserved only by convention: every real-commit test must clean up its *succeeded* rows, which `test_audit_fixes` M-10 does explicitly with a janitor while these two files do not. `test_score_write_lock` and `test_audit_fixes`' af_race clean up completely otherwise (0 personnel/document/audit residue after a full run; the uuid-suffixed `af_race_*` user is deliberately retained, documented in `_cleanup_confirm_fixture`).
- Evidence: psql after full run: `login_attempts=2`, `scheduler_runs=2 skipped_locked`, `module_settings=0`, `audit_log=0`, `evaluation_documents=0`, `personnel=0`, `users=2` (both documented af_race users).
- Fix: `_fresh()` both usernames in a teardown (or finalizer); janitor the skipped_locked row like M-10 does; optionally make the observability precondition explicit by deleting history rows at test start.

## Verified correct

Baseline reproduced on the disposable DB: backend `1131 passed / 0 failed / 0 skipped` (367s), frontend `285/285 in 47 files` (49.5s), launcher `89/89` — matching the CI-equivalent baseline. `git status --porcelain` and `git diff` empty at the end of every mutation window.

**Test isolation and state hygiene (conftest.py) — verified correct, including empirically:**
- `db_session` uses connection + outer transaction + `join_transaction_mode="create_savepoint"`; per-test `db_session.commit()` (used in ~60 test files) only releases the savepoint. Empirical proof: after running the suites that use `employee_view_on` (which commits module settings) and a full 1131 run, `module_settings`, `audit_log`, `evaluation_documents`, `personnel` are all **0 rows** in the shared DB. The historical worry "employee_view_on commits module settings that persist" is unfounded — the fixture commits inside the savepoint.
- `client` overrides only `get_db` (dependency_overrides cleared per test) — no broad masking of the code under test; all guards still execute.
- `_reset_rate_limiter` autouse fixture prevents login-rate-limit order dependence (documented reason).
- `no_cohort_suppression` is deliberately NOT autouse — the suppression guard itself stays under test (test_cohort_suppression.py).
- Tests that need real commits (concurrency) use dedicated engines and clean up (test_score_write_lock: verified 0 residue; test_audit_fixes af_race: everything but the documented uuid user).

**Historical leads — resolved:**
- *UTC timestamps in the legal PDF:* fixed and regression-guarded. `test_pdf_security.py:126-144` explicitly documents that the old test locked in UTC wall-clock ("۰۹:۳۰" for `09:30+00:00`) and now asserts the Tehran-local rendering (`1405/04/01 13:00`); `test_org_timezone.py` covers midnight edges, naive-datetime-as-UTC, local-day filter boundaries, invalid-tz loud failure, and window-is-open semantics with a frozen `now_local`. ISO-string snapshots shift too (line 50).
- *`af_race_*` state in test_audit_fixes.py:* deliberate real-commit race test (atomic claiming of AI confirmations); `log_event` neutralized to keep the append-only audit log empty; marker personnel + AI config cleaned in `finally`; the uuid-suffixed HR user is deliberately retained (audit chain would reference it) — documented in `_cleanup_confirm_fixture`.
- *`pytestmark = usefixtures("employee_view_on")`:* used by exactly 2 files (test_role_overview, test_employee_voice; test_subject_of_any_role and test_employee_self_view use it via the same fixture mechanism). The design is sound: tests of visible behavior opt IN, and module-OFF behavior is tested by test_module_switches with explicit set_module calls — for /api/me and the cards. The endpoints where the fixture masks nothing because nothing covers them at all are findings FND-11-01/02, not the fixture.

**Skips / xfails inventory:** 0 skipped, 0 xfailed in the reproduced full run. All 8 skip markers are environmental guards, none triggered in CI: WeasyPrint availability (test_pdf_security.py:55, test_load_shape.py:120/160, test_subject_of_any_role.py:95 runtime skip after the access-guard is verified), frontend types presence (test_audit_event_labels.py:70/81 — frontend is in the checkout and CI), nginx template presence (test_deployment_config.py:25 — present). No permanent skips, no xfails anywhere (backend, frontend, tools).

**Wall-clock / timezone dependence:** all `datetime.now(UTC)` usages in tests are relative arithmetic (`now - timedelta` for lockout/SLA windows) or frozen clocks via monkeypatch; no loose wall-clock equality assertions. `test_scheduler_reliability.py:82` asserts "recently updated" with a 1-minute bound — sound.

**Suite-by-suite inventory (what the tests actually verify):**

| Suite | Tests | What they actually verify |
|---|---|---|
| tests/test_rbac.py | 5 | Access decisions only (401/403/200/201). Weakest file in the suite — see FND-11-06 |
| tests/test_workflow.py | 6 | Full 4-stage chain with content asserts: status, stage, final_weighted_pct, scores count (20), comments, PDF content-type; manager path incl. seat assignment and evaluator_comment |
| tests/test_return_flow.py | 9 | Return semantics with content: stage/status after each return type, scores preserved, return-comment author, audit count, was_returned flag on list+detail+transitions, notification recipients per stage, state/role 403s |
| tests/test_cancel_and_reassign.py | 21 | Cancel/reassign with reason-as-comment + audit, replacement-after-cancel, terminal-state refusals, reassignment role/inactivity/self-evaluation/notify checks, departed-owner sweeps |
| tests/test_module_switches.py | 11 | **All 9 module keys behaviorally** (write gates, read gate for /api/me, cards, analytics, periods-close-exception, outbound enqueue-off) + source-scan tripwire that every key is read somewhere in app/ |
| tests/test_employee_self_view.py | 8 | /api/me list: own-finalized-only, field-trim asserted; acknowledge happy path w/ audit + HR notification + double-ack 400; foreign 404 / open 400; employee role hardening; finalize notification link; no-notification-when-module-off |
| tests/test_employee_voice.py | 31 | Objection/acknowledge/self-assessment lifecycle incl. module interplay, foreign-record refusals, resolution paths |
| tests/test_subject_of_any_role.py | 20 (5 roles × 4) | Subject-of-any-role semantics: /me list, own-PDF not-403 (content: %PDF magic), ack+object, finalized notification, outsider stays closed |
| tests/test_documents.py | 6 | Archived PDF: sha256 64-hex, %PDF magic, download-racing-archival (unique-insert, 1 document), byte-stability across downloads, public verify payload (document_ready/sha256 transitions), sequential-code and unfinalized 404s |
| tests/test_pdf_security.py | 8 | PDF export 403 for chain roles with Persian detail; WeasyPrint-unavailable → clear 500; HTML escaping of evidence; url_fetcher local-templates-only; jalali filter local-day (incl. the corrected UTC regression); legacy signature block |
| tests/test_document_signatures.py | 11 | Signature block for all 5 chain shapes, empty seats, HR-manager-path, shielded, single_decider flags, final approver; rendered HTML matches function output for all shapes; ≤4-snapshot legacy block |
| tests/test_org_timezone.py | 9 | to_local/naive-UTC, document local-day, ISO-snapshot shift, invalid-tz RuntimeError, window open/closed via frozen now_local, local-midnight filter boundaries, UTC-org symmetry |
| tests/test_audit_chain.py | 16 | Real tamper simulation (trigger disabled, UPDATE/DELETE executed, re-enabled) → broken_at_id + reason; DB refuses UPDATE/DELETE/TRUNCATE; HR integrity check 403-gated; limited-window verification starts at own boundary; logging keeps chain intact |
| tests/test_audit_log.py | 6 | View capability gate; event logging + filters (actor/personnel/org_unit/contract date) + pagination |
| tests/test_notification_delivery.py | 20 | Behavioral channel double: default-off no-op, actionable-only queuing, opt-out/no-address/inactive, per-channel rows, send+success rows, no double-send, permanent→abandoned, transient→retry, backoff, eventual abandon at max attempts, unexpected error doesn't stop sweep, recipient frozen at enqueue, unconfigured SMTP/SMS report as such, SMS template quoting (url/json) |
| tests/test_scheduler_reliability.py | 11 | Leader lock on two real connections (skip, not duplicate), manual endpoint 409 while locked, failing sweep recorded with error text, lock released, run history, SLA reminders with notification content, vacated-seats sweep |
| tests/test_score_write_lock.py | 5 | Real two-connection races: lock blocks a second FOR UPDATE (lock_timeout 100ms), score-write racing a submit sees updated status → 403, comment write locked; fixture commits real rows and cleans them fully (verified) |
| tests/test_login_guard_concurrency.py | 3 | Real barrier races on two sessions: no lost failure (1+2=3), no UniqueViolation on concurrent inserts, threshold not stretched |
| tests/test_load_shape.py | 10 (2 skipif, untriggered) | Backfill sweep idempotence (byte-stable), PDF layout shape (skipif WeasyPrint), background helper missing-record (and the vacuous render-failure test — FND-11-04) |
| tests/test_excel_formula_injection.py | 8 | `_neutralise` prefixes/numbers/bools; real workbook cell data_type != "f"; secondary report sheets guarded; numbers stay numeric; full HTTP chain import→export neutralises the payload; real formula cell rejected in preview |
| tests/test_model_schema_parity.py | 3 | autogenerate diff empty; the 2 critical partial-unique indexes exist (asked of Postgres itself, incl. UNIQUE+WHERE+status predicates). Known blind axis: CHECK constraints (cross-ref FND-03-03 / role-06 — not re-reported here) |
| tests/test_observability.py | 13 | /metrics token gating + prometheus format, path templates not values, unmatched-path cardinality collapse, failed-login/workflow-transition counters, named failure modes in registry, readiness migration-head match/mismatch, last-sweep semantics (skipped ignored, stale reported not fatal) |
| test_ai_* (25 files) | ~360 | OUT OF SCOPE per instructions; noted only: parity suites route copilot actions through the same non-AI guards (strengthening, not masking), and fake_llm's ScriptedAdapter is a scripted port double, not an LLM oracle |
| frontend (47 files) | 285 | No snapshot tests (rg `toMatchSnapshot` = 0). Components assert rendered output + request payloads (apiClient mocked at transport) with 92 userEvent/fireEvent interactions; AuthContext tests verify React-Query cache clearing on login/logout; client.test.ts covers error-message extraction incl. 409 conflict-id |
| tools/tests (5 files) | 89 | Launcher decision logic on simulated Windows output: netstat LISTENING-vs-ESTABLISHED parsing, address-vs-port disambiguation, netsh exclusion ranges (incl. asterisk), never-kill-a-stranger, venv/own-process ownership, free-port search stop, env-file ascii/never-overwrite, version parsing, admin form validation parity with backend password policy, maintenance triage (missing package vs native lib), JSON-extraction robustness |
| e2e/e2e_api_test.py | 12 steps | **In CI** (e2e-api job): login → AI status/tools → upload (real invalid_count=1) → inspect → patch pending+confirm (409-aware) → import pending+confirm → real data assertions (personnel found by unique code, jalali→ISO conversion `2027-08-23`, account created) → audit trail asserted by **tool names** in ai_tool_invoked/ai_action_confirmed (not fixed counts) → double-confirm 409. mock_llm.py is scenario-driven **from real tool results** (STATE keyed on inspect/patch/propose payloads), so the flow continues based on what the backend actually returned; the LLM-decision layer itself is mock by design (AI out of scope) |
| e2e/e2e_browser.py | ~12 steps | Real-browser scenario (login → copilot → upload → patch → confirm → personnel page + audit) with selectors and text waits; **not in CI** (documented: Chromium + runtime cost) — see coverage gaps |

## Could not check, and why

- **Full-suite runs under each surviving mutation** (R11-1, R11-2, R11-3, R11-6): I ran targeted selections covering every test that references the touched routes/files (by rg) — 11 suites/117 tests for R11-1, 6 suites/85 tests for R11-2, 3 files/34 tests for R11-3, 4 suites/34 tests for R11-6 — but did not re-run all 1131 backend / 285 frontend tests under each mutation. Survival beyond the targeted selection is therefore labeled UNVERIFIED (the selections did include every file whose tests touch those endpoints' semantics). Mutations R11-4, R11-5, R11-7 were killed outright, which bounds the risk.
- **Per-route compensation map for the 31 success-status-only tests** (FND-11-06): I verified compensation exists for `/api/users` (mutation R11-7) and sampled content-asserting counterparts elsewhere; a complete per-route compensation audit was not built.
- **Remote CI status for this commit**: not verifiable (GitHub API rate-limited — carried over from baseline; local CI-equivalent runs all pass).
- **e2e_browser.py execution**: not run here (requires Chromium + live backend/frontend/mock-LLM trio; documented as manual). Its selector robustness (e.g. multi-fallback `input[name='username'], #username`) could not be validated against the real DOM.
- **Real Windows netstat/netsh output compatibility** for launcher tests: no Windows runner available; the tests validate parsing/decision logic against captured-format fixtures only (documented design).
- **AI-copilot test quality** (test_ai_* files, fake_llm adapters, mock_llm scenarios beyond their interaction with non-AI guards): out of scope per role instructions.
- **CHECK-constraint parity**: the production drift is already REPRODUCED by Roles 03/06 (FND-03-03, role-06 table); I did not re-run their insert-based verification — cross-referenced, not duplicated.

## Cross-Role Findings

All defects whose combined significance emerges across roles. Full entries live under their owning roles; only the combined impact is stated here.

**CRF-1 — The `employee_evaluation_visibility` bypass family (Roles 01 + 05 + 11).** FND-01-01 (list endpoint, HIGH) and FND-05-01 (subject PDF, HIGH) are two *independent* code paths that both skip the module gate — fixing one does not close the other. FND-05-02 (LOW) is the cheapest id-discovery route for the PDF bypass (403-message oracle), and the sequential id scan works because the evaluations router has no rate limiter. FND-11-01/FND-11-02 (HIGH) are the reason the whole family passed a green CI: the employee branches of exactly these two endpoints have no module-OFF tests and no content assertions — a mutation *adding* the missing gate survived 117 and 85 tests respectively. Combined impact beyond the individual entries: in the default configuration the system's stated privacy promise ("the module gates server reads") is unenforceable end-to-end, and the organization cannot detect the regression with its own test suite. The correct fix is one shared "subject may read own result" helper consumed by all four subject read/write paths (list, PDF, acknowledge, objection) plus two module-OFF regression tests — anything less leaves the family one refactor away from reopening.

**CRF-2 — Chain-shape blindness in the product UI (Roles 02 + 09).** The backend state machine partitions all chain shapes (full, no-deputy, manager path, CEO-direct, and the HR-subject dimension) correctly — exhaustive matrix testing found zero backend transition defects. The frontend action-gating, however, knows only the full chain: FND-02-01 (no-deputy at `hr_approved`: no finalize button, missing from the CEO pending tab, mislabeled «بررسی معاونت» for a chain with no deputy), FND-09-02 (CEO-direct at `submitted`: the server's designated "main correction window" (`ceo_return_ceo_only` from `submitted`) has no UI), FND-09-03 (shielded HR-subject cases: the server grants the entire rescue toolbox to deputy/CEO, the UI renders it for HR only — the one actor the server 403s), FND-09-01 (manager-path approve dialog announces a deputy review that has already happened), and FND-02-02 (return/comments route by *role* instead of *seat*, stranding a CEO-role user legitimately seated as deputy). Combined impact: three server-legal workflow actions are unreachable in the product UI and two more mislead the actor about what they just did — while the backend, the audit log and the legal document all record a correct, different reality. One shared frontend chain-shape module (mirroring `workflow.py`'s own predicates) closes all five.

**CRF-3 — Preview/rounding parity (Roles 03 + 11).** FND-03-02 (LOW): the frontend preview uses `Math.round` (half-up) while the server uses Python `round()` (half-even); on exact `.25` midpoints the evaluator decides on a number 0.1 away from the one finalized. FND-11-05 (LOW) explains why CI missed it: every `computePreview` test value avoids the midpoints, so a banker's-rounding mutation survived 34 frontend tests. With custom threshold bands the preview can even show a different recommendation band than the one that gets finalized. Combined: the preview contract ("same formula as the server") is untested at exactly the boundary where the two implementations differ.

**CRF-4 — Backend-authored message localization reaches the legal document (Role 08, with Role 03's snapshot path).** FND-08-01 (MEDIUM): Gregorian ISO dates are printed inside Persian sentences on three surfaces, and the worst one — the submission-extension comment — is collected by `snapshot.py` and rendered **verbatim inside the hashed legal PDF's** comment table, next to dates the same template renders in Jalali with Persian digits. FND-08-03 (LOW): Latin digits in notification/SMS/error texts contradict the system's own Persian-digit convention (~40 frontend call sites do it correctly). Combined: the document-level localization standard the repo itself established (`pdf.fa_digits`) is violated by text authored one layer above the template — the fix is one shared Jalali/Persian-digit helper used at message-construction time.

**CRF-5 — Schema-truth drift invisible to the parity guard (Roles 03 + 06 + 11).** FND-03-03 (LOW): both chain models declare `supervisor ≠ CEO` CHECK constraints the database deliberately does not have (the shape is legal and disclosed via `single_decider`). Role 06's systematic catalog comparison extended this: of 10 model-declared CHECKs, 2 are absent and 4 exist as deliberate `NOT VALID` — while `alembic check` and `test_model_schema_parity` are structurally blind to CHECK constraints (autogenerate does not compare them). Combined: any future tooling that builds or validates the schema from model metadata (a `create_all` harness, a hand-written "fix the drift" migration) would silently outlaw a chain shape that real data may already use, turning existing rows into constraint violations on their next UPDATE — and the existing guards cannot warn about it.

## Regressions

**No verified regressions.**

Every item on the historical-fixes list was independently re-verified at the reviewed commit before this conclusion was reached:

- **Module switches gate writes** — verified behaviorally for all 9 module keys (Role 11 suite inventory); the `employee_evaluation_visibility` violations (FND-01-01/FND-05-01) are on paths that were *never* guarded (new findings, not returns); the write-side gates and `/api/me`/notifications/dashboard read gates all hold.
- **`add_comment` respects HR handling/visibility; objection and administrative path guards** — re-verified (Role 02 items 7–8; Role 05 items 2, 10).
- **Session-aware capability revocation; evaluation-subject identity independent of `employee` role** — re-verified live (token_version bump kills access+refresh; `require_own_personnel` serves any linked role; Role 01 items 3–4).
- **Bonus bounded by scheme cap and remaining room; applied (not raw) bonus in the official document** — re-verified at the boundaries (Role 03).
- **Signatories from real seats; no duplicate/empty CEO-direct signatures** — re-verified across all five shapes (Role 03). FND-03-01 (supervisor==CEO prints the same person twice) is a *new* legal-shape edge the historical fix (which addressed fake/missing-seat signatures) never claimed to cover — not a return.
- **PDF Latin glyph handling** — re-verified (Vazirmatn + Vazirmatn-Latin embedded, no system-font fallback; Role 03/08).
- **UTC/local boundaries centralized in `core/clock.py`** — re-verified (all 40+ timestamp columns aware; every date filter on local-day boundaries; Role 08). FND-08-02 is a *frontend* preset helper the historical fix never covered.
- **Complete CEO-direct path; HR-unit self-case deadlock; separation/open-case seat ownership; role change/deactivation protections** — re-verified (Role 02 items 5, 8, 9; the T3 deadlock fix holds server-side; FND-09-03 is a UI-only gap in the *new* rescue path, not a return of the deadlock).
- **Distinct-person suppression; concurrent login-failure counting; bounded stage-statistics window; Excel transaction/eager loading; Persian sorting normalization and ICU collation** — all re-verified (Role 05 item 1; Role 07 items 5–6; Role 10 measurement table; Role 06; `fa-x-icu` present and exercised).
- **Historical test-quality leads** — resolved, not regressed: the UTC-timestamps-in-legal-PDF test bug is fixed and regression-guarded (`test_pdf_security.py:126-144` asserts Tehran-local rendering); `af_race_*` is a deliberate, documented real-commit race test with explicit cleanup; `pytestmark = usefixtures("employee_view_on")` is a sound opt-in design — the residual masking is precisely FND-11-01/02, reported as new findings.
- **NafasHR-reported bugs** (checked at the reviewed commit during compilation): #7 (general/specialized indicator separation in the self-assessment form — `OpenCaseCard.tsx:233` now groups by section) and #9 (user search by personnel full name — `users.py:75-77` now includes `personnel_full_name.ilike`) are **fixed**; #6's backend gap (self-assessment completeness) is **fixed** — `me.py:261-270` now rejects incomplete submissions with an actionable Persian message, closing the historical stale-cache lock-in scenario. The browser-side staleness that motivated the guard remains (no refetch trigger on the indicators query), but the server now refuses the incomplete one-shot submission, which is the historical fix's own chosen strategy.

---

## Combined Proposals

Only roles 01, 05, 08, 09 and 10 contribute (per the review contract). Pooled, deduplicated, and ranked by **(value to a real HR user) / (implementation surface)** — effort, risk and files touched included in that judgment. Findings-level defects are excluded here; each proposal states the outcome first. No count cap; no filler.

**CP-1 — One shared "subject may read own result" gate** *(from Roles 05 + 01; closes FND-05-01 and the FND-01-01 family drift risk)*
Outcome: with «نتیجه و وضعیت پروندهٔ کارمند» off, an employee calling the list endpoint, the PDF endpoint, acknowledge, or objection gets the same consistent answer as `/api/me/evaluations` (empty/403) — the org's switch becomes enforceable again; with the module on, nothing changes (verified in both directions).
Change: extract one helper (e.g. `authorization.ensure_subject_may_read_result`) around `employee_results_are_visible`; call it in the employee branch of `scope_evaluations_for_role`/`list_evaluations`, the `is_subject` branch of `evaluation_summary_pdf`, and the acknowledge/objection paths in `me.py`; serialize the employee-branch list rows with the trimmed `MyEvaluationRead` field set.
Files/components: `backend/app/api/routers/evaluations.py`, `me.py`, `schemas/evaluation.py`.
Implementation surface: ~3 call sites + 1 serialization switch + 2 module-OFF regression tests (the tests are FND-11-01/02's fix and must land together).
What could break: orgs that deliberately ran visibility-off while handing subjects the PDF lose that undocumented combination — which is precisely what the module promises to prevent; HR paths unaffected.
Migration/backward compatibility/finalized records: none — read-path gating only; finalized documents unchanged.
Priority: **1 (release-blocking pair with CP-16's tests).**

**CP-2 — One chain-shape module for frontend action gating and texts** *(from Roles 09 + 02; closes FND-02-01, FND-09-01, FND-09-02, FND-09-03, FND-09-04)*
Outcome: every supported chain shape (full / no-deputy / manager / CEO-direct / × HR-subject) sees correct next-stage wording, reachable finalize/return/rescue actions, an honest stepper (consumed stages dashed, not fake-green), and no buttons that always 403; the CEO home pending tab and stage labels stop lying about a deputy that does not exist.
Change: extract `isManagerPath/isCeoOnlyPath/hrClosesTheCase`-style predicates into `frontend/src/utils/chain.ts` mirroring `workflow.py`; consume in `canCeoFinalize` (allow `hr_approved` when `deputy_user_id === null`), ReturnBox gating (CEO-direct at `submitted`), `canRecoverStuckCase`/`canExtend` (deputy/CEO on shielded cases), dialog texts, `WorkflowStepper`, `STATUS_LABELS` qualifiers, and gate the approve button on HR ownership.
Files/components: `frontend/src/pages/EvaluationDetailPage.tsx`, `pages/ceo/CeoHomePage.tsx`, `components/WorkflowStepper.tsx`, `components/SubmissionDeadlineBar.tsx`, `types.ts`, new `utils/chain.ts`.
Implementation surface: pure predicate extraction + gating conditions; covered by the existing evaluation-page test patterns (add one vitest per shape).
Risks: low — no server change; worst case is a wrongly hidden button, caught by the shape tests.
Compat: none (frontend only). Priority: **2.**

**CP-3 — Employee self-assessment reachability** *(from Role 09; closes FND-09-06)*
Outcome: in the default module configuration, an invited employee lands on `/me` and actually sees the open-case card with the self-assessment form auto-opened and focused; the invite's deep link works; deadlines stop passing silently.
Change: gate the open-case cards on the `self_assessment` module (matching server semantics — `/me/evaluations/open` is ungated by design); read `?self-assessment={id}` on mount to open that case's form.
Files/components: `frontend/src/pages/employee/MyEvaluationsPage.tsx`, `components/employee/OpenCaseCard.tsx`.
Surface: two gating lines + one query-param effect. Risks: none server-side; keep result-gated sections on the visibility module.
Compat: frontend only. Priority: **3.**

**CP-4 — Single-pass indicator stats on the HR dashboard** *(from Role 10; closes FND-10-02)*
Outcome: the HR landing page loads ~4× faster as history accumulates (measured 346 ms → ~90 ms at 5-year scale; ~1.4 s → ~0.35 s extrapolated at 10-year).
Change: replace the four `_indicator_stats` queries (weakest/strongest × general/specialized) with one `GROUP BY indicators.id, section` aggregate; pick top/bottom-5 per section in Python — identical output, one scan, no disk spill.
Files/components: `backend/app/api/routers/dashboard.py:261-298`.
Surface: one function rewrite + a parity test asserting the previous output. Risks: none behavioral (same aggregates, same suppression).
Compat: response schema unchanged. Priority: **4.**

**CP-5 — Anchor-and-suffix verification for the audit hash chain** *(from Role 10; closes FND-10-01)*
Outcome: the audit-log page's integrity badge stays instant for the life of the system (measured 1,307 ms at 50.8k rows, linear, auto-fetched on page mount → constant ~ms), and deep full-chain verification stays available on demand.
Change: persist a `verified_up_to (id, entry_hash, checked_at)` checkpoint advanced only after a successful full verify (nightly sweep); the endpoint verifies only rows after the anchor and reports `verified_up_to` + `full: false`; a broken chain freezes the anchor.
Files/components: `backend/app/services/audit.py`, `services/scheduled.py`, `api/routers/audit_log.py`, one Alembic migration, `frontend/src/components/AuditIntegrityBadge.tsx`.
Surface: medium (new table + migration + sweep hook); response schema extended additively.
Risks: the anchor must never advance past an unverified row — freeze-on-failure semantics required.
Migration/compat: additive table; finalized records untouched. Priority: **5.**

**CP-6 — Paginate `/api/improvement-plans/eligible`** *(from Role 10; closes FND-10-03)*
Outcome: the improvement-plans page loads flat (page-sized payload, page-sized DOM) instead of a measured 625 KB / 3,354-row payload at 5 years that grows forever.
Change: `limit/offset` (+ optional subject search) on the endpoint; `PaginationControls` on the «نیازمند برنامه بهبود» card, like the plans table below it; optionally default to the latest period.
Files/components: `backend/app/api/routers/improvement_plans.py:108-152`, `frontend/src/api/queries.ts`, `pages/hr/ImprovementPlansPage.tsx`.
Surface: small (additive params + one paginator). Risks: card-title count needs a total; keep the fresh-case one-click default.
Compat: additive query params. Priority: **6.**

**CP-7 — One `localTodayIso()` for date-filter presets** *(from Role 08; closes FND-08-02)*
Outcome: night-shift HR (00:00–03:29 Tehran) gets the same "today" in the audit-log and reports presets as the backend's own local-day math; contract-expiry reports stop disagreeing with the sweep every night.
Change: derive the ISO key from local components (the pattern `SubmissionDeadlineBar.todayKey` already uses); one shared helper replaces the two private `todayIso()` copies.
Files/components: `frontend/src/pages/hr/AuditLogPage.tsx:53`, `pages/hr/ReportsSection.tsx:428`, `utils/dates.ts`.
Surface: pure function swap. Risks: none. Compat: frontend only. Priority: **7.**

**CP-8 — Anchor user-visible timestamps to the org timezone** *(from Role 08; closes FND-08-05)*
Outcome: the public QR-verify page shows the same Jalali day as the printed legal document regardless of the viewer's timezone (auditor, VPN); traveling staff see Tehran time everywhere.
Change: pass `timeZone: "Asia/Tehran"` to the `Intl.DateTimeFormat` instances (expose `org_timezone` via the config endpoint or a build constant); apply globally or at minimum to `VerifyPage.tsx`.
Files/components: `frontend/src/utils/dates.ts`, `pages/VerifyPage.tsx`, `backend/app/api/routers/config.py`.
Surface: tiny. Risks: users who preferred local time lose it — acceptable for a single-org Tehran deployment.
Compat: additive. Priority: **8.**

**CP-9 — Persian digits + Jalali dates in backend-authored messages** *(from Role 08; closes FND-08-01 and FND-08-03)*
Outcome: notifications, SMS/email bodies, API error details, import dialogs — and the legal PDF's comment table — match the system's own Persian-digit/Jalali convention; no more Gregorian dates printed next to Jalali ones on the hashed document.
Change: move `fa_digits`/a date-only Jalali formatter into a shared core module and apply at message-construction time at the enumerated call sites (never on dedup keys or audit old/new values).
Files/components: `evaluations.py:1196,1222`, `evaluation_window.py:104`, `scheduled.py`, `notifications.py`, `me.py:385`, `personnel_import.py`, new `app/core/persian.py`.
Surface: small but multi-site; tests asserting exact strings need updating.
Risks: low; keep dedup keys ASCII (length caps safe). Compat: message text only; finalized snapshots untouched (they store raw text — the fix applies at authoring time going forward). Priority: **9.**

**CP-10 — Light-theme hint-text contrast token** *(from Role 09; closes FND-09-05)*
Outcome: guidance and empty-state text in light theme meets WCAG AA 4.5:1 (measured 2.54:1 today) for low-vision users — including the only signpost explaining the objection path; dark theme unchanged.
Change: define `--color-hint` at gray-500 level for text; swap the ~15 content-bearing `text-gray-400` sites; add a source-scanning test forbidding hint-bearing `text-gray-400`.
Files/components: `frontend/src/index.css` + content-bearing sites.
Surface: token + one pass. Risks: visual tone shift; do it with the token, not per-site edits. Compat: CSS only. Priority: **10.**

**CP-11 — Normalize the detail-endpoint 403/404 oracle** *(from Role 05; closes FND-05-02)*
Outcome: employees probing sequential evaluation ids can no longer map their own record ids from distinct error bodies; the cheapest discovery route for CP-1's gated PDF disappears.
Change: in `_ensure_can_view`, non-HR callers get the generic 403 (or 404 matching `me.py`'s convention) regardless of subject-ness; the actionable own-case message stays for HR where it belongs.
Files/components: `backend/app/api/routers/evaluations.py:157-172`.
Surface: one branch. Risks: message-only. Compat: none. Priority: **11.**

**CP-12 — Refresh `my-permissions` during long sessions** *(from Role 09; closes FND-09-07)*
Outcome: capability/module revocations by another admin reflect in nav and module-gated UI within ~2 minutes (or immediately after any 403), keeping "hidden = server rules" true for the session.
Change: `refetchInterval: 120_000` on the permissions query and/or invalidate `["administration","my-permissions"]` from the axios interceptor on 403.
Files/components: `frontend/src/auth/PermissionsContext.tsx`, `api/client.ts`.
Surface: two lines. Risks: trivial load. Compat: frontend only. Priority: **12.**

**CP-13 — Deduplicate the repeated aggregate scans in my-scoring / report summary** *(from Role 10; closes FND-10-04)*
Outcome: the supervisor "mirror" and HR report pages stay flat as years accumulate (measured 137.9 ms → ~50 ms at 5-year scale).
Change: materialize the shared "other scores"/"base" subquery once (`.cte()` / `WITH … AS MATERIALIZED`) and derive count/avg/cohort/distribution from one pass.
Files/components: `backend/app/api/routers/analytics.py:108-241`, `routers/reports.py:124-179`.
Surface: moderate SQL refactor; cohort-suppression parity asserted by existing tests.
Risks: suppression parity (P1-08) must hold. Compat: response schemas unchanged. Priority: **13.**

**CP-14 — Client-side length parity with `text_limits.py`** *(from Role 09)*
Outcome: users learn the 4000/1000/2000-character limits while typing (live counter), not from a post-submit 422.
Change: add `maxLength` (+ optional counters) to evaluator comment, chain comments, return/cancel/handover/reassign reasons, objection text/resolution, self-assessment notes.
Files/components: `EvaluationDetailPage.tsx`, `ObjectionPanel.tsx`, `MyEvaluationsPage.tsx`, `HrRecoveryBox.tsx`, `SubmissionDeadlineBar.tsx`, `OpenCaseCard.tsx`; one shared constants module.
Surface: small. Risks: none. Compat: frontend only. Priority: **14.**

**CP-15 — Shared `Switch` component with logical positioning** *(from Role 08; closes FND-08-04)*
Outcome: one knob-direction convention across the app; the module and policy toggles stop contradicting each other on the same Administration page.
Change: extract a `role="switch"` component using `start-*`/`end-*`; replace both implementations.
Files/components: `frontend/src/pages/hr/AdministrationPage.tsx` (2 sites), new `frontend/src/ui/Switch.tsx`.
Surface: tiny. Risks: visual-only. Compat: additive. Priority: **15.**

**CP-16 — Module-OFF and content-semantics regression tests for the two subject branches** *(from Role 11; closes FND-11-01/FND-11-02 — the test half of CP-1)*
Outcome: reintroducing (or failing to implement) the `employee_evaluation_visibility` gate on `GET /api/evaluations` or `GET /api/evaluations/{id}/summary.pdf` turns CI red; the employee branch's field set is pinned to the trimmed view.
Change: module-OFF tests asserting `total == 0` on the list for an employee and 403/trimmed on the subject PDF; field-level assertions mirroring the `MyEvaluationRead` trim; with the module on, content-semantics assertions for the subject branch.
Files/components: `backend/tests/test_employee_self_view.py`, `tests/test_module_switches.py`.
Surface: two tests. Risks: none. Compat: test-only. Priority: **1 (inseparable from CP-1 — the fix and its guard must land together).**

**CP-17 — Permanent tests for the unhandled-error middleware and the background render-failure path** *(from Role 11; closes FND-11-03/FND-11-04)*
Outcome: the production guarantees "a crash yields a safe Persian 500 with a request id and no internal leak" and "a background PDF render failure never corrupts a finalized record" are locked by tests instead of by luck (both currently untested; mutations survived).
Change: a `raise_server_exceptions=False` middleware test with a dependency raising `RuntimeError("secret")`; replace the vacuous render-failure test with a committed finalized record + monkeypatched failing render.
Files/components: `backend/tests/` (2 files). Surface: two tests. Risks: none. Priority: **16.**

**CP-18 — Throttle `POST /api/auth/change-password`** *(from Role 01)*
Outcome: a stolen 30-minute access token cannot brute-force the user's current password at line speed through 400 responses; verification cost rests on Argon2 plus a rate limit.
Change: `@limiter.limit("10/minute")` (login's pattern) and/or count failures via `login_guard.record_failure`.
Files/components: `backend/app/api/routers/auth.py`. Surface: one decorator. Risks: lenient limit avoids annoying legit users. Compat: additive. Priority: **17.**

**CP-19 — Trim `PersonnelRead` for non-HR chain viewers** *(from Role 05)*
Outcome: a unit supervisor / deputy / CEO listing "my people" no longer receives each member's `separation_reason` (dismissal vs resignation), `separation_date`, or `account_username`; HR views unchanged.
Change: blank those fields in `_with_accounts`/serialization when the requester is not HR/`manage_personnel`.
Files/components: `backend/app/api/routers/personnel.py`, `schemas/personnel.py`. Surface: small. Risks: minimal (supervisors don't act on those fields). Priority: **18.**

**CP-20 — Cap (or stream) the evaluations Excel export** *(from Role 10; closes FND-10-05)*
Outcome: the export stays a bounded, predictable request even at 10-year history (measured linear 0.23 ms/row, no cap today; audit export already caps at 5,000).
Change: mirror the 5,000-row cap with a truncation notice in the `excel_exported` audit event it already writes, or openpyxl `write_only` streaming.
Files/components: `backend/app/api/routers/evaluations.py:699-746`, `services/excel.py`. Surface: small. Risks: truncated exports must be visible to HR. Priority: **19.**

**CP-21 — Scope the copilot-confirm cache invalidation** *(from Role 10; closes FND-10-06)*
Outcome: confirming an AI-suggested action no longer refetches every mounted query in the app.
Change: replace the bare `queryClient.invalidateQueries()` with the specific key families the action can touch.
Files/components: `frontend/src/components/copilot/CopilotPanel.tsx:196`. Surface: one line. Risks: none. Priority: **20.**

**CP-22 — Slim the anonymous `/api/health/ready` response** *(from Role 01)*
Outcome: an unauthenticated network probe learns only "ready/not-ready", not pool occupancy, migration head hash, or sweep freshness.
Change: keep status-code semantics (503 when unhealthy); move the detail fields behind the metrics token or `view_diagnostics`.
Files/components: `backend/app/main.py`. Surface: one endpoint. Risks: dashboards scraping those fields must switch to `/metrics`. Priority: **21.**

## Release Gate

**Gate reasons (verified, referencing finding IDs):**

1. **FND-01-01 (HIGH, REPRODUCED)** — the `employee_evaluation_visibility` module (default OFF, accepted purpose: gate server reads) is bypassed by `GET /api/evaluations`, returning the employee's own finalized record with the full chain-side schema including `evaluator_comment` and chain identity. Violates an established requirement; no release-scope exclusion; no effective mitigation (the endpoint is reachable by any employee with a token, no rate limit on the router). **Blocking.**
2. **FND-05-01 (HIGH, REPRODUCED)** — the same module is independently bypassed by the subject branch of `GET /api/evaluations/{id}/summary.pdf`, serving the complete hashed legal document (per-indicator scores, evaluator evidence narratives, stage comments) to the evaluated employee in the default configuration; three independent id-discovery routes (incl. FND-05-02's 403-message oracle and unthrottled sequential scanning). Fixing FND-01-01 does not close this path. **Blocking.**
3. **FND-02-01 (HIGH, SOURCE-PROVEN, API half reproduced)** — the legal no-deputy chain shape dead-ends at `hr_approved` in the product UI: the backend's `ceo_finalize` transition is legal there, but no button, CEO-home tab, or recovery path can advance the case; the SLA sweeper even notifies the CEO to act on a page that offers no action. A supported approval chain stalls with no in-product mitigation. **Blocking.**
4. **FND-11-01 / FND-11-02 (HIGH, REPRODUCED by controlled mutation)** — the two release-blocking privacy defects above passed a fully green CI because the employee branches of exactly those endpoints have no module-OFF tests and no content assertions; a mutation *adding the missing gate* survived 117 and 85 tests. Releasing fixes without these tests would ship them unvalidated. **Blocking (as the validation half of items 1–2).**

Non-blocking verified defects: the remaining 17 MEDIUM and 24 LOW findings all have bounded blast radius, an existing workaround, or an operator-only/degradation-only failure mode (e.g. FND-06-01's downgrade-path data loss requires an operator to run a destructive downgrade cycle; FND-10-01's audit-integrity latency degrades a badge, not correctness; FND-09-05's contrast failure has the dark theme as a workaround). They should be fixed per the priorities in the Executive Verdict and CP ranking, but none meets the blocker standard above.

Material verification gaps that bound this assessment (not blockers by themselves, per the gate rules): remote CI status for this commit is unverifiable (GitHub API rate limit) — the local CI-equivalent is fully green and drift-checked; no real-browser run (frontend findings rest on source + jsdom evidence, each labeled); no live SMTP/SMS; PDF verified at HTML/byte layer; mutation-survival beyond executed selections labeled UNVERIFIED.

**To reach GO:** land CP-1 + CP-16 (gate + tests, closing FND-01-01/FND-05-01/FND-11-01/02), CP-2's finalize/return gating subset (closing FND-02-01), re-run the four CI jobs plus the two new module-OFF tests, and re-verify on this review branch.

**Status: RELEASE: NO-GO**
