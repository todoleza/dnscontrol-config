// Shared values; each consumer still chooses families and TTLs.
var ADDRESSES = {
    web: HCLOUD.hosts.web,
    worker: HCLOUD.hosts.worker,
    office: {ipv4: "198.51.100.10", ipv6: "2001:db8:100::10"},
    resolvers: {ipv4: ["192.0.2.53", "192.0.2.54"]}
};
