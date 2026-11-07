"""Build and verify the public wheel and sdist without contacting COMSOL.

Run ``python tools/check_distribution.py`` in the development environment.
The ``build`` package and build requirements must already be installed. Builds
use disposable source copies, no isolation downloads and no package index.
Local privacy probes check that Git exclusions are also enforced by packaging.
The extracted wheel is exercised outside the checkout in an isolated Python
process. A second wheel is built from the sdist to check its completeness.

Artifacts, checksums and the complete log go to ``output/distribution-check``.
This tool neither installs nor publishes a package and never starts a JVM.
"""

import argparse
from contextlib import redirect_stderr, redirect_stdout
from email.parser import BytesParser
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
import zipfile


_ROOT_FILES = {
    'README.md', 'REFERENCES.md', 'CHANGELOG.md', 'CONTRIBUTING.md',
    'LICENSE', 'COPYRIGHT', 'pyproject.toml', 'setup.py', 'setup.cfg',
    'requirements.txt', 'requirements-dev.txt', 'MANIFEST.in',
    '.gitignore', '.editorconfig', '.readthedocs.yaml', 'comsol.example.json', 'PKG-INFO',
}
_SKIP_DIRECTORIES = {
    '.git', '.agents', '.codex', '.aws', '__pycache__', '.pytest_cache',
    '.mypy_cache', '.ruff_cache', 'output', 'build', 'dist', 'venv',
    'private-designs', 'references', '_build',
}


def _copy_exclusions(directory, names):
    """Copy source and handoff files, but never read personal design trees."""
    return [name for name in names if name in _SKIP_DIRECTORIES
            or name.startswith('.venv') or name.endswith(('.egg-info', '.pyc', '.pyo'))
            or '.local.' in name or name == '.env' or name.startswith('.env.')]


def _public_name(name, *, wheel=False):
    """Keep package contents narrow and reject working context at any depth."""
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts:
        return False
    lower = name.lower()
    if any(part in _SKIP_DIRECTORIES or part == 'agent-memory' for part in path.parts):
        return False
    if path.name == 'AGENTS.md' or path.name.upper().startswith('CONTEXT') \
            or '.local.' in lower or path.name.startswith('.env') \
            or 'do_not_publish' in lower or path.name.startswith('test_private'):
        return False
    parts = path.parts
    if parts[0].endswith('.dist-info') and wheel:
        return parts[0].startswith('geompype-') and (
            path.name in {'METADATA', 'WHEEL', 'RECORD', 'top_level.txt'}
            or parts[1:] in (('licenses', 'LICENSE'), ('licenses', 'COPYRIGHT')))
    if parts[0] == 'geompype':
        return (len(parts) == 2 and path.suffix == '.py') \
            or (len(parts) == 3 and parts[1] == 'library' and path.suffix == '.py') \
            or parts[1:] in (('library', 'data', 'x_diamond_mark.json'),
                             ('library', 'data', 'README.md'))
    if wheel:
        return False
    if len(parts) == 1:
        return name in _ROOT_FILES
    if parts[0] == 'geompype.egg-info':
        return len(parts) == 2 and path.name in {
            'PKG-INFO', 'SOURCES.txt', 'dependency_links.txt', 'requires.txt', 'top_level.txt'}
    if parts[0] in {'tools', 'tests'}:
        return path.suffix == '.py'
    if parts[0] == 'docs':
        return (len(parts) == 2 and (path.suffix == '.md'
            or path.name in {'conf.py', 'requirements.txt'})) \
            or parts[1:] == ('_static', 'catalogue.css') or (len(parts) == 4
            and parts[:3] == ('docs', 'images', 'library') and path.suffix == '.svg')
    if parts[0] == 'examples':
        return path.suffix in {'.yaml', '.yml'} or (len(parts) == 2
            and path.name.startswith('example_') and path.suffix == '.py')
    return parts[:2] == ('.github', 'workflows') and path.suffix in {'.yaml', '.yml'}


def _metadata(data):
    """Check identity, licence and the grid-sensitive KLayout requirement."""
    metadata = BytesParser().parsebytes(data)
    assert metadata['Name'].lower() == 'geompype', metadata['Name']
    assert metadata['Version'], 'Missing version'
    assert metadata['License-Expression'] == 'AGPL-3.0-or-later'
    assert set(metadata.get_all('License-File')) == {'LICENSE', 'COPYRIGHT'}
    assert metadata['Requires-Python'] == '>=3.10'
    assert 'klayout==0.30.1' in metadata.get_all('Requires-Dist')


def _package_files(root):
    return [*root.joinpath('geompype').glob('*.py'),
            *root.joinpath('geompype/library').glob('*.py'),
            root/'geompype/library/data/x_diamond_mark.json',
            root/'geompype/library/data/README.md']


