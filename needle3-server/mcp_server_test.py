#!/usr/bin/env python3
"""Standalone test: calls the Needle3 decision function directly (no MCP
protocol involved) to prove the HTTP call path to Needle3 works end to end.

Run: ./mcp_venv/bin/python3 mcp_server_test.py
"""

import json

from mcp_server import _consult_decision

result = _consult_decision(
    question="Is it safe to restart nginx on this server right now?",
    choices=["yes", "no"],
)

print(json.dumps(result, indent=2))
