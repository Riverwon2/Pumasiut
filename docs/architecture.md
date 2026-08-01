# Prototype architecture

## Confirmed product contract

- The requester enters a name, natural-language request, date, start time, and end time.
- UI date/time fields are authoritative; natural language only enriches task descriptions.
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
      -> match_helpers function tool
          -> deterministic Python assignment for low tasks only
  -> public phase SSE events
  -> typed AssignmentPlan SSE result
  -> helper cards with local accept/decline/mission-complete state
  -> accept keeps the helper card open with a mission-complete action
  -> mission complete changes requester and helper views from accepted to completed
  -> decline advances the task's candidate queue (max 2)
  -> exhausted queue is shown as unmatched
  -> mid task confirmation calls POST /api/tasks/confirm-match
  -> confirmed mid task receives a deterministic candidate queue (max 2)
```

The coordinator cannot author the final assignment. The server returns the assignment stored by
the deterministic tool, which prevents model output from changing eligibility or ranking.
Raw high-risk or excluded segments are not forwarded to the task-planning agent.

## Data and privacy boundaries

- `OPENAI_API_KEY` remains server-side in the ignored root `.env`.
- Raw model stream events and chain-of-thought are not sent to the UI.
- The demo stores neither welfare requests nor helper responses.
- `experienceTags` and `trustScore` are parsed as extra fixture data but ignored for ranking.
