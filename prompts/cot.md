{{marker}}
Mode: {{mode}}

Goal: {{goal}}

Context snapshot:
{{snapshot}}

Previous thought:
{{prior}}

When reasoning internally, prefer crisp sentences: observation, diagnosis, next tool. CoT JSON output stays JSON-only below.

You pick the NEXT tool. Reply with JSON only. The sampler forces JSON. No prose. No tool_call tag.

MUST set next_action to one concrete tool and one concrete target.
The JSON field "thought" MUST be natural-language diagnosis (not a copy of next_action).

Priority (first match wins):
1. Snapshot shows a syntax / parse failure → write_file or edit_file on that path. NEVER ask_epistemic. Syntax is not an API question.
2. New file that uses a third-party library not yet declared → declare_apis for those names (pandas, numpy, requests, …). Stdlib (argparse, csv, pathlib, json) does not need this.
3. Third-party libraries declared but ask_epistemic has not returned a usage brief → ask_epistemic. Implementation APIs only (not unittest/pytest, not stdlib).
4. Last concurrent/lock edit not re-read → read_file that path. Ask whether per-client locks were wrongly collapsed to one global lock.
5. Else locate → read → smallest edit. Do not rewrite whole files. Do not edit tests first unless the bug is in the test.

NEVER:
- Retry a failed edit with the same old_string.
- Call ask_epistemic to "fix" a stray `.` or SyntaxError.
- Call ask_epistemic for argparse/csv/pathlib/json.
- Skip declare_apis / ask_epistemic when creating a new script that depends on third-party libraries.

If nothing changed, keep the JSON update minimal. Record failed attempts so they are not retried blindly.

{{schema}}
{{mode_hint}}
