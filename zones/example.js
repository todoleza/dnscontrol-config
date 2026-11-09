// Local BIND is the default. To use a live profile, enable its declaration
// in dnsconfig.js and add e.g. DnsProvider(DSP_CLOUDNS) here.
D("example.test", REG_NONE,
    DnsProvider(DNS_BIND), DefaultTTL(300),
    ADDRESS_RECORDS("www", ADDRESSES.web, 300),
    ADDRESS_RECORDS("office", ADDRESSES.office, 600),
    CAA("@", "issue", "letsencrypt.org"),
    TXT("@", "example-verification=REPLACE_ME"),
    PROTONMAIL_RECORDS("example-key"),
    TXT_SPF_BUILD({protonmail: true}),
    TXT("_dmarc", "v=DMARC1; p=reject; rua=mailto:reports@example.test"),
    NS("lab", "ns.lab.example.test."),
    A("ns.lab", "192.0.2.53"),
    NS("dyn", "ns1.example.net."),
    NS("monitor", "ns1.example.net."),
END);
