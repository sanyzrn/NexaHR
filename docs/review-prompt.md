# NexaHR multi-angle review prompt — v2

Give each agent **one** angle. Paste the whole block below and fill the
`Your angle:` and `Mode:` lines from the lists at the end.

**What changed from v1:** counts and facts refreshed to the post-audit tree; a
`Mode:` line so an angle can be asked for improvement proposals and not only
defects; and a new `ALREADY FIXED` section — the single most important
addition, because two audit rounds have closed ~60 findings and without that
list you will pay to have them re-reported.

---

```
Repo: https://github.com/sanyzrn/NexaHR
Branch: main  (cut your own branch off it — several agents on one branch
tangle the history)
Your angle: .....
Mode: .....      (either `defects` or `defects + elevation` — see MODE below)

NexaHR is an HR performance-evaluation system for a single Iranian
organization. Persian-first, RTL, no paid third-party services.

  backend/    FastAPI + SQLAlchemy 2 + PostgreSQL 16, Alembic (57 migrations),
              ~27.8k lines. Async only where it must be.
  frontend/   React 19 + TypeScript + Vite + Tailwind 4, ~29k lines.
  tools/      The dev-environment launcher (pure stdlib, has its own tests).
  e2e/        A headless end-to-end scenario with a mock OpenAI-compatible
              server (e2e/mock_llm.py). No real model key needed.

The product is a four-seat approval chain over an evaluation record:
unit supervisor -> HR -> deputy -> CEO. Three chain shapes are legal and all
three are live: the full chain, the "manager path" (deputy scores instead of
the supervisor), and "CEO-direct" (no supervisor, no deputy). The final act
produces a hashed, QR-verifiable PDF that is the organization's official
employment document. There is also an in-app AI copilot that can propose and,
after explicit confirmation, execute writes through the same API.

Do a real review. A summary of the README is worthless to me. So is a
restatement of the doc-comments — see rule 2, it is the most important one.

MODE

`Mode: defects` — hunt bugs only. Rule 5 applies with no exceptions: if you
cannot say how something fails, drop it. This is the right mode for anything
that guards money, access, or the legal document.

`Mode: defects + elevation` — do the defect hunt exactly as above AND add a
fifth output section proposing improvements. Elevation proposals live under a
different standard from findings, and both standards are strict:

  * A proposal names the user-visible outcome first ("HR cannot answer 'why
    is this case stuck' without opening it"), then the change, then the cost
    in files touched. A proposal that leads with a technology is rejected.
  * It must fit this product: one Iranian organization, Persian-first, no
    paid third-party service, single-instance PostgreSQL deployment. "Add
    Elasticsearch" is not a proposal here.
  * Say what it would break. Anything touching `snapshot.py`, the score math,
    or the approval chain must state the migration and the effect on already
    finalized records — those are signed employment documents.
  * Rank by (value to a real HR user) / (files touched). Cap at 6.
  * Never dress a proposal as a finding to raise its severity. Findings are
    things that are wrong; proposals are things that are absent.

RULES

1. RUN IT.
     cd backend && python3 -m venv .venv && . .venv/bin/activate
     pip install -r requirements-dev.txt
     createdb nexahr_test   # or: psql -c "CREATE DATABASE nexahr_test OWNER nexahr;"
     cd .. && scripts/ci-local.sh
   `scripts/ci-local.sh all` runs exactly what CI runs, all ten commands:
   backend (ruff + 1131 pytest), launcher (ruff + 89 pytest), frontend
   (oxlint + 285 vitest + tsc/build), `alembic upgrade head`, and the e2e API
   scenario. `--check-drift` proves the script has not diverged from
   .github/workflows/ci.yml.
   PostgreSQL is required — there is no SQLite fallback; tests use real
   partial indexes, triggers and advisory locks.
   Report anything you could not run and why. A finding you never executed
   must be labelled UNVERIFIED.

2. READ THE CODE THAT RUNS, NOT THE COMMENT ABOVE IT.
   This repo has unusually long, confident Persian doc-comments that assert
   design intent and history. They are often the best documentation you will
   find. They have also been provably wrong, repeatedly, and always in the
   same direction: the comment describes the guard the author *meant* to
   build. Real examples already found and fixed:

     * A module-switch guard (`require_module`) existed in api/deps.py with a
       full docstring — and was wired to zero routes. Every switch in the
       admin panel was cosmetic.
     * A tool-registration check returned True for any tool that declared no
       capabilities and no roles — default-open, in a codebase whose comments
       say fail-closed everywhere.
     * `add_comment` in api/routers/evaluations.py carried the stage table but
       never called `ensure_hr_may_handle`. An HR user who got 403 trying to
       *read* their own evaluation could still write an official `hr_review`
       comment into it — a comment that gets printed into the hashed PDF.
     * Cohort suppression (services/privacy.py) counted evaluation *records*
       where its own docstring said "people". One person over five periods
       cleared a five-person threshold and their score was published as a
       "unit average".
     * A test asserted the UTC wall-clock in the legal PDF, which *locked in*
       an off-by-one-day bug rather than catching it.

   So: for every guarantee a comment claims, find the line that enforces it
   or report that nothing does. Treat a docstring as a hypothesis.

3. CHECK BOTH PATHS FOR EVERY GUARD.
   This is the repo's signature defect class. Endpoint functions carry their
   authorization in `Depends(...)`. The copilot (services/ai/tools/*.py) used
   to call services and models directly, so those `Depends` never ran and
   every guard was half-present. Most tools now delegate to the endpoint
   function with a real Pydantic payload — but verify, do not assume. A guard
   that lives in a `Depends` and is not reachable from the copilot path is a
   finding, and vice versa.
   The same applies to the deliberate inverse: `ensure_module_enabled` is a
   plain function called inside endpoint bodies *on purpose*, so that the
   copilot passes through it too. Do not "fix" that into a `Depends`.

4. CHECK PAIRED INVARIANTS FOR DRIFT.
   Several rules are necessarily written twice, and the pairs must agree.
   Divergence here has already shipped a leak. Known pairs:
     * `workflow.hr_panel_is_shielded()` (row check) and
       `workflow.IS_SHIELDED_FROM_HR_PANEL` (query filter).
     * `IS_OPEN_RECORD` / `OPEN_STATUSES`.
     * backend `compute_result` and frontend `computePreview`.
     * `services/privacy.cohort_size` and every `suppressed_avg` call site.
     * The DB partial unique index `uq_open_evaluation_per_personnel` and the
       Python-side "one open evaluation per person" assumption. Note the index
       covers only *open* records — a person accumulates finalized ones.
     * `models/chain.py` (`SEAT_ROLE`/`SEAT_LABEL`/`SEAT_ORDER`,
       `scorer_field`, `hr_finalizes`) and `services/workflow.TRANSITIONS`.
       chain.py exists only to break an import cycle; workflow re-exports it.
       A chain shape that chain.py admits and TRANSITIONS has no path for is a
       stuck record.
     * `services/audit_events.EVENT_LABELS` (81 entries) and the frontend
       `AUDIT_EVENT_LABELS`. These are locked together by
       `tests/test_audit_event_labels.py` three ways — verify the lock still
       covers every event actually written, not just every key declared.
     * The snapshot version constant, the writer, and every reader. Version 6
       is current (`signatories` at 5, `evaluator.display_name` at 6).
       A reader that assumes the newest shape will misread a v4 document that
       is already signed and archived.
   Find pairs I have not listed, and check them.

5. EVERY FINDING NEEDS: file:line + what breaks + a concrete path to reach it
   (role, inputs, state -> wrong result) + the fix. No "consider...", no
   style preferences, no "might be". If you cannot say how it fails, drop it.
   Persian identifiers and comments are normal here and are not findings.

6. SAY WHAT IS CORRECT TOO. Which risky areas you checked and found sound is
   as useful to me as the defects. Name them specifically.

7. RANK BY SEVERITY, CAP AT 10. Ten real bugs beat forty maybes. I verify
   every claim against the source, so a false positive costs me more than a
   miss.

ALREADY DECIDED — do not re-report these as findings

  * The login page reveals whether a username exists. The owner accepted this
    trade-off explicitly, in writing, after being warned.
  * `employee_evaluation_visibility` gates the *server-side read*, not just
    the UI. Decided and kept deliberately.
  * `hr-handover` lets any HR user take a case from any other. There is no
    "HR supervisor" role yet; the audit trail is the control. Documented.
  * `backend/.env` sets `MIN_COHORT_SIZE=1` and `SEED_DEMO_DATA=true` for the
    demo environment. Tests do not read that file (`NEXAHR_ENV_FILE=""` in
    tests/conftest.py). Both are intentional.
  * In `analytics.executive_overview`, the per-site average is weighted by
    record count on purpose (only record weighting reconstructs the true
    mean); only the suppression threshold counts people.
  * Rate-limit counters are in-process unless `RATE_LIMIT_STORAGE_URI` is
    set. Known, documented, single-instance deployment.
  If you believe one of these is wrong anyway, argue it as a *design*
  objection in the Verdict — not as a bug.

ALREADY FIXED — do not re-report; if you find one, it is a REGRESSION

Two audit rounds closed roughly sixty findings. Every item below was a real
bug, was fixed, and has a test. If your reading of the code says one of these
is still broken, that is a *regression* and is the most valuable thing you can
hand me — but say so explicitly, with the file:line that proves it, and do not
file it as a new finding.

  Guards that existed on one path only
  * `require_module` is now wired; module switches gate real writes. The
    in-body `ensure_module_enabled` form is deliberate (rule 3).
  * `add_comment` now calls the HR handling guard, so an `hr_review` comment
    cannot be written by an HR user who cannot read the case.
  * `resolve_objection` and the copilot's scheme/indicator/role-overview
    tools now pass the same module and capability gates as the UI path.
  * `revoke_all_for_user` gets a real session in all three copilot tools.
  * Being the *subject* of an evaluation is now separate from having the
    `employee` role — every role has a personal report card.

  Score, document, and time
  * Bonus points are clamped by the scheme cap AND by `100 - base_pct`, and
    the *applied* value (not the raw one) is what reaches the hashed document.
  * `snapshot` builds `signatories` from the case's real seats, so a case
    without a deputy no longer prints an empty signature line.
  * `single_decider` recognises CEO-direct, so one person does not sign twice.
  * The official PDF has an explicit `Vazirmatn Latin` family; Latin glyphs
    no longer fall through to DejaVu mid-word (worst case was Jalali dates:
    digits from one font, the slash from another).
  * `core/clock.py` owns the UTC/local boundary. `ORG_TIMEZONE` defaults to
    Asia/Tehran and every day-boundary filter goes through `local_day_start`.

  Chain shapes
  * CEO-direct (no supervisor, no deputy) has a complete path: HR performs
    the final approval when neither middle seat is filled and HR review is
    not skipped (`hr_finalizes`).
  * An HR-unit member's own case skips the HR stage (`hr_review_skipped`),
    and the deadlock that created — including HR being unable to separate a
    member of its own unit at all — is fixed via `cancel_on_separation` and
    `bypasses_hr_unit_shield`.
  * Role change and deactivation are blocked while the account holds an open
    case; separation notifies HR with the list of orphaned seats.

  Privacy, concurrency, cost
  * Cohort suppression counts distinct people (`privacy.cohort_size`), not
    records.
  * `login_guard.record_failure` uses `on_conflict_do_update` + `FOR UPDATE`;
    concurrent failures can no longer under-count toward the lockout.
  * `stage_stats` is capped by `stage_stats_window_days`.
  * The Excel export builds the workbook before `commit` and eager-loads its
    relations.
  * Persian sorting uses `fa-x-icu` with ی/ك normalization, server-side for
    paginated lists and client-side for fully-loaded tables.

  If you want the full list with file:line, read `docs/review-findings.md`,
  `docs/nafashr-port-candidates.md` and `docs/nafashr-reported-bugs-check.md`
  in the repo. Read them *after* forming your own view, not before — they will
  anchor you.

OUTPUT (exactly these sections, nothing else)

## Verdict — 3 lines
## Findings — severity | file:line | what breaks | how to reach it | fix
## Verified correct
## Could not check, and why
## Proposals — only in `Mode: defects + elevation`, max 6, ranked
```

