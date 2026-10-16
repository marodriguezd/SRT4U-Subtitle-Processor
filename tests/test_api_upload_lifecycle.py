"""API upload lifecycle tests with an isolated temporary directory.

``tempfile.tempdir`` is redirected to ``tmp_path`` so every temp file created by
``save_upload`` is visible to the test and cannot touch the real ``/tmp``.
Cleanup is asserted as "the isolated directory is empty again".
"""

import asyncio
import tempfile
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from application.api import deps
from application.api.app import create_app
from application.api.jobs import JobManager

SAMPLE_SRT = "1\n00:00:01,000 --> 00:00:02,000\nHello world\n"


@pytest.fixture
def isolated_tmp(tmp_path, monkeypatch):
    workdir = tmp_path / "tmp"
    workdir.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(workdir))
    return workdir


@pytest.fixture
def client(isolated_tmp):
    app = create_app(job_manager=JobManager(max_workers=1))
    with TestClient(app) as test_client:
        yield test_client


def _post(client, path, filename, content=SAMPLE_SRT):
    return client.post(path, files={"file": (filename, content, "text/plain")}, data={})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd.srt", "passwd.srt"),
        ("..\\..\\windows\\evil.srt", "evil.srt"),
        ("sub/dir/name.vtt", "name.vtt"),
        ("   spaced.srt  ", "spaced.srt"),
        ("..", "upload.tmp"),
        (".", "upload.tmp"),
        ("", "upload.tmp"),
        (None, "upload.tmp"),
        ("subtítulo-日本語.srt", "subtítulo-日本語.srt"),
    ],
)
def test_sanitize_upload_filename_strips_directories(raw, expected):
    assert deps.sanitize_upload_filename(raw) == expected


def test_traversal_filename_never_becomes_a_path(client, isolated_tmp, tmp_path):
    response = _post(client, "/api/v1/analyze", "../../escaped.srt")

    assert response.status_code == 200
    assert not (tmp_path / "escaped.srt").exists()
    assert not (tmp_path.parent / "escaped.srt").exists()
    assert list(isolated_tmp.iterdir()) == []


def test_validation_error_leaves_no_temp_file(client, isolated_tmp):
    response = _post(client, "/api/v1/analyze", "evil.exe", content="x")

    assert response.status_code == 400
    assert list(isolated_tmp.iterdir()) == []


def test_missing_filename_is_rejected_without_temp_file(client, isolated_tmp):
    response = _post(client, "/api/v1/analyze", "", content="x")

    assert response.status_code == 422
    assert list(isolated_tmp.iterdir()) == []


def test_successful_analyze_removes_its_temp_file(client, isolated_tmp):
    response = _post(client, "/api/v1/analyze", "in.srt")

    assert response.status_code == 200
    assert list(isolated_tmp.iterdir()) == []


def test_extension_check_is_case_insensitive(client, isolated_tmp):
    response = _post(client, "/api/v1/analyze", "CLIP.SRT")

    assert response.status_code == 200
    assert list(isolated_tmp.iterdir()) == []


def test_read_failure_maps_to_sanitized_500_and_cleans_up(isolated_tmp):
    class BrokenUpload:
        filename = "broken.srt"

        async def read(self, size):
            raise RuntimeError("disk /secret/path exploded")

    async def run():
        with pytest.raises(HTTPException) as excinfo:
            await deps.save_upload(BrokenUpload(), ".srt")
        return excinfo.value

    error = asyncio.run(run())

    assert error.status_code == 500
    assert "secret" not in error.detail
    assert "/secret/path" not in error.detail
    assert list(isolated_tmp.iterdir()) == []


def test_oversize_upload_leaves_no_temp_file(isolated_tmp):
    class LargeUpload:
        filename = "large.srt"

        def __init__(self):
            self._sent = False

        async def read(self, size):
            if self._sent:
                return b""
            self._sent = True
            return b"x" * 10

    async def run():
        with pytest.raises(HTTPException) as excinfo:
            await deps.save_upload(LargeUpload(), ".srt", max_bytes=5)
        return excinfo.value

    assert asyncio.run(run()).status_code == 413
    assert list(isolated_tmp.iterdir()) == []


def test_save_upload_names_are_generated_not_client_supplied(isolated_tmp):
    class Upload:
        filename = "../../../client-chosen.srt"

        def __init__(self):
            self._sent = False

        async def read(self, size):
            if self._sent:
                return b""
            self._sent = True
            return SAMPLE_SRT.encode()

    async def run():
        return await deps.save_upload(Upload(), ".srt")

    path = asyncio.run(run())
    try:
        assert path.parent == isolated_tmp
        assert path.name.startswith("srt4u-api-")
        assert "client-chosen" not in path.name
        assert path.read_bytes() == SAMPLE_SRT.encode()
    finally:
        Path(path).unlink(missing_ok=True)
