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
    parser.add_argument('--listen-internal', action='store_true', help='Bind container/host internal interface; use only for an approved deployment behind TLS ingress.')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535: parser.error('Port must be1024..65535.')
    from affinityqa.public_demo import create_public_app
    import uvicorn
    app = create_public_app(args.evidence_root.resolve(), origin=args.origin,
                            run_id=args.run_id, receipt_sha256=args.receipt_sha256,
                            web_root=ROOT / 'web/out')
    uvicorn.run(app, host='0.0.0.0' if args.listen_internal else '127.0.0.1',
                port=args.port, proxy_headers=False, access_log=False)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
