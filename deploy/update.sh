#!/bin/bash
# Обновление с git на уже настроенном сервере
set -euo pipefail
APP_DIR="/var/www/something"
cd "$APP_DIR"
sudo -u www-data git pull
sudo -u www-data ./venv/bin/pip install -r requirements.txt
systemctl restart something
echo "OK: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/)"
