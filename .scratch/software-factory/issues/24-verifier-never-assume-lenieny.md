# 24 — verifier never-assume leniency (gate 2 rationalizes instead of escalating)

Type: grilling
Status: open
Blocked by:
Found by: 15 build (dogfood). Split off from 14's grilling (2026-08-27).

## Question

During the decision-15 build, the verifier **PASSed the `parse_trailer` duplication**
instead of escalating it. `impl-02` duplicated `verdict.parse_trailer` as a local
`_parse_trailer` (with an honest comment: "Mirrors impl-01's verdict.parse_trailer
contract, which is not present on this branch") because its dependency's code was not
in its worktree (see ticket 19). The verifier *rationalized* the duplication to PASS
instead of BLOCKing for Wayfinder.

That is a never-assume failure, but in the **judgment** layer, not the test-strength
layer. The standing rule (06) says: the verifier never assumes; ambiguity → a new
Wayfinder ticket, never a guess. Gate 2 (contradictions) is the dedicated escalation
gate. Here the verifier *explained away* a contradiction (a dependent duplicating its
dependency's code because the dependency's code is missing) rather than escalating it.
Explaining-away is leniency; the gate should have BLOCKed ("a dependent is duplicating
a dependency's contract — is this a `depends_on`/worktree defect? escalate to
Wayfinder").

This is distinct from test-strength (14): 14 is the *deterministic* gap (a check that
never ran); 24 is the *verifier judgment* gap (the LLM ran, but was too lenient). 06 Q7
draws the line — judgment stays in the verifier.

Grill to settle:

- Is the leniency a **gate-2 prompt** defect (the contradictions-gate prompt does not
  name "explaining-away a contradiction" as a BLOCK trigger), or a **model-capability**
  defect (qwen3.5 can't hold the never-assume bar on subtle contradictions)?
- If a prompt defect: what is the gate-2 BLOCK trigger wording? (Candidate: "if the
  implementer works around a missing dependency by duplicating its contract, BLOCK and
  escalate — that signals a `depends_on`/worktree defect, not an implementer choice.")
- If a model-capability defect: does the final-verifier model change (decision 14 now
  binds the final verifier to `glm-5.3-flash:cloud`) raise or lower this risk? glm-5.3-flash
  is a stronger reasoner than qwen3.5, so capability may improve — but the prompt must
  still name the trigger, since a stronger model can also rationalize.
- Interaction with 14: the deterministic mutation audit (14 Q5) is the backstop for
  *test* teeth, not for *verifier judgment* leniency. 24 must not rely on the audit; it
  is a verifier-prompt fix.

## Answer

<!-- filled when resolved -->