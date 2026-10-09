"""Stopped real-version stores migrate append-only; never reset admissions."""
import errno
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from affinityqa.errors import SchemaError
from affinityqa.individual_capture import sha
from affinityqa.individual_jobs import read
from affinityqa.public_policy_continuation import execute,propose
import test_public_cases as fixtures

LEGACY=ROOT/'tests/fixtures/policy_v1'
LEGACY_SHA={'public_cases.py': '6326f0d395e856d38b1efc2b42ec185ff938c3ce962704ada4c879bc0cee842e', 'public_policy_continuation.py': 'c8d9af36706bc87bc294eea03fed65fe252a472816be8daeb0e0db215757d826'}
PREFIX='public-policy-continuation-v2-'


class PublicPolicyChainTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.PublicCasesTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def inventory(self,root):
        return {p.relative_to(root).as_posix():sha(p) for p in root.rglob('*')
                if p.is_file() and p.name!='.affinityqa-individual.lock'}

    def predecessor_source(self):
        # Reconstruct the exact historical controller and continuation modules
        # from pinned archive fixtures. Shared unchanged modules are copied from
        # this package, never from a developer's external checkout.
        for name,digest in LEGACY_SHA.items():
            self.assertEqual(sha(LEGACY/name),digest,'Historical module fixture changed.')
        prior=self.fixture.parent/'predecessor';prior.mkdir()
        replacements={'src/affinityqa/'+name:(LEGACY/name).read_bytes() for name in LEGACY_SHA}
        for folder in ('src','tests','scripts'):
            for path in sorted((ROOT/folder).rglob('*.py')):
                relative=path.relative_to(ROOT);destination=prior/relative
                destination.parent.mkdir(parents=True,exist_ok=True)
                data=replacements.get(relative.as_posix(),path.read_bytes())
                with destination.open('xb') as handle:handle.write(data)
        with (prior/'requirements-backend.lock.txt').open('xb') as handle:
            handle.write((ROOT/'requirements-backend.lock.txt').read_bytes())
        return prior

    def old_store(self):
        # Generate the store with the actual preserved predecessor in another
        # interpreter. Never rewrite controller/session/ownership seals.
        prior=self.predecessor_source()
        root=self.fixture.parent/'legacy'
        runner=self.fixture.parent/'legacy-generator.py'
        runner.write_text('''import json,sys
from pathlib import Path
source=Path(sys.argv[1]);root=Path(sys.argv[2])
sys.path[:0]=[str(source/'src'),str(source/'tests')]
import test_public_cases as fixtures
f=fixtures.PublicCasesTests();f.setUp()
try:
 s=f.service(root=root);token=f.visitor(s)
 job=f.finish(s,token,s.prepare(token,f.request['artists']))
 assert job['status']=='COMPLETE'
 s.close()
 with (root.parent/'legacy-case.json').open('x',encoding='utf8') as h:
  json.dump({'token':token,'job_id':job['job_id'],'reads':f.reads},h)
finally:f.doCleanups()
''',encoding='utf8')
        result=subprocess.run([sys.executable,'-I','-B',str(runner),str(prior),str(root)],
                              capture_output=True,text=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stderr)
        info=read(root.parent/'legacy-case.json')
        self.assertEqual(info['reads'],[1,1])  # simulated adapters only
        self.assertEqual(read(root/'public-policy.json')['controller_sha256'],sha(LEGACY/'public_cases.py'))
        self.assertEqual(read(root/'public-policy.json')['manager_sha256'],sha(ROOT/'src/affinityqa/individual_jobs.py'))
        return root,info

    def test_real_predecessor_continuation_retains_records_expiry_receipt_and_budget(self):
        root,info=self.old_store();before=self.inventory(root)
        if sha(ROOT/'src/affinityqa/public_cases.py')!=sha(LEGACY/'public_cases.py'):
            with self.assertRaises(SchemaError):self.fixture.service(root=root)
        else:self.fixture.service(root=root).close()
        proposal=propose(root)
        self.assertEqual(self.inventory(root),before)
        self.assertEqual(proposal['marker']['schema_version'],2)
        execute(root,proposal['proposal_sha256'])
        self.assertTrue((root/(PREFIX+'000001.json')).is_file())
        self.assertTrue(all(sha(root/name)==digest for name,digest in before.items()))
        service=self.fixture.service(root=root,enabled=False)
        self.assertEqual(service.view(info['token'],info['job_id'])['status'],'COMPLETE')
        self.assertEqual(service.capabilities(info['token'])['remaining_executions'],0)
        self.assertEqual(self.fixture.reads,[0,0])
        self.assertEqual(self.fixture.engines,[])

    def test_active_manager_denies_both_proposal_and_execution(self):
        service=self.fixture.service();before=self.inventory(service.root)
        with self.assertRaises(SchemaError):propose(service.root)
        with self.assertRaises(SchemaError):execute(service.root,'0'*64)
        self.assertEqual(self.inventory(service.root),before)
        self.assertEqual(self.fixture.reads,[0,0])

    def test_exact_proposal_denies_changed_inventory_without_creating_marker(self):
        root,info=self.old_store();proposal=propose(root)
        record=next((root/'sessions').iterdir());value=read(record)
        value['expires_utc']='2026-10-08T14:00:00+00:00'
        record.write_text(json.dumps(value),encoding='utf8')
        changed=self.inventory(root)
        with self.assertRaises(SchemaError):execute(root,proposal['proposal_sha256'])
        self.assertEqual(self.inventory(root),changed)
        self.assertFalse(list(root.glob(PREFIX+'*.json')))

    def test_staging_failure_preserves_originals_and_never_creates_partial_final(self):
        root,info=self.old_store();proposal=propose(root);before=self.inventory(root)
        with patch('os.fsync',side_effect=OSError(errno.ENOSPC,'injected')):
            with self.assertRaises(OSError):execute(root,proposal['proposal_sha256'])
        self.assertEqual(self.inventory(root),before)
        self.assertFalse(list(root.glob(PREFIX+'*.json')))

    def test_actual_second_source_and_rollback_append_without_reopening_old_tail(self):
        root,info=self.old_store();before=self.inventory(root)
        first=propose(root);execute(root,first['proposal_sha256'])
        first_record=root/(PREFIX+'000001.json');first_hash=sha(first_record)
        # Distinct actual chain-aware source tree, rather than false policy hashes.
        candidate=self.fixture.parent/'candidate-b';candidate.mkdir()
        for folder in ('src','tests','scripts'):
            for path in (ROOT/folder).rglob('*.py'):
                dest=candidate/path.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(path.read_bytes())
        (candidate/'requirements-backend.lock.txt').write_bytes((ROOT/'requirements-backend.lock.txt').read_bytes())
        controller=candidate/'src/affinityqa/public_cases.py'
        controller.write_bytes(controller.read_bytes()+b'\n# Isolated actual second source version for the continuity contract.\n')
        runner=self.fixture.parent/'second-version.py'
        runner.write_text('''import json,sys
from pathlib import Path
source=Path(sys.argv[1]);root=Path(sys.argv[2]);token=sys.argv[3];job=sys.argv[4]
sys.path[:0]=[str(source/'src'),str(source/'tests')]
import test_public_cases as fixtures
from affinityqa.public_policy_continuation import propose,execute
f=fixtures.PublicCasesTests();f.setUp()
try:
 p=propose(root);execute(root,p['proposal_sha256'])
 s=f.service(root=root,enabled=False)
 assert s.view(token,job)['status']=='COMPLETE'
 assert s.capabilities(token)['remaining_executions']==0
 assert f.reads==[0,0] and not f.engines
 s.close()
finally:f.doCleanups()
''',encoding='utf8')
        # Arguments contain only generated synthetic session tokens, no credentials.
        result=subprocess.run([sys.executable,'-I','-B',str(runner),str(candidate),str(root),info['token'],info['job_id']],
                              capture_output=True,text=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stderr)
        second_record=root/(PREFIX+'000002.json');second_hash=sha(second_record)
        self.assertEqual(read(second_record)['to_source']['controller_sha256'],sha(controller))
        with self.assertRaises(SchemaError):self.fixture.service(root=root,enabled=False)
        rollback=propose(root)
        self.assertEqual(rollback['marker']['from_source'],read(second_record)['to_source'])
        self.assertEqual(rollback['marker']['to_source'],read(first_record)['to_source'])
        execute(root,rollback['proposal_sha256'])
        self.assertEqual(sha(first_record),first_hash);self.assertEqual(sha(second_record),second_hash)
        self.assertTrue(all(sha(root/name)==digest for name,digest in before.items()))
        restored=self.fixture.service(root=root,enabled=False)
        self.assertEqual(restored.view(info['token'],info['job_id'])['status'],'COMPLETE')
        self.assertEqual(restored.capabilities(info['token'])['remaining_executions'],0)
        self.assertEqual(self.fixture.reads,[0,0])

    def test_chain_fields_link_sequence_and_bounds_rejected_without_repair(self):
        root,info=self.old_store();p=propose(root);execute(root,p['proposal_sha256'])
        path=root/p['marker_name'];original=path.read_bytes();value=read(path)
        changes=({'admissions_reset':True},{'sequence':True},{'schema_version':True},
                 {'extra':1},{'previous_record_sha256':'0'*64},
                 {'from_source':{'controller_sha256':'0'*64,'manager_sha256':'1'*64}})
        for change in changes:
            with self.subTest(change=change):
                path.write_text(json.dumps({**value,**change}),encoding='utf8')
                damaged=self.inventory(root)
                with self.assertRaises(SchemaError):self.fixture.service(root=root,enabled=False)
                with self.assertRaises(SchemaError):propose(root)
                self.assertEqual(self.inventory(root),damaged)
        path.write_bytes(b' '*4097)
        with self.assertRaises(SchemaError):propose(root)
        path.write_bytes(original)
        unknown=root/(PREFIX+'000003.json');unknown.write_bytes(original)
        with self.assertRaises(SchemaError):self.fixture.service(root=root,enabled=False)
        self.assertEqual(self.fixture.reads,[0,0])

    def test_runtime_seal_rejects_same_semantics_rewritten_record(self):
        root,info=self.old_store();p=propose(root);execute(root,p['proposal_sha256'])
        service=self.fixture.service(root=root,enabled=False)
        path=root/p['marker_name'];path.write_text(json.dumps(read(path)),encoding='utf8')
        with self.assertRaises(SchemaError):service.capabilities(info['token'])
        with self.assertRaises(SchemaError):service.session()
        self.assertEqual(self.fixture.reads,[0,0])

    def test_no_replace_and_failure_after_publish_keep_full_record_and_staging(self):
        root,info=self.old_store();p=propose(root);before=self.inventory(root)
        real_fsync=__import__('os').fsync;calls=[]
        def fail_second(fd):
            calls.append(fd)
            if len(calls)==2:raise OSError(errno.ENOSPC,'injected after publish')
            return real_fsync(fd)
        # On Windows the second flush is the complete published file. POSIX
        # flushes staging directories first; publication may not yet have begun.
        with patch('os.fsync',side_effect=fail_second):
            with self.assertRaises(OSError):execute(root,p['proposal_sha256'])
        self.assertTrue(all(sha(root/name)==digest for name,digest in before.items()))
        if (root/p['marker_name']).exists():
            self.assertEqual(read(root/p['marker_name']),p['marker'])
        self.assertTrue(list(root.parent.glob('.affinityqa-continuation-*')))
        from affinityqa.public_policy_continuation import _publish
        existing=root/'existing-immutable.json';existing.write_bytes(b'preserved')
        with self.assertRaises(FileExistsError):_publish(root,existing.name,p['marker'])
        self.assertEqual(existing.read_bytes(),b'preserved')

if __name__=='__main__':unittest.main()
