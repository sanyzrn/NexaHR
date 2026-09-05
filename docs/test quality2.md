\## Verdict — 3 lines

High unit-test counts (\~1,400 tests across backend, launcher, and frontend) mask critical test-isolation leaks, empty HTTP body assertions, and mock-only tests that allow severe regressions to pass CI silently.

Significant invariant drift between database partial indexes, SQL queue filters, and frontend score-preview calculations creates live vulnerabilities in workflow shielding, multi-period initialization, and legal document generation.

The AI copilot tool path bypasses route-level authorization dependencies, while module fixtures and UTC-locked PDF tests entrench production defects instead of catching them.



\## Findings — severity | file:line | what breaks | how to reach it | fix



\### 1. CRITICAL | `backend/tests/test\_audit\_fixes.py:74` \[UNVERIFIED]

\* \*\*What breaks:\*\* Concurrency and advisory lock race tests issue raw `db.commit()` calls across separate connection threads, writing rows prefixed with `af\_race\_\*` directly to PostgreSQL outside the transaction rollback fixture. These rows permanently pollute `nexahr\_test`, contaminating subsequent test queries and masking data-leak bugs. Tests that query total record counts or assert deterministic queue contents pass only when run in sequence after this file.

\* \*\*How to reach it:\*\*

&#x20; \* \*Role:\* CI test runner / Pytest.

&#x20; \* \*Inputs:\* Run `pytest backend/tests/test\_audit\_fixes.py` followed by `pytest backend/tests/api/test\_analytics.py` (or run suite with randomized execution ordering).

&#x20; \* \*State:\* Direct DB commits bypass SQLAlchemy `SAVEPOINT` rollbacks configured in `conftest.py`.

&#x20; \* \*Wrong result:\* Leaked `af\_race\_\*` personnel and evaluation records persist in the shared database, altering cohort counts and causing spurious test passes or order-dependent failures.

\* \*\*Mutation suite misses:\*\* In `backend/services/analytics.py`, mutate `get\_unit\_summary` to execute `select(Personnel)` without department filtering. Tests asserting non-empty lists pass because uncleaned `af\_race\_\*` rows remain in the table.

\* \*\*Fix:\*\* Add an explicit teardown block to `backend/tests/test\_audit\_fixes.py`:

&#x20; ```python

&#x20; @pytest.fixture(autouse=True)

&#x20; def cleanup\_race\_records(db\_engine):

&#x20;     yield

&#x20;     with db\_engine.begin() as conn:

&#x20;         conn.execute(text("DELETE FROM evaluations WHERE id::text LIKE 'af\_race\_%'"))

&#x20;         conn.execute(text("DELETE FROM personnel WHERE id::text LIKE 'af\_race\_%'"))

&#x20; ```



\---



\### 2. CRITICAL | `backend/services/ai/tools/workflow.py:112` vs `backend/api/routers/evaluations.py:185` \[UNVERIFIED]

\* \*\*What breaks:\*\* Authorization bypass in the AI Copilot execution path. The API router enforces seat authority via `Depends(require\_seat\_authority)`, but the Copilot tool `advance\_evaluation\_tool` invokes `workflow.advance\_evaluation()` directly without verifying that the requesting user occupies the corresponding seat in the active approval chain.

\* \*\*How to reach it:\*\*

&#x20; \* \*Role:\* `unit\_supervisor`.

&#x20; \* \*Inputs:\* User confirms Copilot proposal: `{"tool": "advance\_evaluation", "arguments": {"evaluation\_id": 42, "next\_stage": "ceo\_review"}}`.

&#x20; \* \*State:\* Evaluation #42 is currently at `deputy\_review`. The authenticated user is a unit supervisor, not a deputy.

&#x20; \* \*Wrong result:\* The Copilot advances the evaluation to `ceo\_review`, bypassing deputy review and approval entirely.

\* \*\*Mutation suite misses:\*\* In `backend/services/ai/tools/workflow.py`, omit seat verification before delegating to `workflow.advance\_evaluation`. The suite passes because Copilot tests mock permissions or execute with admin fixtures.

\* \*\*Fix:\*\* Require Copilot tool executors to validate the user's role against the active chain shape and stage matrix:

&#x20; ```python

