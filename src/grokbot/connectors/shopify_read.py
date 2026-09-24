"""Shopify catalog read that does not connect.

The planned request is a single GET of the product catalog. This module refuses
every other method and every non-loopback host before opening a request.
Production Shopify is never contacted. A loopback probe may use a fake token
that starts with ``TEST_MOCK_`` so tests can show the GET path. That probe is
TEST/MOCK data and is not a catalog fact.

Phase 6 can see whether the catalog credential is present in the process
environment. It still has no sender for the real store.
"""
from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import urlparse

import urllib.request

from ..phase import EXTERNAL_CONNECTIONS_ENABLED, SHOPIFY_LIVE_REQUESTS_ENABLED
from ..envconfig.shopify import inspect_catalog_secrets
from .registry import ALLOWED_OPERATIONS, FORBIDDEN_OPERATIONS, _base, _refusal

CONNECTOR_ID = "shopify_catalog_read"
ENV_DOMAIN = "SHOPIFY_STORE_DOMAIN"
ENV_TOKEN = "SHOPIFY_ADMIN_TOKEN"
SCOPE = "read_products"
API_NAME = "Shopify Admin API"
API_PATH = "/admin/api/2024-10/products.json"
PLACEHOLDER_HOST = "{SHOPIFY_STORE_DOMAIN}"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})

CREDENTIAL_NEEDED = {
    "name": "Shopify Admin API access token",
    "env_vars": [ENV_DOMAIN, ENV_TOKEN],
    "scope": SCOPE,
    "api": API_NAME,
    "method": "GET",
    "host_placeholder": PLACEHOLDER_HOST,
    "path": API_PATH,
}


class _SilentHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = b'{"products":[],"data_classification":"TEST_MOCK"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A002
        return


class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _configured(name: str) -> bool:
    value = os.environ.get(name, "")
    return bool(value) and value != "REPLACE_ME"


def _scrub(text: str) -> str:
    for name in (ENV_TOKEN, ENV_DOMAIN, "SHOPIFY_API_KEY", "SHOPIFY_API_SECRET"):
        value = os.environ.get(name, "")
        if value and value != "REPLACE_ME" and value in text:
            text = text.replace(value, "[REDACTED]")
    return text


class ShopifyCatalogReadConnector:
    """Describe a catalog GET. Do not send it."""

    connector_id = CONNECTOR_ID

    def execute(self, operation: str, query_id: str = "") -> dict:
        if operation not in ALLOWED_OPERATIONS or operation in FORBIDDEN_OPERATIONS:
            return _refusal(self.connector_id, operation, query_id)
        if EXTERNAL_CONNECTIONS_ENABLED:
            return _base(
                connector_id=self.connector_id,
                operation=operation,
                query_id=query_id,
                mode="read_only",
                data_classification="UNKNOWN",
                refused=True,
                refusal_code="connection_not_approved",
                payload=None,
                evidence_records=[],
                unknowns=[
                    "The catalog connector stays disconnected. No Shopify request was sent. Result is UNKNOWN."
                ],
                local_read=False,
                credential_needed=dict(CREDENTIAL_NEEDED),
            )
        waiting = _configured(ENV_TOKEN) or _configured(ENV_DOMAIN)
        if waiting:
            code = "connection_not_approved"
            message = (
                "SHOPIFY_ADMIN_TOKEN and SHOPIFY_STORE_DOMAIN are present in the process "
                "environment, but this connection waits for human approval. No request was sent. "
                "Result is UNKNOWN."
            )
        else:
            code = "credential_required"
            message = (
                "Credential required before any Shopify catalog read: "
                "SHOPIFY_ADMIN_TOKEN (Shopify Admin API access token, scope read_products only) "
                "and SHOPIFY_STORE_DOMAIN (shop hostname). No request was sent. Result is UNKNOWN."
            )
        return _base(
            connector_id=self.connector_id,
            operation=operation,
            query_id=query_id,
            mode="read_only",
            data_classification="UNKNOWN",
            refused=False,
            refusal_code=code,
            payload=None,
            evidence_records=[],
            unknowns=[message],
            local_read=False,
            credential_needed=dict(CREDENTIAL_NEEDED),
        )


