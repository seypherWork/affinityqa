"""Verify recorded individual evidence without credentials, requests or inference."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from affinityqa.individual_verify import verify_individual, write_receipt
from affinityqa.errors import SchemaError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--receipt',type=Path,help='New private receipt file outside the captured artifact directory.')
    args = parser.parse_args()
    receipt = verify_individual(args.directory)
    if args.receipt:
        write_receipt(receipt,args.receipt,args.directory)
    print(json.dumps({k:receipt[k] for k in ('run_id','verification_status','recorded_source','provenance',
        'status','causal_gate','behavioral_gate','cultural_gate','release_gate','verified_model_packets',
        'verified_provider_samples','independent_score_reports','external_service_attested')},indent=2))
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (SchemaError,OSError):
        print('Verification rejected: evidence or receipt destination is invalid or changed. Existing files were retained.',file=sys.stderr)
        raise SystemExit(1)
