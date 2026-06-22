#!/bin/bash
# HTTPS через Let's Encrypt (certbot)
set -euo pipefail

DOMAIN="${1:-vm4420189.firstbyte.club}"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq certbot python3-certbot-nginx

certbot --nginx \
  -d "$DOMAIN" \
  --non-interactive \
  --agree-tos \
  --register-unsafely-without-email \
  --redirect

systemctl reload nginx
echo "OK: https://$DOMAIN/"
