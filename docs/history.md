# Template history

Generalized tooling and fictional configuration from the operational branch. Removed historical inventories and exports from the current tree. Normal ancestry remains intact. Shared fixes are transferred as focused cherry-picks. Validation: 22 tests, current checks, baseline refresh and repeated export pass; no live provider calls or publication.

## Expanded fictional lab

Six zones now demonstrate shared endpoints, explicit mail policy, managed child
delegation, dynamic exclusions, allowlist source snapshots and HCloud services. Remote
providers remain commented in the offline default. The README documents setup,
all wrappers, native usage, refresh/review and adaptation recipes. No tokens or
live calls were used. Current checks, baseline audit and integration tests pass.

## Template nameserver anonymization and directory cleanup

Replaced the Bunny and Cloudflare nameserver identities with reserved .example
placeholders; retained the ClouDNS pns61–pns64 set. Removed empty historical
export/other directories locally; none are required and no .gitkeep is needed.
Nameserver fixture tests cover the anonymized sets.

## Provider-neutral MikroTik allowlist source

The example publishes a reviewed fictional address snapshot through DNS for
downstream MikroTik address-list sourcing and subsequent allowlisting.
Router configuration and list reconciliation remain consumer responsibilities.
