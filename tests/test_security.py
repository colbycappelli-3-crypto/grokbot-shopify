"""Security guardrails for the foundation phase.

These tests fail loudly if a real-looking secret is ever placed in a committed
file, or if the git-ignore protections regress.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SECRET_KEY_PATTERN = re.compile(r"(KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL)", re.IGNORECASE)
PLACEHOLDER_VALUES = {"", "replace_me"}


def _env_lines():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        yield key.strip(), value.strip()


def test_env_example_exists():
    assert (REPO_ROOT / ".env.example").exists()


def test_env_example_has_only_placeholder_secrets():
    for key, value in _env_lines():
        if SECRET_KEY_PATTERN.search(key):
            assert value.lower() in PLACEHOLDER_VALUES, (
                f"{key} in .env.example must be a placeholder, got '{value}'"
            )


def test_gitignore_protects_secrets():
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    for needed in (".env", ".envrc", "*.pem", "*.key"):
        assert needed in gitignore, f".gitignore must ignore {needed}"
    # but the example file must remain trackable
    assert "!.env.example" in gitignore


def test_no_real_env_file_committed():
    # A real .env must never be tracked; only .env.example is allowed.
    assert not (REPO_ROOT / ".env").exists(), "A .env file must never be committed."
