# 13 — orchestrator: line-buffer stdout/stderr for live human-surfacing

Type: task
Status: resolved
Blocked by:
Found by: 07 (live smoke). Follow-up to 09.

## Question

When the orchestrator's stdout is redirected to a file (the background smoke run),
Python block-buffers it, so the human watching the log sees nothing until the process
exits. The smoke log showed only stderr warnings; the `impl-01 BLOCKED -> escalated`
and `impl-01: done` lines only flushed at exit — defeating 05 Q5's human-surfacing.

## Fix

Line-buffer stdout/stderr at the start of `cli.main`:

    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

Robust regardless of how the process is launched (vs relying on `python -u`).

## Answer

Fixed 2026-08-21. Added `cli.configure_live_output()` (reconfigures stdout/stderr to
`line_buffering=True`, tolerating streams without `reconfigure`) and call it at the top
of `main()`. The human watching a redirected smoke log now sees each line live (the
smoke's buffered-until-exit behavior is gone). Covered by `test_cli.py` (sets
line_buffering; tolerates streams without reconfigure; plus a `--mock` end-to-end
`main()` test).

<!-- filled when fixed -->