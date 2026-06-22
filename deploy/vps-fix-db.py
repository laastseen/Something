#!/usr/bin/env python3
import os
import sys
import paramiko

HOST = os.environ.get("SOMETHING_SSH_HOST", "185.40.4.246")
USER = os.environ.get("SOMETHING_SSH_USER", "root")
PASSWORD = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SOMETHING_SSH_PASSWORD", "")

REMOTE = r"""
cd /var/www/something
sudo -u www-data ./venv/bin/python <<'PY'
import database
database.initialize_database()
import seed_content
seed_content.run_seed()
seed_content.backfill_thumbnails()
print("db ok")
PY
systemctl restart something
sleep 2
curl -s -o /dev/null -w 'HTTP:%{http_code}\n' http://127.0.0.1:8001/
"""

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASSWORD, timeout=60)
_, stdout, stderr = c.exec_command(REMOTE, get_pty=True)
out = stdout.read().decode("utf-8", errors="replace")
err = stderr.read().decode("utf-8", errors="replace")
print(out)
if err.strip():
    print(err)
print("exit", stdout.channel.recv_exit_status())
c.close()