&#x20; def advance\_evaluation\_tool(db: Session, user: User, evaluation\_id: int, next\_stage: str):

&#x20;     evaluation = get\_evaluation\_or\_404(db, evaluation\_id)

&#x20;     ensure\_user\_holds\_seat(user, evaluation.chain\_shape, evaluation.status)

&#x20;     return workflow.advance\_evaluation(db, evaluation, next\_stage, actor=user)

&#x20; ```



\---



\### 3. HIGH | `backend/services/workflow.py:142` vs `backend/models/evaluation.py:88` \[UNVERIFIED]

\* \*\*What breaks:\*\* Paired invariant drift between row-level access check `workflow.hr\_panel\_is\_shielded()` and SQL query filter `workflow.IS\_SHIELDED\_FROM\_HR\_PANEL`. The row check shields evaluations where `chain\_shape == "ceo\_direct"` or `personnel.department\_id == HR\_DEPT\_ID`, but the SQL clause `IS\_SHIELDED\_FROM\_HR\_PANEL` checks only `chain\_shape == 'ceo\_direct'`, omitting the HR department exclusion in queue queries.

\* \*\*How to reach it:\*\*

&#x20; \* \*Role:\* `hr\_specialist`.

&#x20; \* \*Inputs:\* `GET /api/evaluations?stage=hr\_review`.

&#x20; \* \*State:\* An HR department employee is being evaluated under the standard four-seat chain.

&#x20; \* \*Wrong result:\* The evaluation appears in the HR specialist's worklist. Clicking the record triggers `hr\_panel\_is\_shielded()` on the detail endpoint and throws a 403, causing UI pagination mismatches and leaking record existence.

\* \*\*Mutation suite misses:\*\* In `backend/services/workflow.py`, strip the department check from `IS\_SHIELDED\_FROM\_HR\_PANEL`. The suite passes because unit tests test `hr\_panel\_is\_shielded()` against isolated objects without asserting on SQL query results containing HR department records.

\* \*\*Fix:\*\* Unify both checks into a single SQLAlchemy `@hybrid\_property`:

&#x20; ```python

&#x20; @hybrid\_property

&#x20; def is\_shielded\_from\_hr(self) -> bool:

&#x20;     return self.chain\_shape == "ceo\_direct" or self.personnel.department\_id == HR\_DEPT\_ID



&#x20; @is\_shielded\_from\_hr.expression

&#x20; def is\_shielded\_from\_hr(cls):

&#x20;     return (cls.chain\_shape == "ceo\_direct") | (cls.department\_id == HR\_DEPT\_ID)

&#x20; ```



\---



\### 4. HIGH | `backend/tests/test\_pdf.py:92` \[UNVERIFIED]

\* \*\*What breaks:\*\* The test asserts that the legal PDF contains a UTC timestamp formatted via `datetime.utcnow()`, locking in an off-by-one-day timestamp bug on official legal documents instead of enforcing Iran Standard Time (`Asia/Tehran`, UTC+03:30).

\* \*\*How to reach it:\*\*

&#x20; \* \*Role:\* CEO approving an evaluation.

&#x20; \* \*Inputs:\* Finalize evaluation at 21:30 UTC on 1403-06-15 (01:00 AM Tehran time on 1403-06-16).

&#x20; \* \*State:\* PDF document is generated, hashed with SHA-256, and sealed.

&#x20; \* \*Wrong result:\* The PDF stamps the legal creation date as 1403-06-15 (UTC date) rather than 1403-06-16 (official organization calendar date). If the PDF generator is corrected to use `ZoneInfo("Asia/Tehran")`, `test\_pdf.py` fails.

\* \*\*Mutation suite misses:\*\* In `backend/services/pdf.py`, mutate generation time from `datetime.now(ZoneInfo("Asia/Tehran"))` to `datetime.now(timezone.utc)`. The test suite passes because the assertion expects UTC time.

\* \*\*Fix:\*\* In `backend/services/pdf.py`, enforce `datetime.now(ZoneInfo("Asia/Tehran"))`. In `backend/tests/test\_pdf.py`, freeze time at 21:30 UTC using `freezegun` or `time\_machine` and assert that the Persian date in the rendered PDF matches the Tehran calendar day (`day + 1`).



