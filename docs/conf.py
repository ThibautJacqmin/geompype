"""Sphinx configuration for the public GeomPype documentation."""

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]
metadata = tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']
project = metadata['name'].replace('geompype', 'GeomPype')
author = ', '.join(person['name'] for person in metadata['authors'])
release = metadata['version']

extensions = ['myst_parser', 'sphinx_rtd_theme']
source_suffix = {'.md': 'markdown'}
root_doc = 'index'
language = 'en'
myst_heading_anchors = 3

# Only public guides are documentation sources, even in a local checkout.
include_patterns = ['*.md']
exclude_patterns = ['agent-memory/**', 'AGENTS.md', '*CONTEXT*.md', '*context*.md', '_build/**']

html_theme = 'sphinx_rtd_theme'
html_title = f'GeomPype {release}'
html_theme_options = {'navigation_depth': 3}
html_static_path = ['_static']
html_css_files = ['catalogue.css']
