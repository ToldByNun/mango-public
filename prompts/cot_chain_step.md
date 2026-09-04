{{marker}}
Mode: CHAIN_STEP thought_{{step}} / {{steps}}
Verify-first strength: {{verify_level}}

<cot_step>
You are thought_{{step}} of {{steps}}. Output JSON only.

Rules:
• thought_1: diagnose Goal + name ONE concrete next tool+target. Do NOT assume APIs/deps are known — re-check with tools.
• thought_2..n: MUST add a NEW fact OR change next_action. NEVER paraphrase prior thoughts.
• FORBIDDEN phrases to recycle: "write_file was blocked", "deps were not installed", "declare_apis succeeded", "building on thoughts".
• If prior already stated a blocker: next_action MUST advance the protocol (install_packages / ask_epistemic / web_research / fetch_url / write_file) — do not restate the blocker.
• Never write tool XML. Never claim files were already edited.
• Stay in the Goal's language.
</cot_step>

Goal:
{{goal}}

Prior thoughts (do NOT copy — advance past them):
{{prior_steps}}

Workspace snapshot:
{{snapshot}}

{{verify_hint}}

Reply JSON only:
{"thought":"string","next_action":"string","known_facts":["string"]}

"thought" = ≤2 short sentences of NEW reasoning.
"next_action" = one concrete tool + target (different from prior next_action when step > 1).
