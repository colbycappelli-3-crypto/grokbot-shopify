# GROKBOT COMMERCE — Phase 4 human approval workflow

Phase 4 presents a proposed consequential action to the human owner, records an
explicit approve or reject decision, and keeps that record on the proposal.
An approved action advances only to the `execution_withheld` gate.

## What an approval does

- `grokbot approve propose` creates a proposal from the current approval policy.
- `grokbot approve show` presents the category, class, summary, gate, and decision record.
- `grokbot approve decide --decision approved|rejected` records the owner decision.
- A classified `APPROVAL_REQUIRED` action that is approved, and that is not blocked by unresolved screening, moves from `awaiting_decision` to `approved_not_executed` with next gate `execution_withheld`.
- `grokbot approve release` confirms that gate and still performs no external effect.
- `grokbot approve demo` runs this path on the TEST/MOCK print-on-demand research packet.

## What stays blocked

- Unclassified categories, including consequential categories that are not in the approval policy, stay blocked even if someone records an approval. The policy default remains `APPROVAL_REQUIRED`.
- `PROHIBITED` categories cannot advance.
- Unresolved IP or prohibited-product screening blocks advancement.
- A rejected proposal does not advance.
- Release never publishes, purchases, contacts a supplier, messages a user, places an order, issues a refund, or makes a financial commitment. No production credentials are read.

The historical block code `phase_2_offline_no_consequential_actions` still refuses execution after approval.

Phase 5 names a disconnected Shopify catalog read. See
[`PHASE5_READONLY_CONNECTOR.md`](PHASE5_READONLY_CONNECTOR.md). Do not connect
that credential without explicit human approval.
