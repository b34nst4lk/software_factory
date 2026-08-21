"""CLI entrypoint for the software-factory orchestrator.

Usage:
    python -m cli <effort> [impl-glob] [--cycle-cap N] [--no-approve]
                            [--mock] [--pr-stage on|off] [--repo PATH]
                            [--gh-repo O/R] [--worktree-parent PATH]

``<effort>`` is the effort slug (e.g. ``software-factory``) under ``.scratch/``; the
impl glob defaults to ``.scratch/<effort>/impl/*.md``. ``--mock`` swaps herdr/gh/gitops
for deterministic stubs (tests). ``--pr-stage off`` skips GitHub PR/Sourcery (smoke runs
with a throwaway branch). ``--no-approve`` disables pi's interactive trust prompt in
worker panes (autonomous scoped runs).
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from collections.abc import Sequence

import config as config_mod
import gitops
import herdr
import pr as pr_mod
import run
import tickets


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="sf-orchestrator", description=__doc__.splitlines()[0])
    p.add_argument("effort", help="effort slug under .scratch/ (e.g. software-factory)")
    p.add_argument(
        "impl_glob",
        nargs="?",
        default=None,
        help="impl ticket glob (default: .scratch/<effort>/impl/*.md)",
    )
    p.add_argument("--repo", default=os.getcwd(), help="repo root path (default: cwd)")
    p.add_argument("--cycle-cap", type=int, default=config_mod.DEFAULT_CYCLE_CAP)
    p.add_argument("--no-approve", action="store_true", help="skip pi interactive trust prompt")
    p.add_argument("--mock", action="store_true", help="use herdr/gh/gitops stubs (tests)")
    p.add_argument(
        "--pr-stage",
        choices=["on", "off"],
        default="on",
        help="GitHub PR + Sourcery stage (off for throwaway smoke runs)",
    )
    p.add_argument("--gh-repo", default="", help="GitHub repo as O/R for the PR stage")
    p.add_argument("--worktree-parent", default=None, help="where to create impl/NN worktrees")
    p.add_argument(
        "--herdr-session", default="", help="herdr --session <name> (the headless server socket)"
    )
    p.add_argument(
        "--implementer-env-hint",
        default="",
        help="repo-specific test-runner hint injected into the implementer prompt",
    )
    return p.parse_args(argv)


def _stdin() -> str:
    try:
        return input()
    except EOFError:
        # unattended/background run with no tty: treat EOF as quit so we don't hang.
        return "q"


def configure_live_output(*, stdout: object | None = None, stderr: object | None = None) -> None:
    """Line-buffer stdout/stderr so a human watching a redirected log sees each line
    live (Python block-buffers a non-tty stream otherwise — 05 Q5 human-surfacing).
    """
    for stream in (stdout or sys.stdout, stderr or sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(line_buffering=True)


def main(argv: Sequence[str] | None = None) -> int:
    configure_live_output()
    args = parse_args(argv)
    impl_glob = args.impl_glob or os.path.join(args.repo, ".scratch", args.effort, "impl", "*.md")
    cfg = config_mod.default(args.repo, args.effort, impl_glob).with_overrides(
        cycle_cap=args.cycle_cap,
        no_approve=args.no_approve,
        mock=args.mock,
        pr_stage=(args.pr_stage == "on"),
        gh_repo=args.gh_repo,
        worktree_parent=args.worktree_parent or os.path.dirname(args.repo),
        herdr_session=args.herdr_session,
        implementer_env_hint=args.implementer_env_hint,
    )
    paths = sorted(glob.glob(impl_glob))
    if not paths:
        print(f"no impl tickets matching {impl_glob}", file=sys.stderr)
        return 2
    units = tickets.parse_impl_files(paths)
    hd = herdr.make_herdr(mock=cfg.mock, session=cfg.herdr_session)
    gh = pr_mod.make_gh(mock=cfg.mock)
    gops = gitops.make_gitops(mock=cfg.mock, repo=cfg.repo_path, base=cfg.repo_path)
    orch = run.Orchestrator(
        config=cfg,
        herdr=hd,
        gh=gh,
        gitops=gops,
        units=units,
        stdin=_stdin,
    )
    result = orch.run()
    for uid, status in result.items():
        print(f"{uid}: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
