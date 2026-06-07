FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends dovecot-core dovecot-imapd dovecot-lmtpd ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 5000 vmail \
    && useradd -u 5000 -g 5000 -d /srv/vmail -s /usr/sbin/nologin vmail

COPY entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
