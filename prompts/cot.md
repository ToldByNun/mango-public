{{marker}}
Mode: {{mode}}

Goal: {{goal}}

Context snapshot:
{{snapshot}}

Previous thought:
{{prior}}

<cot_cycle>
Isolated reasoning. Crisp: observation → diagnosis → next tool.
Reply JSON only. Sampler forces JSON. No prose. No tool_call tag.
MUST set next_action to one concrete tool + one concrete target.
"thought" MUST be natural-language diagnosis (not a copy of next_action).
Do NOT assume you already know APIs or that packages are installed — re-verify.
</cot_cycle>

<priority>
First match wins:
1. Syntax/parse failure in snapshot → write_file COMPLETE on that path ONLY. NEVER insert/edit on broken file. NEVER ask_epistemic for SyntaxError.
2. Snapshot says BLOCKED / missing packages / needs install → next_action MUST be install_packages OR ask_epistemic OR web_research/fetch_url. NEVER restate the blocker. NEVER write_file until gate clears.
3. Need understanding → research_codebase (local) or ask_epistemic (third-party).
4. New file needs third-party not declared → declare_apis (max 5 import names). Stdlib skips this.
5. Declared third-party but no bind_task_prompt yet → bind_task_prompt (MUST mention install_packages + confirm/permission).
6. Declared + bound but no usage brief → ask_epistemic.
7. Packages missing / needs_install → install_packages (confirm) OR web_research/fetch_url. NEVER silent pip.
8. Else: skeleton exists with gaps → insert_lines (fenced, 8+ lines). New file → write_file. Never ±3 edit_file when handlers/HTTP/send missing.
</priority>

<never>
- Retry failed edit with same old_string
- ask_epistemic to "fix" SyntaxError
- ask_epistemic for argparse/csv/pathlib/json
- Skip bind_task_prompt / install permission for third-party deps
- Thought loops that only restate "write_file was blocked"
- Assume third-party APIs from memory
</never>

{{schema}}
{{mode_hint}}
