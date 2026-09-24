#!/usr/bin/env bash
# One-time setup of a fresh Oracle Cloud Ubuntu 24.04 ARM (Ampere A1) server.
# Safe to re-run: every step checks before it changes anything.
#
# On the server:  sudo bash setup.sh yourapp.duckdns.org
# Then on your laptop, once /opt/fantasai/.env is filled in:  deploy/push.sh ubuntu@<server-ip>
set -euo pipefail

DOMAIN="${1:?usage: sudo bash setup.sh <your-subdomain.duckdns.org>}"
APP=/opt/fantasai
HERE="$(cd "$(dirname "$0")" && pwd)"
[ "$(id -u)" = 0 ] || { echo "Run with sudo."; exit 1; }
[ "$(uname -m)" = aarch64 ] || echo "Note: expected an ARM (aarch64) server, got $(uname -m). Continuing."

echo "==> System packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y git curl caddy iptables-persistent
# A fresh image is days or weeks behind; unattended-upgrades only catches up overnight.
apt-get -y -o Dpkg::Options::=--force-confold upgrade

echo "==> Hardening"
# rpcbind (NFS) ships enabled on Oracle's image and listens publicly on port 111. Both
# firewalls already block it; not running it at all is better.
systemctl disable --now rpcbind.socket rpcbind.service 2>/dev/null || true
# Key-only root login is already unusable (Oracle gives root no key); make it explicit.
echo "PermitRootLogin no" > /etc/ssh/sshd_config.d/99-fantasai.conf
sshd -t && systemctl reload ssh

echo "==> uv, which installs the exact Python the lock was built with (Ubuntu ships 3.12)"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh

echo "==> Service user and directories"
id fantasai >/dev/null 2>&1 || useradd --system --home-dir "$APP" --shell /usr/sbin/nologin fantasai
mkdir -p "$APP"
chown fantasai:fantasai "$APP"
# Everything below runs uv as the service user, and uv reads config from the current
# directory. Left in the invoking user's home (e.g. /home/ubuntu), which the service
# user cannot read, it fails with "uv.toml: Permission denied".
cd "$APP"

echo "==> Python 3.14 and the virtualenv"
sudo -u fantasai env UV_PYTHON_INSTALL_DIR="$APP/.python" UV_CACHE_DIR="$APP/.cache/uv" \
  uv python install 3.14
[ -x "$APP/venv/bin/python" ] || sudo -u fantasai env UV_PYTHON_INSTALL_DIR="$APP/.python" UV_CACHE_DIR="$APP/.cache/uv" \
  uv venv --python 3.14 "$APP/venv"

echo "==> Firewall inside the server"
# Oracle's Ubuntu image ships iptables rules that REJECT everything except SSH. Opening
# 80/443 in the cloud console's security list is not enough on its own; this is the
# other half, and the usual reason an Oracle server looks unreachable.
for port in 80 443; do
  iptables -C INPUT -p tcp --dport "$port" -m conntrack --ctstate NEW -j ACCEPT 2>/dev/null \
    || iptables -I INPUT 1 -p tcp --dport "$port" -m conntrack --ctstate NEW -j ACCEPT
done
netfilter-persistent save

echo "==> Caddy (HTTPS) for $DOMAIN"
sed "s/^DOMAIN {/$DOMAIN {/" "$HERE/Caddyfile" > /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl enable caddy
systemctl reload caddy || systemctl restart caddy

echo "==> Backend service"
cp "$HERE/fantasai.service" /etc/systemd/system/fantasai.service
systemctl daemon-reload
systemctl enable fantasai    # started by push.sh once code and .env are in place

echo "==> Environment file"
if [ ! -f "$APP/.env" ]; then
  cp "$HERE/env.example" "$APP/.env"
  CREATED_ENV=1
fi
chown fantasai:fantasai "$APP/.env"
chmod 600 "$APP/.env"

echo
echo "Server setup done."
[ "${CREATED_ENV:-0}" = 1 ] && echo "NEXT: sudo nano $APP/.env and fill in every REQUIRED line."
echo "Also in the Oracle console: open TCP 80 and 443 in the VCN security list (ingress, source 0.0.0.0/0)."
echo "Then from your laptop: deploy/push.sh ubuntu@<this-server-ip>"