def _check_wheel(artifact, root, unpacked):
    with zipfile.ZipFile(artifact) as archive:
        names = archive.namelist()
        assert all(_public_name(name, wheel=True) for name in names), names
        metadata, = [name for name in names if name.endswith('.dist-info/METADATA')]
        _metadata(archive.read(metadata))
        for source in _package_files(root):
            relative = source.relative_to(root).as_posix()
            assert archive.read(relative) == source.read_bytes(), relative
        for filename in ('LICENSE', 'COPYRIGHT'):
            member, = [name for name in names if name.endswith('.dist-info/licenses/'+filename)]
            assert archive.read(member) == (root/filename).read_bytes(), filename
        archive.extractall(unpacked)  # Every member was checked against the public allowlist.


def _check_sdist(artifact, root, extracted):
    with tarfile.open(artifact) as archive:
        members = archive.getmembers()
        prefix = members[0].name.split('/')[0]+'/'
        assert prefix.startswith('geompype-'), prefix
        data = {}
        for member in members:
            if member.isdir():
                continue
            assert member.isfile() and member.name.startswith(prefix), member.name
            relative = member.name[len(prefix):]
            assert _public_name(relative), member.name
            data[relative] = archive.extractfile(member).read()
            path = extracted/relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data[relative])
        _metadata(data['PKG-INFO'])
        expected = [*_package_files(root), root/'LICENSE', root/'COPYRIGHT',
                    root/'pyproject.toml', root/'setup.py', root/'requirements.txt',
                    root/'MANIFEST.in', root/'comsol.example.json',
                    *(root/name for name in _ROOT_FILES if (root/name).is_file()),
                    *root.joinpath('examples').glob('example_*.py'),
                    *root.joinpath('examples').glob('*.yaml'),
                    *root.joinpath('examples').glob('*.yml'),
                    *root.joinpath('tools').glob('*.py'), *root.joinpath('tests').glob('*.py'),
                    *root.joinpath('docs').glob('*.md'),
                    root/'docs/conf.py', root/'docs/requirements.txt',
                    root/'docs/_static/catalogue.css',
                    *root.joinpath('docs/images/library').glob('*.svg')]
        for source in expected:
            relative = source.relative_to(root).as_posix()
            if _public_name(relative):
                assert data[relative] == source.read_bytes(), relative


_SMOKE = r'''
from pathlib import Path
import sys
unpacked = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(unpacked))
import geompype
import geompype.library as library
assert Path(geompype.__file__).is_relative_to(unpacked), geompype.__file__
assert Path(library.__file__).is_relative_to(unpacked), library.__file__
preview_script = unpacked/'geompype/_klayout_preview.py'
assert preview_script.is_file()
assert not (unpacked/'klayout_preview.py').exists()
helpers = ('x_diamond_mark', 'cross_mark', 'l_mark', 'box_mark', 'vernier_mark',
           'two_inch_wafer', 'three_inch_wafer', 'four_inch_wafer')
for name in helpers:
    assert getattr(geompype, name) is getattr(library, name)
    assert getattr(library, name).__module__ == 'geompype.library.' + name
from geompype import Array, Circle, Project
import klayout.db as kdb
p = Project(output='wheel_check')
sites = p.add_layer('sites', comsol=False)
Array(Circle(p, layer=sites, radius=2), size=(3,2), displacement=(10,10), exclude=[(1,0)])
marks = p.add_layer('alignment', comsol=False, gds_layer=2)
for index, name in enumerate(('x_diamond_mark', 'cross_mark', 'l_mark', 'box_mark')):
    getattr(library, name)(p, layer=marks).move(delta=(index*300, 0))
reference = p.add_layer('reference', comsol=False, gds_layer=3)
moving = p.add_layer('moving', comsol=False, gds_layer=4)
library.vernier_mark(p, reference_layer=reference, moving_layer=moving)
for number, name in ((20,'two_inch_wafer'), (30,'three_inch_wafer'), (40,'four_inch_wafer')):
    layer = p.add_layer(name, comsol=False, gds_layer=number)
    getattr(library, name)(p, layer=layer, flats=2)
p.build()
# Check the installed viewer macro path without launching a desktop or JVM.
from unittest.mock import patch
with patch.object(Project, '_executable', return_value='klayout'), \
        patch('geompype.project.subprocess.Popen') as launch:
    p.show()
    arguments = launch.call_args.args[0]
    assert arguments[:2] == ['klayout', '-rr']
    assert Path(arguments[2]).resolve() == preview_script.resolve()
layout = kdb.Layout()
layout.read(str(p.gds_path))
def region(number):
    return kdb.Region(layout.top_cell().begin_shapes_rec(layout.layer(number,0))).merged()
assert region(1).count() == 5
assert region(2).count() == 8
assert sum(polygon.holes() for polygon in region(2).each()) == 1
assert region(3).count() == 11 and region(4).count() == 11
for number, diameter in ((20,50800), (30,76200), (40,100000)):
    shape = region(number)
    assert shape.count() == 1
    assert shape.bbox().right == round(diameter/2/layout.dbu)
    assert shape.bbox().bottom == -round(diameter/2/layout.dbu)
assert p.model is None and 'mph' not in sys.modules
assert not any('private-designs' in str(getattr(module, '__file__', '')) for module in sys.modules.values())
print('Wheel-only GDS smoke passed:', geompype.__file__)
'''


