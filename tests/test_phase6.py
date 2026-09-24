"""Phase 6 prepares a Shopify catalog connection and does not open it."""
import json
import re
import subprocess
from pathlib import Path

from grokbot.audit.log import AuditLog
from grokbot.cli import main
from grokbot.connectors.shopify_read import ENV_DOMAIN, ENV_TOKEN, attempt_live_catalog_read
from grokbot.phase import EXTERNAL_CONNECTIONS_ENABLED, SHOPIFY_LIVE_REQUESTS_ENABLED
from grokbot.envconfig.shopify import inspect_catalog_secrets

REPO_ROOT = Path(__file__).resolve().parents[1]
_TOKEN_VALUE = re.compile(
    r"(shpat_|shpca_|shpss_|shppa_|sk_live_)[A-Za-z0-9]{8,}"
)


def test_enable_flags_stay_off():
    assert EXTERNAL_CONNECTIONS_ENABLED is False
    assert SHOPIFY_LIVE_REQUESTS_ENABLED is False


def test_missing_secrets_are_reported_without_reading_files(monkeypatch):
    monkeypatch.delenv(ENV_TOKEN, raising=False)
    monkeypatch.delenv(ENV_DOMAIN, raising=False)
    report = inspect_catalog_secrets()
    assert report["domain_status"] == "missing"
    assert report["token_status"] == "missing"
    assert report["files_read"] == []
    assert report["values_included"] is False
    assert report["loaded_from"] == "process_environment"
    assert report["scope"] == "read_products"


def test_present_secrets_are_not_returned_or_logged(monkeypatch):
    token = "shpat_testvalue_not_for_git"
    shop = "example-store.myshopify.com"
    monkeypatch.setenv(ENV_TOKEN, token)
    monkeypatch.setenv(ENV_DOMAIN, shop)
    report = inspect_catalog_secrets()
    blob = json.dumps(report)
    assert report["domain_status"] == "present"
    assert report["token_status"] == "present"
    assert report["token_prefix_recognized"] is True
    assert token not in blob
    assert shop not in blob
    audit = AuditLog()
    audit.record("connection_withheld", note=f"domain {shop} token {token}")
    stored = json.dumps(audit.to_list())
    assert token not in stored
    assert shop not in stored
    assert "[REDACTED]" in stored


def test_invalid_secret_shapes_are_not_echoed(monkeypatch):
    token = "short token value"
    shop = "https://user:secret@example.myshopify.com/admin"
    monkeypatch.setenv(ENV_TOKEN, token)
    monkeypatch.setenv(ENV_DOMAIN, shop)
    report = inspect_catalog_secrets()
    blob = json.dumps(report)
    assert report["token_status"] == "invalid"
    assert report["domain_status"] == "invalid"
    assert token not in blob
    assert shop not in blob
    assert "user:secret" not in blob


def test_live_catalog_read_never_calls_urlopen(monkeypatch):
    monkeypatch.setenv(ENV_TOKEN, "shpat_testvalue_not_for_git")
    monkeypatch.setenv(ENV_DOMAIN, "example-store.myshopify.com")
    called = {"n": 0}

    def boom(*_args, **_kwargs):
        called["n"] += 1
        raise AssertionError("urlopen")

    monkeypatch.setattr("grokbot.connectors.shopify_read.urllib.request.urlopen", boom)
    monkeypatch.setattr("grokbot.connectors.shopify_read.EXTERNAL_CONNECTIONS_ENABLED", True)
    monkeypatch.setattr("grokbot.connectors.shopify_read.SHOPIFY_LIVE_REQUESTS_ENABLED", True)
    withheld = attempt_live_catalog_read(approval_granted=True)
    blob = json.dumps(withheld)
    assert withheld["live_request_permitted"] is False
    assert withheld["production_sender_installed"] is False
    assert withheld["urlopen_called"] is False
    assert withheld["network_calls"] == 0
    assert withheld["credentials_used"] is False
    assert withheld["executed"] is False
    assert "shpat_testvalue_not_for_git" not in blob
    assert "example-store.myshopify.com" not in blob
    assert called["n"] == 0


def test_tracked_files_do_not_contain_shopify_tokens():
    tracked = subprocess.check_output(["git", "ls-files"], cwd=REPO_ROOT, text=True).splitlines()
    assert ".env" not in tracked
    assert ".env.example" in tracked
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "src/grokbot/envconfig/shopify.py"],
        cwd=REPO_ROOT,
    )
    assert ignored.returncode != 0
    roots = [REPO_ROOT / "src", REPO_ROOT / "docs", REPO_ROOT / "config", REPO_ROOT / ".env.example"]
    for root in roots:
        paths = [root] if root.is_file() else root.rglob("*")
        for path in paths:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            assert _TOKEN_VALUE.search(text) is None, f"{path} contains a token value"


def test_connector_prepare_command_passes():
    assert main(["connector", "prepare"]) == 0
