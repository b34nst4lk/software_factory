# Research 02 — Wire the three models as pi custom providers

**Ticket:** [02 — Wire the three models as pi custom providers](../issues/02-model-provider-wiring.md)
**Status:** in progress (verifier host pending human choice) · **Date:** 2026-08-19

## Finding 1 — live pi config already wires 2 of 3 models (single Ollama provider)

`~/.pi/agent/models.json` registers one provider, `ollama`, at `http://127.0.0.1:11434/v1`, `api: "openai-completions"`, `apiKey: "ollama"`, with three models:

| Model id | Role | contextWindow | input | `_launch` | Status |
|---|---|---|---|---|---|
| `glm-5.2:cloud` | Wayfinder / grilling / to-tickets | 1,000,000 | text | true | **wired + working** (it's this session's model; `defaultModel`/`defaultProvider` in settings.json) |
| `deepseek-v4-flash:cloud` | Implementer | (unset → pi reports 128K) | text | true | **wired + available** |
| `qwen3.5:4b` | (none assigned) | 262,144 | text+image, reasoning | true | local 4B model, pulled 3 weeks ago |

Source: `~/.pi/agent/models.json`, `~/.pi/agent/settings.json`, `pi --list-models` output (header: `provider model context max-out thinking images`).

So **glm-5.2 and deepseek-v4-flash are done** — both are Ollama-cloud tags (`:cloud`) served through the local Ollama daemon. Per-pane binding (ticket 03) is just `pi --model glm-5.2:cloud` / `pi --model deepseek-v4-flash:cloud`. No new provider needed for those two.

## Finding 2 — qwen3.6 is NOT available on the current Ollama setup

- `ollama show qwen3.6` and `qwen3.6:cloud` → **model not found**. Only `qwen3.5:4b` is pulled locally.
- There is an **open Ollama issue (#16115)** requesting `qwen3.6:35b-a3b-coding-bf16` be added to Ollama **Cloud Models** — i.e. qwen3.6 is *not yet* an Ollama cloud tag. So the map's assumption ("qwen3.6, Ollama cloud, TBD") is wrong: it isn't on Ollama cloud today.

Source: local `ollama show`/`ollama list`; https://github.com/ollama/ollama/issues/16115 (open, labels `model`,`cloud`).

## Finding 3 — qwen3.6 IS real and available via other OpenAI-compatible hosts

Qwen3.6 (released April 2026; 27B dense and 35B-A3B MoE) supports OpenAI-compatible chat completions **with tool use** (`--tool-call-parser qwen3_coder`), 262K context, thinking + `preserve_thinking` (recommended for agents). Access paths:

- **Alibaba Cloud Model Studio (DashScope)** — model id `qwen3.6-flash`, OpenAI-compatible endpoint:
  - Beijing: `https://dashscope.aliyuncs.com/compatible-mode/v1`
  - Singapore: `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`
  - US: `https://dashscope-us.aliyuncs.com/compatible-mode/v1`
  - auth: `DASHSCOPE_API_KEY`. Also offers an Anthropic-compatible interface.
- **Open weights** (HuggingFace/ModelScope, `Qwen/Qwen3.6-27B` / `Qwen3.6-35B-A3B`) — self-host via vLLM/SGLang, OpenAI-compatible at `http://localhost:8000/v1`. 27B ≈ needs ~27GB+ VRAM; 35B-A3B is 36B (3B active).

Source: https://huggingface.co/Qwen/Qwen3.6-27B , https://www.alibabacloud.com/blog/qwen3-6-35b-a3b-agentic-coding-power-now-open-to-all (API Usage, Coding & Agents).

## Finding 4 — recipe for whichever verifier path is chosen

pi `models.json` supports multiple providers. The existing `ollama` provider stays as-is for glm-5.2 + deepseek-v4-flash. The verifier gets its **own provider entry** depending on the chosen path:

**(a) DashScope `qwen3.6-flash`** (no local GPU needed, recommended):
```jsonc
{ "providers": {
    "dashscope": {
      "baseUrl": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
      "api": "openai-completions",
      "apiKey": "$DASHSCOPE_API_KEY",
      "models": [ { "id": "qwen3.6-flash", "reasoning": true, "contextWindow": 262144, "input": ["text","image"] } ]
    }
} }
```
Then bind per-pane via `pi --model dashscope/qwen3.6-flash`. Requires `DASHSCOPE_API_KEY` in env (pi resolves `$VAR` at request time). Set `compat.supportsDeveloperRole: false` if DashScope rejects the `developer` role.

**(b) Self-hosted open weights via local vLLM/SGLang** pointing pi at `http://localhost:8000/v1`, model id `Qwen/Qwen3.6-27B` (or `-35B-A3B`). Needs GPU.

**(c) Fall back to already-available `qwen3.5:4b`** (local, free, no new provider) — but it's a 4B model; weak for adversarial review of a deepseek-v4-flash implementer. Keep only as a smoke-test stand-in, not the production verifier.

## Finding 5 — Decision (human): verifier = `qwen3.5:cloud`, Ollama only

The human chose to keep **Ollama as the sole provider** and use `qwen3.5:cloud` as the verifier (declining DashScope / self-host / qwen3.6). Verified live: `ollama run qwen3.5:cloud "Reply with exactly: ok"` returns thinking + output, exit 0 — the `:cloud` tag resolves on Ollama cloud exactly like `glm-5.2:cloud`.

Tradeoff accepted: qwen3.5 is an older generation than the qwen3.6 originally discussed, so the verifier is somewhat weaker at adversarial review — but it is still a **different model family from the deepseek-v4-flash implementer**, so the cross-model blind-spot benefit (the whole point of ticket 02 / round-2 Q2) holds.

### Recipe — add one model entry to the existing `ollama` provider in `~/.pi/agent/models.json` (build step, not done in this research ticket)

Append to the `ollama` provider's `models` array:
```json
{
  "_launch": true,
  "id": "qwen3.5:cloud",
  "reasoning": true,
  "input": ["text", "image"],
  "contextWindow": 262144
}
```
Per-pane binding (from ticket 03): `pi --model qwen3.5:cloud` (or `ollama/qwen3.5:cloud`). No new provider, no new env var, no GPU.

## Final bindings

- ✅ Wayfinder / grilling / to-tickets → `glm-5.2:cloud` (ollama provider, already wired, working — it's this session).
- ✅ Implementer → `deepseek-v4-flash:cloud` (ollama provider, already wired).
- ✅ Verifier → `qwen3.5:cloud` (ollama provider; one model entry to add at build time).
- All three under the single `ollama` provider at `http://127.0.0.1:11434/v1`, `api: openai-completions`, `apiKey: ollama`. Ollama-only, as requested.