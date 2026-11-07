# Installing and checking GeomPype

Use Python 3.10 or newer. The package contains the geometry API, library data,
examples and tests. COMSOL is only required when building a layer with
`comsol=True`; GDS-only projects use the installed `klayout.db` package.
Native validation has been performed with Python 3.12 on Windows and COMSOL 6.4.

To build the documentation website, follow the separate
[documentation build guide](BUILDING.md).

## Create an environment

From the repository root, create a project environment:

```text
python -m venv .venv
```

On Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pip check
```

On Linux/macOS:

```sh
.venv/bin/python -m pip install -e .
.venv/bin/python -m pip check
```

Use this interpreter in your editor. Public scripts and their YAML files live in
`examples/`; keep the repository root as the working directory when running them.
For example, `python -i examples/example_square.py` uses the configured COMSOL
server and leaves its Python session open after the script.
The commands below use `python` to mean that interpreter, either after activating
its environment or by substituting its full path. For normal use without editable
sources, replace `pip install -e .` with `pip install .`.

Environments contain absolute paths and platform-specific binaries. Recreate
an environment when changing the checkout location or operating system; do not
copy its `.venv` directory. An environment used by an active COMSOL session
must remain available until that session is no longer needed.

Runtime dependencies are declared in [requirements.txt](../requirements.txt)
and package/build metadata in [pyproject.toml](../pyproject.toml).
KLayout is pinned to **0.30.1** for reproducible integer-grid Boolean results.
Updating this pin requires comparison of fabrication contours and grid behavior.
`pip check` verifies installed dependency compatibility; it does not validate
COMSOL licences or geometry.

## COMSOL and viewers

Configure the server through the [COMSOL configuration guide](COMSOL_CONFIGURATION.md).
A compatible COMSOL installation, licence and available server are needed for
native geometry. GeomPype uses installed MPh for the COMSOL/JVM connection;
it does not start, stop or reconfigure the server automatically.

`project.build()` writes files without opening windows. `project.show()` uses
the installed KLayout and COMSOL desktop applications. Most example scripts
end with `project.show()`; comment out that call when only the files are needed.
For GDS-only use, also set `comsol=False` on the example's layers.

## Run checks

Install development tools in the same environment:

```text
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
```

By default, native COMSOL tests are skipped. The remaining checks cover geometry,
parameters, exported GDS, examples and recorded native API calls without a server.

With the configured COMSOL server available, run native checks interactively:

```text
python -i tests/run_comsol_tests.py
```

The runner activates the native tests and keeps the interpreter open afterward.
It checks the connection once before running the suite. Tests remove only their
own temporary models and do not disconnect the shared client.

Keep the interpreter open while its connection is needed. A COMSOL server
started with the default `-multi auto` may exit when its Python client ends.
For a server whose lifetime is independent of clients, COMSOL documents the
`-multi on` launch option; GeomPype does not change that setting.
See the [COMSOL server documentation](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/comsol_ref_running.38.20.html).
A passive operating-system port check can establish whether the server is
listening without opening a temporary client connection.

## Build distributions

```text
python -m build
```

This produces a wheel and source distribution in `dist/`. The supported
installation interface is `pip`; [setup.py](../setup.py) is a small compatibility
entry point that reads the same `pyproject.toml` metadata. No duplicate list of
versions or dependencies is maintained there.

The distributions include the public package and its geometry data. Personal
designs, local server configuration, working context, virtual environments and
generated GDS/MPH files are excluded. The source distribution additionally
contains public documentation, examples and tests. See
[CONTRIBUTING.md](contributing.md) for contribution and release checks.

## Separate design packages

A design package can depend on GeomPype and be installed into the same environment:

```text
python -m pip install -e path/to/design-package
```

Keep its recipes, numerical parameter files, examples and tests in that package.
The public package must not import it. The root `private-designs/` directory is
ignored by Git and excluded from public distributions; it can contain separately
managed local repositories. Ignored files are local files, not a backup.