---

## Angles — one per agent

Paste one verbatim into `Your angle:`.

**1 — authz & session**
> authorization and sessions — the two-axis model (`UserRole` for chain
> position vs `Capability` for administrative power), row-level visibility
> (`scope_evaluations_for_role`, `_can_view_personnel`), JWT + `token_version`
> revocation, refresh cookies, forced password change, account lockout,
> per-IP rate limits, and what `/metrics`, `/docs` and the public
> `/api/verify/{token}` endpoint expose. Start from `api/deps.py`,
> `services/authorization.py`, `services/self_evaluation.py`.

**2 — workflow state machine**
> the approval chain — `services/workflow.py` (`TRANSITIONS`,
> `ensure_transition_allowed`, `apply_transition`) against all three legal
> chain shapes. Returns, cancellation, HR claim/handover, stage reassignment,
> the submission window and HR extensions. Every guard must hold for the
> full chain, the manager path and CEO-direct — the third shape is the one
> that has broken five times.

**3 — scoring & the legal document**
> score computation and the final document — `compute_result`, per-indicator
> weights, absent-section redistribution, scheme versioning and mid-cycle
> activation, bonus rules, `services/snapshot.py`, `services/documents.py`,
> `services/pdf.py`, the hash and the QR verification path. This PDF is an
> employment document; a wrong number here reaches a person's file.

