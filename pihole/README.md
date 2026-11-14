# Labfilter Pi-hole

This Compose project runs Pi-hole on the separate Docker server with its own
reserved LAN address. It does not run on Labfilter and does not change the
Labfilter nftables policy. DNS blocking will remain deferred until lab systems
have been migrated to the Pi-hole address.

Pi-hole uses a macvlan network so clients can reach it directly on the LAN.
The Docker host normally cannot reach its own macvlan child; use another LAN
device for the Pi-hole web interface at `https://<PIHOLE_LAN_IP>/admin`.

## Prepare the Docker server

1. Reserve an unused LAN address for Pi-hole. This Compose project reuses the
   existing Docker macvlan network; it must not create a second network with
   the same LAN pool.
2. Copy the environment sample and fill in the LAN values and password:

   ```sh
   cp .env.example .env
   ${EDITOR:-vi} .env
   ```

   Set `PIHOLE_NETWORK_NAME` to the existing macvlan network on the Docker
   server and set `PIHOLE_WEBPASSWORD_BASE64` to the base64 encoding of the
   Pi-hole web password. The password itself is never committed.

3. Validate and start Pi-hole through the repository helper. It creates the
   ignored Docker secret file from the encoded `.env` value before invoking
   Compose:

   ```sh
   ./scripts/pihole-compose.sh config --quiet
   ./scripts/pihole-compose.sh up -d
   ./scripts/pihole-compose.sh ps
   ```

4. From another LAN device, open the Pi-hole web interface and configure the
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
