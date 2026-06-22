#!/usr/bin/env python3
import paramiko, sys
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("185.40.4.246", username="root", password=sys.argv[1], timeout=30)
cmd = """
certbot certonly --nginx -d vm4420189.firstbyte.club \
  --non-interactive --agree-tos --register-unsafely-without-email \
  -v 2>&1 | tail -50
"""
_, o, _ = c.exec_command(cmd, timeout=180)
print(o.read().decode("utf-8", errors="replace"))
c.close()
