# Citizen Complaint Triage Bot

Citizens submit plain-English complaints about city problems (optionally with a photo and location). An LLM
classifies each complaint into a structured record. City staff use an admin dashboard to see complaints on a map and
in a table, filter, sort, update status (singly or in bulk), add notes and read analytics. Citizens get a public
tracking page with a status timeline.

> **Known limitation: there is no authentication.** Anyone who can reach the app can open the admin dashboard.
> **Do not submit personal data** to a deployment that uses a free-tier LLM key: free-tier prompts may be used by the
> provider to improve its products. All demo, seed and eval data in this repo is synthetic.

## Features
- Complaint submission (text, optional photo, optional geolocation) with LLM triage and a safe fallback
- Public tracking page with a status timeline
- Admin dashboard: stat tiles, map, searchable/filterable/sortable table, bulk status updates, three charts, LLM health card
- Admin detail page with notes and a "How this was triaged" panel
- Evaluation harness for classification quality (`backend/evals/`)
- Semantic search ("By meaning" toggle) over complaint embeddings
- Duplicate detection by a tool-using triage agent (flagged for staff, never auto-merged)
- LLM health card (latency, success/fallback rate, tokens, estimated cost)

## Tech stack
Backend: Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL, `openai` SDK (pointed at Google's
OpenAI-compatible Gemini endpoint), pytest. Frontend: React (Vite), React Router, Recharts, React-Leaflet, lucide-react,
react-hot-toast, plain CSS.

## Architecture
```
Submit form --multipart--> POST /complaints (rate limit, validation, photo checks)
                              |
                              v
             agent.run_agent (only if LLM_API_KEY is set)
               tools: find_similar_complaints (embeddings), lookup_department, get_nearby_complaints
               --(any error / timeout / no key)--> llm_classifier.classify_complaint
                       Structured Outputs call  --(any error / no key)--> static fallback
                              |
                       server-side validation (category/urgency/summary/department)
                              |
                              v
                       PostgreSQL (complaints, complaint_notes, llm_calls)
llm_logging.py records latency, tokens and estimated cost of each LLM call in llm_calls.
embeddings.py embeds each complaint once (best effort, reusing the agent's vector) for semantic search.
```

## Setup
Prerequisites: Python 3.11 or 3.12 (not the newest release; `pydantic-core` wheels lag), Node 18+, PostgreSQL 16+.

```bash
# 1. Databases (macOS/Linux; on Windows use pgAdmin/psql)
createdb citizen_complaints
createdb citizen_complaints_test

# 2. Backend
cd backend
python3.11 -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                # then edit .env (see below)
alembic upgrade head
python seed.py                      # 15 synthetic demo complaints
uvicorn main:app --reload           # http://localhost:8000  (docs at /docs)

# 3. Frontend (second terminal)
cd frontend
npm install
npm run dev                         # http://localhost:5173
```

