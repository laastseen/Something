#!/usr/bin/env python3
import os
import sys
import paramiko

HOST = os.environ.get("SOMETHING_SSH_HOST", "185.40.4.246")
USER = os.environ.get("SOMETHING_SSH_USER", "root")
PASSWORD = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SOMETHING_SSH_PASSWORD", "")

if not PASSWORD:
    print("python deploy/vps-ssl.py ПАРОЛЬ")
    sys.exit(1)

REMOTE = r"""set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq certbot python3-certbot-nginx
certbot --nginx -d vm4420189.firstbyte.club --non-interactive --agree-tos --register-unsafely-without-email --redirect
systemctl reload nginx
curl -s -o /dev/null -w 'HTTPS:%{http_code}\n' https://vm4420189.firstbyte.club/
"""

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASSWORD, timeout=60)
_, stdout, stderr = c.exec_command(REMOTE, get_pty=True, timeout=300)
out = stdout.read().decode("utf-8", errors="replace")
err = stderr.read().decode("utf-8", errors="replace")
print(out)
if err.strip():
    print(err)
code = stdout.channel.recv_exit_status()
c.close()
sys.exit(code)
