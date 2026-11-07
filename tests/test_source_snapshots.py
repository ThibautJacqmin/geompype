"""Preserve source bytes and separate private/output trees in source backups."""

import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest
import zipfile


_script = Path(__file__).resolve().parents[1]/'tools/snapshot_sources.py'
_spec = importlib.util.spec_from_file_location('source_snapshot_tool', _script)
snapshots = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(snapshots)


class TestSourceSnapshots(unittest.TestCase):
    def test_all_source_bytes_survive_with_private_and_generated_files_excluded(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)/'project'
            sources = {'AGENTS.md': b'Keep the handoff.\n',
                       '.gitignore': b'/output/\n/private-designs/\n',
                       'new_untracked.py': b'answer = 42\n',
                       'parameters/chip.yaml': b'width: 8 um\n',
                       'tests/reference/mask.gds': b'\x00\x06\x00\x02\x02X'}
            ignored = ['private-designs/personal/secret.py', 'output/existing.gds',
                       '.venv-clean/pyvenv.cfg', '__pycache__/cached.pyc',
                       'build/generated.py', 'project.egg-info/PKG-INFO',
                       'comsol.local.json', 'settings/config.local.json', '.env',
                       'design.gds', 'design.mph', 'design.mphbin']
            for name, data in {**sources, **dict.fromkeys(ignored, b'not source')}.items():
                path = root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            archive, manifest = snapshots.snapshot_sources(root, label='first')
            self.assertEqual({entry['path'] for entry in manifest['files']}, set(sources))
            with zipfile.ZipFile(archive) as bundle:
                for name, expected in sources.items():
                    self.assertEqual(bundle.read('sources/'+name), expected)
            recorded_digest = archive.with_suffix('.zip.sha256').read_text().split()[0]
            self.assertEqual(recorded_digest, hashlib.sha256(archive.read_bytes()).hexdigest())
            (root/'new_untracked.py').write_bytes(b'changed later\n')
            second, _ = snapshots.snapshot_sources(root, label='second')
            self.assertNotEqual(archive, second)
            snapshots.verify_snapshot(archive)
            with zipfile.ZipFile(archive) as bundle:
                self.assertEqual(bundle.read('sources/new_untracked.py'), sources['new_untracked.py'])
            with zipfile.ZipFile(second) as bundle:
                self.assertEqual(bundle.read('sources/new_untracked.py'), b'changed later\n')

    def test_verification_rejects_changed_source_bytes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)/'project'
            root.mkdir()
            (root/'source.py').write_bytes(b'original\n')
            archive, _ = snapshots.snapshot_sources(root)
            damaged = Path(directory)/'damaged.zip'
            with zipfile.ZipFile(archive) as original, zipfile.ZipFile(damaged, 'w') as copy:
                for name in original.namelist():
                    data = original.read(name)
                    copy.writestr(name, b'changed\n' if name == 'sources/source.py' else data)
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                snapshots.verify_snapshot(damaged)

    def test_public_git_inventory_contains_untracked_files_without_private_paths(self):
        root = Path(__file__).resolve().parents[1]
        files, in_git = snapshots._inventory(root)
        names = {path.as_posix() for path in files}
        self.assertIn('tools/snapshot_sources.py', names)
        if (root/'AGENTS.md').is_file():
            self.assertIn('AGENTS.md', names)
        self.assertIn('geompype/routing.py', names)
        self.assertFalse(any(name.startswith(('private-designs/', '.venv', 'output/')) for name in names))
        if in_git:
            metadata, patches = snapshots._git_metadata(root, files)
            self.assertFalse(any(item['path'].startswith('private-designs/') for item in metadata['status']))
            self.assertEqual(set(patches), {'worktree.patch', 'index.patch'})

    @unittest.skipUnless(shutil.which('git'), 'Git is required for this inventory check.')
    def test_ignored_handoffs_survive_without_machine_settings(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', str(root)], capture_output=True, check=True)
            sources = {'AGENTS.md', 'CONTEXT.md', 'CONTEXT_HISTORY.md',
                       'docs/agent-memory/geometry.md', 'source.py'}
            ignored = {'comsol.local.json', '.env', 'output/design.gds'}
            for name in sources | ignored:
                path = root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('fixture\n', encoding='utf-8')
            (root/'.gitignore').write_text(
                'AGENTS.md\nCONTEXT*.md\ndocs/agent-memory/\n*.local.json\n.env\noutput/\n',
                encoding='utf-8')
            files, in_git = snapshots._inventory(root)
            self.assertTrue(in_git)
            self.assertEqual({path.as_posix() for path in files}, sources | {'.gitignore'})

    @unittest.skipUnless(shutil.which('git'), 'Git is required for this inventory check.')
    def test_staged_copy_is_not_hidden_by_ancestor_ignore_rules(self):
        with TemporaryDirectory() as directory:
            parent = Path(directory)
            subprocess.run(['git', 'init', str(parent)], capture_output=True, check=True)
            (parent/'.gitignore').write_text('output/\n', encoding='utf-8')
            root = parent/'output'/'standalone'
            root.mkdir(parents=True)
            (root/'source.py').write_text('answer = 42\n', encoding='utf-8')
            files, in_git = snapshots._inventory(root)
            self.assertFalse(in_git)
            self.assertEqual(files, [Path('source.py')])

