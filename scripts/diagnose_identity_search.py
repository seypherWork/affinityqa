"""Diagnose retained artist-search evidence without new calls or raw-data output."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from affinityqa.errors import SchemaError
from affinityqa.identity_diagnostics import diagnose_identity_search


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, help='Exact retained capture run directory.')
    args = parser.parse_args()
    try:
        result = diagnose_identity_search(args.directory)
    except (SchemaError, OSError, KeyError, TypeError, ValueError):
        print(json.dumps({'schema_version': 1, 'diagnosis': 'EVIDENCE_REJECTED',
                          'new_provider_calls': 0, 'new_model_calls': 0,
                          'notice': 'Original search evidence or source binding could not be verified; no raw details exported.'}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
