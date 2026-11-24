"""Records every LLM call (latency, tokens, estimated cost, success) in the llm_calls table.

Never stores request text. Logging failures are swallowed so they cannot break a request.
"""
import uuid

from database import SessionLocal
from models import LlmCall

# Estimated USD per 1M tokens (input, output). ESTIMATES that may be out of date.
# Free-tier Gemini usage is billed at $0, so unknown/free models record 0.0.
PRICE_PER_MILLION = {}


def estimate_cost(model: str | None, prompt_tokens: int | None, completion_tokens: int | None) -> float:
    price_in, price_out = PRICE_PER_MILLION.get(model or "", (0.0, 0.0))
    return ((prompt_tokens or 0) * price_in + (completion_tokens or 0) * price_out) / 1_000_000


def log_llm_call(
    kind: str,
    model: str | None,
    latency_ms: int,
    success: bool,
    prompt_version: str | None = None,
    usage=None,
    error: str | None = None,
    complaint_id: uuid.UUID | None = None,
) -> None:
    try:
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        with SessionLocal() as db:
            db.add(LlmCall(
                complaint_id=complaint_id, kind=kind, model=model or "", prompt_version=prompt_version,
                latency_ms=latency_ms, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                est_cost_usd=estimate_cost(model, prompt_tokens, completion_tokens),
                success=success, error=(error or None) and error[:200],
            ))
            db.commit()
    except Exception as exc:  # noqa: BLE001
        print(f"llm_logging: could not record call ({exc.__class__.__name__})")
