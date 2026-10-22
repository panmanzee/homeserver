"""
Jev decision-support server — replaces needle3 as the general-purpose
"programmable common sense" backend for this homelab.

Exposes the same general shape needle3 had (/health, /decide) so any
existing caller (Hermes MCP tool, n8n workflow, etc.) can point at this
service instead with minimal changes.

Backed by TypeSafe's Jev model (https://typesafe.ai) instead of a local
26M-param model — real hosted inference, requires TYPESAFE_API_KEY.
"""
import os
import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, Score

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("jev-decision-server")

TYPESAFE_API_KEY = os.environ.get("TYPESAFE_API_KEY", "")
MODEL = os.environ.get("JEV_MODEL", "jev-latest")

app = FastAPI(title="jev-decision-server")


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL, "backend": "typesafe-jev"}


class NoulRequest(BaseModel):
    state: Any
    question: str
    true_meaning: str | None = None
    false_meaning: str | None = None


class ChoiceRequest(BaseModel):
    state: Any
    question: str
    options: list[str] | None = None
    criteria: dict[str, str] | None = None  # option -> description, richer than bare options


class ScoreRequest(BaseModel):
    state: Any
    question: str
    levels: list[str]


def _client() -> AsyncTypeSafeClient:
    if not TYPESAFE_API_KEY:
        raise HTTPException(500, "TYPESAFE_API_KEY not configured")
    return AsyncTypeSafeClient(api_key=TYPESAFE_API_KEY)


@app.post("/decide/yesno")
async def decide_yesno(req: NoulRequest):
    """Generic yes/no judgment. Mirrors needle3's advisory 'consult_decision'
    use case: ask a bounded question with context, get back a probability."""
    criteria = {}
    if req.true_meaning:
        criteria["true"] = req.true_meaning
    if req.false_meaning:
        criteria["false"] = req.false_meaning

    async with _client() as client:
        resp = await client.system_one(
            state=req.state,
            model=MODEL,
            questions={
                "answer": Noul(instructions=req.question, criteria=criteria or None)
            },
        )
    ans = resp.nouls["answer"]
    return {"probability_yes": ans.noul}


@app.post("/decide/gated")
async def decide_gated(req: ChoiceRequest):
    """Confidence-gated Choice: answer with Jev, but flag low-confidence
    calls for escalation to a stronger/human reviewer instead of trusting
    them blindly. This is the pattern that actually worked in testing —
    NOT a cascade of narrower questions (that was tried and made things
    worse; see this repo's eval history / typesafe-ai skill notes).

    On a 397-article real eval (newsfeed importance labeling vs. Claude
    Haiku / Gemini Flash ground truth):
      threshold 0.7 -> escalate 37.8% of traffic, 93.7% effective accuracy
                        (the escalated 37.8% get the ground-truth label
                        anyway since they go to the strong model), ~70%
                        cost savings vs sending everything to the strong model.
      threshold 0.5 -> escalate 21.4%, 89.9% effective accuracy, ~83% savings.
    Tune `escalate_below` to the accuracy/cost tradeoff that fits the task;
    higher-stakes tasks should use a higher threshold (escalate more).
    """
    if req.criteria:
        criteria = {k: v for k, v in req.criteria.items()}
    elif req.options:
        criteria = {opt: None for opt in req.options}
    else:
        raise HTTPException(400, "must provide either 'options' or 'criteria'")

    async with _client() as client:
        resp = await client.system_one(
            state=req.state,
            model=MODEL,
            questions={"answer": Choice(instructions=req.question, criteria=criteria)},
        )
    ans = resp.choices["answer"]
    escalate_below = float(os.environ.get("JEV_ESCALATE_BELOW", "0.7"))
    return {
        "choice": ans.choice,
        "probabilities": ans.probabilities,
        "confidence": ans.confidence,
        "escalate": ans.confidence < escalate_below,
        "escalate_threshold": escalate_below,
        "usage": {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens},
    }


@app.post("/decide/choice")
async def decide_choice(req: ChoiceRequest):
    """Pick one option from a defined set, with full probability distribution.
    Pass `criteria` (option -> description) for richer discrimination than
    bare option names; falls back to `options` (bare names, no description)."""
    if req.criteria:
        criteria = {k: v for k, v in req.criteria.items()}
    elif req.options:
        criteria = {opt: None for opt in req.options}
    else:
        raise HTTPException(400, "must provide either 'options' or 'criteria'")

    async with _client() as client:
        resp = await client.system_one(
            state=req.state,
            model=MODEL,
            questions={
                "answer": Choice(instructions=req.question, criteria=criteria)
            },
        )
    ans = resp.choices["answer"]
    return {
        "choice": ans.choice,
        "probabilities": ans.probabilities,
        "confidence": ans.confidence,
        "usage": {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens},
    }


@app.post("/decide/score")
async def decide_score(req: ScoreRequest):
    """Rate state along an ordered rubric (2-10 levels)."""
    async with _client() as client:
        resp = await client.system_one(
            state=req.state,
            model=MODEL,
            questions={
                "answer": Score(instructions=req.question, criteria=req.levels)
            },
        )
    ans = resp.scores["answer"]
    return {
        "score": ans.score,
        "legend": ans.legend,
        "probabilities": ans.probabilities,
        "confidence": ans.confidence,
    }
