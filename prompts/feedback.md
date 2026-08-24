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

# action_loop
You are repeating the same action ({{action}}) and making no progress. Do NOT call that tool again with the same arguments. NEXT you MUST make a real change with edit_file or write_file (different old_string/new_string than before). If edit_file keeps failing, call write_file with the FULL corrected file contents.

# action_loop_blocked
BLOCKED by the runner: you already did {{action}} with no progress. Do not repeat it. NEXT tool MUST be write_file (full corrected file) or a different edit_file with a NEW old_string copied verbatim from the file.

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

# lookup_empty
codebase_lookup returned no symbol/file hits for that query.
NEXT: research_codebase with a focused topic, or search_code / list_dir / glob_files / read_file.
Do not finish yet. Do not claim you already answered from empty lookup results.

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

# _note_plan_progress.epistemic_give_up
ask_epistemic failed twice for {{needed}}. Gate cleared. NEXT tool MUST be write_file using known APIs (stdlib urllib if requests missing). Do not call ask_epistemic again.

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
pytest exited 5 for {{targets}}: the file(s) exist but contain NO tests (empty, truncated, or reverted). Running them again can never pass. The runner has LOCKED out run_tests and edit_file. NEXT tool MUST be write_file with the COMPLETE test file (full imports + TestCase with def test_* methods — never a partial edit). Then pytest runs automatically.

# test_collection_broken
pytest could not COLLECT {{targets}} (exit 2) — the file has a syntax error or import failure, usually a truncated write. Editing blind will not fix it. The runner has LOCKED out run_tests and edit_file. NEXT tool MUST be write_file rewriting the COMPLETE test file from scratch (all imports, full TestCase class, every def test_ method closed).{{detail}}

# truncated_write_detected
The previous write to {{path}} produced an INVALID or TRUNCATED file (syntax error, or ends mid-write with a dangling `#` / unfinished line). Do not edit — rewrite the ENTIRE file with write_file now: complete imports, full function bodies, real HTTP/send logic, entry point at the end.

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
Fix the runtime path — real Tracebacks / crashes only. Missing CLI args / argparse usage text is NOT a crash. Add a test for the failing case if possible.

# runtime_no_entry
Goal needs a runnable console/CLI entry point but none was found (see ## Implementation status).
Pytest may already be green — do NOT rewrite the whole file with write_file (that truncates and loops).
NEXT: edit_file to APPEND only the missing entry point (call main). Keep existing functions intact.

# tests_already_green
BLOCKED: pytest already passed this run. Do NOT call run_tests again.
If ## Implementation status still lists gaps, edit_file to fix ONLY those gaps.
Otherwise finish with a short summary — further run_tests calls are blocked.

# blocked_shell_read
BLOCKED: do not use `type`/`cat`/`Get-Content` to read source files. NEXT tool MUST be read_file path="{{path}}" — it returns the FULL file. Judge completeness from ## Implementation status (functions, entry point, subcommands), never from byte size.

# impl_incomplete
Implementation is NOT finished — the runner will reject finish until these are fixed:
{{gaps}}
Trust ## Implementation status on this turn (not earlier thoughts). NEXT: insert_lines path="{{path}}" line={{line}} with a REAL block of missing logic (8+ lines: handler body / HTTP call / send / entry). Use the fence form:
<tool_call=insert_lines : {"path": "{{path}}", "line": {{line}}>
```
...code...
```
Do NOT use edit_file for ±3-line tweaks. Do NOT rewrite the whole file with write_file.

# impl_logic_missing
Implementation is a SKELETON — core behavior is still missing:
{{gaps}}
Do NOT nibble with edit_file (±3 lines) — the runner BLOCKS and reverts those. NEXT tool MUST be insert_lines path="{{path}}" line={{line}} with ALL missing logic in ONE fenced insert (HTTP/API + send/reply + bot.run/entry — at least ~8 lines). Example:
<tool_call=insert_lines : {"path": "{{path}}", "line": {{line}}>
```
    async with aiohttp...
    await message.channel.send(...)
bot.run(TOKEN)
```
Then the runner re-checks gaps.

# nibble_edit_blocked
BLOCKED: tiny edit/insert reverted — core gaps are still open:
{{gaps}}
edit_file ±3 lines will never finish this. NEXT tool MUST be insert_lines path="{{path}}" line={{line}} with a LARGE fenced block covering the gaps above (HTTP + send/reply + entry). Do not read the file again first unless you have never seen it.

# coding_complete
PHASE=CODE_COMPLETE | NEXT=write_file path="{{path}}" (COMPLETE file: imports + handlers + HTTP/send + entry). Fence the body. Do not plan in thought — emit the tool call.

# coding_extend
PHASE=CODE_EXTEND | NEXT=insert_lines path="{{path}}" line={{line}} | OPEN:
{{gaps}}
ONE fenced block (≥8 lines) that closes those gaps. No edit_file. No read_file first.

# coding_repair
PHASE=CODE_REPAIR | NEXT=write_file path="{{path}}" COMPLETE corrected file (fence).
Syntax broken OR file mashed (duplicate imports / glued comments) — never insert_lines/edit_file on a broken or mashed file. One clean rewrite only.

# gap_not_closed
BLOCKED: mutation kept the SAME gaps open — reverted:
{{gaps}}
NEXT: insert_lines path="{{path}}" line={{line}} with a LARGER fenced block that actually closes ≥1 gap above.

# gap_not_closed_rewrite
BLOCKED twice with no gap closed — escalate to full rewrite.
{{gaps}}
NEXT tool MUST be write_file path="{{path}}" with the COMPLETE corrected file (fence). No more tiny inserts.

# hollow_skeleton_blocked
BLOCKED: hollow skeleton kept on disk ({{min_lines}}+ lines of real logic required for this bot/API goal). Still missing:
{{gaps}}
NEXT: insert_lines path="{{path}}" with ALL missing logic in ONE fenced block (HTTP + send/reply + entry). Do not delete/rewrite the skeleton — extend it.

# impl_complete
These items are now done — do NOT re-apply the same fixes:
{{resolved}}
Trust ## Implementation status. NEXT: finish if the goal is met, or run a quick smoke/test — not another identical edit of closed work.

# goal_met_stop
GOAL ALREADY MET — do not edit more. Gaps are empty and required checks passed.
Do NOT call write_file/edit_file/edit_symbol again. NEXT: finish with a short summary of what was delivered (files + tests). Further edits will be blocked.

# work_already_done
BLOCKED loop: your thought re-asserts work that is already closed:
{{resolved}}
Do NOT edit/checkpoint those again. Trust ## Implementation status. NEXT: finish if the goal is met, or tackle only items still listed as open — never redo closed work.

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
{{opening}}

{{body}}

{{closing}}

# _fallback_summary.legacy
(unused — Agent._fallback_summary builds the status in code)

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
