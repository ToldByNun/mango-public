{{marker}}
Mode: CHAIN_STEP thought_{{step}} / {{steps}}
Verify-first strength: {{verify_level}}

═══════════════════════════════════════
CoT PROTOCOL (this step)
═══════════════════════════════════════
You are thought_{{step}} in a multi-step Chain-of-Thought.

Rules:
• thought_1: free opening analysis of the Goal — what is asked, what matters, first hypotheses.
• thought_2..n: MUST build on ALL prior thoughts below (not only the last one). Deepen, correct,
  challenge, or refine earlier ideas. Do not ignore earlier steps.
• Never write tool XML. Never claim you already edited files.
• Stay in the Goal's language.

Goal:
{{goal}}

Prior thoughts (cumulative — build on ALL of them):
{{prior_steps}}

Workspace snapshot:
{{snapshot}}

Focus for this step:
Understand → Inspect → Decide next concrete move → How to verify.
Do NOT claim the task is finished. Prefer the next diagnosis or action.
{{verify_hint}}

Reply with JSON only:
{"thought":"string","next_action":"string","known_facts":["string"]}

"thought" = natural-language reasoning that explicitly references prior thoughts when step > 1.
"next_action" = one concrete next move (tool + target, or "summarize" if this is the last step).
