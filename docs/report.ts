export type Severity = "HIGH" | "MEDIUM" | "LOW";
export type Status = "VERIFIED (source read)" | "PARTIALLY VERIFIED" | "UNVERIFIED";

export interface Finding {
  id: string;
  severity: Severity;
  status: Status;
  title: string;
  location: string; // file:line
  whatBreaks: string;
  howToReach: string;
  mutation: string; // the mutation the suite would not catch
  evidence: string[]; // quoted or paraphrased source lines
  fix: string;
}

export const meta = {
  repo: "https://github.com/sanyzrn/NexaHR",
  branch: "main",
  commit: "95c5433bb655704cef7acb6ca61ba19b7495b0af",
  angle: "test quality",
  scope:
    "97 backend pytest files (~1035 tests), 45 frontend vitest files (270), 89 launcher tests, e2e API scenario",
  executed: false,
};

export const verdict: string[] = [
  "The suite is unusually deliberate (savepoint isolation, timezone pins, negative tests, parametrised role sweeps) but repeats the repo's signature defect in test form: several tests assert the guard the author *meant* to write — the row-lock test compiles its own SELECT and never touches the app function, the read-only-leak sweep never calls any tool that takes an argument, and the legal PDF's signature block is pinned for exactly one of five live chain shapes while being wrong for the other four today.",
  "Highest unguarded risk is the hashed, QR-verifiable document itself: nothing asserts that `record.final_snapshot` matches the record, and the signature lines are derived from a role label string instead of the chain shape — so the manager path prints no HR signature although HR reviewed, and CEO-direct prints supervisor and deputy lines beside the 'single decider' notice.",
  "Nothing in this review was executed: this environment has no shell, no checkout and no PostgreSQL, so `scripts/ci-local.sh` could not run. Every claim below is a source read of main@95c5433 through GitHub, capped at ~10 KB per file, and is labelled VERIFIED (source read), PARTIALLY VERIFIED or UNVERIFIED accordingly.",
];

