"""Non-destructive browser checks: no DB, no Docker, real unavailable-module API."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
FRONT = ROOT / 'frontend'


def main():
    for port in (8001, 5174):
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                raise RuntimeError(f'Port {port} occupied; refusing server reuse')
    node = shutil.which('node')
    artifacts = ROOT / '.artifacts'
    artifacts.mkdir(exist_ok=True)
    env = {**os.environ, 'PERSISTENCE': 'disabled', 'DATABASE_URL': 'postgresql+psycopg://unused:unused@127.0.0.1:1/no_db',
           'CORS_ALLOW_ORIGINS': 'http://127.0.0.1:5174', 'VITE_API_URL': 'http://127.0.0.1:8001', 'PLAYWRIGHT_TRANSFORM_CACHE_DIR': str(artifacts / 'pw-cache'),}
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    processes = []
    with (artifacts / 'ui-servers.log').open('w', encoding='utf-8') as log:
        try:
            for command, cwd, url in [
                ([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8001'], ROOT / 'backend', 'http://127.0.0.1:8001/integrations/modules'),
                ([node, str(FRONT / 'node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '5174', '--strictPort'], FRONT, 'http://127.0.0.1:5174'),
            ]:
                process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
                processes.append(process)
                deadline = time.monotonic() + 30
                while True:
                    if process.poll() is not None: raise RuntimeError('Server exited; inspect .artifacts/ui-servers.log')
                    try:
                        urllib.request.urlopen(url, timeout=1).close()
                        break
                    except OSError:
                        if time.monotonic() > deadline: raise RuntimeError('Server readiness timeout')
                        time.sleep(.1)
            subprocess.run([node, str(FRONT / 'node_modules/@playwright/test/cli.js'), 'test', 'shell.spec.ts'],
                           cwd=FRONT, env=env, check=True)
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)


if __name__ == '__main__': main()
