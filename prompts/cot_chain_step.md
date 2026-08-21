{{marker}}
Mode: CHAIN_STEP {{step}} / {{steps}}
Verify-first strength: {{verify_level}}

Goal:
{{goal}}

Prior chain steps (cumulative — build on all of them):
{{prior_steps}}

Workspace snapshot:
{{snapshot}}

You are one reasoning request in a verify-first chain. Prefer:
Understand → Inspect → Implement → Run → Observe → Verify → Fix → Verify again.
Do NOT claim done after writing code. Focus this step on the next concrete diagnosis or action.
{{verify_hint}}

Reply with JSON only:
{"thought":"string","next_action":"string","known_facts":["string"]}

"thought" MUST be natural-language diagnosis in the Goal's language, not a copy of next_action.
