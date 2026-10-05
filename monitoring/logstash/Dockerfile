# Add the supported DNS filter to the pinned Logstash image. Keeping this in
# the image makes the named pipeline volume contain configuration only.
FROM docker.elastic.co/logstash/logstash:9.5.4

RUN bin/logstash-plugin install logstash-filter-dns
