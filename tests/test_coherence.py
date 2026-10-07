"""Coherence invariants (Fase 12): i18n parity, single version, geo, terminology.

Small regression guards for inconsistencies that functional tests do not catch:
a translated UI must never fall back to another language, the product version
must be identical in every layer, owner-location references must use Sevilla,
and CLI/API/GUI must share the same operation names and burn-in terminology.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXPECTED_VERSION = "1.4.10"
OPERATIONS = {"process", "analyze", "qa", "benchmark", "transcription", "pipeline"}


def _i18n_catalogs():
    from application.services.i18n_service import I18nService

    return I18nService.TRANSLATIONS


def test_i18n_key_parity_and_no_empty_values():
    catalogs = _i18n_catalogs()
    assert set(catalogs) == {"en", "es", "pt", "de", "it", "zh-CN"}
    reference = set(catalogs["en"])
    assert len(reference) > 200
    for lang, catalog in catalogs.items():
        assert set(catalog) == reference, f"key mismatch in {lang}"
        assert all(value.strip() for value in catalog.values()), (
            f"empty value in {lang}"
        )


def test_transcribe_pipeline_pages_are_translated_not_fallback():
    catalogs = _i18n_catalogs()
    for key in (
        "transcribe.title",
        "transcribe.subtitle",
        "transcribe.btn_start",
        "pipeline.title",
        "pipeline.subtitle",
        "pipeline.btn_start",
    ):
        values = {lang: catalogs[lang][key] for lang in catalogs}
        assert values["en"] != values["es"], f"{key} looks untranslated (en == es)"


def test_single_product_version_everywhere():
    import tomllib

    with open(ROOT / "pyproject.toml", "rb") as fh:
        pyproject_version = tomllib.load(fh)["project"]["version"]
    assert pyproject_version == EXPECTED_VERSION

    # Single runtime source: application/version.py re-exports the release
    # version; API schemas, app metadata, the six GUI version pills and the
    # CLI --version all derive from it instead of repeating the literal.
    from application.version import APP_VERSION

    assert APP_VERSION == EXPECTED_VERSION

    from application.api.schemas import APP_VERSION as SCHEMAS_APP_VERSION

    assert SCHEMAS_APP_VERSION is APP_VERSION

    from application.api.app import create_app

    assert create_app().openapi()["info"]["version"] == EXPECTED_VERSION

    catalogs = _i18n_catalogs()
    for lang in catalogs:
        assert catalogs[lang]["about.version_pill"] == f"v{EXPECTED_VERSION}"

    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "application.cli", "--version"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.stdout.strip() == EXPECTED_VERSION


def test_runtime_version_literal_lives_only_in_single_source():
    """The 1.4.10 literal lives only in pyproject.toml + application/version.py;
    every other runtime module derives it via APP_VERSION."""
    # Restrict to application/*.py (the tested scope). pyproject.toml is
    # the authoritative source and lives at the repo root, so it is not
    # scanned here; test_single_product_version_everywhere checks it.
    offenders = []
    for path in (ROOT / "application").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if text.count("1.4.10"):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == ["application/version.py"], offenders


def test_no_madrid_references_in_product():
    hits = []
    for path in list((ROOT / "application").rglob("*.py")) + list(
        (ROOT / "docs").rglob("*.md")
    ):
        text = path.read_text(encoding="utf-8")
        if "Madrid" in text or "Madri," in text or "马德里" in text:
            hits.append(str(path.relative_to(ROOT)))
    assert hits == [], f"stale owner-location references: {hits}"


def test_author_location_is_sevilla_everywhere():
    catalogs = _i18n_catalogs()
    for lang, catalog in catalogs.items():
        location = catalog["about.author_location"]
        assert (
            "Sevilla" in location
            or "Sevilha" in location
            or "Siviglia" in location
            or "塞维利亚" in location
        ), lang


def test_history_operations_coherent_cli_api():
    from application.cli import _build_parser

    cli_choices = set()
    for action in _build_parser()._actions:
        if type(action).__name__ == "_SubParsersAction":
            history_parser = action.choices.get("history")
            if history_parser is not None:
                for sub in history_parser._actions:
                    if getattr(sub, "dest", "") == "operation":
                        cli_choices.update(sub.choices or [])
    assert OPERATIONS <= cli_choices, f"CLI history missing: {OPERATIONS - cli_choices}"

    from application.api.app import create_app

    spec = create_app().openapi()
    history_get = spec["paths"]["/api/v1/history"]["get"]
    op_desc = " ".join(
        str(p.get("description", "")) for p in history_get.get("parameters", [])
    )
    for operation in OPERATIONS:
        assert operation in op_desc, f"API history description misses {operation}"


def test_burn_in_terminology_no_quema_in_cli_api():
    for path in list((ROOT / "application").rglob("*.py")):
        if "test" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        assert "quema" not in text.lower(), f"colloquial burn term in {path.name}"


@pytest.mark.parametrize("lang", ["en", "es", "pt", "de", "it", "zh-CN"])
def test_format_placeholders_survive_translation(lang):
    catalogs = _i18n_catalogs()
    for key in (
        "transcribe.avail_ok",
        "transcribe.progress_pct",
        "transcribe.error_desc",
        "pipeline.error_desc",
    ):
        source = catalogs["en"][key]
        translated = catalogs[lang][key]
        for placeholder in re.findall(r"\{[a-z_]+\}", source):
            assert placeholder in translated, f"{key} loses {placeholder} in {lang}"


def _pyproject():
    import tomllib

    with open(ROOT / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)


def _normalize_requirement(requirement):
    match = re.fullmatch(r"\s*([A-Za-z0-9_.-]+)\s*(.*)\s*", requirement)
    assert match, f"unsupported dependency declaration: {requirement!r}"
    name = re.sub(r"[-_.]+", "-", match.group(1)).casefold()
    return name + match.group(2).replace(" ", "")


def test_install_contract_base_has_desktop_stack():
    """`pip install .` must yield a functional desktop GUI + CLI base."""
    project = _pyproject()["project"]
    base = project["dependencies"]
    assert any(dep.startswith("PyQt6") for dep in base)
    assert any(dep.startswith("deep-translator") for dep in base)

    desktop_alias = project["optional-dependencies"]["desktop"]
    assert {_normalize_requirement(dep) for dep in desktop_alias} == {
        _normalize_requirement(dep) for dep in base
    }

    req_text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    declared = {_normalize_requirement(dep) for dep in base}
    mirrored = {
        _normalize_requirement(line.split("#", 1)[0].strip())
        for line in req_text.splitlines()
        if line.split("#", 1)[0].strip()
    }
    assert mirrored == declared, (
        f"requirements.txt must exactly mirror base dependencies; "
        f"missing={declared - mirrored}, extra={mirrored - declared}"
    )

    extras = project["optional-dependencies"]
    assert "PyQt6" not in " ".join(extras["api"])
    assert "faster-whisper" not in " ".join(base)
    assert "fastapi" not in " ".join(base)
    for extra in ("api", "transcription", "dev"):
        assert extras[extra]
    assert project["scripts"]["srt4u"] == "application.cli:main"
    workflow = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
    minimum = re.search(r"PyQt6>=([0-9]+\.[0-9]+\.[0-9]+)", "\n".join(base))
    assert minimum
    assert "pip install -r requirements.txt" in workflow
    assert r"grep -oP 'PyQt6>=\K[0-9]+\.[0-9]+\.[0-9]+' requirements.txt" in workflow

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_es = (ROOT / "README_es.md").read_text(encoding="utf-8")
    assert "pip install ." in readme and "pip install ." in readme_es


def test_ci_pins_static_ffmpeg_version():
    """El FFmpeg de los builds va fijado por versión, nunca en `latest`."""
    workflow = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")

    # La etiqueta móvil rompe la reproducibilidad y además se purga.
    assert "/releases/download/latest/" not in workflow, (
        "FFmpeg debe descargarse de un tag versionado, no de `latest`"
    )
    # Ninguna descarga puede venir de un publisher sin tag estable.
    assert "github.com/yt-dlp/FFmpeg-Builds/releases/download" not in workflow

    version = re.search(r'FFMPEG_VERSION:\s*"([^"]+)"', workflow)
    assert version, "declare FFMPEG_VERSION en el workflow"
    assert re.fullmatch(r"b\d+\.\d+\.\d+", version.group(1)), version.group(1)

    # Los tres builds consumen la variable, no una URL literal repetida.
    assert "releases/download/${FFMPEG_VERSION}/" in workflow
    assert "releases/download/${{ env.FFMPEG_VERSION }}/" in workflow
    for asset in (
        "ffmpeg-win32-x64",
        "ffmpeg-linux-x64",
        "ffmpeg-darwin-arm64",
        "ffmpeg-darwin-x64",
    ):
        assert asset in workflow, asset

    # appimagetool forma parte del AppImage publicado: también debe ir fijado,
    # o el binario seguiría variando entre builds aunque el FFmpeg no lo hiciera.
    appimage = re.search(r'APPIMAGETOOL_VERSION:\s*"([^"]+)"', workflow)
    assert appimage, "declare APPIMAGETOOL_VERSION en el workflow"
    assert re.fullmatch(r"\d+\.\d+\.\d+", appimage.group(1)), appimage.group(1)
    assert "appimagetool/releases/download/${APPIMAGETOOL_VERSION}/" in workflow
    assert "appimagetool/releases/download/continuous/" not in workflow


def test_ci_installs_the_api_extra_for_the_test_suite():
    """La suite importa fastapi a nivel de módulo: CI debe instalar `[api]`.

    Sin el extra, `pytest` aborta en la colección con
    `ModuleNotFoundError: No module named 'fastapi'` en test_api.py,
    test_pipeline.py y test_transcription.py, y el fallo tumba `test` y
    `compat-min-pyqt6`, lo que a su vez salta los tres builds y la release.
    """
    workflow = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")

    for module in (
        "tests/test_api.py",
        "tests/test_pipeline.py",
        "tests/test_transcription.py",
    ):
        assert "fastapi" in (ROOT / module).read_text(encoding="utf-8"), module

    # Los dos jobs que ejecutan la suite tienen que instalar el extra.
    test_job = workflow.split("\n  test:", 1)[1].split("\n  compat-min-pyqt6:", 1)[0]
    compat_job = workflow.split("\n  compat-min-pyqt6:", 1)[1].split(
        "\n  build-windows:", 1
    )[0]
    for name, block in (("test", test_job), ("compat-min-pyqt6", compat_job)):
        assert '".[api]"' in block, f"el job {name} debe instalar el extra [api]"
        assert "python -m pytest" in block, name

    # El extra sale de pyproject: el workflow no debe re-declarar sus pines.
    extras = _pyproject()["project"]["optional-dependencies"]["api"]
    for dep in extras:
        assert dep not in workflow, f"{dep} no debe duplicarse en el workflow"


def test_ci_release_is_the_only_job_with_write_permission():
    """`contents: write` sólo en `release`; el resto debe poder leer."""
    workflow = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
    assert re.search(r"^permissions:\n  contents: read$", workflow, re.M)
    assert workflow.count("contents: write") == 1
    # Y debe ser el job que publica la release, no otro.
    release_block = workflow.split("\n  release:", 1)[1]
    assert "contents: write" in release_block


# ------------------------------------------------------- release hardening --


def _release_check_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "release_check", ROOT / "tools" / "release_check.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_workflow_gates_publication_on_tag_validation():
    """The `v*` trigger is wide; the release job must be the real gate."""
    workflow = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
    release_block = workflow.split("\n  release:", 1)[1]
    assert "tools/release_check.py" in release_block, (
        "el job release debe ejecutar la puerta de tag antes de publicar"
    )
    assert "github.ref_name" in release_block
    # Procedencia: el tag debe apuntar al commit que se publica (sin API).
    assert "git rev-parse" in release_block and "refs/tags/" in release_block
    assert "github.sha" in release_block
    # Procedencia de artefactos: cada build escribe un sello de versión en
    # texto plano (RELEASE_VERSION) y el job release lo compara con el tag.
    # Los binarios PyInstaller comprimen el código Python, así que el grep
    # del literal dentro del ejecutable nunca puede pasar.
    _JOB_ORDER = [
        "test",
        "compat-min-pyqt6",
        "build-windows",
        "build-linux",
        "build-macos",
        "release",
    ]

    def _job_block(name):
        start = workflow.split(f"\n  {name}:", 1)[1]
        nxt = _JOB_ORDER[_JOB_ORDER.index(name) + 1]
        return start.split(f"\n  {nxt}:", 1)[0]

    for job in ("build-windows", "build-linux", "build-macos"):
        job_block = _job_block(job)
        assert "Stamp release version" in job_block, job
        assert "RELEASE_VERSION" in job_block, job
    assert "RELEASE_VERSION" in release_block
    assert "no contiene la versión" in release_block
    # Sigue publicando desde el cuerpo versionado y como estable.
    assert "body_path: RELEASE_NOTES.md" in release_block
    assert "prerelease: false" in release_block


def test_release_gate_rejects_wrong_version_and_prerelease_tags():
    """v<X.Y.Z+1>, prereleases and suffixed tags must never publish."""
    tool = _release_check_module()
    pyproject = ROOT / "pyproject.toml"
    major, minor, patch = (int(part) for part in EXPECTED_VERSION.split("."))

    assert tool.check_tag(f"v{EXPECTED_VERSION}", pyproject) is None

    for bad_tag in (
        f"v{major}.{minor}.{patch + 1}",  # v1.5.0-style future bump
        f"v{major}.{minor}.{patch - 1}" if patch else f"v{major}.{minor - 1}.0",
        f"v{major + 1}.0.0",
        f"v{EXPECTED_VERSION}-rc1",
        f"v{EXPECTED_VERSION}-beta1",
        f"v{EXPECTED_VERSION}+build.7",
        f"{EXPECTED_VERSION}",  # sin la 'v'
        f"v{EXPECTED_VERSION}.1",  # cuatro componentes
    ):
        reason = tool.check_tag(bad_tag, pyproject)
        assert reason is not None, f"{bad_tag} debe rechazarse"
        assert bad_tag in reason, reason


def test_release_gate_cli_exit_codes():
    """The workflow relies on exit codes: 0 publish, 1 refuse."""
    import subprocess
    import sys

    tool = ROOT / "tools" / "release_check.py"
    ok = subprocess.run(
        [sys.executable, str(tool), f"v{EXPECTED_VERSION}"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert ok.returncode == 0, ok.stderr
    bad = subprocess.run(
        [sys.executable, str(tool), f"v{EXPECTED_VERSION}-rc1"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert bad.returncode == 1
    assert bad.stderr.strip()


def test_release_notes_are_release_facing_not_preparation():
    """RELEASE_NOTES.md is the GitHub Release body: no pre-release claims."""
    notes = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    for stale_phrase in (
        "not published",
        "exist yet",
        "does not exist",
        "latest published release",
        "Status: prepared",
        "future v",
        "kept ready",
    ):
        assert stale_phrase not in notes, stale_phrase
    # Describe la versión que publica el tag.
    assert f"SRT4U {EXPECTED_VERSION}" in notes
    # macOS sigue documentado como arm64-only, nunca universal.
    assert "Apple Silicon (arm64)" in notes
    assert "x86_64 build is produced" not in notes
    assert "x86_64 build is NOT produced" in notes
    assert "will not launch on Intel Macs" in notes


def test_current_docs_describe_history_schema_v3():
    """Current-state docs must match SCHEMA_VERSION (v3, parse_issues)."""
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "schema v3" in agents
    assert "schema v2" not in agents
    database = (ROOT / "docs/database.md").read_text(encoding="utf-8")
    assert "## Schema (v3)" in database
    tech_debt = (ROOT / "docs/tech-debt.md").read_text(encoding="utf-8")
    assert "v1→v2→v3" in tech_debt

    from application.services import history_store

    assert history_store.SCHEMA_VERSION == 3
    assert "parse_issues" in history_store._MIGRATIONS[3]


def test_api_contract_declares_parse_issues_in_openapi():
    """The served OpenAPI must document the /process parse_issues payload."""
    from application.api.app import create_app

    spec = create_app().openapi()
    schemas = spec["components"]["schemas"]
    assert "ProcessResultModel" in schemas
    assert "ParseIssueModel" in schemas
    assert set(schemas["ParseIssueModel"]["properties"]) == {
        "kind",
        "reason",
        "line",
        "snippet",
    }
    parse_issues = schemas["ProcessResultModel"]["properties"]["parse_issues"]
    assert parse_issues["type"] == "array"
    assert parse_issues["items"]["$ref"].endswith("ParseIssueModel")


def test_api_contract_documents_job_result_shape():
    """JobStatusResponse.result must reference the job-result models.

    The slow operations return their payload inside `result`; the served
    OpenAPI documents it as a nullable union of ProcessResultModel /
    TranslationResultModel / TranscriptionResultModel instead of an opaque
    Any, so clients can discover the real shape (including parse_issues).
    """
    from application.api.app import create_app

    spec = create_app().openapi()
    schemas = spec["components"]["schemas"]
    job_status = schemas["JobStatusResponse"]
    result = job_status["properties"]["result"]
    refs = {
        item["$ref"].rsplit("/", 1)[-1] for item in result["anyOf"] if "$ref" in item
    }
    assert {
        "ProcessResultModel",
        "TranslationResultModel",
        "TranscriptionResultModel",
    } <= refs
    # Nullable: null carries the running/failed/cancelled states.
    assert any(item.get("type") == "null" for item in result["anyOf"])
    # The documented models are really present and ProcessResultModel keeps
    # exposing parse_issues to OpenAPI clients.
    for name in refs:
        assert name in schemas
    assert "parse_issues" in schemas["ProcessResultModel"]["properties"]
