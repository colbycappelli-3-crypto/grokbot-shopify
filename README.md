# GROKBOT COMMERCE

GROKBOT COMMERCE is a modular, multi-agent control system for researching,
creating, launching, and operating online businesses — primarily through
Shopify. **GROKBOT** is the master orchestrator that coordinates specialized
agents across three business divisions:

1. **Print-on-Demand Commerce**
2. **US Dropshipping Commerce**
3. **Digital Services / Fiverr Operations**

> **Phase status: HUMAN REVIEW AND READ-ONLY RESEARCH (Phase 3).** Phase 1's
> specs, approval policy, and project state remain in place. Phase 2's offline
> runner, evidence rules, and discovery workflows remain in place. Phase 3 adds
> a human review queue, a read-only HTML review page, and mock read-only
> connectors for print-on-demand, US dropshipping, and Fiverr service research.
> It does **not** connect credentials, purchase, publish, contact suppliers,
> message Fiverr users, place orders, issue refunds, or modify Shopify
> production data. Do not start Phase 4 without human approval.

## Why this design

Agents can be **added, removed, improved, or replaced without rebuilding the
system** because they are declarative specifications validated by shared schemas.
Divisions are expressed as data (agent/workflow specs), not forked code, so they
share one platform while keeping specialized workflows.

## Repository layout

```
config/                     Owner-editable configuration (approval policy)
docs/                       Master operating document, architecture, approval, security, standards
src/grokbot/
  orchestrator/             Master orchestrator: planning plus offline execution
  agents/                   Agent registry and offline logical-agent runtimes
  workflows/                Workflow loader (DAG validation, execution order, gates)
  policy/                   Approval / permission system
  gates/                    Configurable validation-gate defaults
  protocol/                 Job / handoff records and epistemic status
  evidence/                 Evidence ledger (TEST/MOCK in this phase)
  audit/                    Structured audit log
  dossier/                  Opportunity dossier builder
  fixtures/                 TEST/MOCK opportunity packets and research packets
  connectors/               Read-only connector interfaces and TEST/MOCK payloads
  review/                   Human review queue and read-only HTML page
  state/                    Project/store state (auditable)
  schemas/                  Shared JSON schemas (contracts)
  specs/agents/             Agent specifications (data)
  specs/workflows/          Workflow specifications (data)
  specs/connectors/         Read-only connector specifications (data)
  cli.py                    `grokbot validate` / `plan` / `simulate` / `research` / `review`
tests/                      Schema, registry, workflow, policy, state, orchestrator, security tests
.env.example                Placeholders only — never commit real secrets
```

Start with [`docs/MASTER_OPERATING_DOCUMENT.md`](docs/MASTER_OPERATING_DOCUMENT.md).
Phase 2 execution is described in [`docs/PHASE2_ORCHESTRATION.md`](docs/PHASE2_ORCHESTRATION.md).
Phase 3 review and research is described in [`docs/PHASE3_REVIEW_RESEARCH.md`](docs/PHASE3_REVIEW_RESEARCH.md).

## Quickstart

Requires Python 3.10+.

```bash
# 1. Create an isolated environment and install (runtime + dev)
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Validate all specs, config, and cross-references (no external actions)
grokbot validate

# 3. Produce a dependency-ordered, gated plan for a workflow
grokbot plan us_dropshipping_opportunity --objective "Find a US-fulfilled winning product"
grokbot plan pod_opportunity_discovery  --objective "Evaluate a niche t-shirt concept"

# 4. Run an offline simulation against a TEST/MOCK fixture (no external actions)
grokbot simulate pod_opportunity_discovery --fixture promising_pod
grokbot simulate us_dropshipping_opportunity_discovery --fixture promising_dropship

# 5. Run read-only division research. Results are enqueued for human review.
grokbot research pod_research_review --packet pod_research_ready
grokbot research us_dropship_research_review --packet dropship_research_ready
grokbot research fiverr_service_research_review --packet fiverr_revision_ready
grokbot review list
grokbot review render --output /tmp/grokbot-review.html

# 6. Run the test suite
python -m pytest
```

> If `python -m venv` reports that `ensurepip` is unavailable, either install the
> matching `python3-venv` package or install the two dependencies into your user
> site with `pip install --user jsonschema pytest` and run tools with
> `PYTHONPATH=src` (e.g. `PYTHONPATH=src python -m grokbot validate`).

## Core concepts

| Concept | What it is | Schema |
| --- | --- | --- |
| Agent spec | A logical agent role with structured I/O and a default permission. | `agent_spec.schema.json` |
| Workflow spec | A DAG of stages with dependencies, validation gates, and approval gates. | `workflow_spec.schema.json` |
| Project state | Auditable per-project record: stages, evidence, decisions, approvals, escalations. | `project_state.schema.json` |
| Approval policy | Owner-editable mapping of action categories to AUTONOMOUS / APPROVAL_REQUIRED / PROHIBITED. | `approval_policy.schema.json` |
| Validation gates | Owner-editable default thresholds for offline screening. | `validation_gates.schema.json` |
| Opportunity fixture | TEST/MOCK packet used by offline simulations. | `opportunity_fixture.schema.json` |
| Research connector | Read-only or mock interface. Credentials and production connections are refused. | `research_connector.schema.json` |
| Research packet | TEST/MOCK connector queries for a division research workflow. | `research_packet.schema.json` |
| Review item | Human review queue record. A decision never executes an external action. | `review_item.schema.json` |

## Principles

- **No fabrication.** Unknown facts stay `UNKNOWN`; verified evidence requires a
  source.
- **Approval before consequence.** Material external actions require the human
  owner; prohibited actions are never allowed and cannot be relaxed at runtime.
- **Security first.** No secrets in Git; `.env` is ignored; no production
  connections in this phase.
- **Repository isolation.** This repo is exclusively for GROKBOT COMMERCE.

See [`docs/`](docs/) for full detail.