**4 — AI copilot**
> the copilot — `services/ai/` end to end: tool registration and the
> capability/role/`guarded_inline` declaration, `orchestrator.py`, the
> confirmation flow (`confirmations.py`), what `context.py` puts in the
> prompt and whether it respects each role's visibility scope, prompt
> injection through personnel names and uploaded spreadsheets, spend limits,
> and the audit split between `ai_tool_invoked` and `ai_action_confirmed`.
> Rule 3 is your rule.

**5 — privacy & disclosure**
> what leaks — cohort suppression (`services/privacy.py`) at every call
> site, the HR-panel shield over HR-unit employees' own files,
> self-assessment visibility, who can read whose evaluation, PII in the audit
> log / Excel exports / notification bodies / server logs, and the
> employee-facing views. Assume the reader is a curious employee with a valid
> account, not an anonymous attacker.

**6 — data integrity & migrations**
> the database — 58 Alembic migrations replayed from empty, `alembic check`
> for model/schema drift, enum values that exist in Python but not in the DB
> (or the reverse), the partial unique indexes, the append-only audit trigger
> and `services/audit.py`'s hash chain, cascade/orphan behaviour on delete,
> and every place a status or enum is compared as a string.

**7 — concurrency & scheduling**
> races — `with_for_update` coverage on every read-decide-write path,
> `pg_advisory_xact_lock` use in the audit chain, `services/scheduler_lock.py`
> and the nightly sweeps (`services/scheduled.py`), the outbound delivery
> queue and its retry/backoff, double-submit and double-confirm, and
> transaction boundaries around `db.commit()` in endpoint bodies.

