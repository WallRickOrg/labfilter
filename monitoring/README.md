# External ELK monitoring stack

This Compose project runs on the separate Docker server, not on Labfilter.
It receives only rate-limited `LABFILTER_BLOCKED` events forwarded by
Labfilter's Ansible-managed rsyslog rule.

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

4. Upload the Logstash pipeline into the named Docker volume. `docker cp`
   transfers the file from the client running this command, so the Docker
   daemon does not need access to the repository path:

   ```sh
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

Kibana is available on the configured Docker-server management address at port
5601. Elasticsearch is loopback-only. The three named Docker volumes preserve
Elasticsearch, Kibana, and Logstash data across container recreation.

Kibana is configured with a 1 GiB Node.js heap. Ensure the Docker server has
enough free memory for that heap plus Elasticsearch's 1 GiB JVM heap, Logstash,
and container overhead; otherwise reduce the Elasticsearch heap and host other
services elsewhere rather than lowering Kibana back to 512 MiB.

The stack currently has security disabled and should remain on a trusted home
management network until authentication and encrypted transport are added.
