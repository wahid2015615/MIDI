#!/usr/bin/env bash
# One-time AWS EC2 bootstrap (Ubuntu 22.04/24.04). Run as root or with sudo:
#   curl -fsSL ... | sudo bash
#   or: sudo bash setup-ec2.sh
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Re-run as root: sudo bash $0"
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends ca-certificates curl gnupg

if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  # shellcheck disable=SC1091
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin docker-buildx-plugin
fi

systemctl enable --now docker

SSH_USER="${SUDO_USER:-ubuntu}"
if id "$SSH_USER" >/dev/null 2>&1; then
  usermod -aG docker "$SSH_USER"
fi

mkdir -p /opt/midigen/models
chown -R "${SSH_USER}:${SSH_USER}" /opt/midigen
chmod 755 /opt/midigen /opt/midigen/models

echo
echo "EC2 Docker is ready."
echo "  App dir : /opt/midigen"
echo "  Model   : copy Qwen3-4B-Q4_K_M.gguf to /opt/midigen/models/ (optional, text mode)"
echo "  Open SG : TCP 22 (your IP), 80 (public) — do not expose 3001/8000"
echo "  Size    : t3.large (8 GB) minimum; 30 GB disk if you use the GGUF"
echo "  URLs    : http://<public-ip>/  and  http://<public-ip>/docs"
