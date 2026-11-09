// Run DNSControl directly from this directory; Make is optional.
var REG_NONE = NewRegistrar("none");
var DNS_BIND = NewDnsProvider("bind");
// var DSP_CLOUDFLARE = NewDnsProvider("cloudflare");
// var DSP_DESEC = NewDnsProvider("desec");
// var DSP_CLOUDNS = NewDnsProvider("cloudns");
// var DSP_HETZNER = NewDnsProvider("hetzner");

DEFAULTS(
    DnsProvider(DNS_BIND),
    CF_PROXY_DEFAULT_OFF,
    { cloudflare_universalssl: "off" },
    IGNORE("@", "DNSKEY"),
END);

// Load shared values first, then independent helpers, zones, and extensions.
var HCLOUD = require("./data/hcloud-dns.json");
require("./data/addresses.js");
var PROVIDER_NAMESERVERS = require("./data/provider-nameservers.json");
require_glob("./lib/", false);
require_glob("./zones/", false);
require_glob("./services/", false);
