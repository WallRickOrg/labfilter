#!/bin/sh
# Create the blocked-event rollover policy and initial write alias on the
# separate Docker server after Elasticsearch is healthy.
set -eu

es_url='http://127.0.0.1:9200'
policy='labfilter-blocked-weekly'
alias='labfilter-blocked'

curl -fsS -X PUT "$es_url/_ilm/policy/$policy" \
  -H 'Content-Type: application/json' \
  -d '{"policy":{"phases":{"hot":{"actions":{"rollover":{"max_age":"7d","max_primary_shard_size":"5gb"}}}}}}'

curl -fsS -X PUT "$es_url/_index_template/labfilter-blocked" \
  -H 'Content-Type: application/json' \
  -d '{"index_patterns":["labfilter-blocked-*"],"template":{"settings":{"index.lifecycle.name":"labfilter-blocked-weekly","index.lifecycle.rollover_alias":"labfilter-blocked","number_of_shards":1,"number_of_replicas":0}}}'

if ! curl -fsS "$es_url/_alias/$alias" >/dev/null 2>&1; then
  curl -fsS -X PUT "$es_url/$alias-000001" \
    -H 'Content-Type: application/json' \
    -d '{"aliases":{"labfilter-blocked":{"is_write_index":true}}}'
fi
