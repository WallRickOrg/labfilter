# Labfilter Kibana geolocation

`labfilter-ip-geolocation.ndjson` contains the reproducible Kibana data view,
Maps visualization, and dashboard. The map uses blue markers for source
locations and red markers for destination locations from the GeoIP-enriched
fields `source.geo.location` and `destination.geo.location`.

Because the Docker daemon is external, upload the saved objects through the
Docker API rather than relying on a daemon-host bind mount:

```sh
docker cp ./kibana/labfilter-ip-geolocation.ndjson monitoring-kibana-1:/tmp/labfilter-ip-geolocation.ndjson
docker exec monitoring-kibana-1 sh -c \
  'curl -fsS -X POST http://localhost:5601/api/saved_objects/_import?overwrite=true \
   -H "kbn-xsrf: true" -F file=@/tmp/labfilter-ip-geolocation.ndjson'
```

Open the dashboard at `/app/dashboards#/view/labfilter-ip-geolocation-dashboard`.
Only events indexed after GeoIP enrichment is deployed contain geolocation
coordinates; private or reserved addresses are retained without a location.
