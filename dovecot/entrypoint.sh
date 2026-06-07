#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f /config/users ]]; then
  printf 'missing dovecot user file: /config/users\n' >&2
  exit 1
fi

cp /config/users /etc/dovecot/users
chmod 644 /etc/dovecot/users

cat > /etc/dovecot/dovecot.conf <<EOF
protocols = imap lmtp
listen = *, ::
mail_home = /srv/vmail/%d/%n
mail_location = maildir:/srv/vmail/%d/%n/Maildir
first_valid_uid = 5000
last_valid_uid = 5000
ssl = required
ssl_cert = <${TLS_CERT_FILE}
ssl_key = <${TLS_KEY_FILE}
auth_mechanisms = plain login
passdb {
  driver = passwd-file
  args = scheme=SHA512-CRYPT username_format=%u /etc/dovecot/users
}
userdb {
  driver = static
  args = uid=5000 gid=5000 home=/srv/vmail/%d/%n
}
service imap-login {
  inet_listener imap {
    port = 0
  }
  inet_listener imaps {
    port = 993
    ssl = yes
  }
}
service lmtp {
  inet_listener lmtp {
    address = 127.0.0.1
    port = 2525
  }
}
protocol lmtp {
  postmaster_address = postmaster@${MAIL_HOSTNAME}
}
EOF

mkdir -p /srv/vmail
chown -R 5000:5000 /srv/vmail

exec /usr/sbin/dovecot -F
