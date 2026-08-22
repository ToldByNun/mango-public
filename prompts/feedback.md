Runner feedback snippets injected into the model after a tool turn.

Lookup: `feedback("stress")` inside `_handle_run_tests_results` loads `# _handle_run_tests_results.stress`.
Exact heading `# review_message.coarsened` also works from anywhere.
Placeholders look like `{{name}}`.

# run.follow_up
This is a follow-up. Read the current implementation AND existing tests first. ask_epistemic must look up concrete symbols (package + symbol), not a whole module. Then edit. Re-read the result and ask whether the change still preserves invariants (especially lock granularity). Then run_tests. You are not done until tests pass AND the design still makes sense.

# run.declare_first
If you will use a third-party library (pandas, numpy, requests, …), first call declare_apis listing those names, then ask_epistemic. Stdlib (argparse, pathlib, json, csv, …) does not need ask_epistemic — write_file is allowed immediately.

# run.tests_deadline
Tests never passed within iteration limit.

# tests_still_red
Tests still failing. Do NOT finish or summarize. NEXT tool MUST be read_file on the failing implementation, then edit_file (short old_string), then run_tests.

# run.thought_has_code
Do not put source code in thought. Call write_file or edit_file with the code.

# run.thought_too_long
Thought dumped code, tool XML, or an essay. Keep diagnosis only: what failed, why, next tool+file. No source, no <tool_call>.

# run.disabled_tools
Do not call {{dropped}}. Use edit_file or read_file instead.

# run.verification_fix
{{report}}
Do not finish yet. Fix the verification errors with a tool call.{{next_edit}}{{snapshot}}

# run.syntax_broken
{{report}}
Do not finish. Repair the listed syntax error with write_file or edit_file. write_file fence body must be the COMPLETE file (full def + body), never a single keyword like `def`.

