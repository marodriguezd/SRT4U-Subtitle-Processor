"""Single runtime version source for SRT4U.

``pyproject.toml`` remains the authoritative version: ``release_check.py``
compares the release tag against it and
``tests.test_coherence.test_single_product_version_everywhere`` pins every
consumer (CLI ``--version``, API metadata/OpenAPI, health endpoint, GUI
version pill) to the same value. Runtime code imports ``APP_VERSION`` from
here instead of repeating the literal. Update it together with
``pyproject.toml`` when releasing — never separately.
"""

APP_VERSION = "1.4.10"

#: Public project identity shown on the About page. Centralized here so the
#: GUI, docs and coherence tests share one source instead of hardcoding the
#: handle / repository name in widgets.
APP_AUTHOR_NAME = "Miguel Ángel Rodríguez Dalí"
APP_GITHUB_OWNER = "marodriguezd"
APP_GITHUB_REPO = "SRT4U-Subtitle-Processor"
APP_GITHUB_PROFILE_URL = f"https://github.com/{APP_GITHUB_OWNER}"
APP_GITHUB_REPO_URL = f"https://github.com/{APP_GITHUB_OWNER}/{APP_GITHUB_REPO}"
