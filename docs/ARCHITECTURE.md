# GROKBOT COMMERCE — Architecture

This document explains the system structure and how the three business divisions
(Print-on-Demand, US Dropshipping, Digital Services/Fiverr) share common
infrastructure while retaining specialized workflows.

## Layered view

```
                         ┌──────────────────────────────┐
Business objective  ───▶ │        GROKBOT ORCHESTRATOR   │  (plan + offline run;
                         │  plan • delegate • gate • stop │   no external actions)
                         └───────────────┬───────────────┘
                                         │ uses
        ┌────────────────────────────────┼────────────────────────────────┐
        ▼                                ▼                                 ▼
┌───────────────┐              ┌──────────────────┐              ┌──────────────────┐
│ Agent Registry│              │ Workflow Specs   │              │ Approval Policy  │
│ (agent specs) │              │ (stage DAGs +    │              │ (owner-editable  │
│               │              │  validation &    │              │  action classes) │
│               │              │  approval gates) │              │                  │
└───────┬───────┘              └────────┬─────────┘              └────────┬─────────┘
        │                               │                                 │
        └───────────────┬───────────────┴────────────────┬───────────────┘
                        ▼                                 ▼
                 ┌───────────────┐                 ┌───────────────┐
                 │ Project/Store │                 │ Shared Schemas│
                 │ State (audit) │                 │ (JSON Schema) │
                 └───────────────┘                 └───────────────┘
```

Every box is data + pure logic. Nothing here connects to an external service in
this phase.

## Components

| Component | Location | Responsibility |
| --- | --- | --- |
| Shared schemas | `src/grokbot/schemas/*.json` | Contracts for agents, workflows, state, and policy. |
| Agent registry | `src/grokbot/agents/` | Load, validate, and index agent specs. |
| Workflow loader | `src/grokbot/workflows/` | Load workflows, validate the DAG, resolve execution order, expose gates. |
| Approval policy | `src/grokbot/policy/` + `config/approval_policy.yaml` | Classify actions as AUTONOMOUS / APPROVAL_REQUIRED / PROHIBITED. |
| Project state | `src/grokbot/state/` | Auditable per-project state: stages, evidence, decisions, approvals, escalations. |
| Orchestrator | `src/grokbot/orchestrator/` | Plan a workflow, or run it offline: create jobs, delegate to logical agents, enforce dependencies, evaluate gates, and stop at human review. |
| Job protocol | `src/grokbot/protocol/` | Structured jobs, agent results, and FACT / INFERENCE / ASSUMPTION / UNKNOWN labels. |
| Evidence ledger | `src/grokbot/evidence/` | Provenance records. Records are marked TEST/MOCK. |
| Validation gates | `src/grokbot/gates/` + `config/validation_gates.yaml` | Configurable screening rules with machine-readable failure reasons. |
| Dossier | `src/grokbot/dossier/` | Aggregated opportunity dossier. Negative evidence stays visible. |
| Audit log | `src/grokbot/audit/` | Structured events for projects, jobs, evidence, gates, stops, and approvals. |
| Connectors | `src/grokbot/connectors/` | Read-only research interfaces. Shipped connectors are mocks. |
| Human review | `src/grokbot/review/` | Local review queue and a GET-only HTML page. Decisions do not execute. |
| Action approval | `src/grokbot/approval/` | Proposed consequential actions, explicit decisions, and a withheld-execution gate. |
| CLI | `src/grokbot/cli.py` | `validate`, `plan`, `simulate`, `research`, and `review`. |
| Specs (data) | `src/grokbot/specs/` | Agent, workflow, and connector specifications. |

## Shared infrastructure vs. specialized workflows

The **shared platform** is division-agnostic: the schemas, registry, workflow
engine, approval policy, state model, and orchestrator do not know or care which
business division they serve. Divisions are expressed as **data**, not as forked
code:

- An **agent spec** carries a `division` field (`shared`, `print_on_demand`,
  `us_dropshipping`, `digital_services`). Shared agents (e.g. Market Research,
  Compliance/IP Screening, Shopify Store Builder) are reused across divisions.
- A **workflow spec** also carries a `division` and composes agents into a
  division-specific pipeline with its own stages and gates.

This means a new division is added by writing new specs — not by rebuilding the
engine.

### How each division maps onto the platform

| Division | Specialized workflow(s) | Reuses (shared) |
| --- | --- | --- |
| Print-on-Demand | `pod_opportunity_discovery` (Phase 2, stops at human review) and `pod_research_review` (Phase 3 read-only research plus unpublished shirt/hat drafts). `pod_product_concept` remains the Phase 1 planning workflow. | Trend Discovery, Market Research, Product Validation, Unit Economics, Compliance/IP Screening, Opportunity Dossier, Research Connector, POD Product Draft |
| US Dropshipping | `us_dropshipping_opportunity_discovery` (Phase 2) and `us_dropship_research_review` (Phase 3 mock US-warehouse research plus an unpublished listing draft). `us_dropshipping_opportunity` remains the Phase 1 planning workflow. | The shared discovery agents, Supplier Research, Listing Draft |
| Digital Services / Fiverr | `fiverr_service_research_review` prepares a service workflow and an unsent draft. Complaints and refund requests escalate. | Service Research, Service Workflow, Service Communication Draft. Customer Service remains non-executable because sending a message is consequential. |

### Extension points

- **Add an agent:** drop a spec in `specs/agents/`. The registry validates and
  indexes it; workflows can reference it by id.
- **Add a workflow:** drop a spec in `specs/workflows/`. The loader validates the
  DAG (unique ids, resolvable dependencies, acyclic) and computes execution
  order.
- **Change permissions:** edit `config/approval_policy.yaml`. `PROHIBITED`
  categories cannot be relaxed at runtime.
- **Attach a runtime:** offline runtimes for the Phase 2 intelligence agents
  live in `src/grokbot/agents/runtime/`. Agents that would take an external
  action stay unbound. The control system (planning, gating, state, audit) is
  the layer those runtimes plug into.

## Data flow within a workflow

1. The orchestrator computes a topological order over the workflow stages.
2. For each `action` stage it resolves the responsible agent and the declared
   permission class. In an offline run it creates a job and executes the logical
   agent only after dependencies pass. `validation_gate` and `approval_gate`
   stages are control points. An approval gate stops the run.
3. A `ProjectState` object records stage status, evidence (with sources),
   decisions, approvals, and escalations as work proceeds.
4. Validation gates stop or redirect work (`halt`, `request_more_research`,
   `escalate`, `reject`). Approval gates require the human owner.

## Non-goals for this phase

No production Shopify, Fiverr, payment, advertising, or supplier credentials.
No purchases, publication, supplier contact, customer messages, Fiverr orders,
or refunds. Research connectors are read-only or mocked. Human approval is
recorded and does not execute a consequential action.
