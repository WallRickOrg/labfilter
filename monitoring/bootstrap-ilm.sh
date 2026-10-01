#!/bin/sh
# Create the blocked-event rollover policy and initial write alias on the
# separate Docker server after Elasticsearch is healthy.
set -eu

es_url='http://127.0.0.1:9200'
policy='labfilter-blocked-weekly'
alias='labfilter-blocked'

# Keep high-volume accepted traffic on its own weekly lifecycle.
traffic_policy='labfilter-traffic-weekly'
traffic_alias='labfilter-traffic'

curl -fsS -X PUT "$es_url/_ilm/policy/$policy" \
  -H 'Content-Type: application/json' \
  -d '{"policy":{"phases":{"hot":{"actions":{"rollover":{"max_age":"7d","max_primary_shard_size":"5gb"}}}}}}'

curl -fsS -X PUT "$es_url/_index_template/labfilter-blocked" \
-H 'Content-Type: application/json' \
-d '{"index_patterns":["labfilter-blocked-*"],"template":{"settings":{"index.lifecycle.name":"labfilter-blocked-weekly","index.lifecycle.rollover_alias":"labfilter-blocked","number_of_shards":1,"number_of_replicas":0},"mappings":{"properties":{"source":{"properties":{"ip":{"type":"ip"},"port":{"type":"integer"},"mac":{"type":"keyword"}}},"destination":{"properties":{"ip":{"type":"ip"},"port":{"type":"integer"},"mac":{"type":"keyword"}}},"network":{"properties":{"bytes":{"type":"long"},"transport":{"type":"keyword"},"ingress":{"properties":{"interface":{"type":"keyword"}}},"egress":{"properties":{"interface":{"type":"keyword"}}}}},"nftables":{"properties":{"mac":{"type":"keyword"},"ether_type":{"type":"keyword"},"tos":{"type":"keyword"},"precedence":{"type":"keyword"},"ttl":{"type":"integer"},"id":{"type":"integer"},"window":{"type":"integer"},"reserved":{"type":"keyword"},"urgent_pointer":{"type":"integer"},"flags":{"type":"keyword"}}},"syslog":{"properties":{"priority":{"type":"integer"},"version":{"type":"integer"},"timestamp":{"type":"date"},"hostname":{"type":"keyword"},"appname":{"type":"keyword"},"procid":{"type":"keyword"},"msgid":{"type":"keyword"},"structured_data":{"type":"keyword"}}}}}}}'

if ! curl -fsS "$es_url/_alias/$alias" >/dev/null 2>&1; then
  curl -fsS -X PUT "$es_url/$alias-000001" \
    -H 'Content-Type: application/json' \
    -d '{"aliases":{"labfilter-blocked":{"is_write_index":true}}}'
fi

curl -fsS -X PUT "$es_url/_ilm/policy/$traffic_policy" \
 -H 'Content-Type: application/json' \
 -d '{"policy":{"phases":{"hot":{"actions":{"rollover":{"max_age":"7d","max_primary_shard_size":"5gb"}}}}}}'

curl -fsS -X PUT "$es_url/_index_template/labfilter-traffic" \
 -H 'Content-Type: application/json' \
 -d '{"index_patterns":["labfilter-traffic-*"],"template":{"settings":{"index.lifecycle.name":"labfilter-traffic-weekly","index.lifecycle.rollover_alias":"labfilter-traffic","number_of_shards":1,"number_of_replicas":0},"mappings":{"properties":{"source":{"properties":{"ip":{"type":"ip"},"port":{"type":"integer"},"mac":{"type":"keyword"}}},"destination":{"properties":{"ip":{"type":"ip"},"port":{"type":"integer"},"mac":{"type":"keyword"}}},"network":{"properties":{"bytes":{"type":"long"},"transport":{"type":"keyword"},"ingress":{"properties":{"interface":{"type":"keyword"}}},"egress":{"properties":{"interface":{"type":"keyword"}}}}},"nftables":{"properties":{"mac":{"type":"keyword"},"ether_type":{"type":"keyword"},"tos":{"type":"keyword"},"precedence":{"type":"keyword"},"ttl":{"type":"integer"},"id":{"type":"integer"},"window":{"type":"integer"},"reserved":{"type":"keyword"},"urgent_pointer":{"type":"integer"},"flags":{"type":"keyword"}}},"syslog":{"properties":{"priority":{"type":"integer"},"version":{"type":"integer"},"timestamp":{"type":"date"},"hostname":{"type":"keyword"},"appname":{"type":"keyword"},"procid":{"type":"keyword"},"msgid":{"type":"keyword"},"structured_data":{"type":"keyword"}}}}}}}'

if ! curl -fsS "$es_url/_alias/$traffic_alias" >/dev/null 2>&1; then
 curl -fsS -X PUT "$es_url/$traffic_alias-000001" \
  -H 'Content-Type: application/json' \
  -d '{"aliases":{"labfilter-traffic":{"is_write_index":true}}}'
fi
