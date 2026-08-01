# Prototype architecture

## Confirmed product contract

- The requester enters a name, natural-language request, date, start time, and end time.
- The UI date is authoritative. Task-specific natural-language times take precedence over the UI
  time window, which is used only as a fallback.
- A point appointment or deadline is preserved without inventing a duration. Matching pauses until
  the requester confirms a complete start/end range.
- The request is split into one to three tasks.
- Each task receives a distinct helper, so one task equals one helper in the prototype.
- Helper availability repeats daily.
- Eligible helpers are ranked by distance ascending, then completed-help count descending.
- The right side shows no more than three helper response cards.
- Each task has a queue of at most two distinct helper candidates.
- Accept moves that task into an accepted mission state. The helper explicitly completes the mission after doing the work.
- Decline advances to the next candidate; exhausting the queue completes it as unmatched.
- A blocking Safety Triage input guardrail always runs before task planning.
- Emergency findings stop the entire request. High-risk findings are discarded by segment.
- Mid-risk tasks pause before matching and require an explicit requester confirmation.
- Non-actionable convenience or entertainment content is excluded before planning.

## Runtime flow

```text
React form
  -> POST /api/requests/stream
  -> Coordinator Agent (OpenAI Agents SDK streamed run)
      -> blocking Safety Triage input guardrail
          -> structured SafetyAssessment
          -> deterministic emergency/high/mid policy floor
      -> plan_request function tool
          -> Request Planner Agent (approved low/mid findings only)
          -> explicit-time coverage validation
      -> match_helpers function tool
          -> deterministic Python assignment for safe tasks with confirmed schedules only
  -> public phase SSE events
  -> typed AssignmentPlan SSE result
  -> helper cards with local accept/decline/mission-complete state
  -> accept keeps the helper card open with a mission-complete action
  -> mission complete changes requester and helper views from accepted to completed
  -> decline advances the task's candidate queue (max 2)
  -> exhausted queue is shown as unmatched
  -> mid task confirmation calls POST /api/tasks/confirm-match
  -> incomplete schedule confirmation uses the same endpoint with user-confirmed start/end
  -> confirmed task receives a deterministic candidate queue (max 2)
```

The coordinator cannot author the final assignment. The server returns the assignment stored by
the deterministic tool, which prevents model output from changing eligibility or ranking.
Raw high-risk or excluded segments are not forwarded to the task-planning agent.

## Data and privacy boundaries

- `OPENAI_API_KEY` remains server-side in the ignored root `.env`.
- Raw model stream events and chain-of-thought are not sent to the UI.
- The demo stores neither welfare requests nor helper responses.
- The completion card displays `+30 credit` as presentation-only prototype feedback. No balance is
  persisted or transferred in the demo.
- `experienceTags` and `trustScore` are parsed as extra fixture data but ignored for ranking.

## Production credit persistence

For a real service, store a helper credit balance and an immutable credit ledger in the database.
Completing a task should atomically insert a `+30` ledger entry and update the cached balance. Use a
unique idempotency key derived from the completed task and helper so retries cannot issue credit
twice. Reversals should add compensating ledger entries instead of rewriting prior transactions.
