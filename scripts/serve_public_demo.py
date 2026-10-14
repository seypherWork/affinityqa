"""Run the restricted reviewer surface. Default binding remains loopback."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', required=True, help='Exact HTTPS origin, or HTTP loopback for private preview.')
    parser.add_argument('--port', type=int, default=8767)
    parser.add_argument('--evidence-root', type=Path, default=ROOT, help='Read-only extracted authorized review bundle.')
    parser.add_argument('--run-id')
    parser.add_argument('--receipt-sha256')
    parser.add_argument('--cases-config',type=Path,help='Explicit private owner catalog, policy, cadence and HTTP limits JSON.')
    parser.add_argument('--cases-storage',type=Path,help='Absolute persistent storage for the one shared public case manager.')
    parser.add_argument('--repeatable-config',type=Path,help='Explicit versioned repeatable owner policy and provider windows JSON.')
    parser.add_argument('--repeatable-storage',type=Path,help='Absolute separate persistent store for repeatable ownership and queue.')
    parser.add_argument('--legacy-cases-storage',type=Path,help='Sealed historical store exposed only through the read-only reader.')
    parser.add_argument('--cases-execute',action='store_true',help='Enable new remote admissions only after owner/provider/transfer approval.')
    parser.add_argument('--case-qloo-env',type=Path,help='Explicit absolute private Qloo credential file; never read during preview.')
    parser.add_argument('--case-model-env',type=Path,help='Explicit absolute private Groq credential file; never read during preview.')
    parser.add_argument('--listen-internal', action='store_true', help='Bind container/host internal interface; use only for an approved deployment behind TLS ingress.')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535: parser.error('Port must be1024..65535.')
    if (args.cases_config is None)!=(args.cases_storage is None):parser.error('Case configuration and storage must be supplied together.')
    if (args.repeatable_config is None)!=(args.repeatable_storage is None):parser.error('Repeatable configuration and storage must be supplied together.')
    if args.repeatable_config is not None and args.cases_config is not None:parser.error('Select one admission manager; historical storage is read-only in repeatable mode.')
    if args.legacy_cases_storage is not None and args.repeatable_config is None:parser.error('Read-only historical storage requires repeatable mode.')
    if args.cases_config is None and args.repeatable_config is None and (args.cases_execute or args.case_qloo_env is not None or args.case_model_env is not None):
        parser.error('Private case options require explicit case configuration and storage.')
    from affinityqa.public_demo import create_public_app
    import uvicorn
    manager=None;limits={}
    if args.repeatable_config is not None:
        from affinityqa.repeatable_case_config import configure_repeatable_cases
        manager,limits=configure_repeatable_cases(args.repeatable_config,args.repeatable_storage,origin=args.origin,
            execution_enabled=args.cases_execute,qloo_env=args.case_qloo_env,model_env=args.case_model_env,
            legacy_root=args.legacy_cases_storage)
    elif args.cases_config is not None:
        from affinityqa.public_case_config import configure_cases
        manager,limits=configure_cases(args.cases_config,args.cases_storage,origin=args.origin,
            execution_enabled=args.cases_execute,qloo_env=args.case_qloo_env,model_env=args.case_model_env)
    try:
        app = create_public_app(args.evidence_root.resolve(), origin=args.origin,
                                run_id=args.run_id, receipt_sha256=args.receipt_sha256,
                                web_root=ROOT / 'web/out',case_manager=manager,**limits)
    except BaseException:
        if manager is not None:manager.close()
        raise
    try:
        uvicorn.run(app, host='0.0.0.0' if args.listen_internal else '127.0.0.1',
                    port=args.port, proxy_headers=False, access_log=False)
    finally:
        if manager is not None:manager.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
