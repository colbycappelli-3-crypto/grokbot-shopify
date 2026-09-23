# GROKBOT COMMERCE

GROKBOT COMMERCE is a modular, multi-agent control system for researching,
creating, launching, and operating online businesses — primarily through
Shopify. **GROKBOT** is the master orchestrator that coordinates specialized
agents across three business divisions:

1. **Print-on-Demand Commerce**
2. **US Dropshipping Commerce**
3. **Digital Services / Fiverr Operations**

> **Phase status: FOUNDATION & CONTROL SYSTEM.** This repository currently
> contains the architecture, specifications, approval/permission system, project
> state model, and a planning-only orchestrator. It does **not** connect to
> Shopify or any external service, make purchases, deploy, or use real
> credentials. Do not proceed to the next phase without human approval.

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
  orchestrator/             Planning-only master orchestrator
  agents/                   Agent registry (loads + validates agent specs)
  workflows/                Workflow loader (DAG validation, execution order, gates)
  policy/                   Approval / permission system
  state/                    Project/store state (auditable)
  schemas/                  Shared JSON schemas (contracts)
  specs/agents/             Example agent specifications (data)
  specs/workflows/          Example workflow specifications (data)
  cli.py                    `grokbot validate` / `grokbot plan`
tests/                      Schema, registry, workflow, policy, state, orchestrator, security tests
.env.example                Placeholders only — never commit real secrets
```

Start with [`docs/MASTER_OPERATING_DOCUMENT.md`](docs/MASTER_OPERATING_DOCUMENT.md).

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
grokbot plan pod_product_concept        --objective "Launch a niche t-shirt brand"

# 4. Run the test suite
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

## Principles

- **No fabrication.** Unknown facts stay `UNKNOWN`; verified evidence requires a
  source.
- **Approval before consequence.** Material external actions require the human
  owner; prohibited actions are never allowed and cannot be relaxed at runtime.
- **Security first.** No secrets in Git; `.env` is ignored; no production
  connections in this phase.
- **Repository isolation.** This repo is exclusively for GROKBOT COMMERCE.

See [`docs/`](docs/) for full detail.