\---



\### 5. HIGH | `backend/tests/api/test\_employee\_view.py:14` \[UNVERIFIED]

\* \*\*What breaks:\*\* Module-level fixture `pytestmark = pytest.mark.usefixtures("employee\_view\_on")` forces `employee\_evaluation\_visibility` to be ON for all tests in the file. Zero tests verify the production default state where this module is OFF, masking missing guards and unhandled 500 errors.

\* \*\*How to reach it:\*\*

&#x20; \* \*Role:\* `employee`.

&#x20; \* \*Inputs:\* `GET /api/evaluations/my-latest`.

&#x20; \* \*State:\* Fresh deployment where module switches are in default-off state.

&#x20; \* \*Wrong result:\* If `ensure\_module\_enabled(db, "employee\_evaluation\_visibility")` is missing or raises an unhandled exception, unauthorized employees can view in-flight evaluations or receive 500 errors. The suite never exercises this branch.

\* \*\*Mutation suite misses:\*\* In `backend/api/routers/evaluations.py`, delete the `ensure\_module\_enabled(db, "employee\_evaluation\_visibility")` call inside `get\_my\_latest\_evaluation`. `test\_employee\_view.py` passes 100% of tests.

\* \*\*Fix:\*\* Remove `pytestmark` from the top of the file and write explicit test cases for both states:

&#x20; ```python

&#x20; def test\_employee\_view\_default\_off\_returns\_403(client, employee\_token):

&#x20;     res = client.get("/api/evaluations/my-latest", headers=employee\_token)

&#x20;     assert res.status\_code == 403

&#x20;     assert res.json()\["detail"] == "MODULE\_DISABLED"



&#x20; def test\_employee\_view\_when\_enabled\_returns\_200(client, employee\_token, employee\_view\_on):

&#x20;     res = client.get("/api/evaluations/my-latest", headers=employee\_token)

&#x20;     assert res.status\_code == 200

&#x20; ```



\---



\### 6. HIGH | `backend/services/scoring.py:104` vs `frontend/src/features/evaluations/utils/computePreview.ts:48` \[UNVERIFIED]

\* \*\*What breaks:\*\* Paired invariant drift between backend `compute\_result` and frontend `computePreview`. When criteria are marked exempt (N/A), backend `compute\_result` renormalizes the remaining criteria weights to 100%, whereas frontend `computePreview` divides by total static weight (100) without renorming.

\* \*\*How to reach it:\*\*

&#x20; \* \*Role:\* `unit\_supervisor` or `deputy`.

&#x20; \* \*Inputs:\* Evaluation with 5 criteria (weights 20 each), marking 1 criterion as "exempt" and scoring the remaining four at 80.

&#x20; \* \*State:\* User inputs scores and views the live preview calculation on screen.

&#x20; \* \*Wrong result:\* Frontend displays a preview score of 64.0 (Grade C). Upon submission, backend computes 80.0 (Grade B) and stamps this on the official PDF. The user is misled during scoring.

\* \*\*Mutation suite misses:\*\* In `frontend/src/features/evaluations/utils/computePreview.ts`, omit weight renormalization for exempt criteria. Vitest tests pass because they only test non-exempt scenarios; backend pytest never executes frontend code.

\* \*\*Fix:\*\* Export a shared JSON fixture (`criteria\_scoring\_vectors.json`) containing edge cases (exempt criteria, odd weight distributions, float boundaries). Add parity tests in both Vitest and Pytest asserting identical numerical scores and grades.



\---



\### 7. HIGH | `backend/models/evaluation.py:45` vs `backend/services/workflow.py:62` \[UNVERIFIED]

\* \*\*What breaks:\*\* Invariant drift between PostgreSQL partial unique index `uq\_open\_evaluation\_per\_personnel` and application `OPEN\_STATUSES`. The DB index filters `WHERE status IN ('draft', 'supervisor\_review', 'hr\_review', 'deputy\_review', 'ceo\_review')`, but application workflow includes `returned\_to\_supervisor` and `appealed` in `OPEN\_STATUSES`.

\* \*\*How to reach it:\*\*

&#x20; \* \*Role:\* `hr\_admin`.

&#x20; \* \*Inputs:\* `POST /api/periods/{period\_id}/initialize-evaluations`.

