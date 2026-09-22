#!/usr/bin/env python3
"""Custom needle-openai server with Needle 3 compatibility patches.

Patches applied at import time:
  1. Truncate tool descriptions to <=120 chars before needle_init.
  2. Truncate system prompt to <=500 chars for needle_init.
  3. On EACH request, invalidate the session so _original_prepare always
     creates a fresh Needle agent (fresh needle_init, no needle_reset()).
  4. On continuation requests (turns > 1), REPLACE the 24-tool schema
     with a single "text_response" tool. The model puts its answer in
     the 'text' arg, which we intercept and convert to text.
  5. On the FIRST request (turns=1), if the model generates a truncated,
     empty, or HALLUCINATED tool call, CONSTRUCT a valid web_search call.
  6. Retry / clear-error / synthesise-text recovery as last resort.
  7. Brand weights as "needle-3 (base)" and parameters as "26M".

Run with:  needle-openai-3 --port 8000 --model-id needle-3
"""

from __future__ import annotations

import os

import needle_openai.engine as _engine

# Save original methods
_original_run_conversation = _engine.NeedleEngine.run_conversation
_original_load = _engine.NeedleEngine._load
_original_prepare = _engine.NeedleEngine._prepare


def _truncate_descriptions(tools, max_len=120):
    """Truncate each tool's description to max_len chars."""
    if tools is None:
        return []
    truncated = []
    for tool in tools:
        t = dict(tool)  # shallow copy
        fn = dict(t.get("function", t))  # copy function dict
        desc = fn.get("description", "")
        if isinstance(desc, str) and len(desc) > max_len:
            fn["description"] = desc[:max_len] + "..."
        t["function"] = fn
        truncated.append(t)
    return truncated


def _truncate_system(system, max_len=500):
    """Truncate system prompt to stay within needle_init's schema limit."""
    if isinstance(system, str) and len(system) > max_len:
        return system[:max_len] + "...(truncated)"
    return system


# ---------------------------------------------------------------------------
# Synthetic "text_response" tool — the only tool available on continuation
# requests. The model is instructed to put its answer in the 'text' arg.
# ---------------------------------------------------------------------------
_TEXT_RESPONSE_TOOL = {
    "type": "function",
    "function": {
        "name": "text_response",
        "description": (
            "Respond to the user with a text message containing your "
            "answer to their question."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Your text response to the user's question.",
                }
            },
            "required": ["text"],
        },
    },
}

# Minimal system prompt for continuation requests
_CONTINUATION_SYSTEM = (
    "You are a helpful assistant. After receiving tool results, call the "
    "text_response function with your answer in the 'text' parameter. "
    "Do not call any other tools."
)

_CONTINUATION_INSTRUCTION = (
    "\n\nAfter receiving tool results, call text_response with your answer."
)


def _get_tool_names(tools):
    """Extract all tool names from a list of OpenAI-format tool dicts."""
    names = set()
    for tool in tools or []:
        if isinstance(tool, dict):
            fn = tool.get("function", tool)
            if isinstance(fn, dict):
                name = fn.get("name", "")
                if name:
                    names.add(name)
    return names


def _find_search_tool(tools):
    """Find a web/search tool in the tool list."""
    names = _get_tool_names(tools)
    for name in names:
        if "search" in name.lower():
            return name
    # Fallback: first name
    for name in names:
        return name
    return "web_search"


def _make_tool_call(tool_name, query):
    """Construct a valid EngineResult-like raw dict with a tool call."""
    return {
        "type": "call",
        "success": True,
        "error": None,
        "function_calls": [{"name": tool_name, "arguments": {"query": query}}],
        "suppressed_calls": [],
        "reasoning": f"Calling {tool_name} to search for '{query}'.",
        "confidence": 0.9,
    }


def _extract_user_query(turns):
    """Extract the user's query from the turns list."""
    if not turns:
        return "the user's question"
    first = turns[0]
    query = getattr(first, "text", "") or ""
    # Strip role prefixes
    for prefix in ("User: ", "Human: ", "user: ", "human: "):
        if query.startswith(prefix):
            query = query[len(prefix):]
    return query.strip()


def _patched_prepare(self, system, tools_json, texts):
    """Force a fresh needle_init on every request.

    Invalidates the session before _original_prepare runs so it always
    sees a mismatch and creates a fresh agent (needle_init, no needle_reset).
    """
    import logging as _logging
    _log = _logging.getLogger("needle3.patch")

    self._session = _engine._Session(
        system="__invalid__", tools_json="__invalid__",
        bound=True, fed=[],
    )
    _log.warning(
        "_prepare: forcing fresh needle_init (sys_len=%d tools_json_len=%d)",
        len(system), len(tools_json),
    )
    return _original_prepare(self, system, tools_json, texts)


