#!/bin/sh
# Create weekly rollover policies, templates, and aliases on the separate
# Docker server after Elasticsearch is healthy.
set -eu

es_url='http://127.0.0.1:9200'

# Both streams use one explicit ECS/network mapping, including geo_point
# locations required by Kibana Maps and reproducible rollover indices.
mapping='{"properties":{"source":{"properties":{"ip":{"type":"ip"},"port":{"type":"integer"},"mac":{"type":"keyword"},"geo":{"properties":{"city_name":{"type":"keyword"},"continent_code":{"type":"keyword"},"country_iso_code":{"type":"keyword"},"country_name":{"type":"keyword"},"region_name":{"type":"keyword"},"location":{"type":"geo_point"}}}}},"destination":{"properties":{"ip":{"type":"ip"},"port":{"type":"integer"},"mac":{"type":"keyword"},"geo":{"properties":{"city_name":{"type":"keyword"},"continent_code":{"type":"keyword"},"country_iso_code":{"type":"keyword"},"country_name":{"type":"keyword"},"region_name":{"type":"keyword"},"location":{"type":"geo_point"}}}}},"network":{"properties":{"bytes":{"type":"long"},"transport":{"type":"keyword"},"ingress":{"properties":{"interface":{"type":"keyword"}}},"egress":{"properties":{"interface":{"type":"keyword"}}}}},"nftables":{"properties":{"mac":{"type":"keyword"},"ether_type":{"type":"keyword"},"tos":{"type":"keyword"},"precedence":{"type":"keyword"},"ttl":{"type":"integer"},"id":{"type":"integer"},"window":{"type":"integer"},"reserved":{"type":"keyword"},"urgent_pointer":{"type":"integer"},"flags":{"type":"keyword"}}},"syslog":{"properties":{"priority":{"type":"integer"},"version":{"type":"integer"},"timestamp":{"type":"date"},"hostname":{"type":"keyword"},"appname":{"type":"keyword"},"procid":{"type":"keyword"},"msgid":{"type":"keyword"},"structured_data":{"type":"keyword"}}}}}'

put_policy() {
    policy="$1"
    curl -fsS -X PUT "$es_url/_ilm/policy/$policy" \
        -H 'Content-Type: application/json' \
        -d '{"policy":{"phases":{"hot":{"actions":{"rollover":{"max_age":"7d","max_primary_shard_size":"5gb"}}}}}}'
}

put_template() {
    alias="$1"
    curl -fsS -X PUT "$es_url/_index_template/$alias" \
        -H 'Content-Type: application/json' \
        -d "{\"index_patterns\":[\"$alias-*\"],\"template\":{\"settings\":{\"index.lifecycle.name\":\"$alias-weekly\",\"index.lifecycle.rollover_alias\":\"$alias\",\"number_of_shards\":1,\"number_of_replicas\":0},\"mappings\":$mapping}}"
}

ensure_alias() {
    alias="$1"
    if ! curl -fsS "$es_url/_alias/$alias" >/dev/null 2>&1; then
        curl -fsS -X PUT "$es_url/$alias-000001" \
            -H 'Content-Type: application/json' \
            -d "{\"aliases\":{\"$alias\":{\"is_write_index\":true}}}"
    fi
}

for alias in labfilter-blocked labfilter-traffic; do
    put_policy "$alias-weekly"
    put_template "$alias"
    ensure_alias "$alias"
done
