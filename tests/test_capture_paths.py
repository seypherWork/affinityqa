"""Windows path preflight before provider dispatch, with no real providers."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from affinityqa.errors import SchemaError
from affinityqa import individual_capture as capture
from affinityqa.individual_remote_capture import prepare_plan as remote_plan
from affinityqa.public_cases import PublicCaseManager,public_policy
from test_individual_remote import request_fixture

class CapturePathTests(unittest.TestCase):
    def setUp(self):
        self.guard=patch.object(capture,'WINDOWS_PATHS',True);self.guard.start();self.addCleanup(self.guard.stop)

    def boundary(self,units):
        base=ROOT/'path-fixture'
        suffix='/20000101T000000Z-00000000/causal-summary-individual-20000101T000000Z-00000000.json'
        return base/('x'*(units-len(str(base).encode('utf-16-le'))//2-1-len(suffix)))

    def test_longest_summary_boundary_is_checked_before_capture(self):
        capture.validate_capture_paths(self.boundary(259))
        for length in (260,261):
            with self.subTest(length=length),self.assertRaisesRegex(SchemaError,'shorter'):
                capture.validate_capture_paths(self.boundary(length))

    def test_utf16_units_include_surrogate_pairs(self):
        plain=self.boundary(259)
        # Equal Python character count, but one additional UTF-16 unit.
        unicode=plain.parent/('\U0001f3ac'+plain.name[1:])
        self.assertEqual(len(str(plain)),len(str(unicode)))
        with self.assertRaisesRegex(SchemaError,'shorter'):capture.validate_capture_paths(unicode)

    def test_direct_remote_and_local_plans_reject_before_other_inputs(self):
        for plan,args in ((remote_plan,()),(capture.prepare_plan,('http://127.0.0.1:11434',))):
            with self.subTest(plan=plan.__module__),self.assertRaisesRegex(SchemaError,'shorter'):
                request=request_fixture()
                if args:
                    request['schema_version']=1
                    request['model']={'name':'unit-fake-model','digest':'d'*64}
                plan(request,self.boundary(260),*args)

    def test_public_root_is_rejected_before_storage_or_credential_loaders(self):
        root=self.boundary(260)
        self.assertFalse(root.exists())
        policy=public_policy(maximum_sessions=2,maximum_plans=2,maximum_executions=1,
                             plans_per_session=1,executions_per_session=1,session_hours=24)
        with self.assertRaisesRegex(SchemaError,'shorter'):
            PublicCaseManager(root,request_fixture(),origin='https://judge.example',policy=policy,
                minimum_model_interval_seconds=0,execution_enabled=True,
                settings_loader=lambda: self.fail('Read Qloo'),remote_key_loader=lambda:self.fail('Read model'))
        self.assertFalse(root.exists())

if __name__=='__main__':unittest.main()
