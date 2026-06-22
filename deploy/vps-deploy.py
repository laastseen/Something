#!/usr/bin/env python3
"""Деплой на VPS: git clone + setup-server.sh"""
import os
import sys

try:
    import paramiko
except ImportError:
    print("pip install paramiko")
    sys.exit(1)

HOST = os.environ.get("SOMETHING_SSH_HOST", "185.40.4.246")
USER = os.environ.get("SOMETHING_SSH_USER", "root")
PASSWORD = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SOMETHING_SSH_PASSWORD", "")
REPO = os.environ.get("SOMETHING_GIT_REPO", "https://github.com/laastseen/Something.git")
APP_DIR = "/var/www/something"

if not PASSWORD:
    print("Задайте пароль: python deploy/vps-deploy.py ПАРОЛЬ")
    sys.exit(1)

REMOTE = f"""set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git python3 python3-venv python3-pip nginx rsync curl
if [ -d {APP_DIR}/.git ]; then
  cd {APP_DIR} && git pull
else
  rm -rf {APP_DIR}
  git clone {REPO} {APP_DIR}
fi
bash {APP_DIR}/deploy/setup-server.sh
"""

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
print(f"Подключение {USER}@{HOST}...")
client.connect(HOST, username=USER, password=PASSWORD, timeout=60)
stdin, stdout, stderr = client.exec_command(REMOTE, get_pty=True)
for line in stdout:
    print(line, end="")
err = stderr.read().decode()
if err.strip():
    print(err, file=sys.stderr)
code = stdout.channel.recv_exit_status()
client.close()
if code != 0:
    sys.exit(code)
print("\nГотово: http://vm4420189.firstbyte.club/")
