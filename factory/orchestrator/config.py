"""Configuration: model ids, timeouts, reviewer logins, poll cadences, paths.

All knobs the orchestrator needs in one frozen record. The CLI overlays a few flags
(``--cycle-cap``, ``--no-approve``, ``--mock``, ``--pr-stage``) onto :func:`default`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace

IMPLEMENTER_MODEL = "deepseek-v4-flash:cloud"
VERIFIER_MODEL = "qwen3.5:cloud"

DEFAULT_CYCLE_CAP = 5
PROMPT_TIMEOUT_MS = 600_000  # 10 min per worker turn
PR_POLL_CADENCE_S = 60  # gh api reviews poll
SOURCERY_TIMEOUT_S = 600  # ~10 min
FAILOVER_BACKOFF_S = (5, 15, 45)  # 3 exponential retries (06 Q5)
FAILOVER_RETRIES = 3
READ_LINES = 200
ARCHIVE_PREFIX = "archive/"


@dataclass(frozen=True)
class Config:
    repo_path: str
    effort: str
    impl_glob: str
    implementer_model: str = IMPLEMENTER_MODEL
    verifier_model: str = VERIFIER_MODEL
    cycle_cap: int = DEFAULT_CYCLE_CAP
    no_approve: bool = False
    mock: bool = False
    pr_stage: bool = True
    prompt_timeout_ms: int = PROMPT_TIMEOUT_MS
    pr_poll_cadence_s: int = PR_POLL_CADENCE_S
    sourcery_timeout_s: int = SOURCERY_TIMEOUT_S
    read_lines: int = READ_LINES
    sourcery_reviewer_login: str = "sourcery-ai"
    human_login: str = "human-reviewer"
    gh_repo: str = ""
    worktree_parent: str = ".."
    herdr_session: str = ""  # herdr --session <name>; "" = default socket
    db_path: str = ""  # per-repo narrative DB; default resolved in default()
    implementer_env_hint: str = ""  # repo-specific test-runner hint injected into the impl prompt

    def with_overrides(self, **kw: object) -> Config:
        return replace(self, **{k: v for k, v in kw.items() if v is not None})  # type: ignore[arg-type]

    @property
    def impl_dir(self) -> str:
        import os

        return os.path.join(self.repo_path, ".scratch", self.effort, "impl")

    @property
    def issues_dir(self) -> str:
        import os

        return os.path.join(self.repo_path, ".scratch", self.effort, "issues")


def default(repo_path: str, effort: str, impl_glob: str) -> Config:
    return Config(
        repo_path=repo_path,
        effort=effort,
        impl_glob=impl_glob,
        db_path=os.path.join(repo_path, ".factory", "state.db"),
    )
