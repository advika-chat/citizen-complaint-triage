# Eval results

Each run writes `<timestamp>_<model>_<prompt>.md` (report) and `.json` (raw predictions) here.

Reproduce (from `backend/`, with `LLM_API_KEY` and `LLM_MODEL` set in `backend/.env`):

```bash
python -m evals.run                         # default model and prompt
python -m evals.run --model <other-model>   # compare models
python -m evals.run --prompt classify_v2    # compare prompts
python -m evals.run --limit 5               # quick smoke run
```

Notes: calls run sequentially with a 4 s pause (free-tier rate limits). The dataset is synthetic and
the labels are the author's own judgement; the set is small, so treat numbers as indicative only.
Without `LLM_API_KEY` the runner exits with an error and writes nothing.
