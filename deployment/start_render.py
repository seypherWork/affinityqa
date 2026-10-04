"""Proposed Render entrypoint: refuse to expose demo without bound evidence."""
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


def command(env, root):
    origin=env.get('RENDER_EXTERNAL_URL','')
    u=urlsplit(origin)
    if u.scheme!='https' or not u.hostname or u.username or u.password or u.path or u.query or u.fragment:
        raise ValueError('RENDER_EXTERNAL_URL must be one exact HTTPS origin.')
    port=int(env.get('PORT','10000'))
    if not 1024<=port<=65535:raise ValueError('Invalid PORT.')
    run=env.get('AFFINITYQA_RUN_ID','');receipt=env.get('AFFINITYQA_RECEIPT_SHA256','')
    if not re.fullmatch(r'\d{8}T\d{6}Z-[0-9a-f]{8}',run) or not re.fullmatch(r'[0-9a-f]{64}',receipt):
        raise ValueError('Explicit reviewed run and receipt hash are mandatory.')
    evidence=Path('/var/data/affinityqa-evidence')
    if not evidence.is_dir():raise ValueError('Authorized evidence has not been installed.')
    if not (root/'web/out/demo.html').is_file() and not (root/'web/out/demo/index.html').is_file():
        raise ValueError('Built reviewer frontend missing.')
    return [sys.executable,str(root/'scripts/serve_public_demo.py'),'--origin',origin,'--port',str(port),'--listen-internal','--evidence-root',str(evidence),'--run-id',run,'--receipt-sha256',receipt]


def main():
    root=Path.cwd().resolve()
    argv=command(os.environ,root)
    # serve_public_demo constructs _Capture and verifies bindings before uvicorn binds.
    os.execv(sys.executable,argv)

if __name__=='__main__':main()
