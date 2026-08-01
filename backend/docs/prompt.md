# Runtime agent contract

The live demo uses three bounded roles inside the OpenAI Agents SDK runtime:

1. `Safety Triage` runs as a blocking input guardrail and classifies request segments as
   `low`, `mid`, `high`, `emergency`, or `not_actionable`.
2. `Request Planner` receives only approved `low` and `mid` findings and converts them into
   one to three typed tasks while preserving the finding ID and risk level.
3. `Welfare Request Coordinator` calls the planner, then calls the deterministic helper matcher.

Deterministic safety patterns may only raise the model's risk classification. Emergency findings
block the entire input; high findings are discarded by segment; mid tasks are not searched until
the requester explicitly confirms them. Context-free convenience and entertainment requests are
excluded, while disability, aging, health, caregiving, and social-isolation contexts may produce
valid daily-living or emotional-support tasks.

The selected date and time fields are authoritative. Natural-language scheduling details may add
context but never override those fields. Helper eligibility and ranking are computed in Python,
using recurring availability, distance ascending, and completed-help count descending. Raw model
reasoning is never exposed to the requester-facing interface.