# run.truncated_json
Your last tool call was truncated (incomplete ``` fence or cut-off JSON). File was NOT written. NEXT write_file must be SHORT: for tests write ONE TestCase with ONE test method only (<40 lines), close the ``` fence, then edit_file to add more. Do not dump a full suite in one call.

# truncated_write_cli
Your last write_file was truncated (tool JSON cut off). File was NOT fully written. Do NOT dump the whole CLI in one call. NEXT write_file a SHORT skeleton only (<40 lines: imports + load/save stubs + `if __name__ == '__main__': pass`). Then edit_file to add ONE subcommand at a time. Keep each tool call small.

# cli_skeleton_first
This goal is a console/CLI Python project. Do NOT write the entire inventory CLI in one write_file (it will truncate). FIRST tool: write_file a SHORT skeleton (<40 lines) with argparse stubs. Then edit_file to add add/remove/update/describe handlers one by one. Finish only when __main__ + subcommands are complete.

# truncated_write_markup
Your last write_file for HTML/CSS was truncated or incomplete (file not changed). Do NOT dump a full landing page in one tool call. NEXT: write_file a SHORT skeleton only (<80 lines: html/head/body + one heading + one script/style stub). Then edit_file to add sections one at a time.

# run.large_markup_goal
This goal needs a large HTML/CSS/JS page. Do NOT plan the whole file in thought and do NOT write_file the full animation in one call. FIRST tool: write_file a SHORT skeleton (<60 lines) with canvas + empty script. Then edit_file to add drawing code in small chunks.

# stalled
You have now written the same answer several times without calling a tool, so nothing changed. Stop restating the plan. Emit ONE tool call in the canonical format on your very next line, e.g. <tool_call=read_file : {"path": "the file you need"}>. If you truly cannot act, call run_tests.

# run.emit_tool
Do not finish yet. Emit a tool call now (read_file, search_code, or edit_file).

# run.continue_work
Do not finish yet. Your last message said more work remains (tests/edits). Emit the next tool call now (write_file or edit_file). Keep files short.

# continue_work
Do not finish yet. Your last message said more work remains (tests/edits). Emit the next tool call now (write_file or edit_file). Keep files short.

# research_next
Still missing API lookups: {{needed}}. Do not write the brief yet. NEXT tool MUST be package_source_lookup {{example}}. One symbol per call.

# research_summarize
Lookups complete. Do not call more tools. Write the usage brief now (imports, real calls, pitfalls).

# run.no_edit_truncated
No successful edit yet. Your tool JSON was truncated; use edit_file with a short old_string.

# run.no_edit
No successful edit yet. Apply a minimal edit_file fix or read_file first.

# run.readonly_no_impl
Those searches did not locate the implementation. Search package/src modules (not testing/ or test_*.py), then edit_file with old_string copied verbatim from that file.

# run.readonly_edit_now
You have only inspected the repo. Apply a minimal edit_file fix now. Use a short unique old_string and new_string; do not rewrite whole files.

# _note_plan_progress.declare
Third-party libraries recorded: {{libs}}. NEXT TOOL MUST be ask_epistemic (implementation APIs, not unittest/pytest, not stdlib). Then write_file.

# _note_plan_progress.stdlib_ok
Stdlib only ({{libs}}). Skip ask_epistemic. NEXT you may write_file. Then wait for the syntax compile check.

# _note_plan_progress.epistemic_ok
API research done. Use the usage brief (imports and real calls). NEXT you may write_file. Then wait for the syntax compile check. Compile does not run the script.

# _note_plan_progress.epistemic_retry
ask_epistemic must return a usage brief for {{needed}}. unittest/pytest do not count. Then write_file — do not ask again.

# _note_plan_progress.install_failed
Could not install {{pkgs}}. Command: {{command}}. Fix the package name or install manually, then ask_epistemic again.

# _feedback_failed_tools.retry
Retry with ALL required keys. edit_file needs path, old_string, new_string. Copy old_string exactly from an implementation file, including whitespace. Do not edit testing/ or test_*.py unless the bug is in the test.

# _feedback_failed_tools.write_file
edit_file failed repeatedly or the tool JSON was invalid. NEXT tool MUST be write_file with the FULL current file plus your change. Do not call edit_file again until write_file succeeds.

# _execute_tool_calls.blocked_declare
BLOCKED by the runner. Call declare_apis first for third-party libraries (pandas, numpy, …). Stdlib-only files may write_file without this. Then ask_epistemic. write_file is rejected until both succeed for those libraries.

# _execute_tool_calls.blocked_epistemic
BLOCKED by the runner. Call ask_epistemic now for the third-party APIs: {{libs}}. Stdlib and unittest/pytest do not count. write_file is rejected until that call returns a usage brief.

# _execute_tool_calls.blocked_edit_read
BLOCKED by the runner. Do not edit yet. Call read_file on the implementation file, copy old_string verbatim, then edit_file.

# _execute_tool_calls.blocked_edit_search
BLOCKED by the runner. Do not edit yet. Call search_code first, then read_file on the implementation.

# blocked_edit_not_read
BLOCKED by the runner. You have not read {{path}} yet. Call read_file first, then copy old_string verbatim into edit_file.

# blocked_edit_test_first
BLOCKED by the runner. Edit the implementation module first, not test_*.py, unless the goal is explicitly about that test file.

# blocked_edit_fuzzy
BLOCKED by the runner. Fuzzy match rejected on {{path}}. read_file the file and copy old_string exactly (including whitespace).

# no_impl_change
You have not changed any implementation file and tests did not pass. Do NOT finish. read_file the target module, edit_file with a verbatim old_string, then run_tests.

# _handle_run_tests_results.stress
Happy-path tests passed, but the implementation uses threads/locks/async. You MUST add a test using concurrent.futures.ThreadPoolExecutor (or threading.Thread) with at least 8 workers hitting the shared state, plus a high-volume case (200+ operations). Then the runner will re-test.

# _handle_run_tests_results.no_tests
No test_*.py files found. Write tests covering the new behavior (including ThreadPoolExecutor stress tests if the code is concurrent). The runner executes them automatically after the next write.

# tests_before_run
BLOCKED by the runner. No test_*.py file exists in the workspace yet, so run_tests has nothing to collect. FIRST tool MUST be write_file with a test_*.py file (complete file, one TestCase is enough), then the runner executes it automatically.

# no_tests_collected
pytest exited 5 for {{targets}}: the file(s) exist but contain NO tests (empty, wrong names, or reverted). Running them again can never pass. NEXT tool MUST be write_file rewriting the test file with real test functions (def test_* methods in a TestCase class), or write the implementation the tests import.

# _handle_run_tests_results.failed_persistent
Tests still {{hint}} after {{attempts}}+ tries. Do NOT finish. NEXT tool MUST edit the implementation (or tests if the assertion is wrong). The runner keeps re-testing until pytest passes or the iteration limit is hit.{{detail}}

# _handle_run_tests_results.exhausted
Tests {{hint}} after {{attempts}} automatic attempts. Stopping the fix loop and reporting the current result.{{detail}}

# _handle_run_tests_results.failed
Tests {{hint}} (attempt {{attempt}}/{{attempts}}, {{remaining}} left). Fix the failing code or tests. The runner will re-test after the next write.{{extra}}{{detail}}

# failed_read_first
Tests {{hint}} (attempt {{attempt}}/{{attempts}}, {{remaining}} left). Do NOT restate the bug in thought. NEXT tool MUST be read_file path="{{path}}" (copy exact source), then edit_file with a short old_string from that file (e.g. call register in __init__). Then run_tests.{{extra}}{{detail}}

# missing_dependency
Tests failed because a package is missing: {{pkgs}}. Do NOT rewrite unrelated files. Command: {{command}}. NEXT: after install, run_tests again. Prefer mocking discord in unit tests or lazy-importing it inside the bot entrypoint.

# missing_dependency_installed
Installed {{pkgs}} ({{command}}). Do NOT thrash other files. NEXT tool MUST be run_tests.

# _handle_run_tests_results.concurrent_hint
 This code is concurrent — also add a ThreadPoolExecutor/threading.Thread stress test; happy-path tests will miss race bugs.

# runtime_failed
Pytest passed but running {{script}} crashed at runtime (the runner executes `python script.py` after tests):
{{detail}}
Fix the runtime path — often edge cases in main()/render loops that unit tests never hit. Add a test for the failing case if possible.

# runtime_no_entry
Goal needs a runnable console/CLI script but no `if __name__ == '__main__'` entry was found. NEXT: write_file or edit_file to add main(), argparse subcommands, and wire parse_args(). read_file the current file first — do not claim done while functions are stubs.

# blocked_shell_read
BLOCKED: do not use `type`/`cat`/`Get-Content` to read source files. NEXT tool MUST be read_file path="{{path}}" — it returns the FULL file. Judge completeness from ## Implementation status (functions, main, subcommands), never from byte size.

# impl_incomplete
Implementation is NOT finished — the runner will reject finish until these are fixed:
{{gaps}}
NEXT: read_file the current file, then edit_file to ADD only the missing pieces (do NOT rewrite the whole file in one write_file — that truncates). Keep each edit small.

# goal_deliverables_missing
Goal requires these files on disk but they do not exist yet: {{files}}
NEXT: write_file each missing path with complete content (not a stub). For reports (.txt/.csv), write the computed result. For test_*.py goals, include real def test_* functions, then run_tests.

# file_missing_write
BLOCKED: `{{path}}` does not exist yet — read_file/edit_file cannot open it. NEXT tool MUST be write_file path="{{path}}" with the COMPLETE new content. Do not call read_file on this path again.

# file_missing_read_input
BLOCKED: `{{path}}` does not exist yet. Read existing inputs first: NEXT tool MUST be read_file path="{{next_path}}". After all inputs are read, write_file the missing output.

# _note_repo_impact
Repo map (read these before further edits):
{{bits}}

# _locate_failed_edit.test_file
{{path}} is a test file. Edit the implementation module instead.

# _locate_failed_edit.matches
Implementation matches (read this file and copy old_string verbatim):
{{hits}}

# _locate_failed_edit.snippet
Current snippet for {{symbol}} in {{path}}:
{{snippet}}
Next retry: set old_string to an exact verbatim substring from the snippet.

# _apply_syntax_failure
Verification failed (syntax check; tests not run)
COLLECTION ERROR: implementation does not parse.
{{blob}}
write_file the COMPLETE file with the syntax fixed (missing colon, full function body). Do not write a fragment.

# _apply_pending_rename
rename_symbol({{old}} -> {{new}}) failed: {{exc}}. Call rename_symbol; do not add a second function.

# _block_incomplete_rename
Tests passed but the rename is incomplete: {{old}} is still referenced. {{hint}}. Do not add a second function with the new name.

# _fallback_summary
I updated {{files}}.
{{draft}}
{{tests}}

A later follow-up should read these files and the existing tests before editing again.

# _abort_report
Stopped after {{failed}} failed verification attempt(s) (max {{max}}).
{{report}}

# review_message
Green tests do not prove the design is right. NEXT: read_file the implementation you just changed. Check: (1) shared state mutated only under the right lock; (2) no check-then-act race; (3) you did not simplify away per-client locks or other invariants. If anything looks off, edit again. Do not finish yet.

# review_message.coarsened
STOP. You replaced per-client/fine-grained locks with one global lock. Unrelated clients now block each other. Green tests do not make that correct. NEXT: read_file the implementation. Then restore a Lock per client_id (dict/defaultdict of Lock; create missing locks under a short mutex) unless a single lock is truly required. Shared state stays inside the matching lock.

# coarsen_after_read_message
You re-read a file that collapsed per-client locks into ONE global lock. Unrelated clients now serialize on that lock — usually a regression, not a cleanup. If that was accidental, restore a Lock per client_id. Do not finish just because pytest is green.

# experiment.reverted
Hypothesis reverted ({{reason}}). Before {{before}} {{unit}}, after {{after}} {{unit}} ({{delta}}). Next hypothesis must differ — do not repeat the same edit.

# experiment.kept
Hypothesis kept. Before {{before}} {{unit}}, after {{after}} {{unit}} ({{delta}}).

# experiment.unsupported
Claim not met (wanted {{claim}}, measured {{delta}}). Code kept. Next hypothesis must differ if you still need that gain.

# experiment.exhausted
Stop changing these files. 3 reverts already. Report the evidence (tests/timing) instead of editing again.

# experiment.command_changed
Performance command changed; skipped before/after compare. Code kept.
