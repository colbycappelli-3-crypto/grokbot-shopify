"""Phase 5 read-only Shopify catalog connector. It does not connect."""
import json

from grokbot.cli import main
from grokbot.connectors.registry import ConnectorRegistry, FORBIDDEN_OPERATIONS
from grokbot.connectors.shopify_read import (
    ENV_DOMAIN,
    ENV_TOKEN,
    perform_readonly_probe,
    run_loopback_probe,
)
from grokbot.fixtures.loader import load_research_packet
from grokbot.orchestrator.engine import build_runner
from grokbot.phase import EXTERNAL_CONNECTIONS_ENABLED


def test_catalog_connector_names_the_credential_and_stays_disconnected():
    spec = ConnectorRegistry.load().get("shopify_catalog_read")
    assert spec["mode"] == "read_only"
    assert spec["credentials_required"] is True
    assert spec["production_connected"] is False
    assert spec["credential"]["env_vars"] == [ENV_DOMAIN, ENV_TOKEN]
    assert spec["credential"]["scope"] == "read_products"
    assert spec["credential"]["method"] == "GET"
    assert EXTERNAL_CONNECTIONS_ENABLED is False


def test_missing_credential_returns_unknown_without_a_request(monkeypatch):
    monkeypatch.delenv(ENV_TOKEN, raising=False)
    monkeypatch.delenv(ENV_DOMAIN, raising=False)
    result = ConnectorRegistry.load().execute("shopify_catalog_read", "describe", "catalog-products")
    assert result["data_classification"] == "UNKNOWN"
    assert result["refusal_code"] == "credential_required"
    assert result["network_calls"] == 0
    assert result["credentials_used"] is False
    assert result["production_connected"] is False
    assert result["executed"] is False
    assert result["connection_status"] == "not_connected"
    assert result["payload"] is None
    assert result["external_actions"] == []
    assert result["credential_needed"]["scope"] == "read_products"
    assert result["credential_needed"]["env_vars"] == [ENV_DOMAIN, ENV_TOKEN]
    blob = json.dumps(result)
    assert "read_products" in blob
    assert ENV_TOKEN in blob
    assert ENV_DOMAIN in blob


def test_present_credential_is_not_used_and_not_echoed(monkeypatch):
    secret = "shpat_test_value_not_for_git"
    shop = "example-store.myshopify.com"
    monkeypatch.setenv(ENV_TOKEN, secret)
    monkeypatch.setenv(ENV_DOMAIN, shop)
    called = {"n": 0}

    def boom(*_args, **_kwargs):
        called["n"] += 1
        raise AssertionError("urlopen")

    monkeypatch.setattr("grokbot.connectors.shopify_read.urllib.request.urlopen", boom)
    result = ConnectorRegistry.load().execute("shopify_catalog_read", "search", "catalog-products")
    blob = json.dumps(result)
    assert result["refusal_code"] == "connection_not_approved"
    assert result["network_calls"] == 0
    assert result["credentials_used"] is False
    assert result["production_connected"] is False
    assert result["executed"] is False
    assert result["data_classification"] == "UNKNOWN"
    assert secret not in blob
    assert shop not in blob
    assert called["n"] == 0


def test_forbidden_catalog_operations_are_refused():
    registry = ConnectorRegistry.load()
    for operation in sorted(FORBIDDEN_OPERATIONS):
        result = registry.execute("shopify_catalog_read", operation, "catalog-products")
        assert result["refused"] is True
        assert result["executed"] is False
        assert result["network_calls"] == 0
        assert result["external_actions"] == []
        assert result["production_connected"] is False


def test_loopback_get_succeeds_and_production_hosts_do_not(monkeypatch):
    called = {"n": 0}
    real_open = __import__("urllib.request", fromlist=["urlopen"]).urlopen

    def counting_open(*args, **kwargs):
        called["n"] += 1
        return real_open(*args, **kwargs)

    monkeypatch.setattr("grokbot.connectors.shopify_read.urllib.request.urlopen", counting_open)
    probe = run_loopback_probe()
    assert probe["ok"] is True
    assert probe["method"] == "GET"
    assert probe["host"] == "127.0.0.1"
    assert probe["data_classification"] == "TEST_MOCK"
    assert probe["production_connected"] is False
    assert called["n"] == 1

    blocked = perform_readonly_probe(
        "https://example.myshopify.com/admin/api/2024-10/products.json",
        "TEST_MOCK_loopback",
        "GET",
    )
    assert blocked["code"] == "host_not_loopback"
    assert blocked["urlopen_called"] is False
    assert blocked["network_calls"] == 0
    assert called["n"] == 1

    posted = perform_readonly_probe(
        "http://127.0.0.1/admin/api/2024-10/products.json",
        "TEST_MOCK_loopback",
        "POST",
    )
    assert posted["code"] == "method_not_get"
    assert posted["urlopen_called"] is False
    assert called["n"] == 1

    secure_loopback = perform_readonly_probe(
        "https://127.0.0.1/admin/api/2024-10/products.json",
        "TEST_MOCK_loopback",
        "GET",
    )
    assert secure_loopback["code"] == "scheme_not_http"
    assert secure_loopback["urlopen_called"] is False
    assert called["n"] == 1

    live_token = perform_readonly_probe(
        "http://127.0.0.1/admin/api/2024-10/products.json",
        "shpat_test_value_not_for_git",
        "GET",
    )
    assert live_token["code"] == "token_not_test_mock"
    assert live_token["urlopen_called"] is False
    assert "shpat_test_value_not_for_git" not in json.dumps(live_token)
    assert called["n"] == 1


def test_launch_store_stays_blocked_after_the_catalog_read():
    packet = load_research_packet("pod_research_ready")
    runner = build_runner()
    run = runner.open_opportunity(packet["objective"], workflow_id=packet["workflow_id"], fixture=packet)
    runner.run(run)
    described = ConnectorRegistry.load().execute("shopify_catalog_read", "describe", "catalog-products")
    launch = runner.attempt_action(run, "launch_store")
    codes = [reason["code"] for reason in launch["reasons"]]
    assert described["executed"] is False
    assert launch["executed"] is False
    assert "phase_2_offline_no_consequential_actions" in codes
    assert run.external_actions_performed == []


def test_connector_demo_command_passes():
    assert main(["connector", "demo"]) == 0
    assert main(["connector", "status"]) == 0