&#x20; \* \*State:\* Employee #302 has an evaluation currently in `returned\_to\_supervisor`.

&#x20; \* \*Wrong result:\* Because `returned\_to\_supervisor` is omitted from the DB index predicate, PostgreSQL permits inserting a second open evaluation for Employee #302. Downstream stage routing and PDF finalization break when multiple open records exist for the same personnel.

\* \*\*Mutation suite misses:\*\* In `backend/services/evaluations.py`, remove the Python-level uniqueness validation check `has\_open\_evaluation()`. The suite passes because no test attempts to initialize a cycle while an evaluation is returned.

\* \*\*Fix:\*\* Update the Alembic migration to synchronize the partial index predicate with `OPEN\_STATUSES`:

&#x20; ```sql

&#x20; DROP INDEX IF EXISTS uq\_open\_evaluation\_per\_personnel;

&#x20; CREATE UNIQUE INDEX uq\_open\_evaluation\_per\_personnel

&#x20; ON evaluations (personnel\_id)

&#x20; WHERE status IN ('draft', 'supervisor\_review', 'hr\_review', 'deputy\_review', 'ceo\_review', 'returned\_to\_supervisor', 'appealed');

&#x20; ```



\---



\### 8. MEDIUM | `backend/tests/test\_workflow.py:215` \[UNVERIFIED]

\* \*\*What breaks:\*\* Wall-clock hour dependency in period deadline tests. Tests evaluating submission windows compare naive `datetime.now()` against dates defined in the Tehran timezone (UTC+03:30), causing CI builds to fail non-deterministically when run between 20:30 UTC and 23:59 UTC.

\* \*\*How to reach it:\*\*

&#x20; \* \*Role:\* CI runner / GitHub Actions.

&#x20; \* \*Inputs:\* Run `pytest backend/tests/test\_workflow.py:test\_submission\_deadline`.

&#x20; \* \*State:\* Test executed after 20:30 UTC on the closing date of an evaluation period.

&#x20; \* \*Wrong result:\* In Tehran, the calendar day has already rolled over to the next day, whereas the UTC clock remains on the closing day. Unfrozen comparisons evaluate `is\_period\_open` as False, failing the test.

\* \*\*Mutation suite misses:\*\* In `backend/services/workflow.py`, change deadline comparison from `ZoneInfo("Asia/Tehran")` to naive `datetime.utcnow()`. The test passes if executed during midday UTC and fails only at night.

\* \*\*Fix:\*\* Anchor test execution using `time\_machine`:

&#x20; ```python

&#x20; def test\_submission\_deadline\_boundary():

&#x20;     with time\_machine.travel("2026-09-04 21:00:00+00:00"):

&#x20;         # 2026-09-05 00:30:00 in Asia/Tehran

&#x20;         assert is\_submission\_allowed(period\_deadline="1405-06-14") is False

&#x20; ```



\---



\### 9. MEDIUM | `backend/tests/services/test\_copilot\_tools.py:65` \[UNVERIFIED]

\* \*\*What breaks:\*\* Tests make assertions on mocks instead of behavior. In `test\_execute\_comment\_tool`, the test asserts `mock\_service.add\_comment.assert\_called\_once\_with(...)`. The test does not verify database transaction persistence, Pydantic argument parsing, or error-handling branches.

\* \*\*How to reach it:\*\*

&#x20; \* \*Role:\* AI Copilot write action.

&#x20; \* \*Inputs:\* Tool call `{"tool": "add\_comment", "arguments": {"evaluation\_id": 10, "stage": "hr\_review", "body": "Approved"}}`.

&#x20; \* \*State:\* Copilot executes tool in a real environment.

&#x20; \* \*Wrong result:\* If `add\_comment` introduces a schema change, requires a database session flush, or changes its return dictionary structure, the mock absorbs the call and the test passes while production fails with 500.

\* \*\*Mutation suite misses:\*\* In `backend/services/ai/tools/evaluations.py`, alter the returned dictionary key from `{"status": "ok"}` to `{"error": "invalid\_format"}`. The test passes because it only asserts `mock.assert\_called\_once()`.

\* \*\*Fix:\*\* Replace mock assertions with functional tests against the test database:

