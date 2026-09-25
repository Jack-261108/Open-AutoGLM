"""Tests for synchronized provider SDK dependency declarations."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
REQUIRED_MODEL_DEPENDENCIES = {
    "openai": "2.9.0",
    "anthropic": "0.117.1",
    "httpx": "0.28.1",
}


def test_requirements_declares_exact_model_dependency_lower_bounds():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()

    for package, version in REQUIRED_MODEL_DEPENDENCIES.items():
        assert requirements.count(f"{package}>={version}") == 1


def test_setup_declares_matching_model_dependency_lower_bounds():
    setup_text = (ROOT / "setup.py").read_text(encoding="utf-8")

    for package, version in REQUIRED_MODEL_DEPENDENCIES.items():
        pattern = rf'["\']{re.escape(package)}>={re.escape(version)}["\']'
        assert len(re.findall(pattern, setup_text)) == 1


def test_stage_does_not_add_existing_requests_requirement_to_setup():
    setup_text = (ROOT / "setup.py").read_text(encoding="utf-8")

    assert '"requests>=' not in setup_text
    assert "'requests>=" not in setup_text
