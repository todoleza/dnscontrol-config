// Offline export adapter validated with DNSControl v5.8.0. The ordinary dnsconfig.js keeps
// live provider behavior. This separate config never instantiates remote providers.
require("../dnsconfig.js");
// Credential profiles are distinct from canonical nameserver sets.
var nameserverProfileAliases = { desec_iot: "desec" };

// conf is DNSControl's DSL result. Restrict it before Go initializes providers.
// Re-evaluate the DSL to preserve native record construction. This design was
// adopted after v4.42.0 DS round-trip failures and is revalidated on v5.8.0.
conf.dns_providers = conf.dns_providers.filter(function(provider) {
    return provider.name === "bind";
});
conf.domains.forEach(function(zone) {
    Object.keys(zone.dnsProviders).forEach(function(provider) {
        var count = zone.dnsProviders[provider];
        if (provider === "bind" || count === 0) { return; }
        var setName = nameserverProfileAliases[provider] || provider;
        var names = PROVIDER_NAMESERVERS[setName];
        if (!names) { throw "Missing offline nameserver assignment for profile " + provider + " (set " + setName + ")"; }
        D_EXTEND(zone.name, MAKE_NAMESERVERS(count === -1 ? names : names.slice(0, count)));
    });
    zone.dnsProviders = { bind: -1 };
});
