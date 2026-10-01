# SRT4U REST API (local)

Thin HTTP interface over the same application services used by the GUI and
the CLI. Local use, no authentication, no users, no cloud. GUI, CLI and API
share `SubtitleService`, `TranslationService` and `HistoryStore`; routes
contain no business logic and the domain never imports FastAPI.

## Install & run

The desktop app and the CLI work without FastAPI. The API is optional:

```bash
python -m pip install '.[api]'
python -m application.cli serve --host 127.0.0.1 --port 8000
```

Listens on localhost by default; bind another interface only on trusted
networks. Interactive docs at `/docs`, raw schema at `/openapi.json`.
Versioned under `/api/v1` (versioning belongs to the HTTP interface).

## Endpoints

| Method & path | Description |
|---|---|
| `GET /api/v1/health` | Liveness probe (`{status, version}`) |
| `POST /api/v1/analyze` | File upload → grouped analytics + QA report (sync) |
| `POST /api/v1/qa` | File upload → deterministic QA (`strict` form flag; 409 on strict failure) |
| `POST /api/v1/translate` | File + options → **job** (202 `{job_id}`) |
| `POST /api/v1/process` | File + clean/translate options → **job** (202) |
| `POST /api/v1/transcribe` | Media + model/language → **job** (202; Whisper `[transcription]` extra) |
| `POST /api/v1/pipeline` | Media/subtitle + pipeline options → **job** (202; full chain) |
| `GET /api/v1/jobs` | Local in-memory jobs |
| `GET /api/v1/jobs/{id}` | Status + `result` / `error` |
| `DELETE /api/v1/jobs/{id}` | Best-effort cancel: queued jobs are dropped; a **running job is not interrupted** — it finishes in the background and only its result is discarded (409 when already terminal). The OpenAPI documents `result` per operation (`process` → `ProcessResultModel` with `parse_issues`, `translate` → `TranslationResultModel`, `transcription` → `TranscriptionResultModel`). |
| `GET /api/v1/history` | Filters: `provider`, `operation`, `limit`, `errors_only`, `fallback_only` |
| `GET /api/v1/history/{id}` | One execution (404 when missing) |
| `GET /api/v1/benchmarks` | Stored benchmarks grouped by `benchmark_id` |
| `GET /api/v1/benchmarks/{id}` | Per-(provider, run) rows |

Translate/process/transcribe/pipeline run as local `JobManager` jobs (bounded thread pool, states
`queued → running → completed/failed/cancelled`) because provider calls can
take a while; analyze/QA/history are synchronous. Each job thread owns its
service and SQLite connection. No benchmark execution endpoint: only stored
benchmarks are queryable.

## Uploads

Multipart `.srt/.vtt/.ass/.ssa/.txt`, 5 MB cap (413 above), streamed to temp
files deleted after the request. Full subtitle texts are never stored in
SQLite (only aggregate metrics + file identity).

## Errors

Domain errors map to HTTP: 400 unreadable input, 404 unknown run/job/
benchmark, 409 strict-QA failure or cancel of a terminal job, 413 oversized
upload, 422 validation, 500 internal (generic message, details server-side).
No tracebacks, keys, or secrets in responses; every request/response is
validated with Pydantic schemas (`application/api/schemas.py`).

## Examples

```bash
curl -F file=@in.srt http://127.0.0.1:8000/api/v1/analyze
curl -F file=@in.srt -F target_language=es -F provider=ollama \
  http://127.0.0.1:8000/api/v1/translate
# {"job_id": "...", "status": "queued"}
curl http://127.0.0.1:8000/api/v1/jobs/<job_id>
curl "http://127.0.0.1:8000/api/v1/history?provider=ollama&fallback_only=true"
```

## Tests

```bash
python -m pytest -q tests/test_api.py -m "not network"
```

TestClient with mocked providers; no calls to Google/DeepL/OpenAI.
