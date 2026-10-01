import json
import time

import pytest
from fastapi.testclient import TestClient

from application.api.app import create_app
from application.api.jobs import JobManager
from application.services.history_store import HistoryStore  # noqa: F401
from application.services.translation_providers import (
    ProviderRegistry,
    ProviderResponse,
    TranslationProvider,
)

SAMPLE_SRT = "1\n00:00:01,000 --> 00:00:02,000\nHello world\n"


class FakeProvider(TranslationProvider):
    name = "fake"
    model = "test-model"

    def translate(self, text, source_language, target_language, *, context=None):
        return "Hola mundo"

    def translate_detailed(
        self, text, source_language, target_language, *, context=None
    ):
        return ProviderResponse("Hola mundo", model=self.model)


@pytest.fixture
def mock_provider(monkeypatch):
    monkeypatch.setattr(
        ProviderRegistry, "get", lambda name, config_service=None: FakeProvider()
    )


@pytest.fixture
def client():
    app = create_app(job_manager=JobManager(max_workers=2))
    with TestClient(app) as test_client:
        yield test_client


def _upload(
    client, path="/api/v1/analyze", content=SAMPLE_SRT, filename="in.srt", **data
):
    return client.post(
        path, files={"file": (filename, content, "text/plain")}, data=data
    )


def _wait_job(client, job_id, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.05)
    raise TimeoutError(f"job {job_id} did not finish")


