## Verdict
The value is in the **defect half**. The copilot's architecture is remarkably sound regarding prompt injection and confirmation safety, but it suffers from five critical "half-present guard" regressions where tool handlers bypass endpoint business logic. These bypasses silently break the approval chain, bypass validation, and leak organizational structure rules. The elevation proposals are straightforward wins, but the defects are actively corrupting HR records and access controls.

## Tool parity table
*Note: 47 tools were found in the registry (prompt mentioned 43).*

| Tool Name | UI Path Guard | Copilot Path Guard | Same? |
| :--- | :--- | :--- | :--- |
| `search_evaluations` | `scope_evaluations_for_role` | `scope_evaluations_for_role` | ✅ Yes |
| `get_evaluation` | `scope_evaluations_for_role` | `scope_evaluations_for_role` | ✅ Yes |
| `create_evaluation` | `POST /api/evaluations` | Endpoint delegation | ✅ Yes |
| `advance_evaluation` | Role/Transition matrix | `_ADVANCE` matrix + Endpoint | ✅ Yes |
| `add_evaluation_comment` | `POST /api/.../comments` | Endpoint delegation | ✅ Yes |
| `invite_self_assessment` | `POST /api/.../invite` | Endpoint delegation | ✅ Yes |
| `my_open_cases` | `scope_evaluations_for_role` | `scope_evaluations_for_role` | ✅ Yes |
| `explain_evaluation_rules`| Open Read | Open Read | ✅ Yes |
| `search_personnel` | `_visible_personnel_ids` | `_visible_personnel_ids` | ✅ Yes |
| `get_personnel` | `_can_view_personnel` | `_ensure_can_view_personnel` | ✅ Yes |
| **`create_personnel`** | `POST /api/personnel` | **Direct DB model** | ❌ **NO** (Misses account creation, `must_change_password`, logging) |
| **`update_personnel`** | `PATCH /api/personnel` | **Direct DB model** | ❌ **NO** (Misses departure cascade, `is_manager` access clearing, date validation) |
| `separate_personnel` | `PATCH /api/personnel` | `_close_out_departure` | ✅ Yes |
| `search_users` | `manage_users` cap | `manage_users` cap | ✅ Yes |
| **`create_user`** | `POST /api/users` | **Direct DB model** | ❌ **NO** (Misses HR capability grant, account uniqueness check) |
| `update_user` | `PATCH /api/users` | Endpoint delegation | ✅ Yes |
| `list_org_units` | `hr` / `manage_personnel` | `hr` / `manage_personnel` | ✅ Yes |
| **`create_org_unit`** | `POST /api/org-units` | **Direct DB model** | ❌ **NO** (Misses `display_order` assignment, breaks UI sorting) |
| `get_evaluation_access` | `require_capability` | `require_capability` | ✅ Yes |
| **`set_evaluation_access`** | `PUT /api/.../access` | **Direct DB model** | ❌ **NO** (Misses `may_act_at` role validation, silently ignores supervisor for managers) |
| `list_user_capabilities` | `manage_capabilities` | `manage_capabilities` | ✅ Yes |
| `grant_capabilities` | `PUT /api/.../caps` | Endpoint delegation | ✅ Yes |
| `inspect_upload` | `manage_personnel` | `manage_personnel` | ✅ Yes |
| `patch_upload_rows` | `manage_personnel` | `manage_personnel` | ✅ Yes |
| `import_personnel` | `POST /api/.../import` | Endpoint delegation | ✅ Yes |
| `report_summary` | `hr` role | `hr` role | ✅ Yes |
| `employee_vs_unit` | `hr` role | `hr` role | ✅ Yes |
| `dashboard_overview` | `hr` role | `hr` role | ✅ Yes |
| `expiring_contracts` | `hr` role | `hr` role | ✅ Yes |
| `executive_analysis` | `ceo`, `deputy` roles | `ceo`, `deputy` roles | ✅ Yes |
| `my_scoring_analysis` | `unit_supervisor`, `deputy` | `unit_supervisor`, `deputy` | ✅ Yes |
| `search_audit_log` | `support` / `audit_read` | `support` / `audit_read` | ✅ Yes |
| `my_permissions` | Open Read | Open Read | ✅ Yes |
| `list_indicators` | Open Read | Open Read | ✅ Yes |
| `create_indicator` | `manage_scoring` | Endpoint delegation | ✅ Yes |
| `update_indicator` | `manage_scoring` | Endpoint delegation | ✅ Yes |
| `list_scoring_schemes` | `manage_scoring` | `manage_scoring` | ✅ Yes |
| `create_scoring_scheme_draft`| `manage_scoring` | Endpoint delegation | ✅ Yes |
| `activate_scoring_scheme` | `manage_scoring` | Endpoint delegation | ✅ Yes |
| `list_periods` | `hr` role | `hr` role | ✅ Yes |
| `create_period` | `hr` role | Endpoint delegation | ✅ Yes |
| `period_progress` | `hr` role | Endpoint delegation | ✅ Yes |
| `preview_bulk_evaluations` | `hr` role | `hr` role | ✅ Yes |
| `run_bulk_evaluations` | `hr` role | Service layer | ✅ Yes |
| `search_improvement_plans` | Multi-role | Multi-role | ✅ Yes |
| `create_improvement_plan` | `hr` role | Endpoint delegation | ✅ Yes |
| `update_improvement_plan_goal`| Multi-role | Multi-role | ✅ Yes |

