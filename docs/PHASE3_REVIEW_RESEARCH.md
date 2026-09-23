# GROKBOT COMMERCE — Phase 3 human review and commerce research

Phase 3 adds a human review surface and read-only research for three future
operating divisions. It does not connect production credentials and it does not
execute consequential actions.

## What runs

- **Human review queue.** Stopped runs can be enqueued under `.grokbot_state/reviews/`, which is git-ignored. `grokbot review list`, `show`, `render`, `serve`, and `decide` inspect or record a decision.
- **Read-only HTML page.** `grokbot review render` writes a self-contained page. `grokbot review serve` answers GET on localhost and rejects POST. The page cannot approve or execute anything.
- **Read-only connectors.** Shipped connectors are mocks: market signals, a US supplier directory, a Shopify catalog view, and a Fiverr marketplace view. Allowed operations are `search` and `describe`. Publish, purchase, order, message, refund, catalog write, and supplier contact are refused. An unconfigured read-only connector returns UNKNOWN and does not read credentials.
- **Print on demand.** `pod_research_review` researches a TEST/MOCK shirt and hat concept and prepares unpublished drafts.
- **US dropshipping.** `us_dropship_research_review` researches a product, requires mock US-warehouse evidence, calculates economics from supplied numbers, and prepares an unpublished listing. Fast shipping is not labeled FACT.
- **Fiverr services.** `fiverr_service_research_review` researches a service, prepares task state, and drafts a message. A complaint or refund request escalates. Nothing is sent and no refund is issued.

Phase 2 discovery workflows (`pod_opportunity_discovery` and `us_dropshipping_opportunity_discovery`) are unchanged. `shopify_store_builder_agent` and `customer_service_agent` stay non-executable.

## What stays blocked

Approval, including `grokbot review decide --decision approved`, records a decision and sets `executed_external_action` to false. Unresolved IP risk leaves the review pending. The stable block code `phase_2_offline_no_consequential_actions` still refuses launch, purchase, supplier commitment, publication, customer messages, refunds, Fiverr orders, Fiverr contact, supplier contact, and Shopify production changes.

Missing connector queries stay UNKNOWN. FACT claims still require verified TEST/MOCK evidence. PROHIBITED categories cannot be relaxed.

## Commands

```bash
grokbot validate
grokbot research pod_research_review --packet pod_research_ready
grokbot research us_dropship_research_review --packet dropship_research_ready
grokbot research fiverr_service_research_review --packet fiverr_revision_ready
grokbot review list
```

Do not begin Phase 4, and do not add production credentials, without explicit human approval.
