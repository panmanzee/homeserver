FROM python:3.11-slim

LABEL org.opencontainers.image.title="needle3-openai" \
      org.opencontainers.image.description="OpenAI-compatible API server for Needle 3" \
      org.opencontainers.image.source="https://github.com/cactus-compute/needle"

# Install system deps (curl for healthchecks, ca-certificates for HTTPS)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates util-linux && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -s /bin/bash needle

# Install cactus-needle (Needle 3) WITHOUT its heavy ML deps (jax, etc.)
# The native engine is a separate download at runtime, not a pip dep.
RUN pip install --no-deps cactus-needle==3.0.4

# Install the OpenAI-compatible wrapper WITHOUT pulling in cactus-needle (which
# would drag in the v2 pin); we already installed Needle 3 above.
RUN pip install --no-deps needle-openai==0.1.1

# Install the lightweight runtime deps that needle-openai needs.
RUN pip install fastapi uvicorn "pydantic>=2.6" huggingface_hub httpx

# Also install sse-starlette for streaming support
RUN pip install sse-starlette starlette

# ---- Patch needle-openai for Needle 3 branding -----------------------------
# The wrapper was written for Needle 2 (45M params). Needle 3 is 26M params.
# We patch the cosmetic strings so /v1/models and logs reflect Needle 3.
#
# engine.py:  model display name + pip install hint
# config.py:  default model_id
# server.py:  accepted model names, error message, parameter count
RUN sed -i 's/needle-2 (base)/needle-3 (base)/g' \
      /usr/local/lib/python3.11/site-packages/needle_openai/engine.py && \
    sed -i 's/cactus-needle==2.0.3/cactus-needle==3.0.4/g' \
      /usr/local/lib/python3.11/site-packages/needle_openai/engine.py && \
    sed -i 's/model_id: str = "needle-2"/model_id: str = "needle-3"/g' \
      /usr/local/lib/python3.11/site-packages/needle_openai/config.py && \
    sed -i 's/NEEDLE_MODEL_ID.*default.*needle-2/NEEDLE_MODEL_ID, "needle-3"/g' \
      /usr/local/lib/python3.11/site-packages/needle_openai/config.py && \
    sed -i 's/needle-2 needs/needle-3 needs/g' \
      /usr/local/lib/python3.11/site-packages/needle_openai/server.py && \
    sed -i 's/"needle-2", "needle2"/"needle-2", "needle2", "needle-3", "needle3"/g' \
      /usr/local/lib/python3.11/site-packages/needle_openai/server.py && \
    sed -i 's/"parameters": "45M"/"parameters": "26M"/g' \
      /usr/local/lib/python3.11/site-packages/needle_openai/server.py

# Pre-download the native engine so the first request doesn't stall.
# This fetches libneedle.so for linux-x86_64 into the cache.
RUN /usr/local/bin/python -c "import needle; needle.Needle(tools=[])" 2>/dev/null || true

# Create the cache dir as root; entrypoint re-creates/chowns on every start
# so bind-mounted volumes also work.
RUN mkdir -p /cache/needle /cache/huggingface && \
    chown -R needle:needle /cache

ENV NEEDLE_TELEMETRY=0 \
    DO_NOT_TRACK=1 \
    HF_HOME=/cache/huggingface \
    HF_HUB_CACHE=/cache/huggingface/hub \
    NEEDLE_CACHE_DIR=/cache/needle

WORKDIR /app
COPY tools.json /app/tools.json
COPY custom_server.py /app/custom_server.py
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh /app/custom_server.py && chmod -R 755 /app

# Entrypoint runs as root to fix /cache volume permissions, then
# drops to the non-root needle user before starting the server.
EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["--host", "0.0.0.0", "--port", "8000", "--model-id", "needle-3"]
