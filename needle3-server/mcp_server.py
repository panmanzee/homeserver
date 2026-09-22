#!/usr/bin/env python3
"""
MCP server wrapping Needle3 (Cactus Compute's 26M-param tool-calling model)
running locally at http://127.0.0.1:8000. Needle3 is fast and cheap compared
to a full LLM, so Hermes can consult it for quick structured judgment calls
(e.g. "is it safe to do X?") before taking a risky action, without spending
a full model turn.

Setup (this project uses ./mcp_venv, created with `python3 -m venv mcp_venv`):
    ./mcp_venv/bin/pip install mcp requests
Run:
    ./mcp_venv/bin/python3 mcp_server.py
"""

import json

import requests
from mcp.server.mcpserver import MCPServer

NEEDLE_URL = "http://127.0.0.1:8000/v1/chat/completions"
TOOL_NAME = "record_decision"

mcp = MCPServer("needle3-consult")


def _consult_decision(question: str, choices: list[str], context: str = "") -> dict:
    # Needle3 needs the choices spelled out in the prompt text itself, not
    # just the tool schema, or it defaults to a generic "query" argument
    # instead of following the "choice"/"reasoning" schema.
    body = f"{context}\n\n{question}" if context else question
    content = f"{body}\n\nChoices: {', '.join(choices)}"

    payload = {
        "model": "needle-3",
        "messages": [{"role": "user", "content": content}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": TOOL_NAME,
                    "description": "Record your decision and reasoning.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "choice": {
                                "type": "string",
                                "enum": choices,
                                "description": "Your final decision",
                            },
                            "reasoning": {
                                "type": "string",
                                "description": "Why you chose this",
                            },
                        },
                        "required": ["choice", "reasoning"],
                    },
                },
            }
        ],
        "tool_choice": {"type": "function", "function": {"name": TOOL_NAME}},
    }

    try:
        resp = requests.post(NEEDLE_URL, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        tool_calls = data["choices"][0]["message"]["tool_calls"]
        args = json.loads(tool_calls[0]["function"]["arguments"])
        x_needle = data.get("x_needle", {})

        return {
            "choice": args.get("choice"),
            "confidence": x_needle.get("confidence"),
            "reasoning": args.get("reasoning"),
            "raw_needle_type": x_needle.get("type"),
        }
    except requests.exceptions.RequestException as e:
        return {"error": f"could not reach Needle3 server at {NEEDLE_URL}: {e}"}
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        return {"error": f"unexpected response shape from Needle3: {e}"}


@mcp.tool()
def consult_decision(question: str, choices: list[str], context: str = "") -> dict:
    """Consult Needle3 (a fast local decision model) for a quick structured
    judgment call among fixed choices. Use before risky actions when you
    want a fast, cheap second opinion rather than a full LLM turn."""
    return _consult_decision(question, choices, context)


if __name__ == "__main__":
    mcp.run()
