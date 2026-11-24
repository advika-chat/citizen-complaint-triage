"""Evaluate the single-shot classifier on evals/dataset.jsonl.

Usage (from backend/):  python -m evals.run [--model MODEL] [--limit N] [--prompt classify_v1]
Needs LLM_API_KEY. Never fabricates numbers: without a key it exits non-zero.
"""
import argparse
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

HERE = Path(__file__).parent
CATEGORIES = ["streetlight", "pollution", "water", "waste", "energy", "crowd_monitoring", "other"]
URGENCIES = ["low", "medium", "high"]
DELAY_SECONDS = 4.0  # free-tier friendly: sequential calls, ~15 requests/minute at most


def percentile(values, p):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1)))]


def prf(rows, label, key):
    tp = sum(1 for r in rows if r[f"expected_{key}"] == label and r[f"predicted_{key}"] == label)
    fp = sum(1 for r in rows if r[f"expected_{key}"] != label and r[f"predicted_{key}"] == label)
    fn = sum(1 for r in rows if r[f"expected_{key}"] == label and r[f"predicted_{key}"] != label)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else 0.0
    return precision, recall, f1


def confusion(rows, labels, key):
    counts = Counter((r[f"expected_{key}"], r[f"predicted_{key}"]) for r in rows)
    lines = ["| expected \\ predicted | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]
    for exp in labels:
        lines.append(f"| **{exp}** | " + " | ".join(str(counts.get((exp, p), 0)) for p in labels) + " |")
    return "\n".join(lines)


def pct(x):
    return "n/a" if x is None else f"{x * 100:.1f}%"


def build_report(rows, model, prompt):
    n = len(rows)
    cat_acc = sum(r["expected_category"] == r["predicted_category"] for r in rows) / n
    urg_acc = sum(r["expected_urgency"] == r["predicted_urgency"] for r in rows) / n
    high_p, high_r, _ = prf(rows, "high", "urgency")
    macro_f1 = sum(prf(rows, c, "category")[2] for c in CATEGORIES) / len(CATEGORIES)
    fallback_rate = sum(r["used_fallback"] for r in rows) / n
    lat = [r["latency_ms"] for r in rows if r["latency_ms"] is not None]
    ptok = sum(r["prompt_tokens"] or 0 for r in rows)
    ctok = sum(r["completion_tokens"] or 0 for r in rows)

    by_tag = defaultdict(list)
    for r in rows:
        hard = "clean" not in r["tags"]
        by_tag["clean set" if not hard else "hard set (all)"].append(r)
        for t in r["tags"]:
            if t != "clean":
                by_tag[f"tag: {t}"].append(r)

    out = [
        f"# Eval report: {model} / {prompt}",
        "",
        f"Run at {datetime.now().isoformat(timespec='seconds')}. Dataset: {n} synthetic, self-labelled complaints. temperature=0, single run.",
        "",
        "## Headline numbers",
        f"- Category accuracy: **{pct(cat_acc)}**",
        f"- Urgency accuracy: **{pct(urg_acc)}**",
        f"- Urgency `high` recall: **{pct(high_r)}** (precision {pct(high_p)})",
        f"- Category macro-F1: **{macro_f1:.3f}**",
        f"- Fallback rate: **{pct(fallback_rate)}**",
        f"- Latency: median {percentile(lat, 50)} ms, mean {sum(lat) / len(lat):.0f} ms, p95 {percentile(lat, 95)} ms, max {max(lat)} ms (a mean far above the median means outliers)" if lat else "- Latency: n/a (no successful calls)",
        f"- Tokens: {ptok} prompt + {ctok} completion (estimated cost on the free tier: $0.00)",
        "",
        "## Accuracy by subset",
        "| subset | n | category acc | urgency acc |",
        "|---|---|---|---|",
    ]
    for name, subset in sorted(by_tag.items()):
        ca = sum(r["expected_category"] == r["predicted_category"] for r in subset) / len(subset)
        ua = sum(r["expected_urgency"] == r["predicted_urgency"] for r in subset) / len(subset)
        out.append(f"| {name} | {len(subset)} | {pct(ca)} | {pct(ua)} |")
    out += ["", "## Category confusion matrix", confusion(rows, CATEGORIES, "category"),
            "", "## Urgency confusion matrix", confusion(rows, URGENCIES, "urgency"), "",
            "## Misclassified examples", "| id | text | expected | predicted |", "|---|---|---|---|"]
    for r in rows:
        if r["expected_category"] != r["predicted_category"] or r["expected_urgency"] != r["predicted_urgency"]:
            text = r["text"].replace("|", "/")[:140]
            out.append(
                f"| {r['id']} | {text} | {r['expected_category']}/{r['expected_urgency']} "
                f"| {r['predicted_category']}/{r['predicted_urgency']}{' (fallback)' if r['used_fallback'] else ''} |"
            )
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=os.getenv("LLM_MODEL", "").strip())
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--prompt", default="classify_v1")
    args = parser.parse_args()

    if not os.getenv("LLM_API_KEY", "").strip():
        print("Cannot run evals without LLM_API_KEY (set it in backend/.env). No results were produced.")
        return 1
    if not args.model:
        print("No model given: pass --model or set LLM_MODEL in backend/.env.")
        return 1

    sys.path.insert(0, str(HERE.parent))
    from llm_classifier import classify_complaint

    data = [json.loads(line) for line in (HERE / "dataset.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit:
        data = data[: args.limit]

    rows = []
    for i, item in enumerate(data, 1):
        res = classify_complaint(item["text"], prompt_version=args.prompt, model=args.model)
        rows.append({
            "id": item["id"], "text": item["text"], "tags": item["tags"],
            "expected_category": item["category"], "expected_urgency": item["urgency"],
            "predicted_category": res.category, "predicted_urgency": res.urgency,
            "used_fallback": res.used_fallback, "latency_ms": res.latency_ms,
            "prompt_tokens": res.prompt_tokens, "completion_tokens": res.completion_tokens,
        })
        print(f"[{i}/{len(data)}] {item['id']}: {res.category}/{res.urgency}{' (fallback)' if res.used_fallback else ''}")
        time.sleep(DELAY_SECONDS)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_model = re.sub(r"[^A-Za-z0-9._-]", "_", args.model)
    base = HERE / "results" / f"{stamp}_{safe_model}_{args.prompt}"
    # Not with_suffix(): model names contain dots (e.g. gemini-3.5-flash-lite).
    Path(f"{base}.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    Path(f"{base}.md").write_text(build_report(rows, args.model, args.prompt), encoding="utf-8")
    print(f"Wrote {base}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
