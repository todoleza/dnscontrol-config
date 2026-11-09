// Fictional source addresses published for downstream MikroTik allowlisting.
// Replace the reviewed snapshot with the intended allowlist source addresses.
var ALLOWLIST_SOURCES = require("data/allowlist-sources.json");
D("monitor.example.test", REG_NONE, DnsProvider(DNS_BIND), DefaultTTL(300),
    ADDRESS_RECORDS("nodes", ALLOWLIST_SOURCES, 300), END);
