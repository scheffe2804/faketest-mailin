FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends postfix ca-certificates python3 openssl \
    && groupadd -g 1001 router \
    && useradd -u 1001 -g 1001 -d /srv/mailin -s /usr/sbin/nologin router \
    && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
