"""Explicit source-seal upgrade keeps every consumed session/job admission."""
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from affinityqa.errors import SchemaError
from affinityqa.evidence import fingerprint
from affinityqa.individual_jobs import read
from affinityqa.public_policy_continuation import MARKER,execute,propose
import test_public_cases as fixtures


class PublicPolicyContinuationTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.PublicCasesTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def old_storage(self):
        service=self.fixture.service()
        token=self.fixture.visitor(service)
        job=service.prepare(token,self.fixture.request['artists'])
        complete=self.fixture.finish(service,token,job)
        self.assertEqual(complete['status'],'COMPLETE')
        root=service.root;service.close()
        policy=read(root/'public-policy.json')
        policy.update(controller_sha256='0'*64,manager_sha256='1'*64)
        policy['policy_sha256']=fingerprint({k:v for k,v in policy.items() if k!='policy_sha256'})
        (root/'public-policy.json').write_text(json.dumps(policy),encoding='utf8')
        for folder in ('sessions','ownership'):
            for path in (root/folder).iterdir():
                value=read(path);value['policy_sha256']=policy['policy_sha256']
                path.write_text(json.dumps(value),encoding='utf8')
        return root,token,job

    def test_no_automatic_upgrade_exact_proposal_then_same_admissions_and_evidence(self):
        root,token,job=self.old_storage()
        with self.assertRaises(SchemaError):self.fixture.service(root=root)
        proposal=propose(root)
        self.assertFalse((root/MARKER).exists())
        with self.assertRaises(SchemaError):execute(root,'f'*64)
        self.assertFalse((root/MARKER).exists())
        receipt=execute(root,proposal['proposal_sha256'])
        from affinityqa.individual_capture import sha
        self.assertTrue(all(sha(root/name)==digest for name,digest in receipt['preserved_files_sha256'].items()))
        restored=self.fixture.service(root=root)
        cap=restored.capabilities(token)
        self.assertEqual(cap['remaining_executions'],0)
        self.assertEqual(restored.view(token,job['job_id'])['status'],'COMPLETE')
        with self.assertRaises(SchemaError):execute(root,proposal['proposal_sha256'])

    def test_active_storage_denied_and_changed_budget_never_admitted(self):
        service=self.fixture.service()
        with self.assertRaises(SchemaError):propose(service.root)
        with self.assertRaises(SchemaError):execute(service.root,'0'*64)
        self.assertFalse((service.root/MARKER).exists());service.close()
        root,token,job=self.old_storage()
        proposal=propose(root);execute(root,proposal['proposal_sha256'])
        with self.assertRaises(SchemaError):self.fixture.service(root=root,policy=self.fixture.policy(maximum_executions=5))

    def test_marker_tampering_rejected_without_touching_originals(self):
        root,token,job=self.old_storage();proposal=propose(root)
        execute(root,proposal['proposal_sha256'])
        marker_path=root/proposal['marker_name']
        marker=read(marker_path);marker['admissions_reset']=True
        marker_path.write_text(json.dumps(marker),encoding='utf8')
        with self.assertRaises(SchemaError):self.fixture.service(root=root)

    def test_missing_retained_lock_never_creates_auxiliary_storage(self):
        root=self.fixture.parent/'unrecognized';root.mkdir();(root/'jobs').mkdir()
        before=set(root.rglob('*'))
        with self.assertRaises(SchemaError):execute(root,'0'*64)
        self.assertEqual(set(root.rglob('*')),before)
        self.assertFalse((root/'jobs'/'.affinityqa-individual.lock').exists())

    def test_legacy_v1_anchor_is_read_without_rewriting_it(self):
        root,token,job=self.old_storage()
        from affinityqa.individual_capture import sha
        source=ROOT/'src/affinityqa'
        previous=read(root/'public-policy.json')
        marker={'schema_version':1,'previous_binding_sha256':fingerprint(previous),
                'current_controller_sha256':sha(source/'public_cases.py'),
                'current_manager_sha256':sha(source/'individual_jobs.py'),'admissions_reset':False}
        (root/MARKER).write_text(json.dumps(marker),encoding='utf8')
        before=sha(root/MARKER)
        restored=self.fixture.service(root=root)
        self.assertEqual(restored.view(token,job['job_id'])['status'],'COMPLETE')
        self.assertEqual(restored.capabilities(token)['remaining_executions'],0)
        self.assertEqual(sha(root/MARKER),before)