def check_distribution(root, destination):
    """Keep source immutable and save verified artifacts only after all checks."""
    if not __debug__:
        raise RuntimeError('Run without -O: distribution validation uses assertions.')
    destination.mkdir(parents=True, exist_ok=True)
    log_path = destination/'check.log'
    environment = dict(os.environ, PIP_NO_INDEX='1', PIP_DISABLE_PIP_VERSION_CHECK='1')
    environment.pop('PYTHONPATH', None)
    with log_path.open('w', encoding='utf-8', buffering=1) as log, \
            redirect_stdout(log), redirect_stderr(log), \
            TemporaryDirectory(prefix='geompype_distribution_') as directory:
        temporary = Path(directory)
        source = temporary/'source'
        shutil.copytree(root, source, ignore=_copy_exclusions)
        probes = ('private-designs/personal/do_not_publish.py',
                  'geompype/circuits/do_not_publish.py', 'tests/test_private_do_not_publish.py',
                  'AGENTS.md', 'CONTEXT_DO_NOT_PUBLISH.md', 'docs/CONTEXT_DO_NOT_PUBLISH.md',
                  'docs/agent-memory/do_not_publish.md', 'comsol.local.json', '.env',
                  'docs/_build/do_not_publish.html', '.venv-docs/do_not_publish.py',
                  'design.gds', 'design.mph', 'output/do_not_publish.py')
        for relative in probes:
            path = source/relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('DO_NOT_PUBLISH\n', encoding='utf-8')
        artifacts = temporary/'artifacts'
        print('Build wheel and sdist; reject private data, handoffs, local settings and generated outputs.')
        subprocess.run([sys.executable, '-m', 'build', '--no-isolation', '--sdist', '--wheel',
                        '--outdir', str(artifacts)], cwd=source, env=environment,
                       stdout=log, stderr=subprocess.STDOUT, check=True)
        wheel, = artifacts.glob('*.whl')
        sdist, = artifacts.glob('*.tar.gz')
        unpacked = temporary/'wheel'
        _check_wheel(wheel, root, unpacked)
        extracted = temporary/'sdist'
        _check_sdist(sdist, root, extracted)
        print('Exact public source bytes, packaged assets, licence, dependency pin and privacy checks passed.')
        rebuilt = temporary/'rebuilt'
        subprocess.run([sys.executable, '-m', 'build', '--no-isolation', '--wheel',
                        '--outdir', str(rebuilt)], cwd=extracted, env=environment,
                       stdout=log, stderr=subprocess.STDOUT, check=True)
        rebuilt_wheel, = rebuilt.glob('*.whl')
        _check_wheel(rebuilt_wheel, root, temporary/'rebuilt-wheel')
        work = temporary/'outside-checkout'
        work.mkdir()
        subprocess.run([sys.executable, '-I', '-c', _SMOKE, str(unpacked)], cwd=work,
                       env=environment, stdout=log, stderr=subprocess.STDOUT, check=True)
        subprocess.run([sys.executable, '-I', '-c', _SMOKE, str(temporary/'rebuilt-wheel')],
                       cwd=work, env=environment, stdout=log, stderr=subprocess.STDOUT, check=True)
        # This test must also work after local AGENTS/context notes are omitted.
        subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests',
                        '-p', 'test_source_snapshots.py', '-v'], cwd=extracted,
                       env=environment, stdout=log, stderr=subprocess.STDOUT, check=True)
        hashes = {}
        for artifact in (wheel, sdist):
            shutil.copy2(artifact, destination/artifact.name)
            hashes[artifact.name] = hashlib.sha256(artifact.read_bytes()).hexdigest()
        (destination/'SHA256.json').write_text(json.dumps(hashes, indent=2)+'\n', encoding='utf-8')
        print('PASS: wheel, sdist, rebuilt wheel and independent GDS smoke; no COMSOL connection.')
    return log_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Destination for artifacts and check.log.')
    options = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    destination = (options.output or root/'output/distribution-check').resolve()
    try:
        log = check_distribution(root, destination)
    except Exception:
        print(f'Distribution check failed; details: {destination / "check.log"}', file=sys.stderr)
        raise
    print(f'Distribution checks passed: {log}')


if __name__ == '__main__':
    main()
