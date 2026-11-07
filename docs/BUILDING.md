# Build the documentation

The site uses Sphinx, MyST for Markdown files, and the Read the Docs theme.
It combines the user guide, illustrated catalogue and technical pages.
The documentation build uses Python **3.12**. Its dependencies are declared
separately in [docs/requirements.txt](requirements.txt).

## Local build

**Run the commands from the repository root**, the directory containing
`pyproject.toml` and `docs/`. Create an environment dedicated to documentation.
It stays separate from `.venv`, which may be used by an active COMSOL session.
You do not need to install GeomPype, KLayout or COMSOL to build the site:
the catalogue images are already included in the sources.

On Windows, in PowerShell:

```powershell
py -3.12 -m venv .venv-docs
.\.venv-docs\Scripts\python.exe -m pip install -r docs\requirements.txt
.\.venv-docs\Scripts\python.exe -m sphinx -b html -W --keep-going docs output\docs\html
Start-Process .\output\docs\html\index.html
```

If `.venv-docs` already exists for this operating system, keep it and start
at the dependency installation step. After editing the documentation, only
the `python -m sphinx ...` command is needed to rebuild it.

If your terminal is currently in `.venv-docs\Scripts`, return to the repository
root with `Set-Location ..\..` before running these commands.

On Linux or macOS, with Python 3.12 available:

```sh
python3.12 -m venv .venv-docs
.venv-docs/bin/python -m pip install -r docs/requirements.txt
.venv-docs/bin/python -m sphinx -b html -W --keep-going docs output/docs/html
```

The generated site is in **`output/docs/html/`**. Open
`output/docs/html/index.html` in your browser. The `docs/` directory contains
the source files. The `-W` option makes warnings fail the build;
`--keep-going` reports all problems in one build.
Use separate virtual environments for Windows and WSL/Linux.

To serve the pages locally, run the following from the repository root using
the documentation environment's interpreter:

```text
python -m http.server 8000 --bind 127.0.0.1 --directory output/docs/html
```

The site is available at <http://127.0.0.1:8000> while the command is running.
Rebuild the HTML after changing the source files.

## Which sources to edit

The [navigation page](index.md), [catalogue](LIBRARY.md), installation guide
and configuration guide are in `docs/`. The main guide, technical references,
contribution guidelines and changelog are included from the root files
`README.md`, `REFERENCES.md`, `CONTRIBUTING.md` and `CHANGELOG.md`.
Edit those original files: the short `guide.md`, `references.md`,
`contributing.md` and `changelog.md` pages only include them in the site.
Likewise, `library-data.md` includes `geompype/library/data/README.md`.

Relative links in documents included from the root start with `./`; MyST
adjusts them during inclusion. Links to other pages use their paths under
`docs/`. Links to Python or JSON files provide downloads of the corresponding
public files in the built site. The
[MyST include guide](https://myst-parser.readthedocs.io/en/latest/syntax/organising_content.html)
describes these options.

After changing the geometry shown in a thumbnail, regenerate it with the
application environment, then rebuild the site:

```powershell
.\.venv\Scripts\python.exe tools\render_library_catalogue.py
.\.venv-docs\Scripts\python.exe -m sphinx -b html -W --keep-going docs output\docs\html
```

HTML output stays in `output/`, which Git ignores. Local working notes,
agent memory and private PDF manuals are excluded from the site's sources.

## Read the Docs

[.readthedocs.yaml](../.readthedocs.yaml) configures Ubuntu 24.04, Python 3.12,
the documentation dependencies and `docs/conf.py`. The HTML build uses the
same sources and also treats warnings as errors. The
[official Sphinx guide for Read the Docs](https://docs.readthedocs.com/platform/stable/intro/sphinx.html)
describes this configuration.

To publish the site, the repository must be available on a Git hosting service
and connected to a Read the Docs project. The configuration file prepares the
build; it does not create a remote repository or hosted project. When importing
the project, keep `.readthedocs.yaml` as the configuration file. See
[adding a project](https://docs.readthedocs.com/platform/stable/intro/add-project.html).
