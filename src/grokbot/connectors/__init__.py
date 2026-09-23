"""Read-only commerce research connectors.

Shipped connectors are mocks. An unconfigured read-only connector returns
UNKNOWN and does not perform network calls or read credentials.
"""
from .registry import (
    ALLOWED_OPERATIONS,
    FORBIDDEN_OPERATIONS,
    ConnectorRegistry,
    UnconfiguredReadOnlyConnector,
)

__all__ = [
    "ALLOWED_OPERATIONS",
    "FORBIDDEN_OPERATIONS",
    "ConnectorRegistry",
    "UnconfiguredReadOnlyConnector",
]
