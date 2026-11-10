# Labfilter Pi-hole

This Compose project runs Pi-hole on the separate Docker server with its own
reserved LAN address. It does not run on Labfilter and does not change the
Labfilter nftables policy. DNS blocking will remain deferred until lab systems
have been migrated to the Pi-hole address.

Pi-hole uses a macvlan network so clients can reach it directly on the LAN.
The Docker host normally cannot reach its own macvlan child; use another LAN
device for the Pi-hole web interface at `https://<PIHOLE_LAN_IP>/admin`.

## Prepare the Docker server

1. Reserve an unused LAN address for Pi-hole and identify the Docker host's
   physical LAN parent interface.
2. Copy the environment sample and fill in the LAN values:

   ```sh
   cp .env.example .env
   ${EDITOR:-vi} .env
   ```

3. Create the ignored web-password secret file:

   ```sh
   mkdir -p secrets
   umask 077
   ${EDITOR:-vi} secrets/pihole_web_password
   ```

   The file must contain only the Pi-hole web password. It is intentionally
   ignored and is not part of the repository.

4. Validate and start Pi-hole:

   ```sh
   docker compose -f compose.yaml config --quiet
   docker compose -f compose.yaml up -d
   docker compose -f compose.yaml ps
   ```

5. From another LAN device, open the Pi-hole web interface and configure the
   desired blocklists and local DNS records.

## Migration and deferred firewall policy

First update DHCP/router settings and individual systems to use the Pi-hole
address. Verify normal resolution and Pi-hole query visibility from each
network segment. Only after migration is complete should Labfilter add rules
that allow DNS to the Pi-hole address, allow Pi-hole upstream DNS, and block
other forwarded DNS traffic. No such nftables rule is included here.

Do not enable Pi-hole DHCP in this initial deployment. The current Compose
definition exposes DNS and web ports only; DHCP remains with the existing
router until a separate migration is designed and tested.
