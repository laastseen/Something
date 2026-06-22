#!/usr/bin/env python3
import os
import sys
import paramiko

HOST = os.environ.get("SOMETHING_SSH_HOST", "185.40.4.246")
USER = os.environ.get("SOMETHING_SSH_USER", "root")
PASSWORD = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SOMETHING_SSH_PASSWORD", "")

if not PASSWORD:
    print("python deploy/vps-update.py ПАРОЛЬ")
    sys.exit(1)

REMOTE = r"""
set -euo pipefail
git config --global --add safe.directory /var/www/something 2>/dev/null || true
cd /var/www/something
git pull origin main
./venv/bin/pip install -q -r requirements.txt
systemctl restart something
sleep 5
curl -s -o /dev/null -w 'HTTP:%{http_code}\n' http://127.0.0.1:8001/
"""

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASSWORD, timeout=60)
_, stdout, stderr = c.exec_command(REMOTE, get_pty=True, timeout=120)
out = stdout.read().decode("utf-8", errors="replace")
err = stderr.read().decode("utf-8", errors="replace")
print(out)
if err.strip():
    print(err)
code = stdout.channel.recv_exit_status()
c.close()
sys.exit(code)
