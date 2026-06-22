#!/usr/bin/env python3
import paramiko, sys
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("185.40.4.246", username="root", password=sys.argv[1], timeout=30)
cmds = [
    "getent hosts vm4420189.firstbyte.club || host vm4420189.firstbyte.club",
    "curl -s -o /dev/null -w 'http:%{http_code}\n' http://vm4420189.firstbyte.club/",
    "ss -tlnp | grep ':80'",
    "test -f /var/log/letsencrypt/letsencrypt.log && tail -25 /var/log/letsencrypt/letsencrypt.log || echo no-log",
]
for cmd in cmds:
    _, o, e = c.exec_command(cmd)
    print(">", cmd)
    print(o.read().decode("utf-8", errors="replace"))
    err = e.read().decode("utf-8", errors="replace")
    if err.strip():
        print(err)
c.close()
