D("infrastructure.test", REG_NONE, DnsProvider(DNS_BIND), DefaultTTL(300),
    GENERATED_RECORDS(HCLOUD.records, 300),
    ADDRESS_RECORDS("resolver", ADDRESSES.web.dns, 600), END);
