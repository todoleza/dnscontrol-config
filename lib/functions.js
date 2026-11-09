// Generic function to generate NAMESERVER() records for main domain
function MAKE_NAMESERVERS(nslist) {
    var output = [];
    for (var i = 0; i < nslist.length; i++) {
        var ns = nslist[i];
        if (typeof ns === "string") {
            output.push(NAMESERVER(ns));
        } else if (typeof ns === "object" && ns.name) {
            output.push(NAMESERVER(ns.name));
            if (ns.ip) {
                output.push(A(ns.name.replace(/\.$/, ""), ns.ip));
            }
        }
    }
    return output.reverse();
}

function MAKE_NS_RECORDS(label, nslist, ttl) {
    var output = [];
    for (var i = 0; i < nslist.length; i++) {
        var ns = nslist[i];
        var ns_value = (typeof ns === "string") ? ns : (ns.name || "");
        if (ns_value) {
            if (ttl) {
                output.push(NS(label, ns_value, ttl));
            } else {
                output.push(NS(label, ns_value));
            }
        }
    }
    return output.reverse();
}

function NULLROUTE(name) {
    return [
        A(name, "0.0.0.0"),
        AAAA(name, "::")
    ];
}

// Scalar or multiple addresses for either family; every caller chooses a TTL.
function ADDRESS_RECORDS(name, addresses, ttl) {
    if (ttl === undefined || ttl === null) { throw "ADDRESS_RECORDS requires a TTL"; }
    var result = [];
    function append(factory, values) {
        if (values === undefined || values === null) { return; }
        if (!Array.isArray(values)) { values = [values]; }
        values.forEach(function(value) { result.push(factory(name, value, TTL(ttl))); });
    }
    append(A, addresses.ipv4);
    append(AAAA, addresses.ipv6);
    return result;
}

// Generic record template: the input owns record values; the caller owns defaults.
function GENERATED_RECORDS(records, defaultTtl) {
    var result = [];
    var factories = { A: A, AAAA: AAAA, CNAME: CNAME };
    records.forEach(function(record) {
        var factory = factories[record.type];
        if (!factory) { throw "Unsupported generated DNS type: " + record.type; }
        var ttl = record.ttl === undefined || record.ttl === null ? defaultTtl : record.ttl;
        if (ttl === undefined || ttl === null) { throw "Generated record requires a TTL: " + record.name; }
        var values = record.values || [record.value];
        values.forEach(function(value) { result.push(factory(record.name, value, TTL(ttl))); });
    });
    return result;
}
