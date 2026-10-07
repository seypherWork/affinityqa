"""Plan one new local pair; --execute requires the exact printed plan fingerprint."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from affinityqa.individual_capture import read_request, prepare_plan, execute_capture
from affinityqa.qloo import Settings
from affinityqa.errors import AffinityQAError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--url', default='http://127.0.0.1:11434')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--plan-sha256')
    parser.add_argument('--env-file', type=Path)
    args = parser.parse_args()
    request = read_request(args.request)
    plan = prepare_plan(request, args.output, args.url)
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return 0
    if args.plan_sha256 != plan['plan_sha256']:
        parser.error('Execution requires the unchanged plan fingerprint. No model or Qloo request started.')
    settings = Settings.from_environment(args.env_file)
    report, directory = execute_capture(request, args.output, args.url, args.plan_sha256, settings)
    print(json.dumps({'run_id': report['run_id'], 'status': report['status'], 'causal_gate': report['causal_gate'],
                      'behavioral_gate': report['behavioral_gate'], 'source': report['source'],
                      'cultural_gate': report['cultural_gate'], 'independent_verification': report['independent_verification'],
                      'error_class': report['error_class'], 'evidence_directory': str(directory)}, indent=2))
    return 0 if (report['status'] == 'COMPLETE' and report['causal_gate'] == 'PASS'
                 and report['behavioral_gate'] == 'OBSERVED_RECOVERY') else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (AffinityQAError, OSError):
        print('Capture could not start. Inputs or local configuration are invalid; no automatic retry.', file=sys.stderr)
        raise SystemExit(1)