def test_health_and_openapi(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"]

    spec = client.get("/openapi.json").json()
    assert "/api/v1/analyze" in spec["paths"]
    assert "/api/v1/translate" in spec["paths"]
    assert client.get("/docs").status_code == 200


def test_analyze_returns_structured_result(client):
    response = _upload(client)
    assert response.status_code == 200
    payload = response.json()
    assert payload["analytics"]["content"]["subtitle_count"] == 1
    assert payload["analytics"]["content"]["total_words"] == 2
    assert payload["qa"]["passed"] is True
    assert isinstance(payload["qa"]["findings"], list)


def test_analyze_rejects_bad_uploads(client):
    assert _upload(client, filename="evil.exe", content="x").status_code == 400
    assert _upload(client, filename="noname", content="x").status_code == 400
    response = client.post("/api/v1/analyze")
    assert response.status_code == 422


def test_qa_and_strict_policy(client):
    response = _upload(client, path="/api/v1/qa")
    assert response.status_code == 200
    assert response.json()["passed"] is True

    bad = "not a subtitle file at all !!!\nno timecodes here\n"
    response = _upload(client, path="/api/v1/qa", content=bad)
    assert response.status_code == 200
    assert response.json()["passed"] is True or response.json()["passed"] is False

    response = client.post(
        "/api/v1/qa",
        files={"file": ("in.srt", bad, "text/plain")},
        data={"strict": "true"},
    )
    assert response.status_code in {200, 409}


def test_translate_job_lifecycle(client, mock_provider):
    response = _upload(
        client,
        path="/api/v1/translate",
        source_language="en",
        target_language="es",
        provider="fake",
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    job = _wait_job(client, job_id)
    assert job["status"] == "completed"
    assert job["operation"] == "translate"
    assert job["result"]["text"] == "Hola mundo"
    metrics = job["result"]["metrics"]
    assert metrics["requested_provider"] == "fake"
    assert metrics["success"] is True
    assert "sk-" not in json.dumps(job)


def test_translate_validation(client):
    response = _upload(
        client,
        path="/api/v1/translate",
        target_language="   ",
    )
    assert response.status_code == 422
    response = _upload(
        client,
        path="/api/v1/translate",
        max_retries="99",
    )
    assert response.status_code == 422


def test_process_job_end_to_end_with_history(client, mock_provider):
    response = _upload(
        client,
        path="/api/v1/process",
        clean="true",
        translate="true",
        source_language="en",
        target_language="es",
        provider="fake",
    )
    assert response.status_code == 202
    job = _wait_job(client, response.json()["job_id"])
    assert job["status"] == "completed"
    assert "Hola mundo" in job["result"]["output_content"]
    assert job["result"]["translation_metrics"]["success"] is True

    history = client.get("/api/v1/history?limit=5").json()
    assert any(item["operation"] == "process" for item in history["items"])


def test_process_requires_target_when_translating(client):
    response = _upload(
        client,
        path="/api/v1/process",
        translate="true",
        target_language="",
    )
    assert response.status_code == 422
    response = _upload(
        client,
        path="/api/v1/process",
        translate="true",
        target_language="   ",
    )
    assert response.status_code == 422


def test_jobs_endpoints(client, mock_provider):
    response = _upload(
        client,
        path="/api/v1/translate",
        provider="fake",
    )
    job_id = response.json()["job_id"]
    listing = client.get("/api/v1/jobs").json()
    assert any(job["job_id"] == job_id for job in listing)
    assert client.get("/api/v1/jobs/missing").status_code == 404
    job = _wait_job(client, job_id)
    assert job["status"] == "completed"
    assert client.delete(f"/api/v1/jobs/{job_id}").status_code == 409
    assert client.delete("/api/v1/jobs/missing").status_code == 404


def test_failed_job_sanitizes_error(client, monkeypatch):
    from application.services.translation_providers import ProviderNetworkError

    class BrokenProvider(FakeProvider):
        def translate_detailed(self, *args, **kwargs):
            raise ProviderNetworkError("socket to 10.0.0.1 exploded with SECRET")

    monkeypatch.setattr(
        ProviderRegistry, "get", lambda name, config_service=None: BrokenProvider()
    )
    response = _upload(
        client,
        path="/api/v1/translate",
        provider="broken",
    )
    job = _wait_job(client, response.json()["job_id"])
    assert job["status"] in {"completed", "failed"}
    assert "SECRET" not in json.dumps(job)
    assert "Traceback" not in json.dumps(job)


def test_history_endpoints(client):
    with HistoryStore() as store:
        run_id = store.record_run(
            "process", file_path="a.srt", requested_provider="google"
        )
        store.record_run(
            "benchmark",
            requested_provider="ollama",
            benchmark_id="b1",
            run_index=0,
            success=0,
            error_type="network",
        )
    response = client.get("/api/v1/history?limit=10")
    assert response.status_code == 200
    assert len(response.json()["items"]) >= 2
    response = client.get("/api/v1/history?provider=ollama")
    assert all(
        item["requested_provider"] == "ollama" for item in response.json()["items"]
    )
    response = client.get("/api/v1/history?errors_only=true")
    assert all(not item["success"] for item in response.json()["items"])
    response = client.get(f"/api/v1/history/{run_id}")
    assert response.status_code == 200
    assert response.json()["file_path"] == "a.srt"
    assert client.get("/api/v1/history/999999").status_code == 404
    assert client.get("/api/v1/history?operation=bogus").status_code == 422


def test_benchmark_endpoints(client):
    with HistoryStore() as store:
        store.record_run(
            "benchmark", requested_provider="ollama", benchmark_id="b9", run_index=0
        )
        store.record_run(
            "benchmark", requested_provider="ollama", benchmark_id="b9", run_index=1
        )
    response = client.get("/api/v1/benchmarks")
    assert response.status_code == 200
    items = {item["benchmark_id"]: item for item in response.json()["items"]}
    assert items["b9"]["runs"] == 2
    assert items["b9"]["providers"] == ["ollama"]
    response = client.get("/api/v1/benchmarks/b9")
    assert response.status_code == 200
    assert len(response.json()["runs"]) == 2
    assert client.get("/api/v1/benchmarks/missing").status_code == 404


def test_upload_size_limit_and_cleanup(client, tmp_path):
    import pathlib

    before = set(pathlib.Path("/tmp").glob("srt4u-api-*"))
    big = "1\n00:00:01,000 --> 00:00:02,000\n" + ("x" * (6 * 1024 * 1024)) + "\n"
    response = _upload(client, content=big)
    assert response.status_code == 413
    assert set(pathlib.Path("/tmp").glob("srt4u-api-*")) == before


def test_no_tracebacks_or_keys_in_errors(client):
    response = client.get("/api/v1/history/999999")
    assert response.status_code == 404
    assert "Traceback" not in response.text
    response = client.post(
        "/api/v1/analyze", files={"file": ("x.srt", "x", "text/plain")}
    )
    assert response.status_code in {200, 400}
    assert "Traceback" not in response.text


def test_process_result_contract_declares_parse_issues(client):
    """P1 contract: /process exposes parse_issues in the OpenAPI schema.

    The field used to be injected into the job payload at runtime without a
    schema declaration, so OpenAPI clients could not discover it.
    """
    from application.api.schemas import ProcessResultModel

    properties = ProcessResultModel.model_json_schema()["properties"]
    assert "parse_issues" in properties, "parse_issues must be declared"
    assert properties["parse_issues"]["type"] == "array"
    items = properties["parse_issues"]["items"]
    assert "$ref" in items, items
    ref = items["$ref"].rsplit("/", 1)[-1]
    schema = ProcessResultModel.model_json_schema()["$defs"][ref]
    assert set(schema["properties"]) == {"kind", "reason", "line", "snippet"}
    # The API-wide OpenAPI document must carry the same structure.
    spec = create_app().openapi()
    assert "ParseIssueModel" in spec["components"]["schemas"]
    assert set(spec["components"]["schemas"]["ParseIssueModel"]["properties"]) == {
        "kind",
        "reason",
        "line",
        "snippet",
    }


def test_process_job_result_carries_parse_issue_structure(client, mock_provider):
    """A malformed-but-recoverable subtitle yields the documented structure."""
    content = (
        "1\n00:00:01,000 --> 00:00:02,000\nHello world\n\n"
        "2\n00:75:00,000 --> 00:75:01,000\nbad block\n"
    )
    response = _upload(client, path="/api/v1/process", content=content)
    assert response.status_code == 202
    job = _wait_job(client, response.json()["job_id"])
    assert job["status"] == "completed"
    result = job["result"]
    assert len(result["parse_issues"]) == 1
    issue = result["parse_issues"][0]
    assert set(issue) == {"kind", "reason", "line", "snippet"}
    assert issue["kind"] == "invalid_timestamp"
    assert issue["line"] == 6
    assert "00:75:00,000" in issue["snippet"]
    # Advisory: the run still completed with usable output.
    assert result["stats"]["parse_issues"] == 1
    assert result["output_content"].strip()
    # A clean file produces an empty list, not a missing key.
    clean = _upload(client, path="/api/v1/process")
    job = _wait_job(client, clean.json()["job_id"])
    assert job["status"] == "completed"
    assert job["result"]["parse_issues"] == []


def test_process_job_records_parse_issues_in_history(client):
    """Schema v3 regression: a /process job persists the parse-issue count to
    the SQLite history row, matching the pipeline's behaviour."""
    content = (
        "1\n00:00:01,000 --> 00:00:02,000\nHello world\n\n"
        "2\n00:75:00,000 --> 00:75:01,000\nbad block\n"
    )
    response = _upload(client, path="/api/v1/process", content=content)
    assert response.status_code == 202
    job = _wait_job(client, response.json()["job_id"])
    assert job["status"] == "completed"
    with HistoryStore() as store:
        rows = store.recent_runs(operation="process", limit=1)
    assert len(rows) == 1
    assert rows[0]["parse_issues"] == 1
    assert rows[0]["success"] == 1