**8 — Persian, RTL, Jalali & time**
> localization — `core/clock.py` and the UTC/local boundary (storage in UTC,
> "today" and display in `ORG_TIMEZONE`), Jalali conversion in the PDF,
> Persian digits, date-range filters against `timestamptz` columns, logical
> CSS properties vs physical ones (`left`/`right` leftovers), font loading
> and shaping in the PDF, and message/label completeness. There is no i18n
> catalogue — Persian is hard-coded — so check for stray English reaching the
> user and for raw enum values printed instead of labels.

**9 — frontend correctness & accessibility**
> the React app — React Query cache boundaries and cross-user leakage on
> shared machines, `PermissionsContext` fail-closed module gating, focus
> traps and keyboard paths in every overlay, form validation matching the
> server's rules, error and empty states, touch-target size and contrast in
> both themes, and the PWA/service-worker cache. `frontend/src/`.

**10 — performance**
> cost — N+1 queries (the evaluation list and dashboard aggregates are the
> suspects), missing indexes for the filters that actually ship, the
> aggregate endpoints in `api/routers/{dashboard,analytics,reports}.py`,
> Excel/PDF generation on the request path, and frontend bundle size and
> re-render behaviour on the heavy pages.

**11 — test quality (mandatory — highest value here)**
> the test suite itself — 109 backend files (1131 tests), 47 frontend files
> (285), 89 launcher tests. Find tests that *cannot fail*: assertions on
> mocks instead of behaviour, `assert response.status_code == 200` with no
> assertion on the body, tests that lock in a bug rather than catch it (one
> did exactly this with a UTC timestamp in the legal PDF), tests that pass
> only because of state committed by another test (the `af_race_*` rows in
> `test_audit_fixes.py` commit outside the rollback and pollute the shared
> test database), tests whose result depends on the wall-clock hour, and
> `pytestmark = usefixtures("employee_view_on")` hiding a default-off module.
> Then name the highest-risk code paths that have no test at all. For each
> claim, show the mutation you would make to the source that the suite would
> not catch.

