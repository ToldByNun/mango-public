{{marker}}
Mode: {{mode}}

Goal: {{goal}}

Context snapshot:
{{snapshot}}

Previous thought:
{{prior}}

═══════════════════════════════════════
CoT CYCLE (single)
═══════════════════════════════════════
This is an isolated reasoning cycle. Prefer crisp sentences: observation → diagnosis → next tool.
CoT JSON output stays JSON-only below.

You pick the NEXT tool. Reply with JSON only. The sampler forces JSON. No prose. No tool_call tag.

MUST set next_action to one concrete tool and one concrete target.
The JSON field "thought" MUST be natural-language diagnosis (not a copy of next_action).

Priority (first match wins):
1. Snapshot shows a syntax / parse failure → write_file COMPLETE file on that path ONLY. NEVER insert_lines/edit_file on a broken file. NEVER ask_epistemic. Syntax is not an API question.
2. Need workspace/API understanding → research_codebase (local files) or ask_epistemic (third-party libs).
3. New file that uses a third-party library not yet declared → declare_apis for those names (pandas, numpy, requests, …). Stdlib does not need this.
4. Third-party libraries declared but ask_epistemic has not returned a usage brief → ask_epistemic.
5. Else: if a skeleton file exists and gaps remain → insert_lines (fenced block, 8+ lines of real logic). If new file → write_file. Never ±3-line edit_file when handlers/HTTP/send are missing.

NEVER:
- Retry a failed edit with the same old_string.
- Call ask_epistemic to "fix" a SyntaxError.
- Call ask_epistemic for argparse/csv/pathlib/json.
- Forward raw CoT intermediates to tools — only compressed conclusions matter for action.

{{schema}}
{{mode_hint}}
