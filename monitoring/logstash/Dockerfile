# Add the supported DNS filter to the pinned Logstash image. Keeping this in
# the image makes the named pipeline volume contain configuration only.
FROM docker.elastic.co/logstash/logstash:9.5.4

RUN bin/logstash-plugin install logstash-filter-dns

# Pin the bundled GeoLite2 City database to a stable image path. The GeoIP
# filter's default database manager can be unavailable while the pipeline is
# starting; an explicit bundled path keeps enrichment deterministic.
RUN geoip_database=$(find /usr/share/logstash/vendor/bundle/jruby \
      -path '*/logstash-filter-geoip-*/vendor/GeoLite2-City.mmdb' \
      -print -quit) \
    && test -n "$geoip_database" \
    && cp "$geoip_database" /usr/share/logstash/config/GeoLite2-City.mmdb
