#!/usr/bin/env bash
# Runs on the EC2 host from GitHub Actions. Expects /opt/midigen/docker-compose.yml + .env
set -euo pipefail

cd /opt/midigen

if [[ -z "${GHCR_TOKEN:-}" || -z "${GHCR_USER:-}" ]]; then
  echo "GHCR_USER and GHCR_TOKEN must be set"
  exit 1
fi

echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin
docker compose --env-file .env pull
docker compose --env-file .env up -d --remove-orphans
docker compose --env-file .env ps
docker logout ghcr.io >/dev/null 2>&1 || true

ok=0
for _ in $(seq 1 40); do
  if curl -fsS http://127.0.0.1/health >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 3
done
if [[ "$ok" -ne 1 ]]; then
  echo "Public /health failed after wait"
  docker compose --env-file .env logs --tail 80
  exit 1
fi

curl -fsS http://127.0.0.1/health
echo
echo "Deploy OK  tag=${MIDI_IMAGE_TAG:-latest}"
echo "Studio    http://$(hostname -I | awk '{print $1}')/"
echo "API docs  http://$(hostname -I | awk '{print $1}')/docs"
