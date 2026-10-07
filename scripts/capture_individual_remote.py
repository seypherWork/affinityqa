"""Plan a new remote pair; explicit --execute admits only its exact fingerprint."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from affinityqa.individual_remote_capture import read_request, prepare_plan, execute_capture, load_private_credential
from affinityqa.qloo import Settings
from affinityqa.errors import AffinityQAError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--plan-sha256')
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--groq-env-file', type=Path)
    parser.add_argument('--model-minimum-interval', type=float,
                        help='Owner-reviewed seconds between remote model dispatch starts (0-65); required for real execution.')
    args = parser.parse_args()
    request = read_request(args.request)
    plan = prepare_plan(request, args.output, minimum_model_interval_seconds=args.model_minimum_interval)
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return 0
    if args.plan_sha256 != plan['plan_sha256']:
        parser.error('The reviewed plan fingerprint is required. No provider request started.')
    if args.env_file is None or args.groq_env_file is None:
        parser.error('Explicit private Qloo and Groq credential file paths are required; never paste keys in arguments.')
    if args.model_minimum_interval is None:
        parser.error('Choose and review the model interval before reading credentials or executing.')
    settings = Settings.from_environment(args.env_file, use_process_environment=False)
    remote_key = load_private_credential(args.groq_env_file)
    report, directory = execute_capture(request, args.output, args.plan_sha256, settings, remote_key,
                                        minimum_model_interval_seconds=args.model_minimum_interval)
    print(json.dumps({**{k: report[k] for k in ('run_id', 'status', 'causal_gate', 'behavioral_gate', 'source',
        'cultural_gate', 'release_gate', 'independent_verification', 'error_class')},
        'evidence_directory': str(directory)}, indent=2))
    return 0 if report['status'] == 'COMPLETE' and report['causal_gate'] == 'PASS' and report['behavioral_gate'] == 'OBSERVED_RECOVERY' else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (AffinityQAError, OSError, UnicodeError):
        print('Remote capture rejected or incomplete. Inspect private evidence; no retry or fallback occurred.', file=sys.stderr)
        raise SystemExit(1)