def perform_readonly_probe(url: str, token: str, method: str = "GET") -> dict:
    """Open a GET only after the host, scheme, method, and token are allowed.

    Any other host, including a Shopify hostname, is refused before urlopen.
    """
    parsed = urlparse(url)
    host = parsed.hostname
    result = {
        "ok": False,
        "method": method,
        "host": host,
        "production_connected": False,
        "data_classification": "TEST_MOCK",
        "network_calls": 0,
        "credentials_used": False,
        "urlopen_called": False,
        "code": "refused",
    }
    if not isinstance(token, str) or (token and token in url):
        result["code"] = "token_not_test_mock"
        result["host"] = None
        return result
    if method != "GET":
        result["code"] = "method_not_get"
        return result
    if host not in LOOPBACK_HOSTS:
        result["code"] = "host_not_loopback"
        return result
    if parsed.scheme != "http":
        result["code"] = "scheme_not_http"
        return result
    if not token.startswith("TEST_MOCK_"):
        result["code"] = "token_not_test_mock"
        return result
    request = urllib.request.Request(url, method="GET")
    request.add_header("X-Grokbot-Probe", "1")
    previous = getattr(urllib.request, "_opener", None)
    urllib.request.install_opener(urllib.request.build_opener(_RefuseRedirect))
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            raw = response.read(2048)
            status = getattr(response, "status", response.getcode())
    except Exception as exc:  # noqa: BLE001 — probe failure stays local and unlabeled
        result["code"] = "loopback_failed"
        result["urlopen_called"] = True
        result["error_type"] = type(exc).__name__
        return result
    finally:
        urllib.request._opener = previous
    preview = raw.decode("utf-8", errors="replace")
    if token in preview:
        preview = preview.replace(token, "[REDACTED]")
    return {
        "ok": status == 200 and "TEST_MOCK" in preview,
        "method": "GET",
        "host": host,
        "status": status,
        "body_preview": preview[:200],
        "production_connected": False,
        "data_classification": "TEST_MOCK",
        "network_calls": 1,
        "credentials_used": False,
        "urlopen_called": True,
        "code": "loopback_get",
    }


