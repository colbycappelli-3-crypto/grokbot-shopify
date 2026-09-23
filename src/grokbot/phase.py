"""Phase 4 execution boundary.

A human owner can be shown a proposed consequential action and can approve or
reject it. Approval advances that action only as far as a withheld-execution
gate. This phase still does not publish, purchase, contact, message, order,
refund, or spend.

The historical block code ``phase_2_offline_no_consequential_actions`` is
unchanged so earlier workflows keep the same fail-safe.
"""
from __future__ import annotations

PHASE = "phase_4_approval_workflow"
EXTERNAL_CONNECTIONS_ENABLED = False

# Action categories that would change the outside world. This phase never
# executes them. Approval-policy classes still apply; this set is an additional stop.
CONSEQUENTIAL_ACTION_CATEGORIES = frozenset(
    {
        "publish_external_content",
        "launch_store",
        "change_production_system",
        "financial_commitment",
        "purchase",
        "supplier_commitment",
        "send_customer_message",
        "customer_refund",
        "connect_external_account",
        "pod_account_action",
        "advertising",
        "product_publication",
        "place_fiverr_order",
        "contact_fiverr_user",
        "modify_shopify_production",
        "contact_supplier",
    }
)

# Agent roles that would perform consequential work. They stay registered so
# later phases can attach runtimes, but this phase will not invoke them.
NON_EXECUTABLE_AGENTS = frozenset(
    {
        "shopify_store_builder_agent",
        "customer_service_agent",
    }
)

DISCOVERY_WORKFLOWS = {
    "print_on_demand": "pod_opportunity_discovery",
    "us_dropshipping": "us_dropshipping_opportunity_discovery",
}
