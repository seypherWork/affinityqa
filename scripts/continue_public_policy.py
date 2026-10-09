"""Review-first source continuation; requires stopped storage and exact hash."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from affinityqa.public_policy_continuation import execute, propose

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage',type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--expected-proposal-sha256')
    args=parser.parse_args()
    if args.execute and args.expected_proposal_sha256 is None:
        parser.error('Execution needs the exact reviewed proposal hash.')
    print(json.dumps(execute(args.storage,args.expected_proposal_sha256) if args.execute else propose(args.storage),indent=2))
