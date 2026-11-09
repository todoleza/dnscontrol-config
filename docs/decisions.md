# Template decisions

Make is optional. DNSControl owns forward DNS. Refreshes are explicit, validated and atomic. Shared endpoint values do not dictate zone publication. Current checks and optional baseline audits are separate.

## Expanded fictional lab

Six zones now demonstrate shared endpoints, explicit mail policy, managed child
delegation, dynamic exclusions, allowlist source snapshots and HCloud services. Remote
providers remain commented in the offline default. The README documents setup,
all wrappers, native usage, refresh/review and adaptation recipes. No tokens or
live calls were used. Current checks, baseline audit and integration tests pass.
