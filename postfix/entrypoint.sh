#!/usr/bin/env bash
set -euo pipefail

config_dir="/config"
router_script="/opt/mail-router/mail_router.py"
ki_router_script="/opt/mail-router/ki_mail_router.py"
factcheck_router_script="/opt/mail-router/factcheck_router.py"

required_files=(virtual vmailbox transport relay_recipients recipient_access ki_sender_access factcheck_sender_access)
for file in "${required_files[@]}"; do
  if [[ ! -f "$config_dir/$file" ]]; then
    printf 'missing postfix config file: %s\n' "$config_dir/$file" >&2
    exit 1
  fi
done

cp "$config_dir/virtual" /etc/postfix/virtual
cp "$config_dir/vmailbox" /etc/postfix/vmailbox
cp "$config_dir/transport" /etc/postfix/transport
cp "$config_dir/relay_recipients" /etc/postfix/relay_recipients
cp "$config_dir/recipient_access" /etc/postfix/recipient_access
cp "$config_dir/ki_sender_access" /etc/postfix/ki_sender_access
cp "$config_dir/factcheck_sender_access" /etc/postfix/factcheck_sender_access

postmap /etc/postfix/virtual
postmap /etc/postfix/vmailbox
postmap /etc/postfix/transport
postmap /etc/postfix/relay_recipients
postmap /etc/postfix/recipient_access

cat > /etc/postfix/main.cf <<EOF
compatibility_level = 3.6
myhostname = ${MAIL_HOSTNAME}
myorigin = ${MAIL_DOMAIN}
mydestination =
alias_maps = hash:/etc/aliases
alias_database = hash:/etc/aliases
inet_interfaces = ${PUBLIC_IP}, 127.0.0.1, [${PUBLIC_IPV6}]
inet_protocols = all
mynetworks = 127.0.0.0/8 [::1]/128
maillog_file = /dev/stdout
smtpd_banner = \$myhostname ESMTP \$mail_name
smtpd_restriction_classes = ki_sender_check, factcheck_sender_check
ki_sender_check = check_sender_access regexp:/etc/postfix/ki_sender_access, reject
factcheck_sender_check = check_sender_access regexp:/etc/postfix/factcheck_sender_access, reject
smtpd_relay_restrictions = permit_mynetworks,reject_unauth_destination
smtpd_recipient_restrictions = reject_non_fqdn_recipient,reject_unknown_recipient_domain,check_recipient_access hash:/etc/postfix/recipient_access,permit_mynetworks,reject_unauth_destination
virtual_mailbox_domains = ${MAIL_DOMAINS:-${MAIL_DOMAIN}}
virtual_mailbox_maps = hash:/etc/postfix/vmailbox
virtual_alias_maps = hash:/etc/postfix/virtual
relay_domains = localrouter.invalid
relay_recipient_maps = hash:/etc/postfix/relay_recipients
transport_maps = hash:/etc/postfix/transport
virtual_transport = lmtp:inet:127.0.0.1:2525
local_transport = error:local delivery disabled
relayhost = ${RELAYHOST}
message_size_limit = ${MESSAGE_SIZE_LIMIT}
smtp_tls_security_level = may
smtpd_tls_security_level = may
smtpd_tls_cert_file = ${TLS_CERT_FILE}
smtpd_tls_key_file = ${TLS_KEY_FILE}
smtp_host_lookup = native,dns
unknown_local_recipient_reject_code = 550
EOF

if ! grep -q '^mailrouter ' /etc/postfix/master.cf; then
  cat >> /etc/postfix/master.cf <<EOF
mailrouter unix -       n       n       -       -       pipe
  flags=Rq user=router argv=${router_script} --recipient \${recipient}
EOF
fi

if ! grep -q '^kirouter ' /etc/postfix/master.cf; then
  cat >> /etc/postfix/master.cf <<EOF
kirouter unix -       n       n       -       -       pipe
  flags=Rq user=router argv=${ki_router_script} --recipient \${recipient} --original-recipient \${original_recipient} --sender \${sender}
EOF
fi

if ! grep -q '^factcheckrouter ' /etc/postfix/master.cf; then
  cat >> /etc/postfix/master.cf <<EOF
factcheckrouter unix -       n       n       -       -       pipe
  flags=Rq user=router argv=${factcheck_router_script} --recipient \${recipient} --original-recipient \${original_recipient} --sender \${sender}
EOF
fi

exec /usr/sbin/postfix start-fg
