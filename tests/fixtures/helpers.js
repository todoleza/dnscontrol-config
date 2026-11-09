var REG_NONE = NewRegistrar("none");
var DSP_BIND = NewDnsProvider("bind");
require("../../lib/functions.js");
require("../../lib/mail.js");
DEFAULTS(DnsProvider(DSP_BIND), DefaultTTL(300));
D("helpers.example", REG_NONE,
    ADDRESS_RECORDS("dual", {ipv4: "192.0.2.1", ipv6: "2001:db8::1"}, 600),
    ADDRESS_RECORDS("v4", {ipv4: "192.0.2.2"}, 60),
    ADDRESS_RECORDS("v6", {ipv6: "2001:db8::2"}, 120),
    ADDRESS_RECORDS("many", {ipv4: ["192.0.2.10", "192.0.2.11"], ipv6: ["2001:db8::10"]}, 180),
    ADDRESS_RECORDS("empty", {ipv4: [], ipv6: []}, 60),
    GENERATED_RECORDS([
        {type: "A", name: "generated", values: ["192.0.2.20", "192.0.2.21"]},
        {type: "AAAA", name: "generated-v6", value: "2001:db8::20", ttl: 90},
        {type: "CNAME", name: "generated-alias", value: "generated.helpers.example.", ttl: 60}
    ], 240),
    PROTONMAIL_RECORDS("fixture-token"),
    SIMPLELOGIN_RECORDS("custom", 120),
    TXT_SPF_BUILD({label: "custom", simplelogin: true, ttl: 120}),
    DENY_SENDING_MAILS("custom-disabled", 180),
    SIMPLELOGIN_RECORDS("sl"),
    TXT_SPF_BUILD({label: "sl", simplelogin: true}),
    TXT_SPF_BUILD({protonmail: true}),
    DENY_SENDING_MAILS("disabled"),
    DS("delegated", 1234, 13, 2, "0000000000000000000000000000000000000000000000000000000000000000", TTL(3600)),
END);
D("second.example", REG_NONE,
    SIMPLELOGIN_RECORDS(),
    TXT_SPF_BUILD({simplelogin: true}),
    DENY_SENDING_MAILS("@"),
END);
if (typeof records !== "undefined" || typeof label !== "undefined" ||
    typeof parts !== "undefined" || typeof subdomain !== "undefined" || typeof ttl !== "undefined") {
    throw "A record helper leaked temporary variables into the global scope";
}

if (PROTONMAIL_MX_RECORDS() === PROTONMAIL_MX_RECORDS() ||
    PROTONMAIL_MX_RECORDS()[0] === PROTONMAIL_MX_RECORDS()[0]) {
    throw "Proton MX factories must return fresh templates";
}
function EXPECT_FAILURE(callback) {
    var failed = false;
    try { callback(); } catch (error) { failed = true; }
    if (!failed) { throw "Expected invalid template input to fail"; }
}
EXPECT_FAILURE(function() { ADDRESS_RECORDS("missing-ttl", {ipv4: "192.0.2.1"}); });
EXPECT_FAILURE(function() { GENERATED_RECORDS([{type: "A", name: "missing-ttl", value: "192.0.2.1"}]); });
EXPECT_FAILURE(function() { GENERATED_RECORDS([{type: "MX", name: "unsupported", value: "mail.example."}], 300); });
