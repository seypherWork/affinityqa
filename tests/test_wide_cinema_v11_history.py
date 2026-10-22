"""Frozen v11 history is reconstructed, never upgraded or executed again."""
import hashlib
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from affinityqa.errors import SchemaError
from affinityqa import wide_cinema_v11_compat as old
from affinityqa.wide_cinema_verify import verify_identity_search,verify_discoveries,_wire,verify_packet
from affinityqa import wide_cinema_v11_verify as old_reader
from affinityqa.wide_cinema_capture import capture_confirmed

ROOT=Path(__file__).resolve().parents[1]


class HistoricalV11Tests(unittest.TestCase):
    def test_snapshot_exact_and_tampering_rejected(self):
        package=ROOT/'src/affinityqa'
        old.validate_frozen_sources()
        for name,value in old.FROZEN_SOURCE_SHA256.items():
            self.assertEqual(hashlib.sha256((package/'wide_cinema_v11_source'/name).read_bytes()).hexdigest(),value)
            self.assertEqual(old.legacy_source_sha(package/name),value)
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as scratch:
            snapshot=Path(scratch)
            for name in old.FROZEN_SOURCE_SHA256:(snapshot/name).write_bytes((package/'wide_cinema_v11_source'/name).read_bytes())
            with (snapshot/'wide_cinema_verify.py').open('ab') as handle:handle.write(b'\n# synthetic tamper\n')
            with self.assertRaises(SchemaError):old.validate_frozen_sources(snapshot_directory=snapshot)

    def test_original_v11_complete_and_partial_receipts_remain_unchanged(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as scratch:
            scratch=Path(scratch);legacy=scratch/'legacy-package';legacy.mkdir()
            # Construct a disposable v11 producer from the frozen originals.
            # Existing candidates and historical captures are never overwritten.
            for source in ROOT.rglob('*'):
                relative=source.relative_to(ROOT)
                if not source.is_file() or any(n in relative.parts for n in ('.test-runs','__pycache__','node_modules','.next','out')):continue
                destination=legacy/relative;destination.parent.mkdir(parents=True,exist_ok=True)
                if relative.as_posix().startswith('src/affinityqa/') and relative.name in old.FROZEN_SOURCE_SHA256 and len(relative.parts)==3:
                    value=(ROOT/'src/affinityqa/wide_cinema_v11_source'/relative.name).read_bytes()
                else:value=source.read_bytes()
                with destination.open('xb') as handle:handle.write(value)
            captures=scratch/'captures';captures.mkdir()
            child="""import json,sys
from pathlib import Path
from test_wide_cinema_capture import WideCaptureTests,WideTransport,request_fixture
f=WideCaptureTests('test_movie100_actual_candidates_three_qloo_one_model');f.setUp()
try:
 f.base=Path(sys.argv[1]);_,complete=f.finish()
 complete_path=str(f.directory)
 def mutate(body,page):
  if page==2:body['results']['entities'][26]['name']='Synthetic  noncanonical'
 _,partial=f.finish(request_fixture('music',True),WideTransport(mutation=mutate))
 from affinityqa.repeatable_cases import RepeatableCaseManager
 from test_individual_remote_jobs import request_fixture as legacy_request
 from datetime import datetime,timezone
 now=datetime(2026,10,14,20,tzinfo=timezone.utc)
 template=legacy_request()
 owned=RepeatableCaseManager(Path(sys.argv[1])/'owned-v11',template,origin='https://judge.example',
  minimum_model_interval_seconds=22,execution_enabled=False,token_estimator=f.estimator,
  _test_adapters=(lambda:None,lambda:None),_test_now=lambda:now,_test_autostart=False)
 try:
  token,_=owned.session()
  planned=owned.prepare_wide_cinema(token,'movie','Synthetic seed 2000')
  retained={'root':str(owned.root),'job':planned,'token':token,'request':template,'now':now.isoformat()}
 finally:owned.close()
 print(json.dumps({'complete':complete_path,'partial':str(f.directory),'complete_status':complete['verification_status'],'partial_status':partial['verification_status'],'owned':retained}))
finally:f.doCleanups()
"""
            env=dict(os.environ)
            entries=env.get('PYTHONPATH','').split(os.pathsep)
            guard=[p for p in entries if (Path(p)/'sitecustomize.py').is_file()]
            env['PYTHONPATH']=os.pathsep.join(guard+[str(legacy/'src'),str(legacy/'tests')])
            run=subprocess.run([sys.executable,'-B','-c',child,str(captures)],cwd=legacy,env=env,capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            result=json.loads(run.stdout)
            self.assertEqual(result['complete_status'],'VERIFIED_COMPLETE')
            self.assertEqual(result['partial_status'],'VERIFIED_PARTIAL')
            # A retained v11 plan stays owned and readable, but cannot dispatch v12 sources.
            from datetime import datetime
            from affinityqa.repeatable_cases import RepeatableCaseManager
            from affinityqa.wide_cinema_tokens import WideHarmonyTokenEstimator
            retained=result['owned'];root=Path(retained['root']);job=retained['job']
            job_dir=root/'jobs'/job['job_id']
            before_plan={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in job_dir.iterdir() if p.is_file()}
            def forbidden():raise AssertionError('Historical plan must never load provider credentials or dispatch.')
            manager=RepeatableCaseManager(root,retained['request'],origin='https://judge.example',
                minimum_model_interval_seconds=22,execution_enabled=True,settings_loader=forbidden,remote_key_loader=forbidden,
                token_estimator=WideHarmonyTokenEstimator(ROOT/'assets/tokenizers/o200k_base.tiktoken'),
                _test_adapters=(forbidden,forbidden),_test_now=lambda:datetime.fromisoformat(retained['now']),_test_autostart=False)
            try:
                viewed=manager.view(retained['token'],job['job_id'])
                self.assertEqual(viewed['status'],'PLANNED');self.assertTrue(viewed['read_only'])
                self.assertEqual(viewed['continuity_reason'],'EXECUTION_SOURCE_CHANGED')
                with self.assertRaisesRegex(SchemaError,'source or tokenizer assets changed'):
                    manager.start(retained['token'],job['job_id'],job['plan_sha256'])
                self.assertEqual(manager.view(retained['token'],job['job_id'])['status'],'PLANNED')
                self.assertEqual(before_plan,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in job_dir.iterdir() if p.is_file()})
            finally:manager.close()

            for label,verifier in (('complete',verify_discoveries),('partial',verify_discoveries)):
                directory=Path(result[label]);before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir() if p.is_file()}
                receipt=verifier(directory)
                self.assertEqual(receipt['verification_status'],result[label+'_status'])
                self.assertEqual(receipt['protocol_version'],'qloo-wide-cinema-discovery-v11')
                if label=='complete':
                    packet=json.loads((directory/'wide-execution-001.json').read_bytes())
                    manifest=json.loads((directory/'wide-model-manifest.json').read_bytes())
                    decision=packet['effective_request']
                    self.assertEqual(_wire(decision,manifest),old_reader._wire(decision,manifest))
                    self.assertEqual(verify_packet(packet,manifest,decision),old_reader.verify_packet(packet,manifest,decision))
                    broken=copy.deepcopy(packet)
                    broken['observation']['provider_envelope']['choice']['ordered_catalog_indices'][0]['catalog_index']=1000
                    with self.assertRaises(SchemaError):verify_packet(broken,manifest,decision)

                self.assertEqual(before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir() if p.is_file()})
                with self.assertRaises(SchemaError):capture_confirmed(directory,'not-sent',receipt,None,None)
                self.assertEqual(before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir() if p.is_file()})


if __name__=='__main__':unittest.main()