export const findings: Finding[] = [
  {
    id: "F1",
    severity: "HIGH",
    status: "VERIFIED (source read)",
    title:
      "Legal PDF signature block is keyed on a role-label string; wrong for 4 of 5 chain shapes and the test pins only one cell",
    location:
      "backend/app/templates/evaluation_summary.html (signature block: `{% set manager_path = snapshot.evaluator.role_label == 'معاونت' %}` … `{% if not manager_path %} امضای مسئول واحد / امضای منابع انسانی {% endif %} امضای معاونت / امضای مدیرعامل`) · backend/app/services/snapshot.py:`build_final_snapshot` (evaluator.role_label only; no chain-shape keys) · backend/tests/test_pdf_security.py:`test_signature_block_matches_evaluation_path`",
    whatBreaks:
      "The hashed official employment document states who signed. The template has two branches only (evaluator is deputy → drop supervisor+HR lines; otherwise print all four). workflow.py knows five shapes (`is_manager_path`, `is_ceo_only_path`, `skips_hr_review`, no-deputy, full). Result today: (a) manager path — HR *does* review (transition `manager_submit` → `submitted`, README §گردش‌کار) yet the PDF prints no «امضای منابع انسانی» while printing HR's `hr_review` comment under «کامنت‌های مراحل بررسی»; (b) no-deputy chain (sup → HR → CEO) — role_label is «مسئول واحد», so «امضای معاونت» is printed for a seat that does not exist; (c) CEO-direct — role_label is the CEO seat label, `manager_path` is False, so «امضای مسئول واحد» and «امضای معاونت» are printed directly next to the `single_decider` notice that says one person did both; (d) HR-subject chain (`hr_review_skipped=True`) — «امضای منابع انسانی» is printed for a stage that was skipped by design. Only the full four-seat chain is right. The template comment («مرحله مسئول واحد/HR وجود ندارد») describes the pre-a7f3c9b52d18 design.",
    howToReach:
      "Role HR: PUT /api/personnel/{id}/access with unit_supervisor_user_id=null, deputy_user_id=D, ceo_user_id=C (manager path). Deputy D: POST /evaluations, PUT /scores, POST /submit. HR: POST /hr-approve (+ a top-level comment). CEO C: POST /ceo-finalize. HR: GET /summary.pdf → document has HR's review text but no HR signature line. CEO-direct: access with both middle seats null (test_ceo_only_chain.py shows this is registrable) → finalize → PDF prints supervisor and deputy signature lines.",
    mutation:
      "Any of: (1) add «امضای منابع انسانی» inside the manager-path branch; (2) delete «امضای معاونت» for no-deputy chains; (3) hide supervisor/deputy lines for CEO-direct — i.e. *fix* the template — and the suite result is unchanged. Equally, keep it broken. The only pinned cell is `role_label=='معاونت' ⇒ no «امضای مسئول واحد»`; the test asserts nothing about HR on that path and nothing at all for no-deputy, CEO-direct or HR-subject snapshots. `_snapshot_with()` in the test is a hand-written dict, so the snapshot builder is never exercised either.",
    evidence: [
      "evaluation_summary.html: `{# مسیر «مدیر»: معاونت نمره‌دهنده اول است و مرحله مسئول واحد/HR وجود ندارد #}` — stale; workflow.py `manager_submit` now routes the manager path to `submitted` (HR review).",
      "snapshot.py: `\"evaluator\": {\"username\": …, \"role_label\": evaluator_label}` — SEAT_LABEL[scorer_field(...)]; no `deputy_user_id`/`unit_supervisor_user_id`/`hr_review_skipped` in the snapshot, so the template *cannot* know the shape.",
      "test_pdf_security.py `test_signature_block_matches_evaluation_path`: asserts `\"امضای مسئول واحد\" not in html` and `\"امضای معاونت\" in html and \"امضای مدیرعامل\" in html` for role_label «معاونت»; asserts the four lines for «مسئول واحد». No other shape, no HR assertion on the manager path.",
      "workflow.py `is_ceo_only_path` docstring itself notes the old workaround 'در سند هم دروغ می‌گفت' — the document lying is a known failure mode here.",
    ],
    fix:
      "Bump SNAPSHOT_VERSION to 5 and add `\"chain\": {\"has_supervisor\": record.unit_supervisor_user_id is not None, \"has_deputy\": record.deputy_user_id is not None, \"hr_reviewed\": not record.hr_review_skipped, \"ceo_direct\": is_ceo_only_path(record)}` in build_final_snapshot. In the template branch on `snapshot.chain` (fallback to the old role_label rule only when `chain` is absent). Add a parametrised test over the five shapes that finalises through the API, renders `record.final_snapshot` and asserts the *exact set* of «امضای …» lines (present and absent).",
  },
  {
    id: "F2",
    severity: "HIGH",
    status: "VERIFIED (source read)",
    title:
      "Row-lock test compiles its own SELECT and never inspects the app function — the double-approve guard is untested",
    location:
      "backend/tests/test_workflow_concurrency.py ≈L33–L42 (`test_row_lock_clause_is_present_in_generated_sql`) and ≈L18–L31 (`test_get_record_for_update_returns_the_correct_record`) · backend/app/api/routers/evaluations.py:`_get_record_or_404_for_update` (not read; beyond fetch cap)",
    whatBreaks:
      "Module docstring: 'این تست مستقیماً تأیید می‌کند که عبارت SQL تولیدشده توسط _get_record_or_404_for_update واقعاً شامل قفل است'. It does not. The test body builds `select(EvaluationRecord).where(id==1).with_for_update(of=EvaluationRecord)` itself and asserts SQLAlchemy prints FOR UPDATE. The companion test only asserts `record.id == evaluation_id`. Without the lock, two concurrent `ceo-finalize` (double-click, two tabs, or copilot confirm + UI click) both pass the status check → two `finalized` transitions, duplicate audit_log events on an append-only hash chain, two background archival attempts. The very race the docstring says it protects.",
    howToReach:
      "Remove the lock (see mutation), then as CEO fire two POST /api/evaluations/{id}/ceo-finalize within the WeasyPrint/commit window. Both return 200. The suite stays green.",
    mutation:
      "In api/routers/evaluations.py delete `.with_for_update(of=EvaluationRecord)` from `_get_record_or_404_for_update`. Both tests in test_workflow_concurrency.py pass unchanged.",
    evidence: [
      "`stmt = (select(EvaluationRecord).where(EvaluationRecord.id == 1).with_for_update(of=EvaluationRecord))` — constructed in the test, not obtained from the app.",
      "`assert \"FOR UPDATE\" in compiled_sql.upper()` — asserts SQLAlchemy behaviour.",
      "Docstring claims a threading test is infeasible with the shared savepoint fixture — yet test_audit_fixes.py (M-7) imports `threading`, `create_engine`, `sessionmaker` and does exactly that. The pattern exists in the repo.",
    ],
    fix:
      "Capture the SQL the real function emits: register `sqlalchemy.event.listen(engine, 'before_cursor_execute', …)` (or wrap `db_session.execute`) around a call to `_get_record_or_404_for_update(db_session, id)` and assert `FOR UPDATE` in the captured statement with `evaluation_records` in the `OF` clause. Additionally add one real two-connection test (reuse the M-7 pattern with a cleanup `finally`) asserting the second finalize gets 400/409 and exactly one `evaluation_finalized` audit row exists.",
  },
  {
    id: "F3",
    severity: "HIGH",
    status: "VERIFIED (source read)",
    title:
      "Read-only copilot leak sweep invokes every tool with `{}` — tools that take arguments raise before their guard and are counted as 'denied'",
    location:
      "backend/tests/test_ai_security.py ≈L44–L80 (`test_every_readonly_tool_denies_or_hides_other_peoples_data`)",
    whatBreaks:
      "The test iterates `REGISTRY` read-only tools and calls `execute_tool(ctx, spec, {})`. The `except Exception as e:  # ابزارهایی که آرگومانِ اجباری دارند` branch appends to `denied` and continues. Every tool whose schema has a required `record_id` / `personnel_id` / `query` never reaches its authorisation code; the assertion `assert not leaked` is then vacuous for exactly the tools most likely to leak (detail-by-id lookups). The diagnostic `print`s hide how many tools landed in that bucket.",
    howToReach:
      "Role employee with no capabilities and no chain, using the copilot: ask for a specific evaluation by id or a person by id. If an arg-taking read tool lacks `ensure_can_view`/equivalent, the victim's data is returned. The sweep never exercised that tool.",
    mutation:
      "Remove the access check from any arg-taking read-only tool (e.g. the evaluation-detail tool) in services/ai/tools/*.py. The sweep still passes: the tool is called with `{}`, raises a validation error, is filed under `denied`. Only an explicit parity test (not read here) could catch it, and nothing asserts every read tool has one.",
    evidence: [
      "`outcome = tools_base.execute_tool(ctx, spec, {})` — empty arguments for all tools.",
      "`except Exception as e:  # ابزارهایی که آرگومانِ اجباری دارند\\n    denied.append((spec.name, type(e).__name__)); continue`",
      "Contrast: `test_write_switch_off_blocks_every_mutating_tool` in the same file treats a non-HTTPException as *escaped* — that one is strong; the leak sweep is not.",
    ],
    fix:
      "Derive minimal valid arguments per tool from `spec.parameters` (fill `record_id`/`personnel_id` with the victim's ids, strings with the SECRET_NAME) and assert the `denied`-by-non-HTTPException bucket is empty. Keep `denied` for 403/404 only. Add a meta-assertion that every read-only tool appears in at least one arg-bearing negative test.",
  },
  {
    id: "F4",
    severity: "MEDIUM",
    status: "PARTIALLY VERIFIED",
    title:
      "`af_race_*` rows in test_audit_fixes.py are committed on a second engine, outside the rollback, and persist in nexahr_test between local runs",
    location:
      "backend/tests/test_audit_fixes.py (M-7 «claimingِ تأیید اتمی است» and M-10 sections; file is 769 lines, only ≈L1–L230 were readable) · backend/tests/conftest.py:`db_session` (savepoint isolation) · consumers: backend/tests/test_cohort_counts_people.py:`test_period_trend_counts_people`, backend/tests/test_scheduled.py:`test_contract_expiry_sweep_notifies_hr_once`, backend/tests/test_bootstrap_admin.py (assumption 'no admin exists', per conftest comment)",
    whatBreaks:
      "conftest's isolation is `join_transaction_mode=\"create_savepoint\"` on one connection; anything written through a *different* engine (`create_engine` + `sessionmaker` + `threading`, all imported at the top of test_audit_fixes.py, as a real race needs two connections) is a real COMMIT the outer rollback cannot undo. Users, personnel, evaluations created that way stay in the shared DB. Tests that assert on global buckets then depend on run history: `test_period_trend_counts_people` asserts `avg_final_pct is None` for the DB-wide «بدون دوره» bucket — five leftover finalized, period-less records from five distinct people flip it; `test_contract_expiry_sweep_notifies_hr_once` already tolerates strangers with `assert created >= 1`. CI is immune (fresh Postgres service container per job), so local ≠ CI and the order dependence inside one run is invisible because pytest order is fixed.",
    howToReach:
      "Developer: run `pytest` twice against the same nexahr_test (as README instructs). Second run sees rows from the first. Whether it fails or *passes wrongly* depends on which rows those tests leave — the body beyond L230 could not be read here, so the exact rows are unverified; the mechanism (second engine, commit) is confirmed by the imports and by the M-7 claim itself ('اجرا دوبار رخ نمی‌دهد' requires two committed sessions).",
    mutation:
      "None needed — this is state, not code. The observable effect: a test that should fail on the isolated DB may pass on the polluted one (or vice versa), and a regression in a global aggregation would be attributed to 'flaky test' instead of to the code.",
    evidence: [
      "test_audit_fixes.py header imports: `import threading`, `import uuid`, `from sqlalchemy import create_engine, select, text`, `from sqlalchemy.orm import sessionmaker`.",
      "conftest.py: `session_factory = sessionmaker(bind=connection, join_transaction_mode=\"create_savepoint\")` — isolation is per-connection only.",
      "conftest.py comment on BOOTSTRAP_ADMIN: 'دیتابیس تست مشترک است و آن حساب commit می‌شود، پس بین تست‌ها می‌ماند' — the authors know committed rows leak across tests.",
      "ci.yml backend job: `services: postgres: image: postgres:16 … POSTGRES_DB: nexahr_test` — new database every run.",
    ],
    fix:
      "In the M-7/M-10 fixtures, `try/finally` delete every row the second engine created (or `TRUNCATE ai_pending_actions, ai_conversations, users, personnel … CASCADE` restricted to the `af_race_` prefix), or give those tests a dedicated schema. Add a session-scoped autouse fixture that fails fast if `users`/`personnel` are non-empty at start (mirrors 'e2e drops and recreates the DB'). Run CI with `pytest-randomly` so order dependence surfaces.",
  },
  {
    id: "F5",
    severity: "MEDIUM",
    status: "VERIFIED (source read)",
    title:
      "`pytestmark = usefixtures(\"employee_view_on\")` plus explicit `set_module(...)` everywhere — no test ever asserts the shipped *default* (no row) is off",
    location:
      "backend/tests/test_employee_self_view.py:L21 · backend/tests/conftest.py:`employee_view_on` · backend/tests/test_module_switches.py (every test calls `set_module(db_session, key, True/False)` before asserting) · backend/app/core/modules.py:`ModuleDef(key=\"employee_evaluation_visibility\", default_enabled=False)`, `objections`, `employee_result_acknowledgement`",
    whatBreaks:
      "The three employee-view modules are documented as default-off and gate a server-side read (owner decision, kept). But every test that touches them first writes a `ModuleSetting` row. The fallback path — no row → `MODULES_BY_KEY[key].default_enabled` — is executed by production on a fresh install and by no test. The module-switch file tests 'set off → 403' and 'set on → 200'; it never tests 'never set → 403'.",
    howToReach:
      "Fresh install, no admin has visited the modules panel. Employee logs in and GETs /api/me/evaluations or POSTs /object. Whether that returns data depends solely on `default_enabled` and the resolver's fallback — both untested.",
    mutation:
      "core/modules.py: change `default_enabled=False` to `True` on `employee_evaluation_visibility` (or `objections`). Zero test failures — test_employee_self_view forces on, test_module_switches writes explicit rows. A second mutation: in the resolver, treat a missing row as enabled regardless of `default_enabled` (resolver not read; the *test gap* is verified either way).",
    evidence: [
      "test_employee_self_view.py:L20–21: `#: نمایِ خودِ کارمند پیش‌فرض خاموش است و این فایل رفتارِ *روشن* را می‌سنجد.\\npytestmark = pytest.mark.usefixtures(\"employee_view_on\")`",
      "helpers.set_module docstring: 'تستی که رفتارِ روشن را می‌سنجد باید صریح روشنش کند — نه اینکه به پیش‌فرض تکیه کند' — the mirror-image test (rely on default, expect off) was never written.",
      "test_module_switches.py `test_objections_off_refuses_an_objection`: `set_module(…visibility, True); set_module(…objections, False)` — explicit both ways.",
    ],
    fix:
      "Add `test_module_defaults.py`: (a) unit — `assert MODULES_BY_KEY[k].default_enabled is False for k in (…three keys…)`; (b) integration — with zero `module_settings` rows (assert the table is empty in the savepoint), finalise a case and assert GET /api/me/evaluations returns `{total:0, items:[]}`, POST /object and /acknowledge return 403, and `/api/dashboard/role-overview?scope=self` cards are `[]`.",
  },
  {
    id: "F6",
    severity: "MEDIUM",
    status: "VERIFIED (source read)",
    title:
      "No test ties `final_snapshot` content to the record; PDF integration tests only check `%PDF-` and byte stability, content tests use hand-written dicts, and one PDF test skips silently",
    location:
      "backend/tests/test_documents.py (`test_the_archived_pdf_is_hashed_and_is_a_real_pdf`, `test_summary_pdf_serves_stored_bytes_stably`: only `[:5] == b\"%PDF-\"`, `len(sha256)==64`, `r2.content == r1.content`) · backend/tests/test_pdf_security.py (`_snapshot_with()` hand-built; `test_pdf_export_returns_valid_pdf_for_hr` is `@pytest.mark.skipif(not weasyprint_available())`) · backend/app/services/snapshot.py:`build_final_snapshot`",
    whatBreaks:
      "The document that gets hashed is `render(record.final_snapshot)`. Nothing asserts that the snapshot's `full_name`, `evaluation_code`, `final_weighted_pct`, `recommendation`, `finalized_at`, `scores[*]` equal the record they were taken from. Byte-stability proves only that the *same* wrong bytes are served twice. Meanwhile the one HR-download test is skipped on any machine without pango, so a developer sees green while never rendering; test_documents.py on the same machine hard-fails — two files disagree on whether WeasyPrint is required.",
    howToReach:
      "Any regression in build_final_snapshot (field swap, wrong personnel join, dropped recommendation) ships in every new official document and is caught only by a human reading the PDF.",
    mutation:
      "snapshot.py: swap `\"final_weighted_pct\": …record.final_weighted_pct…` with `record.general_score_pct` (or set `\"recommendation\": None`). All of test_documents.py, test_pdf_security.py and test_pdf_table_layout.py stay green — the first two never read the snapshot's values, the third renders fixed dicts.",
    evidence: [
      "test_documents.py: `assert doc.pdf_bytes[:5] == b\"%PDF-\"` / `assert r2.content == r1.content` — no content assertion anywhere in the file.",
      "test_pdf_security.py: `def _snapshot_with(evidence_text: str) -> dict: return {\"evaluation_code\": \"EVL-0001\", …}` — every HTML-content test renders this literal.",
      "test_pdf_security.py: `@pytest.mark.skipif(not weasyprint_available(), reason=\"weasyprint native libs not installed\")` vs test_documents.py `_finalize` + `assert … status_code == 200` with no skip.",
    ],
    fix:
      "After `_finalize`, load `record.final_snapshot` and assert equality with the DB row for personnel fields, code, the three percentages, base/bonus, recommendation, evaluator username/label, and `len(scores) == number of indicators`; render the template from that real snapshot and assert `evaluation_code`, `full_name` and the Jalali `finalized_at` appear in the HTML. Make WeasyPrint availability a single explicit session fixture: fail (not skip) in CI, skip everywhere with one consistent rule.",
  },
  {
    id: "F7",
    severity: "MEDIUM",
    status: "PARTIALLY VERIFIED",
    title:
      "Threaded *reply* on a comment is declared 'deliberately more open'; no test says an HR user cannot reply on their own case, and every comment — replies included — is copied into the hashed PDF",
    location:
      "backend/tests/test_hr_comment_guard.py:`test_reply_path_unchanged` (docstring: «پاسخِ threaded عمداً بازتر است و باید همان بماند») and `test_hr_cannot_comment_on_own_record` (top-level only) · backend/app/services/snapshot.py:`build_final_snapshot` — `comments = db.scalars(select(EvaluationComment).where(EvaluationComment.evaluation_record_id == record.id)).all()` (no parent filter) · backend/app/api/routers/evaluations.py:`add_comment` (not read)",
    whatBreaks:
      "The N15 regression fixed HR writing a top-level `hr_review` comment into their own case. The reply branch of the same endpoint is exempted from the tests by design statement, and the snapshot serialises every `EvaluationComment` with its `stage` label, so a reply carries the same weight in the official document as a top-level comment. If `add_comment` applies `ensure_hr_may_handle` / `ensure_not_deciding_about_oneself` only when `parent_comment_id is None`, the closed door has a second, untested door beside it. Whether the guard covers replies is UNVERIFIED (router not readable within the cap); the test gap is verified.",
    howToReach:
      "HR user whose own case is `submitted`; another HR (or the supervisor) has left a top-level comment. Own-HR POSTs /api/evaluations/{own}/comments with `parent_comment_id` set. If 201, the reply is printed under «کامنت‌های مراحل بررسی» in the PDF.",
    mutation:
      "In `add_comment`, wrap the HR guards in `if payload.parent_comment_id is None:`. test_hr_comment_guard.py passes in full (`test_reply_path_unchanged` even encourages it). Copilot path: if a comment tool delegates to the endpoint, the same hole is reachable from chat.",
    evidence: [
      "test_hr_comment_guard.py `test_hr_cannot_comment_on_own_record` posts `{\"comment_text\": …}` only — no `parent_comment_id` variant.",
      "snapshot.py comments block: `{\"stage\": c.stage.value, \"commenter_user_id\": …, \"comment_text\": …} for c in comments` — replies are indistinguishable from top-level comments in the document.",
    ],
    fix:
      "Add `test_hr_cannot_reply_on_own_record` and `test_second_hr_cannot_reply_on_claimed_case` (expect 403). If replies are meant to be more open, they must at least keep the self-case and shield checks; document the exact relaxed rule in the test instead of 'unchanged'. Either exclude replies from the snapshot or mark them (`parent_comment_id`) so the PDF can render them as replies.",
  },
  {
    id: "F8",
    severity: "MEDIUM",
    status: "PARTIALLY VERIFIED",
    title:
      "The 'count people, not records' cohort rule is proven on three endpoints; `suppressed_avg` trusts whatever count the caller passes, so every other aggregation surface is a place the rule can silently revert",
    location:
      "backend/app/services/privacy.py:`suppressed_avg(value, count)` / `cohort_size(...)` · backend/tests/test_cohort_counts_people.py (covers `/api/dashboard/report/summary` by_org_unit, `/api/dashboard/overview` by_org_unit, `/api/dashboard/period-trend`) · uncovered by that file: per-indicator averages, indicator-by-unit drill-down, per-evaluator «الگوی نمره‌دهی من» (`/api/analytics/my-scoring`), executive per-site (`analytics.executive_overview`), person-vs-unit comparison · backend/app/services/… analytics call sites not read",
    whatBreaks:
      "The paired invariant here is `cohort_size` ⇄ *every* `suppressed_avg` call site. The helper cannot tell a record count from a people count. The regression test that closed the original leak (one person × five periods) exercises three of the surfaces; the README lists at least four more that publish averages. On any of those, passing `func.count()` re-publishes a single person's score as a 'unit average'.",
    howToReach:
      "HR (or, for role analytics, a unit supervisor) opens an uncovered report for a unit with one person evaluated in ≥5 periods; the average equals that person's score.",
    mutation:
      "In any uncovered analytics query, replace `cohort_size(EvaluationRecord.subject_personnel_id)` with `func.count()` as the value fed to `suppressed_avg`. test_cohort_counts_people.py and test_cohort_suppression.py stay green (the latter, by its own docstring in conftest, tests suppression with distinct people, where record count == people count).",
    evidence: [
      "privacy.py: `def suppressed_avg(value, count): if value is None or is_below_cohort(count): return None` — no notion of what `count` counts.",
      "test_cohort_counts_people.py hits exactly three URLs: `/api/dashboard/report/summary`, `/api/dashboard/overview`, `/api/dashboard/period-trend`.",
    ],
    fix:
      "Parametrise `test_one_person_many_periods_is_still_suppressed` over every endpoint that returns an `avg_*` (build the list from the router table, not by hand) and assert each row for the single-person unit is `None`. Structurally: make `suppressed_avg` take a `people: int` keyword only, and have `cohort_size` return a thin `PeopleCount` wrapper so a raw `func.count()` fails type-checking/ruff.",
  },
  {
    id: "F9",
    severity: "LOW",
    status: "VERIFIED (source read)",
    title:
      "CI runs `pytest -q` with no coverage and no order randomisation — 1035 is a count, not a coverage statement, and order dependence (F4) can never surface",
    location:
      ".github/workflows/ci.yml backend job: `- run: ruff check .` / `- run: pytest -q` · launcher job: `python -m pytest tools/tests -q` · frontend: `npm test`",
    whatBreaks:
      "There is no `--cov`, no threshold, no `pytest-randomly`. The findings above (untested signature block, untested `_get_record_or_404_for_update` lock, untested arg-taking tools) would all show up as uncovered lines in a coverage report; today nothing reports them. Fixed collection order also means committed leftovers from F4 always land in the same position, so the suite's greenness on a shared DB is reproducible but not meaningful.",
    howToReach:
      "Read the CI log: only pass/fail counts are printed.",
    mutation:
      "Delete a whole guard function that only the copilot path calls; if no test names it, CI stays green and nothing reports the drop.",
    evidence: [
      "ci.yml: `- run: pytest -q` — the complete backend test invocation.",
    ],
    fix:
      "Add `pytest-cov --cov=app --cov-fail-under=<current>` and `pytest-randomly` to requirements-dev and ci.yml (and mirror in scripts/ci-local.sh so `--check-drift` stays green); publish the HTML report as an artifact.",
  },
  {
    id: "F10",
    severity: "LOW",
    status: "VERIFIED (source read)",
    title:
      "Frontend list tests assert only on mocked `apiClient.get` call params with zero rows; row rendering is never exercised",
    location:
      "frontend/src/components/EvaluationList.test.tsx (all 7 cases use `mockPage()` → `items: []`; assertions are `expect(getMock.mock.calls…params)…`)",
    whatBreaks:
      "For URL→query translation this is the right oracle. But no test in the file renders an item, so the status label, the link target, the score column and any per-row conditional (the surface where a shielded result column once leaked) have no assertion. A regression that renders every row's `final_weighted_pct`, or links to the wrong route, is invisible to vitest.",
    howToReach:
      "HR queue with real items; any per-row rendering bug.",
    mutation:
      "In EvaluationList.tsx render `item.final_weighted_pct` unconditionally in every row, or change the row link to `/evaluations/${item.subject_personnel_id}`. All 7 tests pass.",
    evidence: [
      "`function mockPage(items: unknown[] = []) { return { data: { total: items.length, items } }; }` — called without arguments in every case.",
      "`expect(getMock.mock.calls[0]?.[1]?.params).toMatchObject({ status: \"deputy_approved\" })` — mock-call assertion pattern throughout.",
    ],
    fix:
      "Add one case with two items (one `finalized` with a score, one open) and assert the rendered cells and the `href` of each row; keep the params tests as they are.",
  },
];

