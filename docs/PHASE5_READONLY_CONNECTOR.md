# GROKBOT COMMERCE — Phase 5 read-only catalog connector

Phase 5 adds `shopify_catalog_read`. It is the first connector that describes a
live Shopify read. The connection itself is not open.

## What the connector does

- `search` and `describe` name a planned request: `GET https://{SHOPIFY_STORE_DOMAIN}/admin/api/2024-10/products.json`.
- The credential required before that GET can be connected is:
  - `SHOPIFY_ADMIN_TOKEN` — Shopify Admin API access token, scope `read_products` only
  - `SHOPIFY_STORE_DOMAIN` — shop hostname
- Until a human approves connecting those values, the result is `UNKNOWN`, `network_calls` is 0, `credentials_used` is false, and `production_connected` is false.
- If those variables are already present in the process environment, the connector still sends nothing and returns `connection_not_approved`. It does not copy the values into the result or the audit log.
- A loopback probe on `127.0.0.1` can GET a TEST/MOCK document when the token starts with `TEST_MOCK_`. Any other host, including a `myshopify.com` host, and any method other than GET, is refused before `urlopen`.
- `grokbot connector status` lists the connector. `grokbot connector demo` runs the disconnected query, the loopback GET, and a blocked `launch_store` attempt.
- The query is recorded as audit event `connector_queried`.

## What stays blocked

- Publish, purchase, order, message, refund, supplier contact, listing creation, and Shopify modification are refused by the connector.
- Approval gates are unchanged. `launch_store` still returns `executed=false` and `phase_2_offline_no_consequential_actions`.
- Unclassified and prohibited actions do not advance.
- Mock research workflows still use their TEST/MOCK packets. The live connector is not wired into those packets.
- `EXTERNAL_CONNECTIONS_ENABLED` stays false.
- `SHOPIFY_API_KEY` and `SHOPIFY_API_SECRET` are not used.

Do not put the token or shop domain in the repository. `.env.example` keeps `REPLACE_ME`.

Phase 6 prepares the local credential and still does not enable the connection.
See [`PHASE6_CATALOG_CONNECTION.md`](PHASE6_CATALOG_CONNECTION.md).
