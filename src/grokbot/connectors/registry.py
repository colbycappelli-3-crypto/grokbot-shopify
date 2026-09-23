"""Connector registry.

Operations are search and describe only. Forbidden operations return a refusal
and an empty external-action list. Missing queries stay UNKNOWN.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from ..resources import CONNECTOR_MOCKS_DIR, CONNECTOR_SPECS_DIR
from ..validation import iter_spec_files, load_and_validate, validate

ALLOWED_OPERATIONS = frozenset({"search", "describe"})
FORBIDDEN_OPERATIONS = frozenset(
    {
        "publish",
        "purchase",
        "create_order",
        "place_order",
        "send_message",
        "refund",
        "launch_store",
        "contact_supplier",
        "update_product",
        "create_listing",
        "modify_shopify",
        "connect",
    }
)


class ConnectorError(ValueError):
    pass


def _base(
    *,
    connector_id: str,
    operation: str,
    query_id: str,
    mode: str,
    data_classification: str,
    refused: bool,
    refusal_code: Optional[str],
    payload,
    evidence_records,
    unknowns,
    local_read: bool,
) -> dict:
    result = {
        "connector_id": connector_id,
        "operation": operation,
        "mode": mode,
        "access": "read_only",
        "query_id": query_id,
        "data_classification": data_classification,
        "external_actions": [],
        "network_calls": 0,
        "credentials_used": False,
        "production_connected": False,
        "executed": False,
        "refused": refused,
        "refusal_code": refusal_code,
        "local_read": local_read,
        "payload": payload,
        "evidence_records": list(evidence_records or []),
        "unknowns": list(unknowns or []),
    }
    validate(result, "connector_result", source=f"connector:{connector_id}")
    return result


def _refusal(connector_id: str, operation: str, query_id: str) -> dict:
    return _base(
        connector_id=connector_id or "unspecified",
        operation=operation,
        query_id=query_id or "",
        mode="refused",
        data_classification="UNKNOWN",
        refused=True,
        refusal_code="forbidden_operation",
        payload=None,
        evidence_records=[],
        unknowns=["Operation refused. No external action was performed."],
        local_read=False,
    )


def _unknown(
    connector_id: str,
    operation: str,
    query_id: str,
    *,
    mode: str,
    code: str,
    message: str,
) -> dict:
    return _base(
        connector_id=connector_id,
        operation=operation,
        query_id=query_id,
        mode=mode,
        data_classification="UNKNOWN",
        refused=False,
        refusal_code=code,
        payload=None,
        evidence_records=[],
        unknowns=[message],
        local_read=True,
    )


class UnconfiguredReadOnlyConnector:
    """A connector interface with no credentials and no mock payload.

    Calls do not read the process environment and do not open a network connection.
    """

    connector_id = "unconfigured_read_only"

    def execute(self, operation: str, query_id: str = "") -> dict:
        if operation not in ALLOWED_OPERATIONS or operation in FORBIDDEN_OPERATIONS:
            return _refusal(self.connector_id, operation, query_id)
        return _unknown(
            self.connector_id,
            operation,
            query_id,
            mode="read_only",
            code="connector_not_configured",
            message="Read-only connector is not configured. Result is UNKNOWN. No credentials were read.",
        )


class ConnectorRegistry:
    def __init__(self, specs: Dict[str, dict], mocks: Dict[str, dict]):
        self.specs = specs
        self.mocks = mocks

    def __len__(self) -> int:
        return len(self.specs)

    def get(self, connector_id: str) -> Optional[dict]:
        return self.specs.get(connector_id)

    @classmethod
    def load(
        cls,
        spec_dir: Optional[Path] = None,
        mock_dir: Optional[Path] = None,
    ) -> "ConnectorRegistry":
        spec_dir = spec_dir or CONNECTOR_SPECS_DIR
        mock_dir = mock_dir or CONNECTOR_MOCKS_DIR
        specs: Dict[str, dict] = {}
        for path in iter_spec_files(spec_dir):
            spec = load_and_validate(path, "research_connector")
            _check_spec(spec, path)
            if spec["id"] in specs:
                raise ConnectorError(f"Duplicate connector id '{spec['id']}'.")
            specs[spec["id"]] = spec
        mocks: Dict[str, dict] = {}
        for path in iter_spec_files(mock_dir):
            mock = load_and_validate(path, "connector_mock")
            connector_id = mock["connector_id"]
            if connector_id not in specs:
                raise ConnectorError(f"{path}: mock references unknown connector '{connector_id}'.")
            if specs[connector_id]["mode"] != "mock":
                raise ConnectorError(f"{path}: mock file supplied for a non-mock connector.")
            blob = f"{mock.get('banner', '')} {mock.get('data_classification', '')}".upper()
            if "MOCK" not in blob and "TEST" not in blob:
                raise ConnectorError(f"{path}: mock data must be marked TEST or MOCK.")
            for query_id, query in (mock.get("queries") or {}).items():
                for record in query.get("evidence") or []:
                    validate(record, "evidence_record", source=f"{path}:{query_id}")
            mocks[connector_id] = mock
        for connector_id, spec in specs.items():
            if spec["mode"] == "mock" and connector_id not in mocks:
                raise ConnectorError(f"Mock connector '{connector_id}' has no mock payload file.")
        return cls(specs, mocks)

    def execute(self, connector_id: str, operation: str, query_id: str = "") -> dict:
        if operation not in ALLOWED_OPERATIONS or operation in FORBIDDEN_OPERATIONS:
            return _refusal(connector_id, operation, query_id)
        spec = self.specs.get(connector_id)
        if spec is None:
            return _unknown(
                connector_id,
                operation,
                query_id,
                mode="read_only",
                code="unknown_connector",
                message=f"Connector '{connector_id}' is not registered. Result is UNKNOWN.",
            )
        if operation not in set(spec.get("operations_allowed") or []):
            return _refusal(connector_id, operation, query_id)
        if spec["mode"] != "mock":
            return UnconfiguredReadOnlyConnector().execute(operation, query_id)
        mock = self.mocks.get(connector_id) or {}
        query = (mock.get("queries") or {}).get(query_id)
        if not isinstance(query, dict):
            return _unknown(
                connector_id,
                operation,
                query_id,
                mode="mock",
                code="unknown_query",
                message="Query was not in the TEST/MOCK packet. Result is UNKNOWN. No fact was invented.",
            )
        classification = query.get("data_classification", "UNKNOWN")
        if classification != "TEST_MOCK":
            return _unknown(
                connector_id,
                operation,
                query_id,
                mode="mock",
                code="unlabeled_mock",
                message="Mock query was not labeled TEST_MOCK. Result is UNKNOWN.",
            )
        payload = query.get("payload")
        return _base(
            connector_id=connector_id,
            operation=operation,
            query_id=query_id,
            mode="mock",
            data_classification="TEST_MOCK",
            refused=False,
            refusal_code=None,
            payload=payload if isinstance(payload, dict) else None,
            evidence_records=list(query.get("evidence") or []),
            unknowns=list(query.get("unknowns") or []),
            local_read=True,
        )


def _check_spec(spec: dict, path: Path) -> None:
    if spec["mode"] not in {"mock", "read_only"}:
        raise ConnectorError(f"{path}: mode must be mock or read_only.")
    if spec["access"] != "read_only":
        raise ConnectorError(f"{path}: access must be read_only.")
    if spec.get("credentials_required"):
        raise ConnectorError(f"{path}: credentials are not allowed in this phase.")
    if spec.get("production_connected"):
        raise ConnectorError(f"{path}: production connections are not allowed in this phase.")
    allowed = set(spec.get("operations_allowed") or [])
    forbidden = set(spec.get("operations_forbidden") or [])
    if not allowed or not allowed <= ALLOWED_OPERATIONS:
        raise ConnectorError(f"{path}: operations_allowed must be a subset of search and describe.")
    if not FORBIDDEN_OPERATIONS <= forbidden:
        missing = sorted(FORBIDDEN_OPERATIONS - forbidden)
        raise ConnectorError(f"{path}: operations_forbidden is missing {missing}.")
    if allowed & forbidden:
        raise ConnectorError(f"{path}: an operation cannot be both allowed and forbidden.")
