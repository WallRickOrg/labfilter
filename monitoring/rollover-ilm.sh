#!/bin/sh
# Force new write indices after updating either event index template.
set -eu

es_url='http://127.0.0.1:9200'
for alias in labfilter-blocked labfilter-traffic; do
  curl -fsS -X POST "$es_url/$alias/_rollover" \
    -H 'Content-Type: application/json' \
    -d '{}'
done
