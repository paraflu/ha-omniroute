# OmniRoute Home Assistant Integration

HACS custom integration for OmniRoute health and provider-account quotas.

## Installation
1. Add `https://github.com/paraflu/ha-omniroute` to HACS custom repositories as **Integration**.
2. Download OmniRoute and restart Home Assistant.
3. Add OmniRoute under Settings → Devices & services; enter the base URL and API key.

The API key must be allowed to read `/api/usage/quota`; inference-only keys may receive HTTP 403. Enter secrets in Home Assistant, not in issues or logs. Options let you change URL/key and reload the entry.

## Sensors
- Health: HTTP availability of `/api/health`.
- Remaining quota percentage per connection/account from `/api/usage/quota`.
- Attributes: provider, account name, used/total quota, reset time, token status.

Accounts are identified by `connectionId`, so accounts sharing a provider stay distinct. New accounts are discovered during polling. Unknown quota is represented as unknown, not zero. Values are supplied by OmniRoute: a returned 100% with no known total is **not independently verified upstream credit**. Authentication failures require correcting the key; network/server/schema failures mark coordinator entities unavailable and allow HA retry.

## Development
Run `python -m pytest -q` with Home Assistant, pytest and pytest-asyncio installed. Tests cover sensor import, coordinator-based entities, account parsing, options/reload, entry setup/unload and error handling. Local tests do not replace a live HA installation test.