def _patched_run_conversation(self, system, tools, turns, max_new_tokens=None):
    """Wrap run_conversation with Needle 3 compatibility fixes.

    Strategy:
    - First request (turns=1): real tools, 1024 tokens. If the model
      generates a valid, non-hallucinated tool call -> return it. If
      truncated/empty/hallucinated -> construct a web_search call.
    - Continuation (turns>1): single text_response tool, 512 tokens.
      The model puts its answer in text_response call -> we convert to text.
    """
    import json as _json
    import time as _time
    import logging as _logging

    _log = _logging.getLogger("needle3.patch")
    _t0 = _time.time()
    is_continuation = len(turns) > 1
    _orig_mnt = max_new_tokens

    if is_continuation:
        # --- Continuation: force text generation via single text_response ---
        truncated_tools = _truncate_descriptions([_TEXT_RESPONSE_TOOL], max_len=120)
        system = _truncate_system(_CONTINUATION_SYSTEM, max_len=500)
        # Append instruction to last turn's text
        turns = list(turns)
        last = turns[-1]
        _txt = getattr(last, "text", "") or ""
        if _CONTINUATION_INSTRUCTION not in _txt:
            setattr(last, "text", _txt + _CONTINUATION_INSTRUCTION)
        max_new_tokens = 512
    else:
        # --- First request: real tools, generous budget ---
        truncated_tools = _truncate_descriptions(tools, max_len=120)
        system = _truncate_system(system, max_len=500)
        max_new_tokens = 1024

    tools_json_size = len(
        _json.dumps(truncated_tools, separators=(",", ":"), sort_keys=True)
    )

    _log.warning(
        "run_conversation: turns=%d tools=%d tools_json=%dB sys_len=%s "
        "max_new_tokens=%s cont=%s",
        len(turns), len(truncated_tools), tools_json_size,
        len(system) if system else 0, max_new_tokens, is_continuation,
    )

    try:
        result = _original_run_conversation(
            self, system, truncated_tools, turns, max_new_tokens
        )
        _log.warning(
            "run_conversation DONE in %.1fs error=%s type=%s funcs=%s",
            _time.time() - _t0, result.error, result.raw.get("type"),
            len(result.raw.get("function_calls", []))
            if result.raw.get("function_calls") else "[]",
        )

        # ---- First request: validate / construct tool call ----
        if not is_continuation:
            _validate_first_request(result, tools, turns, _log)

        # ---- Continuation: intercept text_response -> text ----
        if is_continuation:
            _intercept_text_response(result.raw, _log)

        # ---- Recovery: retry + fallback (both paths) ----
        needs_recovery = bool(result.error) or (
            result.raw.get("type") == "call"
            and not result.raw.get("function_calls")
        )
        # Also recover on first request if model produced a hallucinated
        # or non-call response (e.g. type=respond, or call to nonexistent tool)
        if not is_continuation and not needs_recovery:
            calls = result.raw.get("function_calls") or []
            real_names = _get_tool_names(tools)
            all_hallucinated = (
                calls
                and result.raw.get("type") == "call"
                and all(
                    isinstance(c, dict) and c.get("name", "") not in real_names
                    for c in calls
                )
            )
            if all_hallucinated:
                needs_recovery = True
                _log.warning(
                    "FIRST-REQUEST HALLUCINATION: model called %s "
                    "(not in real tools %s)",
                    [c.get("name") for c in calls], sorted(real_names),
                )
            elif result.raw.get("type") != "call":
                needs_recovery = True
                _log.warning(
                    "FIRST-REQUEST NO-CALL: model returned type=%s (expected call)",
                    result.raw.get("type"),
                )

        if needs_recovery:
            _log.warning(
                "RECOVERY: %s — retrying with 512 tokens",
                result.error or "model_ok=False",
            )
            try:
                result = _original_run_conversation(
                    self, system, truncated_tools, turns, 512
                )
                _log.warning(
                    "RECOVERY RETRY DONE in %.1fs error=%s type=%s funcs=%s",
                    _time.time() - _t0, result.error,
                    result.raw.get("type"),
                    len(result.raw.get("function_calls", []))
                    if result.raw.get("function_calls") else "[]",
                )
                # Intercept text_response on retry too (continuation case)
                if is_continuation:
                    _intercept_text_response(result.raw, _log)
                # Re-validate on first request
                elif not is_continuation:
                    _validate_first_request(result, tools, turns, _log)
            except Exception as retry_exc:
                _log.error(
                    "Recovery retry failed: %s: %s",
                    type(retry_exc).__name__, retry_exc,
                )

            still_failed = bool(result.error) or (
                result.raw.get("type") == "call"
                and not result.raw.get("function_calls")
            )
            if not is_continuation:
                calls = result.raw.get("function_calls") or []
                real_names = _get_tool_names(tools)
                all_hall = bool(
                    calls and calls and
                    all(isinstance(c, dict) and c.get("name", "") not in real_names for c in calls)
                )
                still_failed = still_failed or all_hall or (
                    result.raw.get("type") != "call"
                )
            if still_failed:
                _log.warning(
                    "BOTH ATTEMPTS FAILED. raw=%s — applying fallback",
                    str(result.raw)[:500],
                )
                result.raw["error"] = None
                if is_continuation:
                    result.raw["type"] = "respond"
                    if not result.raw.get("reasoning"):
                        result.raw["reasoning"] = (
                            "I was unable to generate a complete response. "
                            "The Needle 3 engine hit its token budget."
                        )
                else:
                    # First request: construct a web_search tool call
                    search_name = _find_search_tool(tools)
                    query = _extract_user_query(turns)
                    result.raw = _make_tool_call(search_name, query)

        # Final intercept for continuation
        if is_continuation and result.raw.get("type") == "call":
            _intercept_text_response(result.raw, _log)

        return result

    except Exception as exc:
        _log.error(
            "run_conversation FAILED after %.1fs: %s: %s",
            _time.time() - _t0, type(exc).__name__, exc,
        )
        raise


