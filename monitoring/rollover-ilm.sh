#!/bin/sh
# Force a new write index after updating the blocked-event index template.
set -eu

es_url='http://127.0.0.1:9200'
alias='labfilter-blocked'

curl -fsS -X POST "$es_url/$alias/_rollover" \
  -H 'Content-Type: application/json' \
  -d '{}'
