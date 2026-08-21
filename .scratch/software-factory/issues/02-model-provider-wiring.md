# 02 — Wire the three models as pi custom providers

Type: research
Status: resolved
Blocked by:

## Question

Confirm how to register each model as a pi custom provider so the implementer and verifier run as pi sessions, and Wayfinder/to-tickets sessions are reproducible:
- **glm-5.2** (Ollama cloud) — already the session model; confirm its pi provider config so it's reusable for wayfinder/to-tickets sessions.
- **deepseek-v4-flash** (DeepSeek platform; OpenAI-compatible chat completions + Responses API) — the implementer.
- **qwen3.6** — the verifier. Confirm its host (Ollama cloud?), OpenAI-compatible endpoint, context window, and tool-use support.

Read pi's custom-provider + model docs (`docs/custom-provider.md`, `docs/models.md`) under the pi install path (`/usr/local/lib/node_modules/@earendil-works/pi-coding-agent/`) and produce a concrete provider+model config recipe (base_url, model id, auth env var) per model. Output: a context pointer here with the recipe; nothing built.

## Answer

Resolved 2026-08-19. Two of three models were already wired in the live `~/.pi/agent/models.json` under one `ollama` provider (`http://127.0.0.1:11434/v1`, `openai-completions`): **glm-5.2:cloud** (Wayfinder/to-tickets, working — it's this session) and **deepseek-v4-flash:cloud** (implementer). The verifier was the gap: qwen3.6 is **not** on Ollama cloud (open issue ollama/ollama#16115). The human chose **Ollama-only**, so the verifier is **qwen3.5:cloud** — verified live (`ollama run qwen3.5:cloud` responds, exit 0). Cross-model review still holds (Qwen vs DeepSeek, different families); qwen3.5 is older than the originally-discussed qwen3.6, a accepted tradeoff for Ollama-only.

Recipe (build step, not applied here): add one entry to the `ollama` provider's `models` array — `{ "_launch": true, "id": "qwen3.5:cloud", "reasoning": true, "input": ["text","image"], "contextWindow": 262144 }`. Per-pane binding: `pi --model qwen3.5:cloud`.

Full findings: [research/02-model-provider-wiring.md](../research/02-model-provider-wiring.md)

Unblocks: 07 (all three provider bindings now known). Build action for 07: apply the models.json entry above.