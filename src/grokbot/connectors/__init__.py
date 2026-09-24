"""Read-only commerce research connectors.

Mock connectors read local TEST/MOCK payloads. The Shopify catalog connector
names the credential it would need and does not connect.
"""
from .registry import (
    ALLOWED_OPERATIONS,
    FORBIDDEN_OPERATIONS,
    ConnectorRegistry,
    UnconfiguredReadOnlyConnector,
)
from .shopify_read import ShopifyCatalogReadConnector

__all__ = [
    "ALLOWED_OPERATIONS",
    "FORBIDDEN_OPERATIONS",
    "ConnectorRegistry",
    "ShopifyCatalogReadConnector",
    "UnconfiguredReadOnlyConnector",
]
