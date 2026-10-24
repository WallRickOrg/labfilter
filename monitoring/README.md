# External ELK monitoring stack

This Compose project runs on the separate Docker server, not on Labfilter.
It receives `LABFILTER_BLOCKED` and `LABFILTER_TRAFFIC` events forwarded by
Labfilter's Ansible-managed rsyslog rule. Accepted traffic is indexed in
`labfilter-traffic`; blocked traffic remains in `labfilter-blocked`. TCP
traffic to or from port 5601 is excluded at the Labfilter logging chain so
Kibana does not recursively monitor itself.

New events are enriched with GeoLite2 City data into
`source.geo.location` and `destination.geo.location`. The reproducible Kibana
map and dashboard are in `kibana/`; deploy them with the named-container
`docker cp` workflow documented there.

## DNS enrichment

Events receive best-effort `source.hostname` and `destination.hostname`
fields from cached reverse-DNS lookups while the original IP fields remain
unchanged. Successful answers are cached for one hour and failed answers for
five minutes, using Google Public DNS as the configured upstream. PTR names
may be absent or may not equal the hostname originally requested by a client.

## Updating Logstash

Use the repository deployment script for pipeline or image changes. It validates
Compose configuration, rebuilds the DNS-enabled image, uploads the pipeline
through the named Docker volume, restarts only Logstash, and verifies the
container and DNS plugin:

```sh
./update-logstash.sh
```

## Start

1. Copy `.env.example` to `.env` on the Docker server and set its local bind
   addresses. Keep the Docker server firewall restricted so UDP/5514 accepts
   events only from Labfilter.
2. Start Elasticsearch and Kibana. Logstash is started after its pipeline is
   uploaded:

   ```sh
   docker compose up -d elasticsearch kibana
   ```

3. After Elasticsearch is healthy, initialize the weekly rollover alias:

   ```sh
   sh bootstrap-ilm.sh
   ```

   When changing the index template, force the current alias onto a new
   index after running the bootstrap:

   ```sh
   sh rollover-ilm.sh
   ```

4. Upload the Logstash pipeline into the named Docker volume. `docker cp`
   transfers the file from the client running this command, so the Docker
   daemon does not need access to the repository path:

   ```sh
docker compose build logstash
   docker compose build logstash
   docker compose stop logstash
   docker compose create logstash
   logstash_container="$(docker compose ps -q logstash)"
   docker cp ./logstash/pipeline/blocked.conf \
     "${logstash_container}:/usr/share/logstash/pipeline/blocked.conf"
   docker compose up -d logstash
   docker compose logs --tail=100 logstash
   ```

   Repeat the upload steps whenever `blocked.conf` changes. The
   `logstash-pipeline` named volume preserves the uploaded file when the
   container is recreated.

## Repair a legacy traffic index mapping

If Kibana Maps reports `Unsupported field type ... geo_point,geo_shape ...
conflict` for the source or destination location, check the mappings before
changing the dashboard. A concrete `labfilter-traffic` index created before
the GeoIP template can map `source.geo.location` and
`destination.geo.location` as generic objects, conflicting with the managed
`geo_point` mapping.

Stop Logstash, reindex the concrete traffic index into an index covered by the
current template, verify the document count and geo mappings, then delete only
the verified legacy index and recreate the `labfilter-traffic` write alias:

```sh
docker compose stop -t 30 logstash
docker compose exec -T elasticsearch curl -fsS -X POST \
  'http://localhost:9200/_reindex?wait_for_completion=true' \
  -H 'Content-Type: application/json' \
  -d '{"source":{"index":"labfilter-traffic"},"dest":{"index":"labfilter-traffic-000001"}}'
docker compose exec -T elasticsearch curl -fsS \
  'http://localhost:9200/labfilter-traffic-000001/_mapping/field/source.geo.location,destination.geo.location?pretty'
docker compose exec -T elasticsearch curl -fsS -X DELETE \
  'http://localhost:9200/labfilter-traffic'
docker compose exec -T elasticsearch curl -fsS -X POST \
  'http://localhost:9200/_aliases' -H 'Content-Type: application/json' \
  -d '{"actions":[{"add":{"index":"labfilter-traffic-000001","alias":"labfilter-traffic","is_write_index":true}}]}'
./update-logstash.sh
```

Do not delete the legacy index until the reindexed document count and both
location mappings have been verified. This migration preserves the traffic
documents and does not modify Labfilter filtering.

Kibana is available on the configured Docker-server management address at port
5601. Elasticsearch must also be reachable from Labfilter's independent
management path for the hourly destination aggregation. Restrict TCP/9200 at
the Docker-server firewall to Labfilter and trusted administrators. The three
named Docker volumes preserve Elasticsearch, Kibana, and Logstash data across
container recreation.

Kibana is configured with a 1 GiB Node.js heap. Ensure the Docker server has
enough free memory for that heap plus Elasticsearch's 1 GiB JVM heap, Logstash,
and container overhead; otherwise reduce the Elasticsearch heap and host other
services elsewhere rather than lowering Kibana back to 512 MiB.

The stack currently has security disabled and should remain on a trusted home
management network until authentication and encrypted transport are added.
