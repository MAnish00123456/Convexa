"""Start using the project virtual environment and install missing demo dependencies."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
candidates = [ROOT / '.venv' / name for name in ('Scripts/python.exe', 'bin/python', 'bin/python.exe')]
venv_python = next((p for p in candidates if p.exists()), candidates[0])
if not venv_python.exists():
    print('Creating the project Python environment...', flush=True)
    subprocess.run([sys.executable, '-m', 'venv', str(ROOT / '.venv')], check=True)
venv_python = next((p for p in candidates if p.exists()), None)
if venv_python is None:
    raise SystemExit('Could not locate the environment Python. Use the manual commands in DEPLOYMENT.md.')
subprocess.run([str(venv_python), '-m', 'ensurepip', '--upgrade'], check=True)
check = subprocess.run([str(venv_python), '-c', 'import pypdf, youtube_transcript_api, cryptography'], capture_output=True)
if check.returncode:
    print('Installing PDF, caption and encrypted-key support. Internet is needed for this first setup.', flush=True)
    subprocess.run([str(venv_python), '-m', 'pip', 'install', '-r', str(ROOT / 'requirements.txt')], check=True)
print('Starting Convexa at http://127.0.0.1:8765', flush=True)
raise SystemExit(subprocess.call([str(venv_python), str(ROOT / 'app.py'), *sys.argv[1:]]))
