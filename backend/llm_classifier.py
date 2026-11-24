"""Single-shot complaint classification with validation and a safe fallback."""
import logging
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

from models import Category, Urgency

load_dotenv()
log = logging.getLogger("triage.classifier")

PROMPT_DIR = Path(__file__).parent / "prompts"
DEFAULT_PROMPT = "classify_v1"
DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
REQUEST_TIMEOUT = 15
MAX_TRIES = 3


class Classification(BaseModel):
    category: Category
    urgency: Urgency
    summary: str
    suggested_department: str


@dataclass
class ClassificationResult:
    category: str
    urgency: str
    summary: str
    suggested_department: str
    model: str | None
    prompt_version: str | None
    used_fallback: bool
    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


def get_client() -> OpenAI | None:
    """Create the client lazily. Returns None when no API key is configured."""
    key = os.getenv("LLM_API_KEY", "").strip()
    if not key:
        return None
    return OpenAI(
        api_key=key,
        base_url=os.getenv("LLM_BASE_URL") or DEFAULT_BASE_URL,
        timeout=REQUEST_TIMEOUT,
        max_retries=0,  # retries are handled by call_with_backoff
    )


def llm_configured() -> bool:
    return bool(os.getenv("LLM_API_KEY", "").strip())


def load_prompt(version: str = DEFAULT_PROMPT) -> str:
    return (PROMPT_DIR / f"{version}.txt").read_text(encoding="utf-8").strip()


def _retryable(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status is not None:
        return status == 429 or status >= 500
    # connection errors / timeouts have no status code
    return exc.__class__.__name__ in {"APIConnectionError", "APITimeoutError"}


def call_with_backoff(fn, max_tries: int = MAX_TRIES):
    """Retry on 429/5xx with exponential backoff + jitter. Never retries forever."""
    for attempt in range(max_tries):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            if attempt == max_tries - 1 or not _retryable(exc):
                raise
            time.sleep(min(1.0 * 2**attempt, 4.0) + random.uniform(0, 0.5))


def fallback_result(text: str) -> ClassificationResult:
    return ClassificationResult(
        category="other",
        urgency="medium",
        summary=text[:100],
        suggested_department="General Services",
        model=None,
        prompt_version=None,
        used_fallback=True,
    )


def validate(raw_category, raw_urgency, raw_summary, raw_department, text: str) -> dict:
    """Second layer of defence: normalise every field regardless of how it was parsed."""
    category = str(getattr(raw_category, "value", raw_category) or "").strip().lower()
    if category not in {c.value for c in Category}:
        category = "other"
    urgency = str(getattr(raw_urgency, "value", raw_urgency) or "").strip().lower()
    if urgency not in {u.value for u in Urgency}:
        urgency = "medium"
    summary = (raw_summary or "").strip() or text[:100]
    department = (raw_department or "").strip() or "General Services"
    return {
        "category": category,
        "urgency": urgency,
        "summary": summary,
        "suggested_department": department,
    }


def classify_complaint(text: str, prompt_version: str = DEFAULT_PROMPT, model: str | None = None) -> ClassificationResult:
    """Classify a complaint. Never raises: any failure returns the static fallback."""
    from llm_logging import log_llm_call  # local import avoids a cycle at import time

    start = time.perf_counter()
    model_name = model or os.getenv("LLM_MODEL", "").strip()
    try:
        client = get_client()
        if client is None or not model_name:
            return fallback_result(text)

        completion = call_with_backoff(
            lambda: client.beta.chat.completions.parse(
                model=model_name,
                temperature=0,
                messages=[
                    {"role": "system", "content": load_prompt(prompt_version)},
                    {"role": "user", "content": text},
                ],
                response_format=Classification,
            )
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise ValueError("model returned no parsed output")
        fields = validate(parsed.category, parsed.urgency, parsed.summary, parsed.suggested_department, text)
        latency_ms = int((time.perf_counter() - start) * 1000)
        usage = getattr(completion, "usage", None)
        log_llm_call(
            kind="classify", model=model_name, prompt_version=prompt_version,
            latency_ms=latency_ms, usage=usage, success=True,
        )
        return ClassificationResult(
            **fields, model=model_name, prompt_version=prompt_version, used_fallback=False,
            latency_ms=latency_ms,
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
        )
    except Exception as exc:  # noqa: BLE001 - the LLM must never break a request
        log.warning("classification failed (%s), using fallback; text_len=%d", exc.__class__.__name__, len(text))
        if llm_configured():
            log_llm_call(
                kind="classify", model=model_name, prompt_version=prompt_version,
                latency_ms=int((time.perf_counter() - start) * 1000),
                usage=None, success=False, error=exc.__class__.__name__,
            )
        return fallback_result(text)