export const verifiedCorrect: { area: string; detail: string }[] = [
  {
    area: "conftest.py isolation and environment pinning",
    detail:
      "`db_session` binds a sessionmaker with `join_transaction_mode=\"create_savepoint\"` on one connection and rolls back the outer transaction; app-level `commit()` becomes RELEASE SAVEPOINT. `NEXAHR_ENV_FILE=\"\"`, `ENABLE_SCHEDULER=false`, `BOOTSTRAP_ADMIN=false`, `_reset_rate_limiter` autouse, and `no_cohort_suppression` deliberately *not* autouse are all sound decisions with the right comments.",
  },
  {
    area: "Paired invariants in workflow.py",
    detail:
      "`IS_OPEN_RECORD = EvaluationRecord.status.in_(OPEN_STATUSES)` is derived, so it cannot drift. `hr_panel_is_shielded(record) = skips_hr_review(record) and status in OPEN_STATUSES` and `IS_SHIELDED_FROM_HR_PANEL = hr_review_skipped.is_(True) & IS_OPEN_RECORD` agree, including on a NULL `hr_review_skipped` (bool(None) is False; `is_(True)` is False).",
  },
  {
    area: "Timezone regression (the UTC-in-PDF bug)",
    detail:
      "test_org_timezone.py pins fixed instants (`2025-10-06T21:30Z` → «۱۴۰۴/۰۷/۱۵ ساعت ۰۱:۰۰») and monkeypatches `clock.now_local` for window tests; `test_jalali_filter_converts_iso_dates` was corrected to local time with an explicit note about the old locked-in bug. `core/clock.py` refuses an invalid ORG_TIMEZONE instead of falling back to UTC. No wall-clock-hour dependence found in test_org_timezone.py, test_self_assessment_rules.py (uses `today_local()` with ≥1-day margins) or test_scheduled.py (±5-day margins on `stage_entered_at`).",
  },
  {
    area: "Module switches — explicit off-state tests",
    detail:
      "test_module_switches.py covers self_assessment (submission and invitation), objections, acknowledgement, visibility (a *read* switch, asserted as `{total:0, items:[]}` while HR still sees the record), overview cards under both switches, role_analytics (both views), periods (creation refused, closing still allowed). Only the *default* path is missing (F5).",
  },
  {
    area: "HR comment guard (N15) — HTTP path",
    detail:
      "test_hr_comment_guard.py covers own case (GET 403 ⇒ POST 403 with «خودِ شما»), HR-unit teammate while open (shield), first comment claims the seat, second HR refused on a claimed case, comment-not-stricter-than-approval symmetry, deputy seat still enforced on a no-deputy chain. Solid; only the reply branch is open (F7).",
  },
  {
    area: "Copilot write switch and prompt-context scoping",
    detail:
      "`test_write_switch_off_blocks_every_mutating_tool` treats any non-403 outcome — including argument validation errors — as an escape, which proves `allow_writes` is checked *before* argument parsing. `test_no_role_sees_more_in_the_prompt_than_in_the_ui` is parametrised over every `UserRole` and uses `/api/personnel` as the oracle rather than a hand list; the positive branch guards against 'nobody sees anything'.",
  },
  {
    area: "CEO-direct chain tests",
    detail:
      "test_ceo_only_chain.py asserts registration with both middle seats NULL, `scored_by == \"ceo\"`, HR stage retained (`hr-approve` → `deputy_approved`, then `ceo-finalize`), outsiders/deputy/HR cannot submit (403/404), CEO return goes to `draft` and can be resubmitted, and `final_weighted_pct` is computed on submit.",
  },
  {
    area: "Document archival and public verify",
    detail:
      "documents.archive_final_pdf uses `begin_nested()` and falls back to `get_document` on IntegrityError; test_documents.py reproduces the race by blinding `get_document` once and asserts 200 + exactly one document. Verify endpoint rejects the sequential `EVL-` code (404), returns `document_ready: False` + empty sha256 before archival and a 64-char hash after.",
  },
  {
    area: "Cohort-counts-people regression",
    detail:
      "test_cohort_counts_people.py forces `min_cohort_size=5` locally, and asserts 1 person × 5 records suppressed, 4 people × 8 records suppressed, 5 people published, on three endpoints, while `count` stays the record count. `privacy.cohort_size` is `count(distinct subject_personnel_id)`.",
  },
  {
    area: "Launcher tests (tools/tests/test_ports.py)",
    detail:
      "Behavioural and stubbed at real seams: netstat/netsh parsing with LISTENING vs ESTABLISHED, administered `*` ranges, reversed ranges ignored; `choose()` never kills a stranger (`assert killed == []`), reclaims its own leftover and reuses the port, moves on for Windows-reserved ranges without an owner lookup, and the empty-root guard (`\"\" in haystack`) is pinned.",
  },
  {
    area: "CI shape",
    detail:
      "ci.yml runs the e2e-api scenario as a job (with `alembic upgrade head` + `setup_e2e.py` + `run_e2e.sh --api-only`), uses fresh Postgres 16 service containers, runs `ruff check .` (not `ruff check app`) and `ruff check tools`, and cancels superseded runs except on main.",
  },
];

