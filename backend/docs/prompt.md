# Runtime agent contract

The live demo uses two bounded roles inside the OpenAI Agents SDK runtime:

1. `Request Planner` converts the natural-language request into one to three typed tasks.
2. `Welfare Request Coordinator` calls the planner, then calls the deterministic helper matcher.

The selected date and time fields are authoritative. Natural-language scheduling details may add
context but never override those fields. Helper eligibility and ranking are computed in Python,
using recurring availability, distance ascending, and completed-help count descending. Raw model
reasoning is never exposed to the requester-facing interface.
