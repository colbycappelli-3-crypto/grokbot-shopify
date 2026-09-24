# GROKBOT COMMERCE — Phase 6 catalog connection, not enabled

Phase 6 prepares the first controlled Shopify catalog connection. The connection
stays off.

## Local secret configuration

Set these in the process environment, or in a gitignored `.env` file that this
program does not read:

- `SHOPIFY_ADMIN_TOKEN` — Shopify Admin API access token, scope `read_products` only
- `SHOPIFY_STORE_DOMAIN` — shop hostname

Do not paste either value into chat, source code, GitHub, or a committed file.
`.env.example` keeps `REPLACE_ME`. `.env` and `.envrc` are gitignored.
`SHOPIFY_API_KEY` and `SHOPIFY_API_SECRET` are not used.

`grokbot connector status` and `grokbot connector prepare` report each variable
as missing, placeholder, invalid, or present. They do not print the value.
The audit log redacts the value and recognizable admin-token prefixes.

## What stays disabled

- `EXTERNAL_CONNECTIONS_ENABLED` is false.
- `SHOPIFY_LIVE_REQUESTS_ENABLED` is false.
- No production sender is installed. Forcing both flags on in a test still does not call the store.
- An approved `connect_external_account` proposal still releases with `executed=false` and `phase_2_offline_no_consequential_actions`.
- The planned request remains `GET https://{SHOPIFY_STORE_DOMAIN}/admin/api/2024-10/products.json`.
- Create, edit, publish, purchase, supplier contact, messaging, orders, refunds, payments, fulfillment, and advertising are refused.

Stop here. Explicit human approval is required before either enable flag is turned on or any request is sent to the real store.

## Next phase

Do not start it from this change. After that approval, a later phase may add one production GET for `read_products` and turn the enable flags on. Writes stay blocked.
