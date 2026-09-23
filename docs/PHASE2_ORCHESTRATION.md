# GROKBOT COMMERCE — Phase 2 offline orchestration

Phase 2 runs commerce-intelligence workflows **offline**. Agents read TEST/MOCK
fixtures or upstream structured outputs. They do not fetch URLs, contact
suppliers, or call Shopify, Fiverr, or a payment provider.

## What the runner does

`WorkflowRunner` (`grokbot.orchestrator.engine`):

1. Selects a workflow by explicit id, or by division (`print_on_demand` →
   `pod_opportunity_discovery`, `us_dropshipping` →
   `us_dropshipping_opportunity_discovery`).
2. Creates a project id and one job per action stage.
3. Runs a stage only after its dependencies have passed.
4. Passes upstream structured outputs forward. Only trend discovery and market
   research receive the fixture. Later agents read the handoff.
5. Downgrades any `FACT` that lacks verified evidence to `UNKNOWN` before the
   next agent sees it.
6. Evaluates validation gates from `config/validation_gates.yaml`.
7. On failure, stops with `request_more_research`, `reject`, `escalate`, or
   `halt`, and still writes a dossier.
8. Stops at the human-review gate. A simulated approval is recorded only. It
   does not launch a store, commit a supplier, purchase, publish, or advertise.
9. Refuses `PROHIBITED` stages and any consequential action category.

Phase 1 workflows `pod_product_concept` and `us_dropshipping_opportunity` still
load and still plan. They are not the Phase 2 discovery paths.

## Epistemic labels

| Label | Meaning |
| --- | --- |
| FACT | Every cited evidence record exists and is verified. Mock support is labeled TEST/MOCK. |
| INFERENCE | A conclusion drawn from supplied inputs. Not a fact. |
| ASSUMPTION | An explicit assumption. Not a fact. |
| UNKNOWN | Missing or unsupported. Never promoted silently. |

## Validation gates

Thresholds live in `config/validation_gates.yaml` and are marked
`configurable_defaults`. Current gates:

- `minimum_evidence_completeness`
- `excessive_unknown_critical_fields`
- `product_validation_outcome` (`VALIDATE`, `RESEARCH_FURTHER`, `REJECT`)
- `economics_completeness`
- `margin_threshold` (applied only when gross margin was computed)
- `unresolved_ip_risk`
- `unresolved_prohibited_product_risk`
- `supplier_evidence_requirement` (US dropshipping workflows)

Unit economics uses only supplied numbers:

`gross_profit = selling_price - product_cost - shipping - platform_fees - payment_fees - fulfillment_cost`

A missing input stays `UNKNOWN`. Break-even units are computed only when fixed
costs and a positive gross profit are both present.

## Discovery workflows

Both end at a human-review gate. Nothing after that gate is executed.

- `pod_opportunity_discovery`
- `us_dropshipping_opportunity_discovery` (adds preliminary supplier/fulfillment
  evidence; no live supplier call)

## Fixtures

Shipped packets in `src/grokbot/fixtures/` are `TEST_MOCK` data:

| Fixture | Expected stop |
| --- | --- |
| `promising_pod` | Human review |
| `promising_dropship` | Human review, mock US fulfillment, no supplier contact |
| `research_further` | More research; economics not assessed |
| `rejected_opportunity` | Reject; verified absence of demand |
| `attractive_economics_ip_risk` | Escalation; margin does not clear unresolved IP |
| `dropship_missing_us_fulfillment` | More research; US fulfillment stays UNKNOWN |

```bash
grokbot simulate pod_opportunity_discovery --fixture promising_pod
grokbot simulate us_dropshipping_opportunity_discovery --fixture promising_dropship
```

## Audit events

`project_created`, `job_created`, `job_assigned`, `job_completed`, `job_failed`,
`evidence_added`, `validation_gate_evaluated`, `workflow_stopped`,
`approval_requested`, `approval_decision`, plus `action_blocked`,
`retry_scheduled`, and `decision_recorded`. Secret-like keys and recognizable
credential values are redacted.
