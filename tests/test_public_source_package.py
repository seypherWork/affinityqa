"""Synthetic allowlist and archive-boundary regressions; no real ZIP generated."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SOURCE=Path(__file__).resolve().parents[1]/'scripts/build_public_source.py'
spec=importlib.util.spec_from_file_location('public_package_fixture',SOURCE)
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


class PublicSourcePackageTests(unittest.TestCase):
    def setUp(self):
        base=SOURCE.parents[1]/'.test-runs';base.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='public-source-unit-',dir=base)
        self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)/'source';self.root.mkdir()
        for folder in ('src','web/app','web/components','web/lib'):(self.root/folder).mkdir(parents=True,exist_ok=True)
        for name in (*builder.EXACT,*('tests/'+n for n in builder.TESTS),*('scripts/'+n for n in builder.DRIVERS)):
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('synthetic source fixture\n',encoding='utf8')
        self.root_patch=patch.object(builder,'ROOT',self.root);self.root_patch.start();self.addCleanup(self.root_patch.stop)

    def test_allowlist_excludes_secrets_captures_receipts_and_compiled_output(self):
        denied=('.env','evidence/private.json','runs/private.json','web/out/index.html','web/node_modules/vendor.js','web/app/hidden.json','docs/STATUS.md','scripts/not-allowed.py')
        for name in denied:
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('must not be included',encoding='utf8')
        (self.root/'tests/test_public_demo_verifier.py').write_text('synthetic verifier test',encoding='utf8')
        files=builder.inventory()
        self.assertIn('tests/test_public_demo_verifier.py',files)
        self.assertTrue(set(denied).isdisjoint(files));self.assertIn('fixtures/synthetic.json',files)
        for name in ('.env','runs/private.json','../outside'):
            with self.assertRaises(ValueError):builder.read_safe(name)

    def test_source_symlink_is_rejected_without_following(self):
        # Mock filesystem link metadata so this regression requires no OS link privilege.
        target=self.root/'src/linked.py';target.write_text('synthetic',encoding='utf8')
        real=Path.is_symlink
        with patch.object(Path,'is_symlink',lambda p:p==target or real(p)):
            with self.assertRaisesRegex(ValueError,'Linked'):builder.inventory()

    def test_archive_hash_manifest_and_no_overwrite(self):
        output=Path(self.temp.name)/'synthetic-public.zip'
        with patch('sys.argv',['builder','--execute','--output',str(output)]),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(builder.main(),0)
            with zipfile.ZipFile(output) as archive:
                manifest=json.loads(archive.read('affinityqa-source/PUBLIC-SOURCE-MANIFEST.json'))
                self.assertIsInstance(manifest['files'],dict);self.assertFalse(manifest['license_granted']);self.assertFalse(manifest['provider_captures_included'])
                self.assertFalse(manifest['mit_original_code'])
                self.assertIn('LICENSE-PROPOSAL.md',manifest['files'])
                self.assertNotIn('LICENSE',manifest['files'])
                self.assertEqual(len(archive.namelist()),len(manifest['files'])+1)
                for name,digest in manifest['files'].items():self.assertEqual(builder.digest(archive.read('affinityqa-source/'+name)),digest)
            before=output.read_bytes()
            with self.assertRaisesRegex(ValueError,'already exists'):builder.main()
            self.assertEqual(output.read_bytes(),before)

    def test_source_mutation_stops_before_archive_and_secret_marker_rejected(self):
        selected=builder.inventory();path=self.root/'pyproject.toml';path.write_text('changed',encoding='utf8');output=Path(self.temp.name)/'must-not-exist.zip'
        with patch.object(builder,'inventory',return_value=selected),patch('sys.argv',['builder','--execute','--output',str(output)]):
            with self.assertRaisesRegex(ValueError,'changed after inventory'):builder.main()
        self.assertFalse(output.exists())
        path.write_text('sk-'+'A'*32,encoding='utf8')
        with self.assertRaisesRegex(ValueError,'Credential-shaped'):builder.read_safe('pyproject.toml')

    def test_approved_mit_is_preserved_and_proposal_removed(self):
        license_bytes=(SOURCE.parents[1]/'LICENSE').read_bytes()
        (self.root/'LICENSE').write_bytes(license_bytes)
        (self.root/'docs/THIRD-PARTY-LICENSES.txt').write_text('Synthetic dependency notice',encoding='utf8')
        (self.root/'docs/LICENSING.md').write_text('Synthetic scope note',encoding='utf8')
        output=Path(self.temp.name)/'synthetic-mit.zip'
        with patch('sys.argv',['builder','--execute','--output',str(output)]),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(builder.main(),0)
        with zipfile.ZipFile(output) as archive:
            prefix='affinityqa-source/'
            manifest=json.loads(archive.read(prefix+'PUBLIC-SOURCE-MANIFEST.json'))
            self.assertTrue(manifest['mit_original_code']);self.assertTrue(manifest['license_granted'])
            self.assertEqual(archive.read(prefix+'LICENSE'),license_bytes)
            self.assertNotIn('LICENSE-PROPOSAL.md',manifest['files'])
            for path in ('LICENSING-NOTES.md','docs/THIRD-PARTY-LICENSES.txt','docs/LICENSING.md'):self.assertIn(path,manifest['files'])
            self.assertIn('MIT licensed',archive.read(prefix+'README.md').decode())
            for name,digest in manifest['files'].items():self.assertEqual(builder.digest(archive.read(prefix+name)),digest)

    def test_incomplete_or_mutated_license_stops_before_output(self):
        output=Path(self.temp.name)/'invalid-license.zip'
        valid=(SOURCE.parents[1]/'LICENSE').read_bytes()
        for invalid in (b'MIT License',valid.replace(b'Seypher',b'Other owner'),valid[:len(valid)//2]):
            (self.root/'LICENSE').write_bytes(invalid)
            with patch('sys.argv',['builder','--execute','--output',str(output)]):
                with self.assertRaisesRegex(ValueError,'owner-approved MIT'):builder.main()
            self.assertFalse(output.exists())


if __name__=='__main__':unittest.main()
