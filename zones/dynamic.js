// Externally written A records at client survive provider reconciliation.
D("dyn.example.test", REG_NONE, DnsProvider(DNS_BIND), DefaultTTL(60),
    IGNORE("client", "A"), DENY_SENDING_MAILS(), END);
