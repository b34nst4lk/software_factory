# (auto) impl-01 blocked at cycle 1

Type: grilling
Status: open

## Question

Work unit **impl-01** (`greet(name) returns f'hello, {name}'`) hit a BLOCKED verdict at cycle 1. The verifier flagged ambiguity it will not assume:

- greet(None) behavior is unspecified by the decision

Resolve the ambiguity; the orchestrator will re-scan this ticket and re-inject the answer verbatim into the implementer and verifier prompts.

## Answer

<!-- filled by the wayfinder/human; on `Status: resolved` the orchestrator resumes -->
