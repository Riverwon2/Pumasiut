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
- Accept completes that task. Decline advances to the next candidate; exhausting the queue completes it as unmatched.

## Runtime flow

```text
React form
  -> POST /api/requests/stream
  -> Coordinator Agent (OpenAI Agents SDK streamed run)
      -> plan_request function tool
          -> Request Planner Agent (structured TaskPlan)
      -> match_helpers function tool
          -> deterministic Python assignment
  -> public phase SSE events
  -> typed AssignmentPlan SSE result
  -> helper cards with local accept/decline state
  -> decline advances the task's candidate queue (max 2)
  -> exhausted queue is shown as unmatched
```

The coordinator cannot author the final assignment. The server returns the assignment stored by
the deterministic tool, which prevents model output from changing eligibility or ranking.

## Data and privacy boundaries

- `OPENAI_API_KEY` remains server-side in the ignored root `.env`.
- Raw model stream events and chain-of-thought are not sent to the UI.
- The demo stores neither welfare requests nor helper responses.
- `experienceTags` and `trustScore` are parsed as extra fixture data but ignored for ranking.
