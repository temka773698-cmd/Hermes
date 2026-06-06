#!/usr/bin/env bash
set -euo pipefail

# Family VPN setup script for Ubuntu 22.04/24.04
# Run as root on a fresh VPS.

if [[ $EUID -ne 0 ]]; then
  echo "Run this script as root."
  exit 1
fi

if ! command -v apt >/dev/null 2>&1; then
  echo "apt not found. This script expects Ubuntu/Debian."
  exit 1
fi

SERVER_PUBLIC_IP="${SERVER_PUBLIC_IP:-}"
WG_HOST="${WG_HOST:-}"
WG_PASSWORD="${WG_PASSWORD:-ChangeMeNow!}"
WG_PORT="${WG_PORT:-51820}"
WG_UI_PORT="${WG_UI_PORT:-51821}"

if [[ -z "$SERVER_PUBLIC_IP" ]]; then
  echo "Set SERVER_PUBLIC_IP to the server public IP before running."
  echo "Example: SERVER_PUBLIC_IP=1.2.3.4 bash install-wg-easy.sh"
  exit 1
fi

if [[ -z "$WG_HOST" ]]; then
  WG_HOST="$SERVER_PUBLIC_IP"
fi

export DEBIAN_FRONTEND=noninteractive
apt update
apt install -y ca-certificates curl gnupg ufw

# Install Docker if missing
if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt update
  apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

systemctl enable --now docker

mkdir -p /opt/wg-easy
cat >/opt/wg-easy/docker-compose.yml <<YAML
services:
  wg-easy:
    image: ghcr.io/wg-easy/wg-easy:latest
    container_name: wg-easy
    environment:
      - WG_HOST=${WG_HOST}
      - PASSWORD=${WG_PASSWORD}
      - WG_PORT=${WG_PORT}
      - PORT=${WG_UI_PORT}
    volumes:
      - /opt/wg-easy/data:/etc/wireguard
    ports:
      - "${WG_PORT}:${WG_PORT}/udp"
      - "${WG_UI_PORT}:${WG_UI_PORT}/tcp"
    cap_add:
      - NET_ADMIN
      - SYS_MODULE
    sysctls:
      - net.ipv4.conf.all.src_valid_mark=1
      - net.ipv4.ip_forward=1
    restart: unless-stopped
YAML

# Enable IP forwarding persistently
cat >/etc/sysctl.d/99-wireguard.conf <<CONF
net.ipv4.ip_forward=1
net.ipv6.conf.all.forwarding=1
CONF
sysctl --system >/dev/null

# Configure UFW
ufw allow OpenSSH
ufw allow ${WG_PORT}/udp
ufw allow ${WG_UI_PORT}/tcp
ufw --force enable

cd /opt/wg-easy
docker compose up -d

echo
 echo "wg-easy is up."
 echo "VPN UDP port: ${WG_PORT}"
 echo "Web UI port: ${WG_UI_PORT}"
 echo "Server public IP: ${WG_HOST}"
 echo "Open the UI at: http://${WG_HOST}:${WG_UI_PORT}"
 echo "Login password: ${WG_PASSWORD}"
 echo
 echo "Next steps:"
 echo "1) Open the web UI"
 echo "2) Create a peer for each person/device"
 echo "3) Scan the QR code on phones"
 echo "4) Import configs on PCs"
