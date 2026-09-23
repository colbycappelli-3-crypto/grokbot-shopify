# GROKBOT COMMERCE — Master Operating Document

> This is the persistent, authoritative description of what GROKBOT COMMERCE is,
> how it is organized, and the rules every agent and workflow must follow. It is
> the first document any contributor (human or agent) should read.

## 1. Mission

Build a modular agent system capable of researching, creating, launching, and
operating multiple online businesses, primarily through Shopify. The system is
organized into three business divisions that share common infrastructure:

1. **Print-on-Demand Commerce** — Shopify stores selling products such as shirts
   and hats via print-on-demand fulfillment.
2. **US Dropshipping Commerce** — products with demonstrated demand, sourced from
   reliable suppliers (US-based inventory/fulfillment preferred), validated on
   unit economics and competition.
3. **Digital Services / Fiverr Operations** — workflows that perform digital
   services, manage work through defined processes, perform QA, prepare customer
   communications, handle revisions, and escalate complaints/refunds/disputes to
   the human owner.

## 2. Core architecture

**GROKBOT is the master orchestrator.** It coordinates specialized agents. Agents
remain declarative specifications. Phase 2 attaches offline logical runtimes for
the commerce-intelligence roles. Phase 3 adds read-only research runtimes and a
human review queue. Those runtimes are explicit functions over supplied inputs.
They are not self-modifying processes and they do not call external services.

Logical agent roles the system is designed to support (added incrementally):
Market Research, Trend Discovery, Product Validation, Supplier Research, Unit
Economics, Brand Strategy, Creative Director, Product Design, Copywriting,
Shopify Store Builder, Merchandising, SEO, Quality Assurance, Customer Service,
Analytics, and Compliance / IP Screening.

The architecture is deliberately modular so agents can be **added, removed,
improved, or replaced without rebuilding the system**:

- **Agents** are validated specs in `src/grokbot/specs/agents/` (schema:
  `agent_spec.schema.json`). The `AgentRegistry` loads and indexes them.
- **Workflows** are validated specs in `src/grokbot/specs/workflows/` (schema:
  `workflow_spec.schema.json`). They define stages, dependencies, validation
  gates, and approval gates as a directed acyclic graph.
- **Project/store state** is validated data (schema: `project_state.schema.json`)
  that records progress, evidence, decisions, approvals, and escalations.
- **The orchestrator** (`grokbot.orchestrator`) turns an objective + workflow
  into a dependency-ordered plan, and can run that plan offline. It creates
  jobs, passes structured outputs, evaluates gates, writes an audit log, and
  stops at human review. It performs no external actions.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for how the divisions share
infrastructure.

## 3. Operating model

GROKBOT is responsible for:

1. Receiving a business objective.
2. Breaking it into tasks (workflow stages).
3. Selecting the appropriate agents.
4. Determining task dependencies (the workflow DAG).
5. Routing structured outputs between agents.
6. Maintaining project/store state.
7. Detecting failed validation gates.
8. Requesting additional research when evidence is insufficient.
9. Stopping bad opportunities before resources are wasted.
10. Escalating defined decisions to the human owner.
11. Maintaining an auditable record of important decisions and agent outputs.

Agents communicate through **structured outputs** so that one agent's output can
be consumed by another. Each agent spec declares its `inputs`, `outputs`, and
which agents it `consumes_from`.

## 4. Quality principle (no fabrication)

Agents must **not** manufacture research results, supplier information, prices,
sales figures, product demand, customer information, legal conclusions, or
completed actions.

- Unknown information must remain explicitly **UNKNOWN** until verified. The
  project-state model enforces this: evidence defaults to `UNKNOWN` and can only
  be marked `verified` when at least one **source** is attached.
- Research findings must preserve sources/evidence where technically practical.
- Compliance/IP screening flags risk; it never asserts legal conclusions.

## 5. Approval model (summary)

Every consequential action belongs to exactly one class:

- **AUTONOMOUS** — low-risk, reversible: research, analysis, drafting,
  calculations, organizing information, generating concepts, preparing proposed
  changes.
- **APPROVAL_REQUIRED** — material external actions: publication, financial
  commitments, purchases, supplier commitments, launching a store, changing
  production systems, meaningful refunds, consequential customer communications.
- **PROHIBITED** — exposing credentials, bypassing safeguards, deceptive
  reviews/engagement, impersonation, IP infringement, fabricating
  orders/activity, unauthorized transactions, circumventing platform rules.

The mapping is owner-editable (`config/approval_policy.yaml`), except that
`PROHIBITED` categories cannot be relaxed at runtime. The fail-safe default for
any unlisted action is `APPROVAL_REQUIRED`. See
[`APPROVAL_MODEL.md`](APPROVAL_MODEL.md).

## 6. Security rules

- Never place API keys, passwords, tokens, payment credentials, or customer PII
  in source code or commit them to Git.
- Use environment variables / secret managers. `.env` is git-ignored; only
  `.env.example` (placeholders) is committed.
- Do **not** connect to production Shopify, Fiverr, payment providers, ad
  accounts, or supplier accounts in this phase.
- See [`SECURITY.md`](SECURITY.md).

## 7. Repository isolation

This repository is exclusively for GROKBOT COMMERCE. Do not search for, modify,
reference, import, or interact with unrelated repositories or projects. In
particular, do not interact with any PoH Wallet project or repository.

## 8. Phase discipline

Phase 1 (foundation and control system) is merged. Phase 2 is the **offline
orchestration and commerce-intelligence** layer: job handoffs, evidence,
validation gates, dossiers, and two discovery workflows that stop at human
review. Phase 3 is the **human review and commerce research** layer: a review
queue, a read-only review page, and mock read-only connectors for
print-on-demand drafts, US-dropshipping research, and Fiverr service drafts.

Do NOT connect production Shopify, Fiverr, supplier, or payment credentials.
Do NOT purchase, publish, advertise, contact suppliers, message Fiverr users,
place Fiverr orders, or issue refunds. Do NOT add real credentials. Do NOT
start Phase 4 without explicit human approval. A recorded approval still does
not execute a consequential action.

## 9. Standards for adding an agent or workflow

- Write a spec file that validates against the relevant schema.
- Keep outputs structured and sourced; leave unknowns UNKNOWN.
- Set the correct `default_permission` / stage `permission`.
- Run `grokbot validate` and `pytest` before committing. See
  [`AGENT_STANDARDS.md`](AGENT_STANDARDS.md).
