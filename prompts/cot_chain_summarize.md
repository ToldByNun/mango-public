{{marker}}
Mode: CHAIN_SUMMARY

Goal:
{{goal}}

Full chain (all steps):
{{all_steps}}

Produce a short summary for the MAIN ACTION AGENT only.
Include: what was understood, what to inspect/edit, how to verify, and what to avoid.
Do not dump raw step text. No tool calls. JSON only:

{"summary":"string","next_action":"string","verify_plan":["string"]}
