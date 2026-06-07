#!/usr/bin/env bash
set -euo pipefail

ensure_rule() {
  local port="$1"
  if ! nft list chain ip filter INPUT | grep -Fq "tcp dport ${port} ct state new accept"; then
    nft add rule ip filter INPUT tcp dport "${port}" ct state new accept
  fi
  if nft list chain ip6 filter INPUT >/dev/null 2>&1; then
    if ! nft list chain ip6 filter INPUT | grep -Fq "tcp dport ${port} ct state new accept"; then
      nft add rule ip6 filter INPUT tcp dport "${port}" ct state new accept
    fi
  fi
}

ensure_rule 25
ensure_rule 993
