# GROKBOT COMMERCE — Security

Security defaults for the foundation phase. These rules are mandatory.

## Secrets

- **Never** place API keys, passwords, access tokens, payment credentials,
  customer PII, or any other secret in source code, specs, config, logs, or
  commit messages.
- Use environment variables and/or a secret manager. Local development uses a
  `.env` file that is **git-ignored**.
- Only `.env.example` is committed, and it contains **placeholders only**
  (`REPLACE_ME` for secret-bearing keys). A test
  (`tests/test_security.py`) fails the build if a secret-looking key in
  `.env.example` ever holds a non-placeholder value.

## Git-ignore protection

`.gitignore` blocks common secret and credential artifacts before they can be
introduced, including:

- `.env` and `.env.*` (except `.env.example`)
- `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.secret`
- `secrets/`, `credentials/`, `service-account*.json`
- local databases and runtime state (`*.db`, `.grokbot_state/`)

`tests/test_security.py` also asserts that no real `.env` file is tracked.

## No production connections in this phase

Do **not** connect to a production Shopify store, Fiverr account, payment
provider, advertising account, supplier account, or any other external
production service. Phase 2 simulations are offline. Phase 3 connectors are
mock or unconfigured read-only interfaces: they do not read credentials, do
not place network calls, and refuse publish, purchase, order, message, refund,
and supplier-contact operations. Consequential categories (store launch,
purchase, supplier commitment, publication, advertising, customer messages,
Fiverr orders, Fiverr contact, Shopify production changes) stay blocked even
if a human approval is recorded. Phase 4 can record that approval and advance
the action only to a withheld-execution gate. Phase 5 can describe one GET of
the Shopify product catalog. The credential it needs is `SHOPIFY_ADMIN_TOKEN`
with scope `read_products`, plus `SHOPIFY_STORE_DOMAIN`. Those values stay out
of the repository. The connector does not read them into a request, including
when they are present in the process environment, until a human approves the
connection. Unclassified categories stay blocked by the policy default.
Prohibited categories still cannot be relaxed.

## Prohibited actions (never permitted)

Exposing credentials, bypassing platform safeguards, deceptive reviews or
engagement, impersonation, knowingly infringing IP, fabricating orders/customer
activity, unauthorized financial transactions, and circumventing platform rules
are classified `PROHIBITED` and cannot be enabled at runtime. See
[`APPROVAL_MODEL.md`](APPROVAL_MODEL.md).

## Repository isolation

This repository is exclusively for GROKBOT COMMERCE. Do not reference, import,
or interact with unrelated repositories or projects — in particular, do not
interact with any PoH Wallet project or repository.

## Reporting

If you discover a committed secret, treat it as compromised: rotate the
credential immediately and remove it from history. Do not simply delete it in a
new commit.
