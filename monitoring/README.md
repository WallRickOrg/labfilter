# External ELK monitoring stack

This Compose project runs on the separate Docker server, not on Labfilter.
It receives only rate-limited `LABFILTER_BLOCKED` events forwarded by
Labfilter's Ansible-managed rsyslog rule.

## Start

1. Copy `.env.example` to `.env` on the Docker server and set its local bind
   addresses. Keep the Docker server firewall restricted so UDP/5514 accepts
   events only from Labfilter.
2. Start the stack:

   ```sh
   docker compose up -d
   ```

3. After Elasticsearch is healthy, initialize the weekly rollover alias:

   ```sh
   sh bootstrap-ilm.sh
   ```

Kibana is available on the configured Docker-server management address at port
5601. Elasticsearch is loopback-only. The three named Docker volumes preserve
Elasticsearch, Kibana, and Logstash data across container recreation.

The stack currently has security disabled and should remain on a trusted home
management network until authentication and encrypted transport are added.
