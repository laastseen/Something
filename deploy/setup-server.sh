#!/bin/bash
set -euo pipefail

APP_DIR="/var/www/something"
REPO_URL="${1:-}"

echo "==> Установка пакетов"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip nginx git rsync curl

echo "==> Каталог приложения"
mkdir -p "$APP_DIR"
chown -R www-data:www-data /var/www

if [[ -n "$REPO_URL" ]]; then
  if [[ ! -d "$APP_DIR/.git" ]]; then
    git clone "$REPO_URL" "$APP_DIR"
  else
    cd "$APP_DIR" && sudo -u www-data git pull
  fi
fi

cd "$APP_DIR"

echo "==> Python venv"
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

echo "==> Права на uploads"
mkdir -p uploads/thumbs uploads/stock
chown -R www-data:www-data "$APP_DIR"
chmod +x "$APP_DIR/deploy/setup-server.sh" 2>/dev/null || true

echo "==> systemd"
cp deploy/something.service /etc/systemd/system/something.service
systemctl daemon-reload
systemctl enable something
systemctl restart something

echo "==> nginx"
cp deploy/nginx-something.conf /etc/nginx/sites-available/something
ln -sf /etc/nginx/sites-available/something /etc/nginx/sites-enabled/something
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo "==> Готово. Проверка:"
systemctl --no-pager status something | head -5
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:8001/ || true