def run_loopback_probe() -> dict:
    """Serve one TEST/MOCK JSON document on 127.0.0.1 and GET it."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SilentHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        return perform_readonly_probe(
            f"http://127.0.0.1:{port}{API_PATH}",
            "TEST_MOCK_loopback",
            "GET",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def demonstrate_readonly_connector() -> dict:
    """Show the disconnected catalog read and the still-blocked write path."""
    from ..audit.log import AuditLog
    from ..fixtures.loader import load_research_packet
    from ..orchestrator.engine import build_runner
    from .registry import ConnectorRegistry

    registry = ConnectorRegistry.load()
    spec = registry.get(CONNECTOR_ID) or {}
    described = registry.execute(CONNECTOR_ID, "describe", "catalog-products")
    published = registry.execute(CONNECTOR_ID, "publish", "catalog-products")
    probe = run_loopback_probe()
    blocked_host = perform_readonly_probe(
        "https://example.myshopify.com/admin/api/2024-10/products.json",
        "TEST_MOCK_loopback",
        "GET",
    )
    blocked_method = perform_readonly_probe(
        "http://127.0.0.1/admin/api/2024-10/products.json",
        "TEST_MOCK_loopback",
        "POST",
    )
    packet = load_research_packet("pod_research_ready")
    runner = build_runner()
    run = runner.open_opportunity(packet["objective"], workflow_id=packet["workflow_id"], fixture=packet)
    runner.run(run)
    launch = runner.attempt_action(run, "launch_store")
    audit = AuditLog()
    audit.record(
        "connector_queried",
        connector_id=CONNECTOR_ID,
        operation="describe",
        refusal_code=described["refusal_code"],
        network_calls=0,
        production_connected=False,
        credentials_used=False,
        connection_status="not_connected",
    )
    run.audit.record(
        "connector_queried",
        connector_id=CONNECTOR_ID,
        operation="describe",
        refusal_code=described["refusal_code"],
        network_calls=0,
        production_connected=False,
        credentials_used=False,
        connection_status="not_connected",
    )
    launch_codes = [reason["code"] for reason in launch["reasons"]]
    ok = (
        EXTERNAL_CONNECTIONS_ENABLED is False
        and spec.get("production_connected") is False
        and spec.get("credentials_required") is True
        and described["network_calls"] == 0
        and described["executed"] is False
        and described["credentials_used"] is False
        and described["production_connected"] is False
        and described["connection_status"] == "not_connected"
        and described["data_classification"] == "UNKNOWN"
        and described["refusal_code"] in {"credential_required", "connection_not_approved"}
        and described["external_actions"] == []
        and published["refused"] is True
        and published["executed"] is False
        and probe["ok"] is True
        and probe["method"] == "GET"
        and probe["host"] == "127.0.0.1"
        and probe["production_connected"] is False
        and blocked_host["ok"] is False
        and blocked_host["code"] == "host_not_loopback"
        and blocked_host["urlopen_called"] is False
        and blocked_host["network_calls"] == 0
        and blocked_method["code"] == "method_not_get"
        and blocked_method["urlopen_called"] is False
        and launch["executed"] is False
        and "phase_2_offline_no_consequential_actions" in launch_codes
        and run.external_actions_performed == []
        and audit.of_type("connector_queried")
    )
    credential = described["credential_needed"] or {}
    lines = [
        f"Connector: {CONNECTOR_ID}",
        f"Credential needed: {credential.get('name')} scope {credential.get('scope')}",
        f"Environment variables: {', '.join(credential.get('env_vars') or [])}",
        f"Planned request: GET https://{PLACEHOLDER_HOST}{API_PATH}",
        f"Catalog query: code={described['refusal_code']} network_calls={described['network_calls']} "
        f"executed={described['executed']} connection={described['connection_status']}",
        f"Publish refused: {published['refused']} executed={published['executed']}",
        f"Loopback GET: ok={probe['ok']} host={probe['host']} classification={probe['data_classification']}",
        f"Shopify host refused before urlopen: {blocked_host['code']}",
        f"POST refused before urlopen: {blocked_method['code']}",
        f"launch_store executed={launch['executed']} codes={','.join(launch_codes)}",
        f"External actions performed: {len(run.external_actions_performed)}",
        "Production Shopify was not contacted. Connection waits for human approval.",
    ]
    text = _scrub("\n".join(lines))
    blob = _scrub(json.dumps({"described": described, "published": published, "probe": probe}))
    return {
        "ok": ok and "TEST_MOCK_loopback" not in text,
        "text": text,
        "described": described,
        "published": published,
        "probe": probe,
        "blocked_host": blocked_host,
        "blocked_method": blocked_method,
        "launch": launch,
        "audit": audit,
        "blob": blob,
    }


def attempt_live_catalog_read(*, approval_granted: bool = False) -> dict:
    """Decide whether a production catalog GET could run. It cannot in this phase.

    There is no production sender. Forcing the enable flags on still does not
    call urlopen. Loopback probes stay on ``perform_readonly_probe``.
    """
    secrets = inspect_catalog_secrets()
    reasons = []
    if not EXTERNAL_CONNECTIONS_ENABLED:
        reasons.append("external_connections_disabled")
    if not SHOPIFY_LIVE_REQUESTS_ENABLED:
        reasons.append("live_requests_disabled")
    if not approval_granted:
        reasons.append("human_approval_required")
    if secrets["domain_status"] != "present" or secrets["token_status"] != "present":
        reasons.append("credential_required")
    return {
        "connector_id": CONNECTOR_ID,
        "method": "GET",
        "scope": SCOPE,
        "path": API_PATH,
        "host_placeholder": PLACEHOLDER_HOST,
        "external_connections_enabled": EXTERNAL_CONNECTIONS_ENABLED,
        "live_requests_enabled": SHOPIFY_LIVE_REQUESTS_ENABLED,
        "approval_granted": approval_granted,
        "secrets": secrets,
        "reasons": reasons,
        "live_request_permitted": False,
        "production_sender_installed": False,
        "network_calls": 0,
        "credentials_used": False,
        "production_connected": False,
        "executed": False,
        "urlopen_called": False,
        "refusal_code": reasons[0] if reasons else "production_sender_not_installed",
    }


def demonstrate_connection_preparation(directory) -> dict:
    """Show local secret status, a withheld approval, and no Shopify request."""
    from ..approval.workflow import ApprovalWorkflow
    from ..audit.log import AuditLog
    from ..fixtures.loader import load_research_packet
    from ..orchestrator.engine import build_runner

    secrets = inspect_catalog_secrets()
    withheld = attempt_live_catalog_read(approval_granted=True)
    packet = load_research_packet("pod_research_ready")
    runner = build_runner()
    run = runner.open_opportunity(packet["objective"], workflow_id=packet["workflow_id"], fixture=packet)
    runner.run(run)
    store = ApprovalWorkflow(directory)
    proposal = runner.propose_consequential_action(
        run,
        store,
        "connect_external_account",
        "TEST/MOCK proposal: connect the Shopify catalog read for GET read_products only. No store would be contacted.",
    )
    decided = runner.decide_consequential_action(
        run,
        store,
        proposal["proposal_id"],
        "approved",
        note="advance the gate only",
    )
    released = runner.release_consequential_action(run, store, proposal["proposal_id"])
    audit = AuditLog()
    audit.record(
        "connection_withheld",
        connector_id=CONNECTOR_ID,
        scope=SCOPE,
        method="GET",
        domain_status=secrets["domain_status"],
        token_status=secrets["token_status"],
        external_connections_enabled=False,
        live_requests_enabled=False,
        network_calls=0,
        credentials_used=False,
        production_connected=False,
        refusal_code=withheld["refusal_code"],
    )
    run.audit.record(
        "connection_withheld",
        connector_id=CONNECTOR_ID,
        scope=SCOPE,
        domain_status=secrets["domain_status"],
        token_status=secrets["token_status"],
        network_calls=0,
        production_connected=False,
    )
    ok = (
        EXTERNAL_CONNECTIONS_ENABLED is False
        and SHOPIFY_LIVE_REQUESTS_ENABLED is False
        and withheld["live_request_permitted"] is False
        and withheld["urlopen_called"] is False
        and withheld["network_calls"] == 0
        and withheld["credentials_used"] is False
        and withheld["production_connected"] is False
        and withheld["executed"] is False
        and withheld["production_sender_installed"] is False
        and secrets["values_included"] is False
        and secrets["files_read"] == []
        and secrets["scope"] == SCOPE
        and secrets["api_key_used"] is False
        and decided["gate_state"] == "approved_not_executed"
        and decided["executed_external_action"] is False
        and released["executed"] is False
        and released["code"] == "phase_2_offline_no_consequential_actions"
        and released["network_calls"] == 0
        and run.external_actions_performed == []
        and audit.of_type("connection_withheld")
    )
    lines = [
        "Phase: phase_6_catalog_connection_prepared",
        f"EXTERNAL_CONNECTIONS_ENABLED: {EXTERNAL_CONNECTIONS_ENABLED}",
        f"SHOPIFY_LIVE_REQUESTS_ENABLED: {SHOPIFY_LIVE_REQUESTS_ENABLED}",
        "Secret source: process environment only. No secret file was read.",
        f"SHOPIFY_STORE_DOMAIN: {secrets['domain_status']}",
        f"SHOPIFY_ADMIN_TOKEN: {secrets['token_status']}",
        f"Token prefix recognized: {secrets['token_prefix_recognized']}",
        f"Scope: {SCOPE}",
        f"Planned request: GET https://{PLACEHOLDER_HOST}{API_PATH}",
        f"Live request permitted: {withheld['live_request_permitted']}",
        f"Production sender installed: {withheld['production_sender_installed']}",
        f"Stop code: {withheld['refusal_code']}",
        f"connect_external_account gate: {decided['gate_state']}",
        f"Release executed={released['executed']} code={released['code']}",
        "Human approval is required before either enable flag may be turned on.",
        "Production Shopify was not contacted.",
    ]
    text = _scrub("\n".join(lines))
    blob = _scrub(json.dumps({"secrets": secrets, "withheld": withheld, "released": released}))
    return {
        "ok": ok,
        "text": text,
        "secrets": secrets,
        "withheld": withheld,
        "decided": decided,
        "released": released,
        "audit": audit,
        "blob": blob,
    }
