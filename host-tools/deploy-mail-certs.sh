#!/usr/bin/env bash
set -euo pipefail

source_dir="/etc/letsencrypt/live/mail.m00h.eu"
target_dir="/srv/mailin/certs"
stack_dir="/home/chris/web/diverses/mailin-docker"

install -d -m 755 "$target_dir"
install -m 644 "$source_dir/fullchain.pem" "$target_dir/fullchain.pem"
install -m 600 "$source_dir/privkey.pem" "$target_dir/privkey.pem"

docker compose -f "$stack_dir/docker-compose.yml" restart mailin-postfix mailin-dovecot
