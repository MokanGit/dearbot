#!/usr/bin/env bash
set -u

# Read-only Docker-host inventory for DearBot deployment planning.
# Intentionally excludes container environments, file contents, and secrets.

printf 'host=%s\n' "$(hostname 2>/dev/null || printf unknown)"
printf 'kernel=%s\n' "$(uname -srm 2>/dev/null || printf unknown)"

if ! command -v docker >/dev/null 2>&1; then
  printf 'docker=missing\n'
  exit 1
fi

printf 'docker_client=%s\n' "$(docker version --format '{{.Client.Version}}' 2>/dev/null || printf unavailable)"
printf 'docker_server=%s\n' "$(docker version --format '{{.Server.Version}}' 2>/dev/null || printf unavailable)"
printf 'compose=%s\n' "$(docker compose version --short 2>/dev/null || printf unavailable)"

printf '\n[containers]\n'
docker ps --format 'name={{.Names}} image={{.Image}} status={{.Status}} ports={{.Ports}}' 2>/dev/null || true

printf '\n[networks]\n'
docker network ls --format 'name={{.Name}} driver={{.Driver}} scope={{.Scope}}' 2>/dev/null || true

printf '\n[expected_paths]\n'
for path in /opt/apps/cv /opt/apps/dearbot; do
  if [[ -d "$path" ]]; then
    printf '%s=present\n' "$path"
  else
    printf '%s=absent\n' "$path"
  fi
done

printf '\n[listening_http_ports]\n'
if command -v ss >/dev/null 2>&1; then
  ss -ltn 2>/dev/null | awk 'NR == 1 || $4 ~ /:80$|:443$|:3000$|:8000$/'
else
  printf 'ss=unavailable\n'
fi

printf '\n[disk]\n'
df -h / 2>/dev/null | tail -n 1 || true
