# 20 — Parameterization: root config + per-repo bindings, worktrees inherit

Type: task
Status: open
Blocked by:
Found by: 17 grilling (deferred from 17). Map "Not yet specified: Parameterization".

## Question

The factory is a prototype built in this repo; the destination is to generalize it as the
**base for arbitrary target repos/projects**. Open questions deferred from ticket 17's
grilling (the user's forward-looking vision: "the factory will eventually be used in
other repos and projects; configurations set up in the root git worktree folder, and
every worktree picks up the details from the root config in the repo"):

1. **Where does per-repo config live, and how do worktrees/workers get it?**
   - A **committed** config file at the repo root (e.g. `factory.toml` / `.factory/config`)
     that worktrees inherit via `git checkout` (git-tracked), OR
   - A **gitignored** config in `.factory/` that only the orchestrator reads and threads
     to workers (like the `state.db` from 17).
   17 deliberately introduced only the gitignored `.factory/` *runtime-state* folder +
   the orchestrator-threading pattern (for `state.db`), so as not to paint into a corner.
   This ticket decides the **config** mechanism.
2. **What is configurable per repo?** (from the map: per-repo tracker path, model bindings,
   repo path as config; plus effort slug, `gh-repo`, `worktree-parent`, cycle-cap,
   test-runner env-hint, pr-stage.) Which of these move from CLI flags / `models.json`
   into a per-repo config?
3. **Multi-repo ergonomics**: how does a target repo opt into the factory? A `factory
   init` that drops a config + the orchestrator? A shared orchestrator binary pointed at
   a repo? The thin-layer-over-existing-skills principle still holds — reuse, don't
   rebuild the skills.
4. **Interaction with 16/17**: config + log/state (the `.factory/` folder) should be
   designed together. 17 put `state.db` in gitignored `.factory/`; this ticket decides
   whether config joins it there (gitignored, orchestrator-threaded) or lives as a
   committed file worktrees inherit.

Not blocked by 16/17, but should not *start* until 16/17 settle the durability/state
shape (so the config mechanism is consistent with it).

## Build (to settle — grill further when picked up)

- Decide committed-vs-gitignored config + worktree inheritance mechanism.
- Define the configurable surface + a config schema (TOML?).
- Define the multi-repo onboarding path (`factory init`?).
- Keep it a thin layer; don't rebuild the matt pocock skills.

## Answer

<!-- filled when resolved -->