export const couldNotCheck: { item: string; why: string }[] = [
  {
    item: "RULE 1 — running scripts/ci-local.sh (backend ruff+pytest, launcher, frontend oxlint/vitest/tsc/build, e2e) and `--check-drift`",
    why: "This environment has no shell, no repository checkout and no PostgreSQL. Nothing was executed. Every finding is a source read and is labelled UNVERIFIED with respect to execution; 'VERIFIED (source read)' means the quoted lines were read at main@95c5433.",
  },
  {
    item: "backend/tests/test_audit_fixes.py beyond ≈L230 (M-7 `af_race_*`, M-8, M-10 bodies)",
    why: "Fetch cap of ~10 KB per file; file is 32.5 KB / 769 lines. The pollution mechanism (second engine + commit) is inferred from the header imports and the nature of the M-7 claim; the exact rows left behind are not confirmed.",
  },
  {
    item: "backend/app/api/routers/evaluations.py (`add_comment`, `_get_record_or_404_for_update`), backend/app/services/workflow.py past the TRANSITIONS table, backend/app/services/evaluation.py `compute_result`, analytics call sites of `suppressed_avg`",
    why: "Each exceeds the fetch cap; only heads were readable. F2's mutation target and F7's guard placement are therefore stated as mutations the *tests* cannot catch, not as confirmed source defects.",
  },
  {
    item: "backend `compute_result` ⇄ frontend `computePreview` drift",
    why: "`compute_result` was cut off at the cap and the frontend file could not be located from the truncated tree listing (`frontend/src/utils` holds only dates/jalali/password). Not compared.",
  },
  {
    item: "Copilot parity tests (test_ai_workflow_parity.py, test_ai_people_parity.py, test_ai_framework_parity.py) and services/ai/tools/*.py",
    why: "Not read. F3 states what the sweep proves; whether specific arg-taking tools have their own negative tests is unknown.",
  },
  {
    item: "The last test in test_module_switches.py ('هر کلیدِ ماژول باید دستِ‌کم یک‌جا در سرور خوانده شود') and the module resolver's no-row fallback",
    why: "Beyond the cap for the test file; resolver module not read. F5 is about the missing default-state assertion, which is verified from the visible tests and helpers.",
  },
  {
    item: "`uq_open_evaluation_per_personnel` vs the Python 'one open evaluation per person' assumption; `ensure_module_enabled` reachability from every copilot tool; `require_module` wiring",
    why: "Would require reading the router bodies and tool modules in full; not possible within the cap and step budget.",
  },
  {
    item: "Frontend: 44 of 45 vitest files; launcher: test_database.py, test_maintenance.py, test_session.py, test_setup.py; e2e/e2e_api_test.py and mock_llm.py; scripts/ci-local.sh",
    why: "Budget. Only EvaluationList.test.tsx and tools/tests/test_ports.py were read as samples.",
  },
];

export const methodology: string[] = [
  "Source was read at commit 95c5433 (main) through raw.githubusercontent.com; each fetch was capped at roughly 10 KB, so files longer than that are reported as head-only.",
  "Files read in full: tests/conftest.py, tests/helpers.py, tests/test_documents.py, tests/test_org_timezone.py, tests/test_scheduled.py (most), tests/test_pdf_security.py, tests/test_ceo_only_chain.py (most), tests/test_module_switches.py (most), tests/test_employee_self_view.py (most), tests/test_self_assessment_rules.py (most), tests/test_cohort_counts_people.py, tests/test_ai_security.py (most), tests/test_hr_comment_guard.py, tests/test_workflow_concurrency.py, app/core/modules.py, app/core/clock.py, app/services/documents.py, app/services/snapshot.py, app/services/privacy.py, app/templates/evaluation_summary.html, .github/workflows/ci.yml, tools/tests/test_ports.py, frontend/src/components/EvaluationList.test.tsx.",
  "Files read head-only: tests/test_audit_fixes.py (≈230/769 lines), app/services/workflow.py, app/services/evaluation.py.",
  "Severity reflects the consequence of the untested/locked-in behaviour on the product's official output and authorisation model, not the effort of the fix.",
];
