"""Preserve a source tree, including untracked work, without changing Git.

Run from the public project with ``python tools/snapshot_sources.py``. For a
separate private repository, pass its directory explicitly. Each archive stays
in that source tree's ignored ``output/source_snapshots`` directory; private
sources never enter the public archive. This backs up source files, not Git
history, virtual environments, local connection settings or generated outputs.
Ignored handoff Markdown is retained in these local backups. Do not publish
the archives: their purpose is continuity, not distribution. Reference GDS
fixtures under ``tests/reference`` are preserved for private regression tests.

Only the Python standard library and the existing Git executable are used.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import zipfile


_EXCLUDED_DIRECTORIES = {
    '.git', '.agents', '.codex', '.aws', '__pycache__', '.pytest_cache',
    '.mypy_cache', '.ruff_cache', 'output', 'build', 'dist', 'venv',
    'private-designs',
}


def _excluded(path):
    """Exclude machine settings and outputs even when no Git metadata exists."""
    name = path.name.lower()
    local_settings = '.local.' in name or name.endswith('.local') \
        or name == '.env' or name.startswith('.env.')
    geometry_output = path.suffix.lower() in ('.gds', '.gdsii', '.oas', '.oasis') \
        and path.parts[:2] != ('tests', 'reference')
    return local_settings or geometry_output \
        or any(part in _EXCLUDED_DIRECTORIES or part.startswith('.venv')
               or part.endswith('.egg-info') for part in path.parts) \
        or path.suffix.lower() in ('.pyc', '.pyo', '.mph', '.mphbin', '.mphlog', '.mphstatus')


def _git(root, *arguments, required=False):
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS='0')
    result = subprocess.run(['git', '-C', str(root), *arguments],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=environment, check=False)
    if required and result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace').strip())
    return result.stdout if result.returncode == 0 else None


def _inventory(root):
    """Use Git's ignore rules, including untracked files, when in a repository.

    A source tree already extracted from an archive can also be backed up:
    without Git metadata the directory walk applies the explicit exclusions.
    Use only this directory's own Git root: an ancestor's ignore rules must not
    hide an extracted project staged under its output directory. Handoff notes
    are retained explicitly, even when this project's Git rules ignore them.
    """
    root = Path(root).resolve()  # Windows temporary roots may use an 8.3 alias.
    repository = _git(root, 'rev-parse', '--show-toplevel') if shutil.which('git') else None
    in_git = repository is not None and Path(os.fsdecode(repository).strip()).resolve() == root
    if in_git:
        data = _git(root, 'ls-files', '--cached', '--others', '--exclude-standard',
                    '-z', '--', '.', required=True)
        candidates = {Path(os.fsdecode(name)) for name in data.split(b'\0') if name}
    else:
        candidates = set()
        for directory, folders, files in os.walk(root, followlinks=False):
            relative = Path(directory).relative_to(root)
            folders[:] = [name for name in folders if not _excluded(relative/name)]
            candidates.update(relative/name for name in files)
    for pattern in ('AGENTS.md', 'CONTEXT*.md', 'docs/CONTEXT*.md', 'docs/agent-memory/*.md'):
        candidates.update(path.relative_to(root) for path in root.glob(pattern) if path.is_file())
    files = []
    for relative in sorted(candidates):
        if _excluded(relative):
            continue
        path = root/relative
        if not path.exists():
            continue  # Deleted tracked files remain recorded in the Git patch.
        if path.is_symlink():
            raise ValueError(f'Symlinks require explicit review before snapshot: {relative}')
        if not path.is_file():
            raise ValueError(f'Nested repository or non-file requires its own snapshot: {relative}')
        if not path.resolve().is_relative_to(root):
            raise ValueError(f'Source path escapes its root: {relative}')
        files.append(relative)
    return files, bool(in_git)


def _git_metadata(root, files):
    """Scope every Git record to this source tree; never inspect a remote."""
    prefix = os.fsdecode(_git(root, 'rev-parse', '--show-prefix', required=True)).strip()
    statuses = []
    raw = _git(root, 'status', '--porcelain=v1', '-z', '--untracked-files=all',
               '--', '.', required=True).split(b'\0')
    index = 0
    while index < len(raw):
        entry = raw[index]
        index += 1
        if not entry:
            continue
        code, path = os.fsdecode(entry[:2]), os.fsdecode(entry[3:])
        original = None
        if 'R' in code or 'C' in code:
            original = os.fsdecode(raw[index])
            index += 1
        if prefix and not path.startswith(prefix):
            continue
        relative = PurePosixPath(path[len(prefix):])
        if _excluded(relative):
            continue
        record = {'status': code, 'path': relative.as_posix()}
        if original and original.startswith(prefix):
            old = PurePosixPath(original[len(prefix):])
            if not _excluded(old):
                record['original_path'] = old.as_posix()
        statuses.append(record)
    head = _git(root, 'rev-parse', '--verify', 'HEAD')
    # Include deleted/renamed source paths in the patch even though their bytes
    # are no longer in the working tree. Passing an explicit list limits scope.
    paths = {path.as_posix() for path in files}
    paths.update(record['path'] for record in statuses)
    paths.update(record['original_path'] for record in statuses if 'original_path' in record)
    arguments = sorted(paths)
    patches = {}
    for name, extra in [('worktree.patch', []), ('index.patch', ['--cached'])]:
        patches[name] = _git(root, 'diff', *extra, '--binary', '--relative',
                            '--no-ext-diff', '--', *arguments, required=True)
    return {'head': head.decode().strip() if head else None,
            'status': statuses}, patches


def verify_snapshot(archive):
    """Verify every archived source against its captured SHA256 inventory."""
    with zipfile.ZipFile(archive) as bundle:
        corrupt = bundle.testzip()
        if corrupt:
            raise ValueError(f'Corrupt ZIP member: {corrupt}')
        manifest = json.loads(bundle.read('snapshot.json'))
        expected = {'sources/'+entry['path'] for entry in manifest['files']}
        actual = {name for name in bundle.namelist() if name.startswith('sources/')}
        if expected != actual:
            raise ValueError('Archive members do not match the source inventory.')
        for entry in manifest['files']:
            relative = PurePosixPath(entry['path'])
            if relative.is_absolute() or '..' in relative.parts or _excluded(relative):
                raise ValueError(f'Unexpected archive path: {relative}')
            data = bundle.read('sources/'+entry['path'])
            if len(data) != entry['size'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
                raise ValueError(f'Source checksum mismatch: {relative}')
    return manifest


def snapshot_sources(root, *, label='checkpoint'):
    """Write and verify a new timestamped ZIP; never overwrite old snapshots."""
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError('The source root must be an existing directory.')
    if not re.fullmatch(r'[A-Za-z0-9_-]+', label):
        raise ValueError('Use letters, numbers, hyphens or underscores in the label.')
    files, in_git = _inventory(root)
    if not files:
        raise ValueError('No source files found.')
    git, patches = _git_metadata(root, files) if in_git else (None, {})
    created = datetime.now(timezone.utc)
    destination = root/'output/source_snapshots'
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination/f'{label}_{created:%Y%m%dT%H%M%S_%fZ}.zip'
    manifest = {'format_version': 1, 'created_utc': created.isoformat(),
                'source_name': root.name, 'git': git, 'files': []}
    # Read each file once: its archived bytes and checksum always agree, even
    # if a colleague subsequently edits the source while the backup finishes.
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as bundle:
        for relative in files:
            data = (root/relative).read_bytes()
            name = relative.as_posix()
            bundle.writestr('sources/'+name, data)
            manifest['files'].append({'path': name, 'size': len(data),
                                      'sha256': hashlib.sha256(data).hexdigest()})
        for name, data in patches.items():
            bundle.writestr('changes/'+name, data)
        bundle.writestr('snapshot.json', json.dumps(manifest, indent=2, ensure_ascii=False)+'\n')
        bundle.writestr('README.txt',
            'Verified source snapshot. Extract sources/ into an empty review directory.\n'
            'snapshot.json lists every captured file, SHA256, and scoped Git status.\n'
            'changes/ preserves tracked worktree/index diffs, including deletions.\n'
            'Untracked source contents are included directly under sources/.\n'
            'This archive contains no Git history, environments or generated outputs.\n'
            'A private repository needs its own separate archive.\n')
    verify_snapshot(archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(f'{digest}  {archive.name}\n', encoding='utf-8')
    return archive, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--label', default='checkpoint')
    parser.add_argument('--verify', type=Path, metavar='ARCHIVE')
    options = parser.parse_args()
    if options.verify:
        manifest = verify_snapshot(options.verify)
        archive = options.verify
    else:
        archive, manifest = snapshot_sources(options.root, label=options.label)
    print(f'Verified {len(manifest["files"])} source files: {archive}')


if __name__ == '__main__':
    main()
