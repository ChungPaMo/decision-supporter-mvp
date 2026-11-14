"""Offline candidate-file scan. Heuristics plus known local-secret comparison, not a guarantee."""
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def main():
    result = subprocess.check_output(['git', '-c', f'safe.directory={ROOT.as_posix()}',
                                      'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT)
    paths = set(filter(None, result.decode('utf-8').split('\0')))
    secrets = []
    for env in [ROOT / '.env', ROOT / 'frontend/.env.local']:
        if not env.exists(): continue
        for line in env.read_text(encoding='utf-8-sig').splitlines():
            if '=' not in line or line.lstrip().startswith('#'): continue
            key, value = line.split('=', 1)
            value = value.strip().strip('"').strip("'")
            if re.search('PASSWORD|TOKEN|SECRET|API_KEY', key) and len(value) >= 12:
                secrets.append(value)
            if key == 'DATABASE_URL':
                password = urlsplit(value).password
                if password and len(password) >= 12 and not password.startswith('change_me'):
                    secrets.append(password)
    patterns = {
        'private-key': r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
        'token': r'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,}|sk-proj-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16})',
        'local-user-path': r'(?i)(?:[A-Z]:[\\/]+Users[\\/]|/Users/|/home/)[^\s]+',
        'phone': r'(?<!\w)01[016789][- ]?\d{3,4}[- ]?\d{4}(?!\w)',
    }
    findings, binary, count = [], [], 0
    for path in sorted(paths):
        source = ROOT / path
        if not source.is_file(): continue
        if ((source.name.startswith('.env') and source.name != '.env.example')
                or source.suffix in {'.pptx', '.pem', '.key', '.dump', '.db', '.sqlite', '.xlsx', '.xls'}
                or any(part in {'.venv', 'node_modules', 'dist', '.artifacts', '.e2e'} for part in source.relative_to(ROOT).parts)):
            findings.append((path, 0, 'forbidden-artifact'))
        try: content = source.read_text(encoding='utf-8-sig')
        except UnicodeDecodeError:
            binary.append(path)
            continue
        count += 1
        for number, line in enumerate(content.splitlines(), 1):
            for kind, pattern in patterns.items():
                if not re.search(pattern, line): continue
                if kind == 'local-user-path' and path == 'scripts/security_check.py' and "'local-user-path':" in line: continue
                # Existing synthetic path-stripping regression case, not a workstation path.
                if kind == 'local-user-path' and path == 'backend/tests/test_ingest.py' and 'someone' in line: continue
                findings.append((path, number, kind))
            if any(secret in line for secret in secrets): findings.append((path, number, 'matches-local-secret'))
    print(json.dumps({'text_files': count, 'binary_files': binary, 'findings': findings}, ensure_ascii=False))
    return bool(findings)


if __name__ == '__main__': raise SystemExit(main())
