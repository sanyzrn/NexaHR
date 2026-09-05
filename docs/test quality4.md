## Verdict — 3 lines
The test suite has structural isolation failures that hide real defects: `test_audit_fixes.py` pollutes the shared database via standalone commits, `test_audit_pass.py` trusts HTTP 200 without verifying filter correctness, and `pytestmark = usefixtures("employee_view_on")` masks a missing module guard in `resolve_objection`. Verified correct: cohort suppression correctly counts *people* not records, the `employee_evaluation_visibility` server-side gate is intentionally deliberate, and the AI copilot correctly delegates to endpoint guards for comments.

## Findings — severity | file:line | what breaks | how to reach it | fix
**HIGH | backend/tests/test_audit_fixes.py:624 | Test isolation / DB pollution**
The test creates `af_race_*` users and pending actions using a standalone `make_session()` and calls `setup.commit()`, bypassing the pytest `db_session` rollback fixture. This pollutes the shared test database with leftover state that causes subsequent tests to pass or fail unpredictably based on execution order.
*Path:* Run the full suite; rows persist across test boundaries.
*Fix:* Inject and use the `db_session` fixture for all database operations in this test, ensuring automatic rollback.
*Mutation:* Change the `af_slow_write` tool to return `ToolOutcome(success=True)` without actually writing to the DB. The test will still pass if it relies on leftover state from a previous polluted run, proving it doesn't verify DB state via the rolled-back session.

**HIGH | backend/tests/test_audit_pass.py:263 | Unverified filter logic (Assert 200 only)**
In `test_audit_log_date_filter_and_export`, the test asserts `assert r_old.status_code == 200` for the `created_to` filter but never verifies that `r_old.json()["total"] == 0`. If the filter logic is broken or removed, the endpoint returns all logs but the test still passes.
*Path:* 1. Remove the `created_to` filter block in `app/api/routers/audit_log.py`. 2. Run the test. It passes green.
*Fix:* Add `assert r_old.json()["total"] == 0` after the status code assertion to verify the filter actually excluded records.
*Mutation:* Delete the `if created_to is not None:` condition in `api/routers/audit_log.py`. The suite will not catch the regression.

**HIGH | backend/app/api/routers/evaluations.py:~450 | Missing module guard hidden by pytestmark**
The `resolve_objection` endpoint lacks `ensure_module_enabled(db, "objections")`. Because `test_employee_voice.py` (which tests resolution) uses `pytestmark = usefixtures("employee_view_on")`, the `objections` module is artificially forced ON during testing. The suite never exercises the default-OFF production state, so it fails to catch that HR can still resolve objections via API even when the organization has disabled the objections module.
*Path:* 1. Disable `objections` module in DB. 2. HR user POSTs to `/api/evaluations/{id}/resolve-objection`. It succeeds (200) instead of returning 403.
*Fix:* Add `ensure_module_enabled(db, "objections")` at the top of the `resolve_objection` function body.
*Mutation:* The suite already fails to catch the missing guard. If you were to add a dummy parameter or change the return value of `resolve_objection`, the suite wouldn't catch that it bypasses the module switch because the switch is never OFF in its test file.

**UNVERIFIED | tests/test_*.py | Wall-clock hour dependency**
Could not execute the suite to verify which specific test fails based on the wall-clock hour (requires PostgreSQL setup with real partial indexes/triggers as noted in rules). `test_audit_pass.py` uses `today_local()` which could theoretically shift dates across UTC boundaries depending on execution time, but the API's `local_day_start` conversion appears sound on static analysis.

## Verified correct
*   **Cohort suppression logic:** `services/privacy.py` correctly counts distinct *people* (personnel IDs) rather than evaluation records, preventing the "one person over five periods" leak described in the prompt.
*   **AI copilot delegation:** `services/ai/tools/evaluations.py` correctly delegates to `add_comment_endpoint` rather than building stages inline, ensuring the endpoint's `ensure_hr_may_handle` and stage guards are actually executed for AI-initiated writes.
*   **Module switch enforcement:** `test_module_switches.py` correctly verifies the OFF state for `objections` and `employee_result_acknowledgement`, proving the endpoints themselves are properly gated (unlike `resolve_objection` which is missed).
*   **PDF hashing/archival:** `test_documents.py` correctly verifies that the finalized PDF is hashed and archived independently of the HTTP response, preventing race conditions between finalization and download.

## Could not check, and why
*   **Full test execution:** Could not run `scripts/ci-local.sh` to completion because it requires a PostgreSQL 16 database with specific extensions/partial indexes that were not available in the sandbox environment. All findings are based on static analysis of the source code and test logic.
*   **Wall-clock hour test:** Could not definitively identify which test fails based on the hour of day without executing the suite and observing flaky behavior across different timezones/times. Static analysis of `today_local()` usage did not reveal an obvious off-by-one boundary error in the API logic itself.