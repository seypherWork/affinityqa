"""Build source with exact tool versions; never read provider evidence."""
from pathlib import Path
import subprocess
import sys

def run(args, cwd):
    subprocess.run(args, cwd=cwd, check=True)

def main():
    if sys.version_info[:3] != (3, 12, 14):
        raise RuntimeError('Expected reviewed Python 3.12.14.')
    root = Path.cwd().resolve()
    node = subprocess.check_output(['node', '--version'], text=True).strip()
    if node != 'v24.19.0':
        raise RuntimeError('Expected reviewed Node 24.19.0.')
    pnpm = ['npx', '--yes', 'pnpm@11.25.0']
    version = subprocess.check_output([*pnpm, '--version'], cwd=root, text=True).strip()
    if version != '11.25.0':
        raise RuntimeError('Expected reviewed pnpm 11.25.0.')
    run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements-backend.lock.txt'], root)
    run([sys.executable, '-m', 'pip', 'check'], root)
    for args in (['install', '--frozen-lockfile', '--ignore-scripts'], ['typecheck'], ['build']):
        run([*pnpm, *args], root / 'web')

if __name__ == '__main__': main()
