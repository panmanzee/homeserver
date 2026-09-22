# Needle3 OpenAI-compatible API Server

An OpenAI-compatible HTTP API server wrapping [Needle 3](https://github.com/cactus-compute/needle) — Cactus Compute's 26M-parameter tool-calling model that runs on CPU.

Needle 3 is not a chat model — it emits tool calls or nothing at all (no free-form text generation). It's designed for fast, structured decisions: tool routing, classification, extraction, and on-device automation. At ~6000 tok/s prefill on a warm CPU, it's ideal for low-latency first-pass decisions where a full LLM would be overkill.

## What this server provides

- `POST /v1/chat/completions` — OpenAI-compatible chat with tools
- `POST /v1/completions` — Legacy text completion
- `GET /v1/models` — Model discovery
- `GET /health` — Readiness + queue depth
- `x_needle` response header — calibrated confidence, reasoning, decode speed

## Quick start (Docker)

```bash
docker compose up -d
curl http://localhost:8000/health
```

## Direct usage (no Docker)

```bash
# Install Needle 3 + wrapper
pip install --no-deps cactus-needle==3.0.4
pip install --no-deps needle-openai
pip install fastapi uvicorn pydantic huggingface_hub httpx

# Run
needle-openai --host 0.0.0.0 --port 8000 --model-id needle-3
```

## First start

On first launch, the server downloads the native engine (~35 MB of weights from HuggingFace) into `/cache`. Subsequent starts are instant.

## Configuration

| Env var              | Default         | Description                                   |
|----------------------|-----------------|-----------------------------------------------|
| `NEEDLE_MODEL_ID`    | `needle-3`      | Model id advertised in `/v1/models`           |
| `NEEDLE_PORT`        | `8000`          | Server port                                   |
| `NEEDLE_HOST`        | `0.0.0.0`       | Bind address                                  |
| `NEEDLE_TELEMETRY`   | `0`             | Disable Cactus usage telemetry                |
| `NEEDLE_WEIGHTS`     | (none)          | Path to a tuned `.cact` archive (optional)    |
| `NEEDLE_API_KEY`     | (none)          | Optional bearer-token auth                    |

## Integrating with Hermes as an MCP tool (recommended)

`mcp_server.py` wraps this server as a Hermes-native MCP tool,
`consult_decision(question, choices, context)`. Hermes can call it mid-conversation
to get a fast, free, local yes/no-style judgment (with a calibrated confidence
score) before a risky action, without switching the whole session's model.

```bash
python3 -m venv mcp_venv
./mcp_venv/bin/pip install mcp requests
```

Register it in `~/.hermes/config.yaml` (use `hermes config set`, never hand-edit):

```bash
hermes config set mcp_servers.needle3.command /home/pan/homeserver/needle3-server/mcp_venv/bin/python3
hermes config set mcp_servers.needle3.args '["/home/pan/homeserver/needle3-server/mcp_server.py"]'
hermes config set mcp_servers.needle3.timeout 30
```

Requires the Needle3 OpenAI-compatible server (below) running at
`http://127.0.0.1:8000`. Restart Hermes to pick up the new MCP server (no
hot-reload). Test standalone with `./mcp_venv/bin/python3 mcp_server_test.py`.

Needle3's confidence is often low/noisy for open-ended judgment calls (it's a
26M-param tool-router, not a reasoning model) — treat its output as one weak
signal, not an authoritative gate, especially for genuinely risky actions.

## Integrating with Hermes as a full model swap (alternative)

1. Start the server: `docker compose up -d` (listens on `http://localhost:8000`)
2. Add a custom provider alias in Hermes:

```bash
hermes config set model.aliases.needle3 \
  '{"model":"needle-3","provider":"custom","base_url":"http://host.docker.internal:8000/v1"}'
```

On the homeserver, use the host IP directly:

```bash
hermes config set model.aliases.needle3 \
  '{"model":"needle-3","provider":"custom","base_url":"http://127.0.0.1:8000/v1"}'
```

3. Switch models in Hermes:

```
/model needle3
```

### Use case

Because Needle 3 is a pure tool-calling model with calibrated confidence, the recommended pattern is:

- Use a full LLM (Claude, GPT, etc.) for the main conversation.
- Route cheap, high-volume, or latency-sensitive decisions through Needle 3 by switching the model alias.
- Gate on `x_needle.confidence` — above 0.9 act automatically, below 0.7 escalate to a larger model.

## Fidelity notes

- Needle 3 emits **tool calls only** — when no tool applies, the `reasoning` trace is returned as `content` with `finish_reason: "stop"`.
- Decoding is deterministic — `temperature`, `top_p`, `seed` are accepted but ignored.
- Long inputs truncate silently; gate on `confidence` (0.0 means truncation likely occurred).
- Single-request-at-a-time per container; scale horizontally with multiple containers behind a load balancer.

## Patches applied

This server ships a `custom_server.py` entry point that applies compatibility
patches at import time on top of `needle-openai 0.1.1`:

1. **Tool description truncation** — truncates each tool description to
   ≤120 chars. Needle 3's `needle_init` rejects tool schemas that push the
   combined system+tables payload past ~22 KB. Hermes sends 24 tools totaling
   ~38 KB, which triggers a silent `needle_init failed` crash.
2. **System prompt truncation** — truncates the system message to ≤500 chars.
   Hermes' system prompt is ~19 KB and must be shortened to coexist with the
   tool schemas within the engine limit.
3. **Branding** — model id, weights name, and parameter count are overridden
   to reflect Needle 3 (26 M params) rather than the Needle 2 branding that
   `needle-openai` defaults to.
4. **Served model set** — `needle-3` and `needle3` are added to the accepted
   model-name set in `/v1/models/{model_id}` so strict-model mode also works.