---

## Which mode for which angle

`defects` only — the areas where a wrong answer reaches a person's file, and
where a proposal would be a distraction:

> 2 workflow · 3 scoring & document · 6 database · 7 concurrency ·
> 11 test quality

`defects + elevation` — the areas where the honest answer is "it works, and it
is thin":

> 1 authz · 5 privacy · 8 Persian/RTL/time · 9 frontend · 10 performance

Angle **4 (AI copilot)** does not use this file. It has its own prompt:
`docs/review-prompt-ai-elevate.md`. The generic frame caps findings at 10 and
forbids "consider…", which is right for a chain guard and wrong for a
subsystem whose main problem is that it is *shallow*, not that it is broken.

## How to dispatch

**Do not send all eleven at once.** Eleven parallel agents produce eleven
reports, three of which carry the same finding, and you verify it three
times. Suggested order:

**Wave 1 (four agents, mostly non-overlapping):**
11 test quality (`defects`) · 2 workflow (`defects`) ·
4 AI copilot (its own prompt) · 8 Persian/RTL/time (`defects + elevation`)

These are four largely separate areas with the highest chance of *new*
findings. Test quality goes first on purpose: if the suite is blind somewhere,
every other angle needs to know where it cannot lean on green.

**Wave 2 (after reading wave 1):**
1 authz (`+ elevation`) · 5 privacy (`+ elevation`) · 6 database (`defects`) ·
7 concurrency (`defects`)

These overlap with each other and with wave 1 (authz and privacy are nearly
the same boundary). Add wave 1's confirmed findings to `ALREADY DECIDED` or
`ALREADY FIXED` in their prompt so they are not reported twice.

**Wave 3 (optional):**
3 scoring & document (`defects`) · 9 frontend (`+ elevation`) ·
10 performance (`+ elevation`)

Angle 3 needs the deepest domain knowledge; if you only have one strong agent
left, give it to 3, not to 10.

**Three things that raise report quality:**

* Tell them to work from `main` and cut their own branch — several agents on
  one branch will tangle the history.
* Every finding you confirm, add to `ALREADY FIXED` before the next wave.
  That list is the only thing preventing duplicate reports, and after two
  audit rounds it is now doing most of the work.
* Ask for the mutation, not the opinion: "show me the one-line change to the
  source that your finding predicts, and the test that fails." An agent that
  cannot produce it usually has not read the code that runs.