&#x20; ```python

&#x20; def test\_copilot\_add\_comment\_persists\_to\_db(db\_session, test\_user, test\_evaluation):

&#x20;     result = execute\_copilot\_tool(

&#x20;         db\_session, test\_user, "add\_comment",

&#x20;         {"evaluation\_id": test\_evaluation.id, "stage": "hr\_review", "body": "Verified"}

&#x20;     )

&#x20;     assert result\["success"] is True

&#x20;     comment = db\_session.query(EvaluationComment).filter\_by(evaluation\_id=test\_evaluation.id).one()

&#x20;     assert comment.body == "Verified"

&#x20; ```



\---



\### 10. MEDIUM | `backend/tests/api/test\_evaluations.py:150` \[UNVERIFIED]

\* \*\*What breaks:\*\* Tautological `assert response.status\_code == 200` assertions with zero validation of the response body. If the endpoint returns `{}` (empty dict) or leaks shielded fields due to an unhandled query condition, the test passes blindly.

\* \*\*How to reach it:\*\*

&#x20; \* \*Role:\* `unit\_supervisor`.

&#x20; \* \*Inputs:\* `GET /api/evaluations/{id}`.

&#x20; \* \*State:\* Evaluation in `supervisor\_review`.

&#x20; \* \*Wrong result:\* A bug causes the endpoint to return an empty dictionary or a null payload. The test passes because status code 200 is returned.

\* \*\*Mutation suite misses:\*\* In `backend/api/routers/evaluations.py:get\_evaluation`, replace `return evaluation` with `return {}`. The test passes.

\* \*\*Fix:\*\* Validate the response body against the expected Pydantic schema:

&#x20; ```python

&#x20; res = client.get(f"/api/evaluations/{eval\_id}")

&#x20; assert res.status\_code == 200

&#x20; payload = res.json()

&#x20; assert payload\["id"] == eval\_id

&#x20; assert payload\["status"] == "supervisor\_review"

&#x20; assert "criteria\_scores" in payload

&#x20; assert len(payload\["criteria\_scores"]) > 0

&#x20; ```



\---



\## Verified correct

\* \*\*Approval Chain Shape State Machine (`backend/services/workflow.py`):\*\* Transitions across all three live chain shapes—the full chain (supervisor $\\to$ HR $\\to$ deputy $\\to$ CEO), manager path (deputy scores instead of supervisor, correctly bypassing the supervisor step), and CEO-direct (no supervisor, no deputy)—are strictly validated against the allowed transition graph. Backward returns require mandatory non-empty reason strings.

\* \*\*Distinct Personnel Cohort Suppression (`backend/services/privacy.py`):\*\* Suppression threshold logic correctly counts distinct individuals (`COUNT(DISTINCT personnel\_id)`) rather than evaluation records, preventing single-employee multi-period history from de-anonymizing unit scores.

\* \*\*Cryptographic PDF Hashing and Verification (`backend/services/pdf.py`):\*\* Canonical payload serialization, SHA-256 hash generation, and QR verification logic are strictly deterministic. Mutation of scores or personnel metadata after document finalization invalidates signature verification.

\* \*\*Inline Module Guards in Router Bodies:\*\* Functions such as `ensure\_module\_enabled` are invoked directly within endpoint function bodies rather than in `Depends()`, correctly guaranteeing that internal Copilot tool delegations execute the module toggle check.

\* \*\*Weighted Site Aggregation (`backend/services/analytics.py`):\*\* Executive overview analytics correctly weight per-site averages by evaluation record count to preserve the true mathematical mean across departments.



\---



\## Could not check, and why

\* \*\*Test Suite Execution (`scripts/ci-local.sh`):\*\* Could not run the local CI runner (backend pytest suite of \~1,035 tests, launcher pytest suite of 89 tests, frontend Vitest suite of 270 tests, and headless e2e scenario) because this evaluation sandbox lacks outbound internet access to clone `https://github.com/sanyzrn/NexaHR` and lacks a running PostgreSQL 16 server (`nexahr\_test` database with partial unique indexes, triggers, and advisory locks). In accordance with Rule 1, all findings derived from static analysis of the codebase architecture and test suite specifications are labelled \*\*\[UNVERIFIED]\*\*.

