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
    config=env.get('AFFINITYQA_PUBLIC_CASE_CONFIG','');storage=env.get('AFFINITYQA_PUBLIC_CASE_STORAGE','')
    execute=env.get('AFFINITYQA_ENABLE_NEW_CASES','0')
    if execute not in ('0','1'):raise ValueError('AFFINITYQA_ENABLE_NEW_CASES must be0or1.')
    if bool(config)!=bool(storage):raise ValueError('Case configuration and storage must be supplied together.')
    if not config and execute=='1':raise ValueError('New cases require explicit owner configuration.')
    if not config and not (run and receipt):raise ValueError('An explicit reviewed replay or owner case configuration is mandatory.')
    if bool(run)!=bool(receipt) or (run and (not re.fullmatch(r'\d{8}T\d{6}Z-[0-9a-f]{8}',run)
            or not re.fullmatch(r'[0-9a-f]{64}',receipt))):
        raise ValueError('Explicit reviewed run and receipt hash must match.')
    evidence=Path('/var/data/affinityqa-evidence')
    if run and not evidence.is_dir():raise ValueError('Authorized evidence has not been installed.')
    if not (root/'web/out/demo.html').is_file() and not (root/'web/out/demo/index.html').is_file():
        raise ValueError('Built reviewer frontend missing.')
    argv=[sys.executable,str(root/'scripts/serve_public_demo.py'),'--origin',origin,'--port',str(port),'--listen-internal']
    if run:argv+=['--evidence-root',str(evidence),'--run-id',run,'--receipt-sha256',receipt]
    if config:
        if not Path(config).is_absolute() or not Path(storage).is_absolute():raise ValueError('Case paths must be absolute private persistent paths.')
        argv+=['--cases-config',config,'--cases-storage',storage]
        if execute=='1':
            qloo,model=env.get('AFFINITYQA_QLOO_ENV_FILE',''),env.get('AFFINITYQA_MODEL_ENV_FILE','')
            if not qloo or not model or not Path(qloo).is_absolute() or not Path(model).is_absolute():
                raise ValueError('Explicit absolute private credential paths are required for enabled cases.')
            argv+=['--cases-execute','--case-qloo-env',qloo,'--case-model-env',model]
    return argv


def main():
    root=Path.cwd().resolve()
    argv=command(os.environ,root)
    # serve_public_demo constructs _Capture and verifies bindings before uvicorn binds.
    os.execv(sys.executable,argv)

if __name__=='__main__':main()
