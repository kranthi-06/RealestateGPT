# AI evaluation

The deterministic evaluation set for a Groq-configured environment is:

1. `3BHK under 90 lakhs in Hyderabad` → `search_properties`; assert BHK and
   INR normalization, returned IDs, deterministic rank, and citations.
2. `2 bedroom apartment below 60 lakh near metro` → search plus bounded live
   nearby enrichment where results have coordinates.
3. `Show homes close to schools and hospitals` → search with nearby criteria.
4. `Find something near HITEC City with reasonable commute` → search and route
   only when a destination is required.
5. `Show me the second property` → use prior conversation result IDs, then
   `get_property`.
6. `Only properties under 1 crore` → preserve prior criteria and change budget.
7. `How far is this property from HITEC City?` → `route` with verified
   coordinates.

For each run, retain audit metadata and verify: selected tool, valid arguments,
tool-derived IDs/facts, deterministic rank, citations, and no provider fallback.
These are live evaluations and are NOT PASS until a configured Groq deployment
and a functioning backend are available.
