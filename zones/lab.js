D("lab.example.test", REG_NONE,
    DnsProvider(DNS_BIND), DefaultTTL(300),
    NAMESERVER("ns.lab.example.test."), A("ns", "192.0.2.53"),
    ADDRESS_RECORDS("resolvers", ADDRESSES.resolvers, 120),
    SIMPLELOGIN_RECORDS("mail"),
    TXT_SPF_BUILD({simplelogin: true, label: "mail"}),
END);