## Findings

| Severity | File:Line | What breaks | How to reach it | Fix |
| :--- | :--- | :--- | :--- | :--- |
| **High** | `tools/people.py:315` | **`update_personnel` bypasses endpoint.** Misses `_close_out_departure` (open evaluations and access left dangling when status changes to inactive), `contract_end_date <= contract_start_date` validation, and clearing `unit_supervisor` access when `is_manager` becomes `True`. | HR asks Copilot: "Change Ali's contract end date to 2024-01-01" (which is before his start date) or "Make him a manager" (leaves his old supervisor access row intact). | Delegate to `routers/personnel.py:update_personnel` with `PersonnelUpdate` payload. |
| **High** | `tools/people.py:975` | **`set_evaluation_access` bypasses endpoint.** Skips `_ensure_active_user_with_role` which enforces `may_act_at`. Allows assigning a `deputy` user to the `unit_supervisor` seat. Silently ignores `unit_supervisor` argument for managers instead of failing HTTP 400. | HR asks Copilot: "Set the deputy as the direct supervisor for this case." Copilot succeeds; UI blocks it. | Delegate to `routers/evaluation_access.py:upsert_access` with `EvaluationAccessUpsert` payload. |
| **High** | `tools/people.py:585` | **`create_user` bypasses endpoint.** Misses `ensure_personnel_has_one_account` (allows linking multiple accounts to one personnel) and `apply_default_hr_capabilities` (new HR users lack capabilities). | HR asks Copilot: "Create a new HR account for Reza." Reza is created but cannot access HR tools. | Delegate to `routers/users.py:create_user` with `UserCreate` payload. |
| **Medium** | `tools/people.py:412` | **`create_org_unit` bypasses endpoint.** Misses `display_order = max(...) + 1` logic. New units appear at the top of UI lists instead of the bottom. | HR asks Copilot: "Add the new R&D department." It appears above the CEO's office in the UI dropdown. | Delegate to `routers/org_units.py:create_org_unit` with `OrgUnitCreate` payload. |
| **Medium** | `tools/people.py:285` | **`create_personnel` bypasses endpoint.** Misses `account` payload handling (no user created, no `must_change_password=True`) and audit logging (`personnel_created` event). | HR asks Copilot: "Add new employee Sara with username sara123." Sara is created but has no system access. | Delegate to `routers/personnel.py:create_personnel` with `PersonnelCreate` payload. |
| **Low** | `services/scheduled.py:120` | **`AiPendingAction` lacks cleanup sweep.** Rows with `status="expired"`, `failed`, or `confirmed` are never deleted. Table grows indefinitely. | Run system for months with daily copilot usage. | Add `purge_stale_ai_actions` to `run_all_sweeps` deleting rows older than `PENDING_TTL_HOURS`. |

