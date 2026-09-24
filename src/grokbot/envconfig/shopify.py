"""Shopify catalog environment configuration.

Values are read from the process environment only. This module does not read
`.env`, does not return secret values, and does not contact Shopify.
"""
from __future__ import annotations

import os
import re

ENV_DOMAIN = "SHOPIFY_STORE_DOMAIN"
ENV_TOKEN = "SHOPIFY_ADMIN_TOKEN"
SCOPE = "read_products"
PLACEHOLDER = "REPLACE_ME"
_SECRET_ENV_NAMES = (
    ENV_TOKEN,
    ENV_DOMAIN,
    "SHOPIFY_API_KEY",
    "SHOPIFY_API_SECRET",
    "GROK_API_KEY",
)
_HOSTNAME = re.compile(
    r"^(?:localhost|127\.0\.0\.1|(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,})$"
)
_ADMIN_PREFIXES = ("shpat_", "shpca_", "shpss_", "shppa_")


def configured_secret_values() -> list:
    """Return configured secret strings so logs can redact them. Callers must not print the list."""
    found = []
    for name in _SECRET_ENV_NAMES:
        value = os.environ.get(name, "")
        if value and value != PLACEHOLDER and len(value) >= 8:
            found.append(value)
    return found


def _domain_status(value: str) -> str:
    if not value:
        return "missing"
    if value == PLACEHOLDER:
        return "placeholder"
    candidate = value.strip().lower()
    if any(mark in candidate for mark in ("://", "/", "\\", "@", " ", "?", "#")):
        return "invalid"
    if _HOSTNAME.match(candidate) is None:
        return "invalid"
    return "present"


def _token_status(value: str) -> tuple:
    if not value:
        return "missing", False
    if value == PLACEHOLDER:
        return "placeholder", False
    if any(character.isspace() for character in value) or len(value) < 16 or "://" in value:
        return "invalid", False
    return "present", value.startswith(_ADMIN_PREFIXES)


def inspect_catalog_secrets() -> dict:
    """Describe whether the catalog credential is present. Do not include its value."""
    domain = os.environ.get(ENV_DOMAIN, "")
    token = os.environ.get(ENV_TOKEN, "")
    token_status, prefix_recognized = _token_status(token)
    report = {
        "env_vars": [ENV_DOMAIN, ENV_TOKEN],
        "scope": SCOPE,
        "loaded_from": "process_environment",
        "files_read": [],
        "values_included": False,
        "domain_status": _domain_status(domain),
        "token_status": token_status,
        "token_prefix_recognized": prefix_recognized,
        "api_key_used": False,
        "api_secret_used": False,
    }
    blob = str(report)
    for value in (domain, token):
        if value and value != PLACEHOLDER and value in blob:
            raise RuntimeError("Catalog secret inspection included a secret value.")
    return report
