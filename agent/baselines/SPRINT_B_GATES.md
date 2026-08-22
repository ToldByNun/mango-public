# Sprint B+ gate decisions (measure→build→measure)

## B1 apply_patch — NOT SHIPPED

Checklist from plan:
- [ ] Post-A3 `edit_fail_rate` still high on multi-hunk scenarios — **no**: fake-suite edit recovery + write_file fallback covers the observed cases.
- [ ] `write_file` full-rewrite fallback too often / too destructive — **no** evidence in current golden/fake suite that requires unified diffs.
- [x] Written decision record in this file.

**Decision:** Do not introduce `apply_patch` yet. Prefer edit recovery (`grounded_ws`) + `write_file` fallback. Revisit when multi-hunk real-model smoke shows systematic failures.

`MANGO_APPLY_PATCH` remains `0` / unused.

## B2 Full Undo UI — deferred stub

Checkpoints (A1) + IPC `agent:undoLastMutation` / `continueStall` are wired. Full timeline picker UI deferred; Composer exposes a Continue control for stall kill-switch.

## B3 Repo map — deferred

Profile-dependent map can land after A5 latency baseline; not required to close the original tool/loop complaints.

## B4 Lint-on-edit / git opt-in — deferred

## B5 Settings presets — deferred
