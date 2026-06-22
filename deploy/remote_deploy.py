#!/usr/bin/env python3
"""Заливка проекта на VPS и первичная настройка (без git на локальной машине)."""
from __future__ import annotations

import argparse
import os
import stat
import sys

try:
    import paramiko
except ImportError:
    print("Установите: pip install paramiko")
    sys.exit(1)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REMOTE_DIR = "/var/www/something"
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "srcdodep", ".vscode", ".idea"}
SKIP_FILES = {".env", "media_platform.db"}
SKIP_PREFIXES = ("uploads/",)


def should_skip(rel: str) -> bool:
    parts = rel.replace("\\", "/").split("/")
    if parts[0] in SKIP_DIRS:
        return True
    if rel.replace("\\", "/") in SKIP_FILES:
        return True
    if rel.replace("\\", "/").startswith(SKIP_PREFIXES) and not rel.endswith(".gitkeep"):
        return True
    return False


def collect_files() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            local = os.path.join(dirpath, name)
            rel = os.path.relpath(local, ROOT)
            if should_skip(rel):
                continue
            out.append((local, rel.replace("\\", "/")))
    return out


def run_ssh(client: paramiko.SSHClient, cmd: str) -> None:
    print(f"$ {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd)
    code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if out.strip():
        print(out.rstrip())
    if err.strip():
        print(err.rstrip(), file=sys.stderr)
    if code != 0:
        raise RuntimeError(f"Команда завершилась с кодом {code}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default=os.environ.get("SOMETHING_SSH_HOST", "185.40.4.246"))
    p.add_argument("--user", default=os.environ.get("SOMETHING_SSH_USER", "root"))
    p.add_argument("--password", default=os.environ.get("SOMETHING_SSH_PASSWORD", ""))
    p.add_argument("--repo", default=os.environ.get("SOMETHING_GIT_REPO", ""), help="URL git-репозитория (опционально)")
    args = p.parse_args()
    if not args.password:
        print("Задайте пароль: --password или переменная SOMETHING_SSH_PASSWORD")
        sys.exit(1)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Подключение к {args.user}@{args.host}...")
    client.connect(args.host, username=args.user, password=args.password, timeout=30)

    sftp = client.open_sftp()

    def mkdir_p(remote_path: str) -> None:
        parts = remote_path.strip("/").split("/")
        cur = ""
        for part in parts:
            cur += "/" + part
            try:
                sftp.stat(cur)
            except FileNotFoundError:
                sftp.mkdir(cur)

    mkdir_p(REMOTE_DIR)
    files = collect_files()
    print(f"Загрузка {len(files)} файлов...")
    for local, rel in files:
        remote = f"{REMOTE_DIR}/{rel}"
        mkdir_p(os.path.dirname(remote))
        sftp.put(local, remote)

    sftp.close()

    run_ssh(client, f"chmod +x {REMOTE_DIR}/deploy/setup-server.sh")
    repo_arg = f'"{args.repo}"' if args.repo else '""'
    run_ssh(client, f"bash {REMOTE_DIR}/deploy/setup-server.sh {repo_arg}")

    client.close()
    print("\nГотово: http://vm4420189.firstbyte.club/")


if __name__ == "__main__":
    main()
