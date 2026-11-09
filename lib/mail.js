// Reusable provider records. Zone-specific policy stays in the zone files.
var MX_TTL_VALUE = 3600;
var MX_TTL = TTL(MX_TTL_VALUE);

function MAIL_TTL(ttl) {
    return TTL(ttl === undefined || ttl === null ? MX_TTL_VALUE : ttl);
}

function PROTONMAIL_MX_RECORDS(ttl) {
    return [
        MX("@", 10, "mail.protonmail.ch.", MAIL_TTL(ttl)),
        MX("@", 20, "mailsec.protonmail.ch.", MAIL_TTL(ttl)),
    ];
}

function PROTONMAIL_DKIM(token, ttl) {
    return ["protonmail", "protonmail2", "protonmail3"].map(function(selector) {
        return CNAME(selector + "._domainkey",
            selector + ".domainkey." + token + ".domains.proton.ch.", MAIL_TTL(ttl));
    });
}

function SIMPLELOGIN_MX_RECORDS(label, ttl) {
    label = label || "@";
    return [
        MX(label, 10, "mx1.simplelogin.co.", MAIL_TTL(ttl)),
        MX(label, 20, "mx2.simplelogin.co.", MAIL_TTL(ttl)),
    ];
}

function SIMPLELOGIN_DKIM_RECORDS(label, ttl) {
    var suffix = label && label !== "@" ? "." + label : "";
    return ["dkim", "dkim02", "dkim03"].map(function(selector) {
        return CNAME(selector + "._domainkey" + suffix,
            selector + "._domainkey.simplelogin.co.", MAIL_TTL(ttl));
    });
}

function TXT_SPF_BUILD(options) {
    options = options || {};
    var parts = ["v=spf1"];
    if (options.protonmail) { parts.push("include:_spf.protonmail.ch"); }
    if (options.simplelogin) { parts.push("include:simplelogin.co"); }
    if (options.protonmail) { parts.push("mx"); }
    parts.push("~all");
    return SPF_BUILDER({
        label: options.label || "@",
        ttl: options.ttl === undefined || options.ttl === null ? MX_TTL_VALUE : options.ttl,
        parts: parts,
    });
}

function DENY_SENDING_MAILS(label, ttl) {
    label = label || "@";
    var suffix = label !== "@" ? "." + label : "";
    return [
        TXT(label, "v=spf1 -all", MAIL_TTL(ttl)),
        TXT("*._domainkey" + suffix, "v=DKIM1; p=", MAIL_TTL(ttl)),
        TXT("_dmarc" + suffix, "v=DMARC1; p=reject; sp=reject; adkim=s; aspf=s;", MAIL_TTL(ttl)),
    ];
}

function PROTONMAIL_RECORDS(token, ttl) {
    return [PROTONMAIL_MX_RECORDS(ttl), PROTONMAIL_DKIM(token, ttl)];
}

function SIMPLELOGIN_RECORDS(label, ttl) {
    return [SIMPLELOGIN_MX_RECORDS(label, ttl), SIMPLELOGIN_DKIM_RECORDS(label, ttl)];
}
