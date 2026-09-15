# NexaHR — AI copilot: conversation reliability review

A third prompt for the same subsystem, and deliberately **not** a third
authorization audit.

Why it exists: two rounds hunted guards, and a third
(`review-prompt-ai-elevate.md`) hunted depth. Both were competent and both
missed the thing that actually made the copilot unusable in production — the
conversation did not survive its own plumbing. Four independent defects, none
of them an authorization bug, none of them visible in any unit test:

  * the provider's own required field on a tool call was dropped, so every
    tool-using turn died at step two;
  * the "I read your file" message the user replied to was fabricated in the
    browser and never existed on the server;
  * a failed turn left the user's question in the history with no answer, and
    those orphans pushed real messages out of the 12-message window;
  * the history window filtered roles *after* `LIMIT`, so the window was
    quietly smaller than its own constant.

Every one of them presented to the user as the same symptom: **"it forgets
what I just said."** A reviewer looking for guard gaps would have walked past
all four.

So this prompt has one question: **does a real conversation work, end to end,
across turns, across reloads, across providers, and across failures?**

Paste everything between the fences.

---

```
Repo: https://github.com/sanyzrn/NexaHR
Branch: main  (cut your own branch off it)
Subsystem: the conversation path of the in-app AI copilot —
  backend/app/services/ai/{port,provider,orchestrator,summary,context,prompt}.py
  backend/app/services/ai/tools/{base,uploads}.py
  backend/app/api/routers/ai.py
  frontend/src/components/copilot/{Copilot,CopilotPanel,CopilotSession}.tsx

NexaHR is a Persian-first, RTL HR performance-evaluation system for one
Iranian organization. Single-instance PostgreSQL. The LLM endpoint is
OpenAI-compatible and configurable per deployment: in practice it is OpenAI,
Anthropic's compatibility gateway, Google Gemini's `/v1beta/openai` gateway,
OpenRouter, or a self-hosted server. They are NOT interchangeable, and that
is the point of half one.

This is NOT an authorization review. Guards, capabilities, row scoping, the
confirmation flow and prompt injection were covered by
`docs/review-prompt-ai-elevate.md` and two rounds before it. If you find an
authorization defect, report it — but do not spend the review there, and do
not re-derive the tool parity table.

=== WHAT YOU ARE LOOKING FOR ===

A "conversation defect" is anything that makes the assistant's view of the
conversation differ from the user's view of it, or from what actually
happened. Four shapes, in descending order of how much they cost us:

  A. STATE THE USER SEES BUT THE MODEL DOES NOT.
     Anything rendered as an assistant message that was not persisted as one.
     Anything persisted that `_history_messages` will not return. Anything
     shown in a card that never enters the prompt. The upload notice was
     exactly this: `setMessages` in the browser, nothing on the server, and
     the user answering an invitation the model never issued.

  B. WIRE-FORMAT LOSS BETWEEN OUR TYPES AND THE PROVIDER'S.
     `ChatMessage.to_wire()` and `ToolCall.to_wire()` are the only places our
     conversation becomes HTTP. Anything a provider sends that we do not
     round-trip is a defect waiting for that provider's next release.
     Gemini's `extra_content.google.thought_signature` was this: required to
     be replayed verbatim, silently dropped, HTTP 400 on every multi-step
     turn. Fixed generically (keep every non-standard key) — verify that
     generality actually holds, including through `orchestrator.run_turn`,
     which rebuilds messages and where the first fix was re-broken.

  C. PARTIAL WRITES ON A FAILED OR ABANDONED TURN.
     `run_turn` commits per loop step on purpose. Enumerate what is already
     committed when step four throws: pending actions, audit rows, upload
     overlays, the summary refresh, the usage ledger, messages. For each,
     say whether leaving it is correct. Then do the same for a client that
     disconnects mid-turn and for two concurrent turns in one conversation.

  D. SILENT WINDOW SHRINKAGE.
     `HISTORY_WINDOW`, `_ATTACHMENT_LIMIT`, `MAX_SUMMARY_CHARS`,
     `context_record_limit`, `max_tokens`, `max_tool_iterations`. For each:
     what does the user lose when it binds, and are they told? A cap that
     drops context with no signal is the defect; the number itself is not.

=== HALF ONE: PROVIDER DIALECTS ===

The adapter is one file (`provider.py`) claiming to speak to five services.
Build a table — provider x behaviour — and fill it from documentation and
from the mock, not from assumption:

  1. Tool-call id: present, absent, or reused across parallel calls?
  2. Extra per-call fields that must be echoed (Gemini's thought signature;
     anything equivalent on Anthropic's gateway or OpenRouter).
  3. Reasoning / thinking content: returned where, and must it be replayed?
  4. `tool_choice: "none"` with `tools` present — honoured or rejected?
     The final loop step depends on it.
  5. An assistant message with `content: null` plus tool calls.
  6. Parallel tool calls in one response: does our loop pair every result
     back to the right id?
  7. `finish_reason` vocabulary — we only special-case `"length"`.
  8. `usage` key names (`prompt_tokens` vs `input_tokens`, cache fields).
     `services/ai/usage.py` normalises two families; is that still enough?
  9. What their 400 body looks like, and whether `_error_text` +
     `ToolProtocolUnsupported` misclassifies it. That heuristic matches on
     the substrings "tool"/"function": a 400 that merely MENTIONS a function
     name would be misread as "this service has no tool support" and drop the
     whole conversation into the JSON fallback protocol. Show whether that is
     reachable.

For each row: does our code handle it, and what is the user-visible symptom
when it does not? A row you cannot verify without a paid key is UNVERIFIED —
say so, do not guess. `e2e/mock_llm.py` can be extended to emit any of these
shapes; extending it is a legitimate deliverable of this review.

=== HALF TWO: THE CONVERSATION, END TO END ===

Run it. PostgreSQL is required; there is no SQLite fallback.

    cd backend && python3 -m venv .venv && . .venv/bin/activate
    pip install -r requirements-dev.txt
    createdb nexahr_test
    cd .. && scripts/ci-local.sh all          # ten commands, all must pass
    bash e2e/run_e2e.sh --api-only            # upload -> patch -> confirm -> import
    bash e2e/e2e_browser.sh                   # real browser, real servers, mock model

Then answer these, each with a reproduction:

 a. A message is sent. The browser tab is closed mid-request and reopened.
    What does the user see, what does the server hold, and do they agree?
 b. The same conversation is open in two tabs. Send from both. Reload both.
 c. Upload a file, send three messages, reload. Is the upload still in the
    prompt? Is its notice still in the history? Do the cards duplicate?
 d. Thirteen turns, then ask about turn one. The summary is supposed to carry
    it (`summary.py`). Show that it does, or where it drops.
 e. A pending confirmation is created, the page is reloaded, then confirmed.
    Does the result message land in the conversation the user is looking at?
 f. Two uploads with the SAME filename. Can the user, or the model, tell
    which is which?
 g. `max_tool_iterations` is reached. What does the user get, and can they
    continue from there, or is the turn lost?
 h. The model returns a tool call for a tool the user's role cannot reach.
    The loop returns the error as a tool result and keeps going. Does the
    final answer tell the user the truth about what did not happen?

=== HALF THREE: WHAT THE INTERFACE CLAIMS ===

The panel is ~760 lines holding conversation state
(`CopilotSession.tsx`) outside the component so the floating window survives
being closed. Check, in a real browser:

  * Every place the browser CONSTRUCTS an assistant message rather than
    rendering one from the server. There was one; prove there are no more.
    `grep` for `setMessages` and read every call site.
  * Optimistic user messages: `sendText` appends locally with
    `id: Date.now()`, and the server assigns its own. After any reload or
    `loadConversation`, do they reconcile or duplicate?
  * Scroll: in `variant="page"` the sidebar and composer must stay put and
    only the message list may scroll, at any viewport height. In
    `variant="drawer"` the panel must not cover the mascot button.
  * Error text: a failed turn shows the provider's own message
    (deliberately — a 401 and "model not found" are different fixes). Is any
    of it something a non-engineer cannot act on, and is any of it a leak?

=== RULES ===

  * Every finding: file:line, what breaks, a concrete path to reach it
    (provider / role / inputs / state -> wrong result), and the fix.
    No "might be". No "consider".
  * Persian identifiers, comments and test names are normal here and are
    never findings.
  * Prove each fix by reverting it and watching a named test go red. A fix
    with no test that fails without it is not finished.
  * Do not refactor. This subsystem is heavily commented with the reasons
    behind its shape; a rewrite throws those away and we will reject it.

=== ALREADY FIXED IN THIS ROUND — DO NOT RE-REPORT ===

Each was proven by reverting it and watching a named test go red.

  * Gemini's `thought_signature` dropped. `ToolCall.provider_extra` now keeps
    every non-standard key from the response and `to_wire()` replays it
    beneath the standard keys, so a provider cannot overwrite the call id.
    `run_turn` passes the objects through instead of rebuilding them.
    (`tests/test_ai_provider_dialect.py`, and two tests in
    `tests/test_ai_assistant.py`.)
  * Tool-call ids were normalised AFTER the assistant message was built, so a
    provider that omits `id` produced a mismatched pair. Now normalised once,
    before.
  * The upload notice ("فایل … را دیدم") was built in the browser and never
    persisted. Now `uploads.staged_notice()` writes a real assistant message
    and the panel reloads from the server.
    (`tests/test_ai_excel_flow.py`.)
  * A failed turn persisted the user's question with no answer, duplicated it
    on every retry, and starved the history window. Now the question, and an
    empty conversation created by that same turn, are removed — while the
    usage ledger row stays. (`tests/test_ai_turn_atomicity.py`.)
  * `_history_messages` filtered roles after `LIMIT`. Now filtered in SQL.
  * The floating panel opened on top of the mascot; the full-page view used a
    guessed `calc(100vh-14rem)` with a `min-h` that could exceed the
    viewport and push the composer off-screen.

Known and written down: `docs/open-findings-ai.md`, sections "پ" (never
measured) and "ت" (five earlier claims checked and found WRONG — re-filing
one of those is worse than filing nothing).

OUTPUT (exactly these sections, nothing else)

## Verdict — 5 lines. Does a real multi-turn conversation work, or not?
## Provider dialect table — provider x the nine behaviours, with UNVERIFIED marked
## Findings — severity | file:line | what breaks | how to reach it | fix
## Reproductions — the eight end-to-end scenarios, each with what you saw
## Verified correct — what you checked and found sound
## Could not check, and why
```
