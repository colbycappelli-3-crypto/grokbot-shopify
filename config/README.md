# Configuration

Owner-editable configuration for GROKBOT COMMERCE. These files are validated
against JSON schemas in `src/grokbot/schemas/`.

| File | Purpose | Schema |
| --- | --- | --- |
| `approval_policy.yaml` | Maps action categories to `AUTONOMOUS` / `APPROVAL_REQUIRED` / `PROHIBITED`. | `approval_policy.schema.json` |

Notes:

- The human owner may re-map categories, but `PROHIBITED` categories cannot be
  relaxed at runtime (`ApprovalPolicy.set_override` refuses to weaken them).
- `default_class` is the fail-safe applied to any category not listed. It is
  intentionally `APPROVAL_REQUIRED` so unknown actions are never auto-approved.
- Never put real secrets in configuration. Secrets belong in `.env` (git-ignored)
  or a secret manager. See `.env.example`.
