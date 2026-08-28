# 27 — pr.merge_gate crashed on GitHub review `user` object (unhashable dict key)

Type: bug
Status: resolved
Blocked by:
Found by: 25 build (first run, 2026-08-28). Crashed the orchestrator at the first PR poll.
Resolved: 2026-08-28 (manual fix on main, commit 5550ed0).

## Question

`pr.merge_gate` built `states_by_user = {r.get("user", ""): r.get("state", "") ...}` —
using the raw GitHub review `user` field as a dict key. But GitHub's
`/pulls/N/reviews` returns `user` as an **object** `{"login": "sourcery-ai[bot]",
...}`, not a string. So the first review with a user raised
`TypeError: cannot use 'dict' as a dict key (unhashable type: 'dict')` and killed
the orchestrator.

Two latent bugs, both day-1 (blame 169f8be6):
1. `user` is an object; `merge_gate` used it as a key → crash.
2. `config.sourcery_reviewer_login` defaulted to `"sourcery-ai"` but the real bot
   login is `"sourcery-ai[bot]"` — so even past the crash, Sourcery would never be
   recognized.

The tests hid it: `test_pr.py` constructed reviews with `user` as a **string**
(`review(state, user)` → `{"user": user, ...}`), which does not match the real API
shape. The `api_reviews` test likewise used a string user. So the suite was green
against a fictional shape.

This did not bite 15/17 (the prior dogfooded builds) — likely because the human
merged on GitHub before Sourcery's review arrived (the poll saw empty reviews, or
the run was stopped/restarted around the merge).

## Answer

**Fixed in commit 5550ed0 (manual, on main).**

- `Gh.api_reviews` now **normalizes** each review to `{"user": <login>, "state":
  <state>}` at the fetch boundary — extracting `login` from the `user` object
  (handling dict / null / missing). Downstream consumers (`merge_gate` dict keys,
  `_format_comments`) get a hashable, readable login string. `merge_gate` and
  `_format_comments` are unchanged.
- `config.sourcery_reviewer_login` default → `"sourcery-ai[bot]"`.
- Tests updated: `test_api_reviews` feeds the real object shape and asserts the
  normalized output; new `test_api_reviews_normalizes_user_object_to_login`
  (regression for the crash) and `test_api_reviews_handles_missing_user`.
  `merge_gate` tests (string `user`) now match the normalized contract.

Suite 200 passed; ruff/black/mypy clean.

## Exposure: ticket 16 is now acute

The crash + restart exposed that the orchestrator **cannot resume an interrupted
run** (ticket 16): no status-seed from the frontmatter, and `worktree_add -b
impl-NN` fails on an existing branch. The 25-build restart required manually
closing the two open PRs, deleting the worktrees/branches, and re-running
impl-01/02 from scratch. 16 should be the next build so a crash/restart doesn't
discard in-flight work.