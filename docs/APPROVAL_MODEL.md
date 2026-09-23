# GROKBOT COMMERCE — Approval Model

Every consequential action belongs to exactly one of three classes. The mapping
from action **category** to class lives in `config/approval_policy.yaml` and is
validated by `approval_policy.schema.json`.

## Classes

### AUTONOMOUS
Low-risk, reversible activities with no external side effects: research,
analysis, drafting, calculations, organizing information, generating concepts,
and preparing proposed changes.

### APPROVAL_REQUIRED
Material external actions that require explicit human owner approval **before**
execution: external publication, financial commitments, purchases, supplier
commitments, launching a store, changing production systems, meaningful customer
refunds, consequential customer communications, connecting external accounts.

### PROHIBITED
Actions that must never be performed by any agent under any circumstances:
exposing credentials, bypassing platform safeguards, deceptive reviews or
engagement, impersonating people, knowingly infringing intellectual property,
fabricating orders/customer activity, unauthorized financial transactions, or
circumventing platform rules.

## Rules and defaults

- Each category maps to one class (see `config/approval_policy.yaml`).
- `default_class` is the **fail-safe** for any category not listed. It is
  `APPROVAL_REQUIRED`, so unknown actions are never silently auto-approved.
- The human owner may re-map categories via the policy file or
  `ApprovalPolicy.set_override(...)`.
- **`PROHIBITED` categories can never be relaxed at runtime.**
  `set_override` raises if you attempt to weaken a prohibited category, and it
  raises entirely when `owner_can_override` is `false`.

## How it is enforced in code

`grokbot.policy.approval.ApprovalPolicy`:

```python
from grokbot.policy.approval import load_default_policy, ActionClass

policy = load_default_policy()
policy.classify("market_research").action_class      # ActionClass.AUTONOMOUS
policy.classify("launch_store").requires_approval     # True
policy.classify("expose_credentials").prohibited      # True
policy.classify("unlisted_action").action_class       # ActionClass.APPROVAL_REQUIRED (fail-safe)

policy.set_override("expose_credentials", ActionClass.AUTONOMOUS)  # raises PermissionError
```

## How it appears in workflows and plans

- Each `action` stage in a workflow declares a `permission` class.
- The orchestrator marks a planned task `requires_approval` when it is
  `APPROVAL_REQUIRED` or when it is an `approval_gate`, and flags `PROHIBITED`
  stages as warnings.
- `Plan.requires_owner_approval` is `True` for any workflow containing an
  approval-required action or an approval gate.

## Owner workflow

1. GROKBOT produces a plan and advances autonomous stages.
2. At an `approval_gate` (or before any `APPROVAL_REQUIRED` action), work pauses
   and an approval request is recorded in project state (`status: pending`).
3. The human owner approves or denies. Denied/undecided actions never execute.
4. All approvals are retained in the project's auditable record.