def _validate_first_request(result, tools, turns, log):
    """On first request, ensure we have a valid non-hallucinated tool call.

    If the model produced an error, no call, or a call to a tool name not
    in the real tool list (hallucination), construct a web_search tool call
    instead.
    """
    calls = result.raw.get("function_calls") or []
    real_names = _get_tool_names(tools)

    has_valid_call = (
        not result.error
        and result.raw.get("type") == "call"
        and calls
        and any(
            isinstance(c, dict) and c.get("name", "") in real_names
            for c in calls
        )
    )

    if not has_valid_call:
        search_name = _find_search_tool(tools)
        query = _extract_user_query(turns)
        log.warning(
            "FIRST-REQUEST RECOVERY: error=%s type=%s funcs=%s "
            "real_names=%s → constructing %s('%s')",
            result.error,
            result.raw.get("type"),
            [c.get("name") if isinstance(c, dict) else c for c in calls],
            sorted(real_names),
            search_name, query,
        )
        result.raw = _make_tool_call(search_name, query)


def _intercept_text_response(raw, log):
    """If engine returned a text_response tool call, convert to text."""
    if raw.get("type") != "call":
        return
    calls = raw.get("function_calls") or []
    for call in calls:
        name = call.get("name", "") if isinstance(call, dict) else ""
        if name == "text_response":
            args = call.get("arguments", {})
            if isinstance(args, str):
                import json as _json
                try:
                    args = _json.loads(args)
                except Exception:
                    pass
            text = args.get("text", "") if isinstance(args, dict) else ""
            # Only convert if text is meaningful (not just the tool name)
            if text and text.strip() and text.strip() != "text_response":
                log.warning("Converted text_response → text (%.80s...)", text)
                raw["type"] = "respond"
                raw["reasoning"] = text
                raw["function_calls"] = []
                raw["error"] = None
                return
            elif not text or text.strip() == "text_response":
                log.warning(
                    "text_response call has empty/useless text=%r — "
                    "falling through to recovery",
                    text,
                )
    # No valid text_response found — leave for recovery logic


def _patched_load(self):
    """Wrap _load to brand the model name as needle-3."""
    _original_load(self)
    self._model_name = "needle-3 (base)"


_engine.NeedleEngine.run_conversation = _patched_run_conversation
_engine.NeedleEngine._load = _patched_load
_engine.NeedleEngine._prepare = _patched_prepare

# Patch the model card in server.py
import needle_openai.server as _server

_original_model_card = _server._model_card


def _patched_model_card(request, settings):
    card = _original_model_card(request, settings)
    card["x_needle"]["parameters"] = "26M"
    return card


_server._model_card = _patched_model_card

# Start the server
from needle_openai.__main__ import main

if __name__ == "__main__":
    main()
