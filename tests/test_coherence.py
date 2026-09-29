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
EXPECTED_VERSION = "1.4.9"
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

    from application.api.schemas import APP_VERSION

    assert APP_VERSION == EXPECTED_VERSION

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
    assert f"pip install -r requirements.txt" in workflow
    assert r"grep -oP 'PyQt6>=\K[0-9]+\.[0-9]+\.[0-9]+' requirements.txt" in workflow

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_es = (ROOT / "README_es.md").read_text(encoding="utf-8")
    assert "pip install ." in readme and "pip install ." in readme_es