Docker route (untested here, see below): `docker compose up --build`, then open http://localhost:5173
(backend http://localhost:8000). Set `LLM_API_KEY`, `LLM_MODEL`, `EMBEDDING_MODEL` in your shell or a root `.env`.

`backend/.env` (never commit it): set `DATABASE_URL`/`TEST_DATABASE_URL` for your Postgres, and optionally
`LLM_API_KEY` (free key from https://aistudio.google.com/apikey), `LLM_MODEL` (a free-tier Flash/Flash-Lite model
available to your key) and `EMBEDDING_MODEL`. The frontend reads `VITE_API_BASE` from `frontend/.env`
(default `http://localhost:8000`). Without an LLM key the app still works: every complaint gets the fallback
classification (`other` / `medium` / General Services).

## LLM approach
- **Structured Outputs**: classification uses `client.beta.chat.completions.parse(..., response_format=Classification)`
  against Gemini's OpenAI-compatible endpoint, `temperature=0`, 15 s timeout.
- **Server-side validation as a second layer**: after parsing, every field is re-checked (bad category becomes `other`,
  bad urgency `medium`, empty summary the first 100 characters, empty department `General Services`).
- **Prompt-injection stance**: the system prompt tells the model the complaint is untrusted and must only be
  classified; whatever the model returns still goes through the same validation, and the output has no capability
  beyond filling those four fields.
- **Fallback**: any exception (no key, network, 429 after retries, bad output) returns the static fallback with
  `used_fallback=true`, so a submission never fails because of the LLM. 429/5xx are retried up to 3 tries with
  exponential backoff and jitter.
- **Versioned prompts**: `backend/prompts/classify_v1.txt`; the filename stem is stored as `prompt_version`.
- **Agent**: when a key is configured, `POST /complaints` runs a short function-calling loop (max 3 model turns, 40 s
  overall) with three tools, then forces a structured final answer (classification, `duplicate_of`, one-sentence
  reasoning). `duplicate_of` is kept only if the id was returned by a tool in that run; duplicates are flagged, never
  merged or hidden. The tool calls and reasoning are saved as `agent_trace` (admin-only "How this was triaged" panel).
  Any failure (tool error, bad JSON, timeout, no key) falls back to the single-shot classifier, then to the static
  fallback, so a submission never fails because of the agent.
- **Embeddings / pgvector**: pgvector was not available in the development Postgres, so embeddings are stored as
  `double precision[]` and cosine similarity is computed in Python (`/health` reports `python-fallback`). This is
  fine for demo-sized data. To use pgvector, replace the column type and the query in `embeddings.py`.
- **Logging**: each call writes latency, token usage and an estimated cost (0 on the free tier) to `llm_calls`; the
  text of complaints is never stored there.

## Evaluation
`backend/evals/dataset.jsonl` holds 46 synthetic complaints that I labelled by hand (23 are a deliberate "hard" set:
ambiguous, multi-issue, vague, slang/typos, mixed-language, rambling, and 3 prompt-injection cases). The labels are my own
judgement and the set is small, so any numbers are indicative only.

**Results (one run, `gemini-3.5-flash-lite`, prompt `classify_v1`, temperature 0, 46 items)**, full report in
`backend/evals/results/20261124-212900_gemini-3.5-flash-lite_classify_v1.md`:

| metric | value |
|---|---|
| Category accuracy | 95.7% (clean set 100%, hard set 91.3%) |
| Urgency accuracy | 73.9% (clean set 82.6%, hard set 65.2%) |
| Urgency `high` recall / precision | 93.8% / 88.2% (missed 1 of 16 high-urgency items) |
| Category macro-F1 | 0.954 |
| Fallback rate | 2.2% (1 of 46: a transient API failure) |
| Latency | median 3.8 s, p95 20.9 s; one call stalled for ~47 minutes (machine or network stall), which inflates the mean to 69 s, so use the median |
| Tokens | 8,946 prompt + 2,275 completion |

Most errors are urgency disagreements of one level on `medium` items, which is subjective; the 3 injection cases
were all classified by their real content. The Spanish/mixed cases were the weakest. Only one model was evaluated
(only one model was exercised end to end; a second model and a `classify_v2` prompt were not run). Limitations: 46
synthetic items labelled by me, a single run, and a free-tier API that was flaky at times (some 429/500s and
timeouts, so a larger or repeated run could differ). Reproduce: `cd backend && python -m evals.run`.

## API overview
| Method & path | Notes |
|---|---|
| `GET /health` | `{status, db, llm_configured, embeddings}` |
| `POST /complaints` | `multipart/form-data`: `text` (required, max 4000), `latitude`, `longitude`, `photo` (jpeg/png/webp/gif, max 5MB). 10 requests/min/IP (`RATE_LIMIT_PER_MINUTE`) |
| `GET /complaints` | `category`, `urgency`, `status`, `q` (substring on text/summary), `sort` (`created_at\|urgency\|status\|category`), `order`, `limit` (1-200, default 50), `offset`. Returns `{items, total}` |
| `GET /complaints/search` | `q` (required), `limit` (1-50). Cosine-similarity search with a `similarity` score; 503 without `LLM_API_KEY`/`EMBEDDING_MODEL` |
| `GET /complaints/{id}` | Complaint with notes (plus `duplicate_of`, `agent_trace` when present) |
| `PATCH /complaints/{id}` | `{status}` |
| `PATCH /complaints/bulk-status` | `{ids: [...], status}` |
| `POST /complaints/{id}/notes` | `{text}` |
| `GET /analytics/summary` | `by_category`, `by_urgency`, `by_status`, 14-day zero-filled `trend` |
| `GET /analytics/llm` | Last 7 days: calls, success rate, fallback rate (share of non-seed complaints that used the fallback), p50/p95 latency, tokens, estimated cost, calls by kind/model |

## Testing
```bash
cd backend && pytest
```
38 tests currently pass. Tests use `TEST_DATABASE_URL` (schema is created by running the Alembic migrations), mock the LLM client, and need no
network or API key. Uploaded test photos go to a temp folder.

## Known limitations
- No authentication (see top).
- Photos are stored on the local disk (`backend/uploads/`).
- Status history is kept as timeline notes, not a separate audit table.
- Small, self-labelled eval set; single run at temperature 0.
- Until `LLM_API_KEY` is set, classification is the static fallback.
- Free-tier LLM rate limits and data-use terms apply; Gemini's OpenAI-compatibility layer is in beta.
- The in-memory rate limiter does not work across multiple workers.
- Cost figures are estimates.

## Next steps
Run the evals with a real key and iterate the prompt, move embeddings to pgvector, add authentication, move photos to object storage, and add a staff review queue for flagged duplicates.

## Deployment (untested guidance)
Not tried by the author. A host such as Render or Railway with a managed Postgres should work: provide `DATABASE_URL`,
`LLM_API_KEY`, `LLM_MODEL`, `EMBEDDING_MODEL`; run `alembic upgrade head` on deploy; build the frontend with
`VITE_API_BASE` pointing at the API; and add the frontend's origin to the CORS list in `backend/main.py`
(it currently allows only http://localhost:5173 and http://127.0.0.1:5173). Photos need a persistent volume.

## Verified / Not verified
Verified on Windows 11 with Python 3.11.8, PostgreSQL 17 (native install, no pgvector), Node 22, and a real Gemini
free-tier key (`LLM_MODEL=gemini-3.5-flash-lite`, `EMBEDDING_MODEL=gemini-embedding-001`; the 2.5 models returned
404 for this key):
- Real calls: one structured-output parse, one tool call, one embedding (3072 dims), the full eval above, and 15 real
  agent submissions. The agent called its tools and correctly flagged `duplicate_of` for 2 deliberate duplicates of
  seeded complaints. Several submissions fell back (timeouts, 429, 500, or the agent's 40 s limit) and were still
  saved correctly. A second near-duplicate pair submitted one after the other was not flagged because that run fell back.
- Alembic migrations (upgrade/downgrade round trips), every endpoint except semantic search against a real model
  (curl and pytest), the 11th request in a minute returning 429, photo upload and serving.
- `pytest`: 38 tests pass with no network and no key (classifier, API, agent with a scripted mock model, embeddings
  with mocked vectors, LLM logging).
- Frontend in a browser pane: dashboard tiles, map pins and legend, keyword search, category/urgency/status filters,
  sorting, pagination, a single status change and a bulk update (PATCH calls seen and confirmed in the DB), the three
  charts, the LLM Health empty state, submit flow, public and admin detail pages (status change adds a timeline
  entry, note added), no horizontal overflow at 375 px, no console errors, `npm run build`.

Not verified:
- **A second model and a `classify_v2` prompt** were not evaluated.
- **Semantic search results** (`GET /complaints/search` against real embeddings) and the "By meaning" toggle were not
  exercised in the UI; embeddings themselves were created for all seed rows.
- Agent reliability: on the free tier some submissions fell back because of timeouts or 429/500 responses.
- **Docker**: `docker-compose.yml` and the Dockerfiles were written and only syntax-checked with
  `docker compose config`; Docker Desktop was not running, so nothing was built or started.
- **GitHub Actions**: the workflow has not been run.
- Photo upload and the geolocation button in the browser UI; the "By meaning" toggle and duplicate badges in the UI
  (code written, built, not exercised with data).