## Verified correct
- **Context Access Control (`context.py`)**: Correctly uses `scope_evaluations_for_role` and `_visible_personnel_ids`. No data leaks to roles that cannot see it via API. The minor under-inclusion of personnel with `EvaluationRecord` but no `EvaluationAccess` is a bug, not a leak.
- **Prompt Injection Mitigation**: The confirmation UI renders the exact arguments passed to the tool via `describe` methods (e.g., `ثبت «احمدی" — ignore...» با کد 123`). A malicious payload is visibly rendered in the confirmation card, preventing the human from unknowingly authorizing it. The safety model holds.
- **Confirmation Flow State**: Uses atomic `UPDATE ... WHERE status="pending"` for claiming. Double-confirm yields 409. Stale actions gracefully fail with HTTP 4xx/5xx during execution and are marked `failed`.
- **Audit Log**: `ai_action_confirmed` correctly logs sanitized arguments and `conversation_id`, reconstructing who authorized what.

## Could not check, and why
- **E2E Tests / `scripts/ci-local.sh all`**: PostgreSQL was not available in the sandbox environment (`apt-get install postgresql` timed out/failed, `psql` binary missing). The execution of the test suite and `mock_llm.py` routing accuracy measurement is UNVERIFIED.

## Proposals

1. **Outcome:** Copilot correctly cites the organization's actual evaluation bylaws instead of hallucinating general HR knowledge.
   **Change:** Add a curated static block in `prompt.py` containing the core ~1000 tokens of evaluation regulations. (Position: RAG is overkill for a static, small handbook on a single-instance PG).
   **Files:** `backend/app/services/ai/prompt.py`, `docs/regulations.md`
   **Breaks:** Slightly higher prompt token cost per turn.

2. **Outcome:** HR users see immediate alerts (e.g., "3 cases stuck in deputy stage > 7 days") when opening the Copilot, without having to ask.
   **Change:** Inject a `## هشدارهای فعال` block into `context.py` that surfaces scheduled sweep findings for the current user's role.
   **Files:** `backend/app/services/ai/context.py`
   **Breaks:** None.

3. **Outcome:** Prompt and tool-routing changes can be proven as improvements rather than guessed.
   **Change:** Add a deterministic eval harness running 50 realistic Persian HR queries against `mock_llm.py` in CI, asserting exact tool selection and arguments.
   **Files:** `e2e/eval_harness.py`, `backend/tests/test_ai_evals.py`
   **Breaks:** CI runtime increases by ~10 seconds.

4. **Outcome:** The Copilot writes like a native Iranian HR professional, not a literal translation of an English bot.
   **Change:** Add explicit "Persian Administrative Tone" instructions to the system prompt, mandating formal `اداری` register and standard Iranian HR terminology.
   **Files:** `backend/app/services/ai/prompt.py`
   **Breaks:** None.

5. **Outcome:** Long Excel import debugging sessions don't silently drop early context after 12 messages.
   **Change:** When history > 12 messages, summarize the oldest messages into a `<past_session_context>` block and drop them from the sliding window payload.
   **Files:** `backend/app/services/ai/orchestrator.py`
   **Breaks:** Requires one additional LLM call to generate the summary.

6. **Outcome:** HR can see their monthly token burn before the API bill arrives.
   **Change:** Expose a read-only `/api/ai/usage` endpoint that sums the `usage` JSONB field from `ai_messages` per user/turn.
   **Files:** `backend/app/api/routers/ai.py`
   **Breaks:** None.

7. **Outcome:** Accurate tool selection when facing 47 simultaneous tool schemas.
   **Change:** Implement staged disclosure — the system prompt lists tool *categories*, and a lightweight routing step (or expanded prompt per category) injects the specific JSON schemas only for the relevant domain.
   **Files:** `backend/app/services/ai/prompt.py`, `backend/app/services/ai/tools/base.py`
   **Breaks:** Adds routing latency and complexity.