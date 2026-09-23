# Configuration

Owner-editable configuration for GROKBOT COMMERCE. These files are validated
against JSON schemas in `src/grokbot/schemas/`.

| File | Purpose | Schema |
| --- | --- | --- |
| `approval_policy.yaml` | Maps action categories to `AUTONOMOUS` / `APPROVAL_REQUIRED` / `PROHIBITED`. | `approval_policy.schema.json` |
| `validation_gates.yaml` | Configurable default thresholds for offline validation gates. | `validation_gates.schema.json` |

Notes:

- The human owner may re-map categories, but `PROHIBITED` categories cannot be
  relaxed at runtime (`ApprovalPolicy.set_override` refuses to weaken them).
- `default_class` is the fail-safe applied to any category not listed. It is
  intentionally `APPROVAL_REQUIRED` so unknown actions are never auto-approved.
- Gate thresholds in `validation_gates.yaml` are owner-editable defaults.
  They are not hard-coded in agent logic. A failed gate records a
  machine-readable reason code.
- Phase 3 adds autonomous categories for read-only research and review-queue
  updates, and approval-required categories for Fiverr orders, Fiverr contact,
  Shopify production changes, and supplier contact. Those approval-required
  categories are still blocked from execution in this phase. Existing
  PROHIBITED rules are unchanged.
- Never put real secrets in configuration. Secrets belong in `.env` (git-ignored)
  or a secret manager. See `.env.example`.
