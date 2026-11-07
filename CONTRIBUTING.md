# Contributing to GeomPype

GeomPype defines planar geometry for COMSOL and GDS masks. Contributions should
keep geometric behavior explicit, preserve parameter expressions, and explain
any differences between the native geometry and fabrication representation.
The [README](./docs/guide.md) describes the API; [feature coverage](./docs/FEATURE_COVERAGE.md)
connects it to examples and current limits. Setup and test commands are in the
[environment guide](./docs/ENVIRONMENT.md).

The [documentation build guide](./docs/BUILDING.md) covers local HTML previews
and the Read the Docs configuration.

To contribute a reusable mark or wafer outline, start with the illustrated
[geometry catalogue](./docs/LIBRARY.md) and its
[step-by-step contribution recipe](./docs/LIBRARY.md#add-a-geometry).

## Code and documentation

Write public documentation, examples and user-facing text in English.

Public modules live in `geompype/`; each library element has its own file in
`geompype/library/`. Use ordinary classes, explicit functions and named arguments.
Public docstrings should state units, coordinate conventions, returned objects,
parameter behavior and relevant limitations. Keep internal comments focused on
why a calculation or native API sequence is needed.

Numeric lengths are micrometres and angles are degrees. Layer settings choose
COMSOL and GDS independently. Named workplanes write separate GDS files in local
coordinates. Do not silently snap COMSOL geometry to the GDS grid or substitute
a different curve algorithm without validating agreement.

Keep public examples and their YAML parameter files in `examples/`. Examples
are flat scripts with `# %%` cells: imports, parameters, project/layers,
geometry, build and optional display. Keep parameter values easy to find. Tests
and maintenance tools may have command-line runners. Update examples and public
documentation when an API or its constraints change.

Use the native API documentation linked in [REFERENCES.md](./docs/references.md).
The geometry API and desktop/application API have different responsibilities;
verify properties against the supported backend version.

## Validate a change

Run the offline suite from the project environment:

```text
python -m unittest discover -s tests -v
```

Add focused tests when geometry behavior changes: use independent dimensions,
areas or boundaries, verify parameter rebuilds, and inspect the exported file.
Tests that only repeat the implementation do not establish geometric correctness.
Native changes also need the affected COMSOL checks using the interactive runner
in the environment guide. Keep the server and existing models available.
State which checks ran and which require a native installation.

Build both public distributions before a release:

```text
python -m build
```

Inspect their contents for public library data and the absence of local settings,
private designs, working notes and generated files. Check an import and a small
GDS build from an installed wheel outside the source checkout. Dependency changes,
particularly the KLayout version, also require fabrication-grid regression checks.

## Public and local files

Generic geometry, public examples and documentation belong in this repository.
Personal circuit recipes and their parameter files belong in separately managed
design packages. The public package and its tests must work without those packages.

The ignore rules cover `private-designs/`, local server settings, working context,
virtual environments and generated files. `.gitignore` does not remove files
already tracked by Git: inspect staged paths and the diff before committing.
Commit the server configuration template, never a workstation's actual settings.
Licence and attribution are provided in [LICENSE](./LICENSE) and [COPYRIGHT](./COPYRIGHT).
