"""Tool-using triage agent: a short function-calling loop, then a forced structured answer.

Never raises: run_agent returns None on any failure so the caller can fall back to the
single-shot classifier (and from there to the static fallback).
"""
import json
import logging
import math
import os
import time
import uuid
from dataclasses import dataclass, field

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

import embeddings
from llm_classifier import (
    Classification, ClassificationResult, call_with_backoff, get_client, load_prompt, validate,
)
from llm_logging import log_llm_call
from models import Complaint

log = logging.getLogger("triage.agent")

PROMPT_VERSION = "agent_v1"
MAX_TURNS = 3
OVERALL_TIMEOUT = 40.0  # seconds for the whole agent run (the free tier often needs 5-20 s per call)

# Static mapping keeps department names consistent instead of free text.
DEPARTMENTS = {
    "streetlight": "Public Works - Street Lighting",
    "pollution": "Environmental Health",
    "water": "Water Utility",
    "waste": "Solid Waste Services",
    "energy": "Austin Energy",
    "crowd_monitoring": "Public Safety - Event Management",
    "other": "General Services",
}


class AgentAnswer(Classification):
    duplicate_of: str | None = None
    reasoning: str = ""


@dataclass
class AgentResult:
    classification: ClassificationResult
    duplicate_of: uuid.UUID | None
    trace: list
    text_vector: list[float] | None = None


@dataclass
class Context:
    db: Session
    text: str
    latitude: float | None
    longitude: float | None
    seen_ids: set = field(default_factory=set)  # ids returned by tools in this run
    text_vector: list[float] | None = None


def _brief(c: Complaint, **extra) -> dict:
    return {"id": str(c.id), "summary": c.summary, "status": c.status.value, "category": c.category.value, **extra}


def find_similar_complaints(ctx: Context, text: str, k: int = 3) -> list[dict]:
    if ctx.text_vector is None:
        ctx.text_vector = embeddings.embed_text(text)
    found = embeddings.search(ctx.db, text, max(1, min(int(k), 5)), vector=ctx.text_vector)
    out = [_brief(c, similarity=round(sim, 3)) for c, sim in found]
    ctx.seen_ids.update(r["id"] for r in out)
    return out


def lookup_department(ctx: Context, category: str) -> dict:
    return {"category": category, "department": DEPARTMENTS.get(category, DEPARTMENTS["other"])}


def haversine_m(lat1, lng1, lat2, lng2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(a))


def get_nearby_complaints(ctx: Context, latitude: float, longitude: float, radius_m: int = 200) -> list[dict]:
    rows = ctx.db.scalars(select(Complaint).where(Complaint.latitude.is_not(None))).all()
    near = [(haversine_m(latitude, longitude, c.latitude, c.longitude), c) for c in rows]
    out = [_brief(c, distance_m=round(d)) for d, c in sorted(near, key=lambda p: p[0]) if d <= radius_m][:5]
    ctx.seen_ids.update(r["id"] for r in out)
    return out


TOOL_FUNCS = {
    "find_similar_complaints": find_similar_complaints,
    "lookup_department": lookup_department,
    "get_nearby_complaints": get_nearby_complaints,
}


def tool_specs(has_coords: bool) -> list[dict]:
    def spec(name, description, properties, required):
        return {"type": "function", "function": {
            "name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required}}}

    specs = [
        spec("find_similar_complaints", "Search existing complaints by meaning to detect duplicates.",
             {"text": {"type": "string"}, "k": {"type": "integer", "description": "results to return, default 3"}}, ["text"]),
        spec("lookup_department", "Get the official department name for a category.",
             {"category": {"type": "string"}}, ["category"]),
    ]
    if has_coords:
        specs.append(spec(
            "get_nearby_complaints", "Find existing complaints within a radius of a location.",
            {"latitude": {"type": "number"}, "longitude": {"type": "number"}, "radius_m": {"type": "integer"}},
            ["latitude", "longitude"]))
    return specs


def run_agent(db: Session, text: str, latitude: float | None, longitude: float | None) -> AgentResult | None:
    client = get_client()
    model = os.getenv("LLM_MODEL", "").strip()
    if client is None or not model:
        return None

    started = time.perf_counter()
    ctx = Context(db=db, text=text, latitude=latitude, longitude=longitude)
    trace: list[dict] = []
    messages = [
        {"role": "system", "content": load_prompt(PROMPT_VERSION)},
        {"role": "user", "content": text},
    ]
    if latitude is not None and longitude is not None:
        messages.append({"role": "system", "content": f"The complaint is located at latitude {latitude}, longitude {longitude}."})
    tools = tool_specs(latitude is not None and longitude is not None)

    def check_time():
        if time.perf_counter() - started > OVERALL_TIMEOUT:
            raise TimeoutError("agent exceeded its overall time limit")

    def timed_call(fn, ok_usage=lambda r: getattr(r, "usage", None)):
        t0 = time.perf_counter()
        try:
            resp = call_with_backoff(fn)
        except Exception as exc:  # noqa: BLE001
            log_llm_call(kind="agent", model=model, prompt_version=PROMPT_VERSION,
                         latency_ms=int((time.perf_counter() - t0) * 1000), success=False, error=exc.__class__.__name__)
            raise
        log_llm_call(kind="agent", model=model, prompt_version=PROMPT_VERSION,
                     latency_ms=int((time.perf_counter() - t0) * 1000), success=True, usage=ok_usage(resp))
        return resp

    try:
        for turn in range(1, MAX_TURNS + 1):
            check_time()
            resp = timed_call(lambda: client.chat.completions.create(
                model=model, temperature=0, messages=messages, tools=tools, tool_choice="auto"))
            msg = resp.choices[0].message
            calls = getattr(msg, "tool_calls", None) or []
            if not calls:
                break
            messages.append(msg.model_dump(exclude_none=True) if hasattr(msg, "model_dump") else dict(msg))
            for call in calls:
                name = call.function.name
                args = json.loads(call.function.arguments or "{}")
                if name not in TOOL_FUNCS:
                    raise ValueError(f"model requested unknown tool {name!r}")
                result = TOOL_FUNCS[name](ctx, **args)  # a raising tool aborts the agent -> fallback
                payload = json.dumps(result)
                trace.append({"type": "tool", "turn": turn, "tool": name, "arguments": args, "result": payload[:400]})
                messages.append({"role": "tool", "tool_call_id": call.id, "content": payload})

        check_time()
        final = timed_call(lambda: client.beta.chat.completions.parse(
            model=model, temperature=0, messages=messages, response_format=AgentAnswer))
        answer = final.choices[0].message.parsed
        if answer is None:
            raise ValueError("model returned no parsed final answer")

        fields = validate(answer.category, answer.urgency, answer.summary, answer.suggested_department, text)
        duplicate_of = None
        if answer.duplicate_of and str(answer.duplicate_of) in ctx.seen_ids:
            duplicate_of = uuid.UUID(str(answer.duplicate_of))  # only ids a tool actually returned
        trace.append({"type": "final", "reasoning": (answer.reasoning or "")[:300],
                      "duplicate_of": str(duplicate_of) if duplicate_of else None})
        result = ClassificationResult(**fields, model=model, prompt_version=PROMPT_VERSION, used_fallback=False)
        return AgentResult(result, duplicate_of, trace, ctx.text_vector)
    except Exception as exc:  # noqa: BLE001 - the agent must never break a submission
        log.warning("agent failed (%s), falling back to single-shot classifier; text_len=%d", exc.__class__.__name__, len(text))
        return None
